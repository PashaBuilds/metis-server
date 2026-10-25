"""Model zenginleştirmesi (İş 4): model açıkken yayımlanmış bloklara bağlam cümlesi ve "bu blok hangi soruları cevaplar".

Tasarım bölüm 7. Yalnız yayımlanmış bloklar (search_passages) modele gider; taslak gitmez. Çıktı deterministik süzgeçten
geçer (blokta olmayan tanımlayıcı uydurulamaz) ve proje başına `passage_enrichments`'a yazılır; bloklar yerinde güncellenir
(tsv D ağırlığı + gömme anahtarı), yalnız vektör sayacı artar. Zenginleştirme kanıt değildir: bilgi metnine, alıntıya,
Mentor paketine girmez. Düşük öncelik: sağlayıcıda boş yer yoksa beklenir; hataları devre kesiciyi açmaz. Model yoksa ya da
proje kapattıysa iş yapılmaz; arama zenginleştirmesiz sürer.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from metis.core.db import transaction, utcnow
from metis.core.models import PassageEnrichment, Project, Provider, ProviderSlot, SearchDocument, SearchPassage
from metis.llm import contracts, prompts
from metis.modules.search.index import _weighted, extract_symbols
from metis.modules.search.text import fold
from metis.modules.search.vectors import bump, embed_hash

log = logging.getLogger("metis.enrichment")

BLOCKS_PER_CALL = 8
MIN_BLOCK = 40  # bu kadar kısa blok zenginleştirilmez (ör. tek satırlık başlık)
MAX_CONTEXT = 300
MAX_QUESTION = 200
# Bu hatalar "model şu an yok" demektir: aynı sayfa sonra yeniden denenir. Diğerleri (geçersiz çıktı) o bloklar için kalıcı.
TRANSIENT = ("TIMEOUT", "CONNECTION_FAILED", "TLS_FAILED", "PROVIDER_BUSY", "BUDGET_EXCEEDED", "MODEL_UNAVAILABLE", "ENDPOINT_NOT_ALLOWED")

_PENDING = """
    pr.enrichment_enabled AND pr.deleted_at IS NULL
    AND NOT sp.is_heading AND length(sp.body) >= :min AND sp.base_sha256 IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM passage_enrichments pe
                    WHERE pe.project_id = sp.project_id AND pe.base_sha256 = sp.base_sha256 AND pe.prompt_version = :pv)
