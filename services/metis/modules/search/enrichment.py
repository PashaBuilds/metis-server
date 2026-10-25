"""Model zenginleştirmesi (İş 4): model açıkken yayımlanmış bloklara bağlam cümlesi ve "bu blok hangi soruları cevaplar".

Tasarım bölüm 7. Yalnız yayımlanmış bloklar (search_passages) modele gider; taslak gitmez. Çıktı deterministik süzgeçten
geçer (blokta olmayan tanımlayıcı uydurulamaz) ve `passage_enrichments`'a yazılır; sayfa yeniden indekslenir (tsv D
ağırlığı + gömme metni). Zenginleştirme kanıt değildir: bilgi metnine, alıntıya, Mentor paketine girmez. Model yoksa ya
da proje kapattıysa iş yapılmaz; arama zenginleştirmesiz sürer.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from metis.core.db import transaction
from metis.core.models import PassageEnrichment, Project, Provider
from metis.llm import contracts, prompts
from metis.modules.search.index import extract_symbols, index_pages

log = logging.getLogger("metis.enrichment")

BLOCKS_PER_CALL = 12
MIN_BLOCK = 40  # bu kadar kısa blok zenginleştirilmez (ör. tek satırlık başlık)
MAX_CONTEXT = 300
MAX_QUESTION = 200


def accept(block: str, title: str, context: str, questions: list[str]) -> tuple[str, list[str]]:
    """Süzgeç: bağlam ve sorulardaki her tanımlayıcı (sembol/hex) blokta ya da sayfa başlığında birebir geçmeli; boş ve
    aşırı uzun olanlar atılır. Dönen: (bağlam ya da "", kabul edilen sorular)."""
    known = set(extract_symbols(block, title))

    def ok(s: str, limit: int) -> bool:
        s = s.strip()
        return bool(s) and len(s) <= limit and all(sym in known for sym in extract_symbols(s))

    ctx = context.strip() if ok(context, MAX_CONTEXT) else ""
    qs = [q.strip() for q in questions if ok(q, MAX_QUESTION)][:3]
    return ctx, qs


def _next_page() -> dict | None:
    """Zenginleştirmesi eksik bloğu olan, zenginleştirmesi açık ve uygun modeli olan ilk projenin ilk sayfası."""
    from metis.modules.lab.service import route

    with transaction() as db:
        rows = db.execute(
            text(
                """
                SELECT sp.project_id, sp.page_id
                FROM search_passages sp
                JOIN projects pr ON pr.id = sp.project_id
                WHERE pr.enrichment_enabled AND pr.deleted_at IS NULL
                  AND NOT sp.is_heading AND length(sp.body) >= :min
                  AND NOT EXISTS (SELECT 1 FROM passage_enrichments pe WHERE pe.base_sha256 = sp.base_sha256 AND pe.prompt_version = :pv)
                GROUP BY sp.project_id, sp.page_id
                ORDER BY sp.project_id, min(sp.id)
                LIMIT 50
                """
            ),
            {"min": MIN_BLOCK, "pv": prompts.ENRICH},
        ).all()
        seen: set[uuid.UUID] = set()
        for project_id, page_id in rows:
            if project_id in seen:
                continue
            seen.add(project_id)
            project = db.get(Project, project_id)
            model, _ = route(db, project) if project else (None, [])
            if model is None:
                continue
            blocks = db.execute(
                text(
                    """
                    SELECT sp.base_sha256, sp.heading_path, sp.body, d.title
                    FROM search_passages sp JOIN search_documents d ON d.page_id = sp.page_id
                    WHERE sp.page_id = :page AND NOT sp.is_heading AND length(sp.body) >= :min
                      AND NOT EXISTS (SELECT 1 FROM passage_enrichments pe WHERE pe.base_sha256 = sp.base_sha256 AND pe.prompt_version = :pv)
                    ORDER BY sp.ord LIMIT :n
                    """
                ),
                {"page": page_id, "min": MIN_BLOCK, "pv": prompts.ENRICH, "n": BLOCKS_PER_CALL},
            ).all()
            if not blocks:
                continue
            provider = db.get(Provider, model.provider_id)
            db.expunge(model)
            if provider:
                db.expunge(provider)
            return {"project_id": project_id, "page_id": page_id, "model": model, "provider": provider, "blocks": blocks}
    return None


def enrich_next() -> int:
    """Bir sayfanın en çok 12 bloğunu zenginleştirir. Dönen: işlenen blok sayısı; iş yoksa 0; model çağrısı başarısızsa -1."""
    from metis.llm.client import ModelClient

    job = _next_page()
    if job is None or job["provider"] is None:
        return 0
    blocks = job["blocks"]
    title = blocks[0].title
    payload = {"page_title": title, "blocks": [{"id": str(i), "heading_path": b.heading_path, "text": b.body} for i, b in enumerate(blocks)]}
    res = ModelClient().call(
        job["model"], job["provider"], prompt_id=prompts.ENRICH, payload=payload, schema=contracts.PassageEnrichmentOut, purpose="enrichment", max_tokens=2500
    )
    if not res.ok:
        log.warning("enrichment call failed", extra={"event": res.error})
        return -1
    by_id = {it["id"]: it for it in res.output.get("items", [])}
    with transaction() as db:
        for i, b in enumerate(blocks):
            it = by_id.get(str(i), {})
            ctx, qs = accept(b.body, title, str(it.get("context", "")), [str(q) for q in it.get("questions", [])])
            db.execute(
                insert(PassageEnrichment)
                .values(
                    base_sha256=b.base_sha256,
                    prompt_version=prompts.ENRICH,
                    model_id=job["model"].id,
                    context=ctx,
                    questions=qs,
                    status="ok" if (ctx or qs) else "rejected",
                )
                .on_conflict_do_nothing()
            )
        db.flush()
        project = db.get(Project, job["project_id"])
        if project and project.active_publication_id:
            index_pages(db, project.id, project.active_publication_id, {job["page_id"]})
    return len(blocks)


def enrichment_status() -> dict:
    with transaction() as db:
        row = db.execute(
            text(
                """
                SELECT count(*) AS eligible,
                       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM passage_enrichments pe
                                                      WHERE pe.base_sha256 = sp.base_sha256 AND pe.prompt_version = :pv)) AS done
                FROM search_passages sp JOIN projects pr ON pr.id = sp.project_id
                WHERE pr.enrichment_enabled AND NOT sp.is_heading AND length(sp.body) >= :min
                """
            ),
            {"pv": prompts.ENRICH, "min": MIN_BLOCK},
        ).one()
    return {"blocks_eligible": int(row.eligible or 0), "blocks_enriched": int(row.done or 0), "prompt_version": prompts.ENRICH}