"""


def accept(block: str, title: str, heading_path: str, context: str, questions: list[str]) -> tuple[str, list[str]]:
    """Süzgeç: bağlam ve sorulardaki her tanımlayıcı (sembol/hex) blokta, başlık yolunda ya da sayfa başlığında birebir
    geçmeli; boş ve aşırı uzun olanlar atılır, en çok 3 soru. Dönen: (bağlam ya da "", kabul edilen sorular)."""
    known = set(extract_symbols(block, title, heading_path))

    def ok(s: str, limit: int) -> bool:
        s = s.strip()
        return bool(s) and len(s) <= limit and all(sym in known for sym in extract_symbols(s))

    ctx = context.strip() if ok(context, MAX_CONTEXT) else ""
    qs = [q.strip() for q in questions if ok(q, MAX_QUESTION)][:3]
    return ctx, qs


def _provider_has_room(db, provider: Provider) -> bool:  # noqa: ANN001
    """Etkileşimli çağrılara (Mentor) yer bırak: en az bir boş yer kalmıyorsa zenginleştirme bekler."""
    used = db.scalar(select(func.count()).select_from(ProviderSlot).where(ProviderSlot.provider_id == provider.id, ProviderSlot.expires_at >= utcnow())) or 0
    return used < max(1, provider.max_concurrency - 1) if provider.max_concurrency > 1 else used == 0


def _next_page() -> dict | None:
    """Sırayla projeler: zenginleştirmesi açık, uygun modeli olan ve sağlayıcısında yer olan ilk projenin ilk sayfası."""
    from metis.modules.lab.service import route

    with transaction() as db:
        project_ids = list(
            db.scalars(
                text(f"SELECT DISTINCT sp.project_id FROM search_passages sp JOIN projects pr ON pr.id = sp.project_id WHERE {_PENDING}"),
                {"min": MIN_BLOCK, "pv": prompts.ENRICH},
            )
        )
        for project_id in project_ids:
            project = db.get(Project, project_id)
            model, _ = route(db, project) if project else (None, [])
            if model is None:
                continue
            provider = db.get(Provider, model.provider_id)
            if provider is None or not _provider_has_room(db, provider):
                continue
            page_id = db.scalar(
                text(
                    f"""SELECT sp.page_id FROM search_passages sp JOIN projects pr ON pr.id = sp.project_id
                        WHERE sp.project_id = :p AND {_PENDING} ORDER BY sp.id LIMIT 1"""
                ),
                {"p": project_id, "min": MIN_BLOCK, "pv": prompts.ENRICH},
            )
            if page_id is None:
                continue
            blocks = db.execute(
                text(
                    f"""SELECT sp.base_sha256, sp.heading_path, sp.body, d.title
                        FROM search_passages sp JOIN search_documents d ON d.page_id = sp.page_id
                        JOIN projects pr ON pr.id = sp.project_id
                        WHERE sp.page_id = :page AND {_PENDING} ORDER BY sp.ord LIMIT :n"""
                ),
                {"page": page_id, "min": MIN_BLOCK, "pv": prompts.ENRICH, "n": BLOCKS_PER_CALL},
            ).all()
            if not blocks:
                continue
            db.expunge(model)
            db.expunge(provider)
            return {"project_id": project_id, "page_id": page_id, "model": model, "provider": provider, "blocks": blocks}
    return None


def apply_enrichment(db, project_id: uuid.UUID, bases: set[str]) -> int:  # noqa: ANN001
    """Zenginleştirilen blokları yerinde günceller (tsv D + gömme anahtarı); yalnız vektör sayacı artar — sayfa yeniden
    kurulmaz, arama önbelleği tümden yenilenmez. Eski vektör, yenisi hesaplanana dek o blok için geçerli kalır."""
    enr = {
        e.base_sha256: e
        for e in db.scalars(
            select(PassageEnrichment).where(
                PassageEnrichment.project_id == project_id,
                PassageEnrichment.base_sha256.in_(bases),
                PassageEnrichment.prompt_version == prompts.ENRICH,
                PassageEnrichment.status == "ok",
            )
        )
    }
    rows = db.execute(
        select(SearchPassage, SearchDocument.title)
        .join(SearchDocument, SearchDocument.page_id == SearchPassage.page_id)
        .where(SearchPassage.project_id == project_id, SearchPassage.base_sha256.in_(list(enr)))
    ).all()
    for p, title in rows:
        e = enr[p.base_sha256]
        extra = " ".join([e.context, *e.questions])
        db.execute(
            update(SearchPassage)
            .where(SearchPassage.id == p.id)
            .values(
                embed_sha256=embed_hash(title, p.heading_path, p.body, e.context, list(e.questions)),
                tsv_simple=_weighted("simple", fold(title), fold(p.heading_path), fold(p.body), fold(extra)),
                tsv_turkish=_weighted("turkish", title, p.heading_path, p.body, extra),
            )
        )
    if rows:
        bump(db, {project_id}, vectors=True)
    return len(rows)


def enrich_next() -> int:
    """Bir sayfanın en çok 8 bloğunu zenginleştirir. Dönen: işlenen blok sayısı; iş yoksa 0; model geçici olarak yoksa -1.
    Model geçersiz çıktı verirse o bloklar 'failed' işaretlenir (aynı istem sürümüyle tekrar gönderilmez; diğer sayfalar
    ilerler)."""
    from metis.llm.client import ModelClient

    job = _next_page()
    if job is None:
        return 0
    blocks = job["blocks"]
    title = blocks[0].title
    payload = {"page_title": title, "blocks": [{"id": str(i), "heading_path": b.heading_path, "text": b.body} for i, b in enumerate(blocks)]}
    res = ModelClient().call(
        job["model"], job["provider"], prompt_id=prompts.ENRICH, payload=payload, schema=contracts.PassageEnrichmentOut, purpose="enrichment", max_tokens=3000
    )
    if not res.ok and (res.error or "") in TRANSIENT:
        log.warning("enrichment call failed", extra={"event": res.error})
        return -1
    by_id = {it["id"]: it for it in (res.output or {}).get("items", [])} if res.ok else {}
    with transaction() as db:
        project = db.get(Project, job["project_id"], with_for_update=True)  # yayımla ile çakışmasın
        if project is None or project.deleted_at is not None or not project.enrichment_enabled:
            return 0  # çağrı sürerken proje kapatıldı/silindi: hiçbir şey yazılmaz
        for i, b in enumerate(blocks):
            it = by_id.get(str(i), {})
            if res.ok:
                ctx, qs = accept(b.body, title, b.heading_path, str(it.get("context", "")), [str(q) for q in it.get("questions", [])])
                status = "ok" if (ctx or qs) else "rejected"
            else:
                ctx, qs, status = "", [], "failed"
            db.execute(
                insert(PassageEnrichment)
                .values(
                    project_id=project.id,
                    base_sha256=b.base_sha256,
                    prompt_version=prompts.ENRICH,
                    model_id=job["model"].id,
                    context=ctx,
                    questions=qs,
                    status=status,
                )
                .on_conflict_do_nothing()
            )
        db.flush()
        apply_enrichment(db, project.id, {b.base_sha256 for b in blocks})
    if not res.ok:
        log.warning("enrichment output rejected for page", extra={"event": res.error})
    return len(blocks)


def enrichment_status() -> dict:
    with transaction() as db:
        row = db.execute(
            text(
                """
                SELECT count(*) AS eligible,
                       count(pe.base_sha256) FILTER (WHERE pe.status IN ('ok', 'rejected')) AS done,
                       count(pe.base_sha256) FILTER (WHERE pe.status = 'failed') AS failed
                FROM search_passages sp
                JOIN projects pr ON pr.id = sp.project_id
                LEFT JOIN passage_enrichments pe
                  ON pe.project_id = sp.project_id AND pe.base_sha256 = sp.base_sha256 AND pe.prompt_version = :pv
                WHERE pr.enrichment_enabled AND pr.deleted_at IS NULL AND NOT sp.is_heading AND length(sp.body) >= :min
                """
            ),
            {"pv": prompts.ENRICH, "min": MIN_BLOCK},
        ).one()
    return {
        "blocks_eligible": int(row.eligible or 0),
        "blocks_enriched": int(row.done or 0),
        "blocks_failed": int(row.failed or 0),
        "prompt_version": prompts.ENRICH,
    }
