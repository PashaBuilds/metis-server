"""Faz 5 pipeline (sabit adımlar, araçsız): extract → retrieve → compare → judge → relate → taslak.

Çıktı her zaman insan incelemesine giden taslaktır (origin=metis, state=in_review); worker yayın yapamaz.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select

from metis.core.db import transaction
from metis.core.models import (
    Claim,
    ClaimEvidence,
    Evidence,
    ExtractedClaim,
    JobMessage,
    JobOutput,
    Model,
    OpenDecision,
    PageRevision,
    Provider,
    Source,
    SourceRevision,
)
from metis.core.util import fingerprint
from metis.llm import contracts, prompts
from metis.llm.client import SHARED, KeyRef, ModelClient
from metis.modules.changes import schemas as cs
from metis.modules.changes import service as changes
from metis.modules.lab.service import eligibility
from metis.modules.scopes.semantics import DIMENSIONS, normalize_scope, overlaps
from metis.modules.sources.locator import build_locator
from metis.worker.runtime import (
    MAX_SOURCE_CHARS,
    MAX_SOURCES,
    AwaitInput,
    BudgetExceeded,
    JobContext,
    JobFailed,
    worker_identity,
)

KIND_FOR_SOURCE = {"note": "concept", "code": "component", "document": "procedure", "test": "validation", "table": "table", "image": "concept"}


def job_key(job) -> KeyRef:  # noqa: ANN001
    """Kişinin başlattığı görev onun anahtarıyla (2.0.28); zamanlanmış bakım ve eski görevler ortak anahtarla (sistem işi)."""
    source = (job.inputs or {}).get("key_source")
    if source == "personal":
        return KeyRef(user_id=job.requester_id, personal=True)
    if source == "shared":
        return KeyRef(user_id=job.requester_id, personal=False)
    return SHARED


def load_model(db, job, ctx=None) -> tuple[Model, Provider]:  # noqa: ANN001
    from metis.core.models import Project, UserProviderKey

    model = db.get(Model, uuid.UUID(job.inputs["model_id"])) if job.inputs.get("model_id") else None
    project = db.get(Project, job.project_id)
    if model is None:
        raise JobFailed("MODEL_REQUIRED", "Görev için model seçilmemiş.")
    ok, reason = eligibility(db, model, project)
    if not ok:
        raise JobFailed("MODEL_UNAVAILABLE", f"Seçilen model artık kullanılamıyor ({reason}). Başka bir modelle yeniden dene.")
    provider = db.get(Provider, model.provider_id)
    key = job_key(job)
    if key.personal and db.get(UserProviderKey, (key.user_id, model.provider_id)) is None:
        raise JobFailed("PERSONAL_KEY_MISSING", "Görevi başlatanın bu modelin sağlayıcısında kişisel API anahtarı yok (kaldırılmış). Ayarlar → Anahtarım'dan ekleyip yeniden başlat.")
    if ctx is not None:
        ctx.key = key
    db.expunge(model)
    db.expunge(provider)
    return model, provider  # type: ignore[return-value]


EXTRACT_CHUNK_CHARS = 3000  # yoğun teknik metinde ≈40 olgu; 4000 çıktı token'ına sığar
MAX_DRAFT_CLAIMS = 200  # ItemIn.claims sınırı


def text_chunks(text: str, size: int = EXTRACT_CHUNK_CHARS) -> list[str]:
    """Uzun kaynağı satır sınırlarından bölümlere ayırır (alıntılar satır içinde kalır; satır bölünmez).
    Canlı modelle bulundu (2026-10-18): tek çağrıda ≈50'den çok olgu çıktı sınırında kesiliyor, JSON yarım kalıyordu."""
    out: list[str] = []
    cur: list[str] = []
    n = 0
    for line in text.splitlines(keepends=True):
        if cur and n + len(line) > size:
            out.append("".join(cur))
            cur, n = [], 0
        cur.append(line)
        n += len(line)
    if cur:
        out.append("".join(cur))
    return [c for c in out if c.strip()] or [text]


def call(ctx: JobContext, model, provider, prompt_id, payload, schema, validator=None, output_tokens=2000):  # noqa: ANN001, ANN201
    ctx.reserve(payload, output_tokens)
    res = ModelClient().call(model, provider, prompt_id=prompt_id, payload=payload, schema=schema, validator=validator, purpose="worker", job_id=ctx.job_id, max_tokens=output_tokens, key=ctx.key)
    ctx.note_call(res.call_id)
    if not res.ok:
        code = "INVALID_MODEL_OUTPUT" if res.error in ("INVALID_RESPONSE", "VALIDATION") else "MODEL_ERROR"
        raise JobFailed(code, f"Model adımı tamamlanamadı ({res.error}). Kısmi sonuçlar korunuyor; yeniden deneyebilirsin.")
    return res.output


def _stem_words(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[\wçğıöşü]+", text.casefold()) if len(w) > 3 and not w.isdigit()}


def _strip_numbers(text: str) -> str:
    return re.sub(r"\d+(?:[.,]\d+)?", "#", text.casefold())


def run_prepare(ctx: JobContext) -> None:
    with transaction() as db:
        job = ctx.guard(db)
        requester = ctx.requester(db)
        model, provider = load_model(db, job, ctx)
        rev_ids = [uuid.UUID(r) for r in job.inputs.get("source_revision_ids", [])]
        if len(rev_ids) > MAX_SOURCES:
            raise BudgetExceeded("sources")
        revisions = []
        for rid in rev_ids:
            rev = db.get(SourceRevision, rid)
            src = db.get(Source, rev.source_id)  # type: ignore[union-attr]
            revisions.append({"id": str(rev.id), "title": src.title, "kind": src.kind, "text": rev.text, "scope": rev.scope, "extraction": rev.extraction})  # type: ignore[union-attr]
        answered = [m.body for m in db.scalars(select(JobMessage).where(JobMessage.job_id == job.id, JobMessage.role == "user"))]
        project_id, job_id, requester_id = job.project_id, job.id, requester.id
        instructions = job.inputs.get("instructions", "")

    # Kapsam sorusu: tamamen belirlenmemiş kaynak → kullanıcıya sor (awaiting_input).
    unscoped = [r for r in revisions if not any(normalize_scope(r["scope"])[d] for d in DIMENSIONS)]
    if unscoped and not answered:
        raise AwaitInput(
            [
                {
                    "body": f"«{r['title']}» kaynağının kapsamı belirlenmemiş. Hangi Domain/YATT/Kart/Proje için geçerli? Seçtiğin kapsamla kaynağın yeni bir sürümü kaydedilir.",
                    "detail": {"kind": "scope", "source_revision_id": r["id"]},
                }
                for r in unscoped
            ]
        )
    for r in revisions:
        if r["extraction"] == "annotation_only" and not r["text"].strip():
            raise JobFailed("NO_TEXT", f"«{r['title']}» kaynağından metin çıkarılamadı; Metis bu kaynakla taslak hazırlayamaz.")
        if len(r["text"]) > MAX_SOURCE_CHARS:
            raise BudgetExceeded("source_chars")

    cp = ctx.checkpoint()
    report = cp.get("report") or {"sources": [], "conflicts": [], "relations": [], "open_decisions": [], "dropped_quotes": 0}
    processed: list[str] = list(cp.get("processed", []))
    extracted: dict[str, list[dict]] = dict(cp.get("extracted", {}))

    for r in revisions:
        if r["id"] in processed:
            continue
        ctx.step("extract", source=r["title"])
        raw_claims: list[dict] = []
        raw_decisions: list[dict] = []
        for part in text_chunks(r["text"]):
            out = call(ctx, model, provider, prompts.EXTRACT, {"text": part, "scope": normalize_scope(r["scope"]), "instructions": instructions, "human_responses": answered}, contracts.Extraction, output_tokens=4000)
            raw_claims.extend(out["claims"])
            raw_decisions.extend(out["open_decisions"])
        claims = list({c["quote"]: c for c in raw_claims if c["quote"] in r["text"]}.values())  # iddia = alıntı; bölüm sınırında tekrar olmaz
        decisions = list({d["quote"]: d for d in raw_decisions if d["quote"] in r["text"]}.values())
        report["dropped_quotes"] += sum(1 for c in raw_claims if c["quote"] not in r["text"]) + sum(1 for d in raw_decisions if d["quote"] not in r["text"])
        if len(claims) > MAX_DRAFT_CLAIMS:
            report["claims_over_limit"] = report.get("claims_over_limit", 0) + len(claims) - MAX_DRAFT_CLAIMS
            claims = claims[:MAX_DRAFT_CLAIMS]
        with transaction() as db:
            ctx.guard(db)
            for c in claims:
                fp = fingerprint("claim", project_id, r["id"], c["quote"], c["value"])
                if not db.scalar(select(ExtractedClaim.id).where(ExtractedClaim.fingerprint == fp)):
                    start = r["text"].index(c["quote"])
                    db.add(ExtractedClaim(project_id=project_id, source_revision_id=uuid.UUID(r["id"]), job_id=job_id, fingerprint=fp, subject=c["subject"][:300], attribute=c["attribute"][:300], value=c["value"], condition=c["condition"], quote=c["quote"], quote_start=start, quote_end=start + len(c["quote"]), scope=normalize_scope(r["scope"])))
            for d in decisions:
                fp = fingerprint("decision", project_id, r["id"], d["quote"])
                if not db.scalar(select(OpenDecision.id).where(OpenDecision.fingerprint == fp)):
                    start = r["text"].index(d["quote"])
                    db.add(OpenDecision(project_id=project_id, source_revision_id=uuid.UUID(r["id"]), job_id=job_id, fingerprint=fp, description=d["description"], quote=d["quote"], quote_start=start, quote_end=start + len(d["quote"])))
        report["open_decisions"].extend({"source": r["title"], "description": d["description"], "quote": d["quote"]} for d in decisions)
        entry = {"source_revision_id": r["id"], "title": r["title"], "claims": len(claims), "open_decisions": len(decisions), "comparisons": []}
        report["sources"].append(entry)
        extracted[r["id"]] = claims
        ctx.save(report=report, extracted=extracted)  # kısmi sonuç, bütçe aşılırsa korunur

        ctx.step("retrieve", source=r["title"])
        with transaction() as db:
            ctx.guard(db)
            from metis.core.models import User
            from metis.modules.search.service import search

            req = db.get(User, requester_id)
            src_id = db.get(SourceRevision, uuid.UUID(r["id"])).source_id  # type: ignore[union-attr]
            hits = search(db, req, project_id, r["text"][:4000], None, None, 10).hits  # type: ignore[arg-type]
            candidates = []
            for h in hits:
                own = db.scalar(
                    select(Evidence.id)
                    .join(ClaimEvidence, ClaimEvidence.evidence_id == Evidence.id)
                    .join(Claim, Claim.id == ClaimEvidence.claim_id)
                    .join(SourceRevision, SourceRevision.id == Evidence.source_revision_id)
                    .where(Claim.page_revision_id == h.revision_id, SourceRevision.source_id == src_id)
                    .limit(1)
                )
                if own:  # kendi kanıtına dayanan sayfa aday değildir
                    continue
                rev = db.get(PageRevision, h.revision_id)
                statements = [c.statement for c in db.scalars(select(Claim).where(Claim.page_revision_id == rev.id).order_by(Claim.ord))]  # type: ignore[union-attr]
                candidates.append({"page_id": str(h.page_id), "title": h.title, "scope": h.scope, "summary": rev.summary, "statements": statements})  # type: ignore[union-attr]
                if len(candidates) == 3:
                    break

        comparisons = []
        for cand in candidates:
            ctx.step("compare", page=cand["title"])
            page_text = "\n".join([cand["title"], cand["summary"], *cand["statements"]])
            res = call(ctx, model, provider, prompts.PAGE_DIFF, {"kayit_a": r["text"][:8000], "kayit_b": page_text}, contracts.PageDiff, output_tokens=1200)
            comparisons.append({"page_id": cand["page_id"], "page_title": cand["title"], "verdict": res["verdict"], "reason": res["reason"]})
            entry["comparisons"] = comparisons
            ctx.save(report=report)
            if res["verdict"] == "conflict_candidate":
                pairs = []
                for c in claims:
                    for st in cand["statements"]:
                        same_shape = _strip_numbers(c["quote"]) == _strip_numbers(st)
                        overlap = len(_stem_words(c["quote"]) & _stem_words(st)) / max(1, len(_stem_words(c["quote"])))
                        if c["quote"] != st and (same_shape or overlap >= 0.5):
                            pairs.append((c, st))
                for c, st in pairs[:3]:
                    left = {"subject": c["subject"], "attribute": c["attribute"], "value": c["value"], "quote": c["quote"], "scope": {**normalize_scope(r["scope"]), "condition": c["condition"]}}
                    right = {"subject": c["subject"], "attribute": c["attribute"], "value": st, "quote": st, "scope": {**normalize_scope(cand["scope"]), "condition": ""}}
                    if not overlaps(r["scope"], cand["scope"]):
                        verdict = {"verdict": "scope_disjoint", "reason": "Kapsamlar ayrık; model çağrılmadı."}
                    else:
                        ctx.step("judge", page=cand["title"])
                        verdict = call(ctx, model, provider, prompts.CLAIM_CONFLICT, {"kayit_a": left, "kayit_b": right}, contracts.ClaimJudgement, output_tokens=800)
                    report["conflicts"].append({"page_id": cand["page_id"], "page_title": cand["title"], "new_quote": c["quote"], "existing": st, **verdict})
        for cand in candidates:
            ctx.step("relate", page=cand["title"])
            res = call(ctx, model, provider, prompts.RELATION, {"kayit_a": {"text": r["text"][:6000]}, "kayit_b": {"title": cand["title"], "statements": cand["statements"][:20]}}, contracts.RelationJudgement, output_tokens=600)
            if res["verdict"] == "relation":
                report["relations"].append({"page_id": cand["page_id"], "page_title": cand["title"], "predicate": res["predicate"], "reason": res["reason"]})
        entry["comparisons"] = comparisons
        processed.append(r["id"])
        ctx.save(report=report, processed=processed, extracted=extracted)

    total_claims = sum(len(v) for v in extracted.values())
    all_no_change = all(c["verdict"] == "no_change" for s in report["sources"] for c in s["comparisons"]) and any(s["comparisons"] for s in report["sources"])
    if total_claims == 0:
        ctx.finish("completed", "Kaynakta doğrulanabilir iddia bulunamadı; taslak oluşturulmadı.", report=report, produced_draft=False)
        return
    if all_no_change:
        ctx.finish("completed", "Kaynak, yayımlanmış bilgiye yeni bir şey eklemiyor; taslak oluşturulmadı.", report=report, produced_draft=False)
        return

    ctx.step("draft")
    with transaction() as db:
        job = ctx.guard(db)
        from metis.core.models import User

        requester = db.get(User, requester_id)
        worker = worker_identity(db)
        items = []
        for r in revisions[:5]:
            rev = db.get(SourceRevision, uuid.UUID(r["id"]))
            claim_ins = []
            for c in extracted.get(r["id"], []):
                start = r["text"].index(c["quote"])
                end = start + len(c["quote"])
                ev = db.scalar(select(Evidence).where(Evidence.source_revision_id == rev.id, Evidence.char_start == start, Evidence.char_end == end))  # type: ignore[union-attr]
                if ev is None:
                    page_no = None
                    for pe in db.scalars(select(Evidence).where(Evidence.source_revision_id == rev.id, Evidence.locator["auto"].astext == "page")):  # type: ignore[union-attr]
                        if pe.char_start is not None and pe.char_end is not None and pe.char_start <= start < pe.char_end:
                            page_no = pe.locator.get("page")
                    ev = Evidence(source_revision_id=rev.id, locator=build_locator(r["text"], start, end, rev.meta, page=page_no), excerpt=c["quote"], char_start=start, char_end=end)  # type: ignore[union-attr]
                    db.add(ev)
                    db.flush()
                claim_ins.append(cs.ClaimIn(statement=c["quote"], kind="expert_statement", support="supported", evidence=[cs.EvidenceRef(evidence_id=ev.id, quote=c["quote"])]))
            if not claim_ins:
                continue
            unknowns = [f"{d['description']} — «{d['quote']}»" for d in report["open_decisions"] if d["source"] == r["title"]]
            items.append(
                cs.ItemIn(
                    title=re.sub(r"\s+[—-]\s+.*$", "", r["title"])[:240] or r["title"][:240],
                    summary=claim_ins[0].statement[:400],
                    body_md="\n\n".join(c.statement for c in claim_ins),
                    kind=KIND_FOR_SOURCE.get(r["kind"], "concept"),  # type: ignore[arg-type]
                    scope=normalize_scope(r["scope"]),  # type: ignore[arg-type]
                    unknowns=unknowns[:50],
                    claims=claim_ins,
                )
            )
        change = changes.create_change(
            db,
            worker,
            job.project_id,
            cs.ChangeCreateIn(summary="Metis kaynaktan taslak hazırladı", items=items, submit=True),
            requester=requester,
            job_id=job.id,
            idempotency_key=f"job:{job.id}",
        )
        change.detail = {**change.detail, "job_report": report}
        if not db.get(JobOutput, (job.id, change.id)):
            db.add(JobOutput(job_id=job.id, change_set_id=change.id))
        change_id = change.id
    conflicts = sum(1 for c in report["conflicts"] if c["verdict"] == "conflict")
    summary = f"{total_claims} yeni iddia" + (f", {conflicts} çelişki adayı" if conflicts else "") + (f", {len(report['relations'])} ilişki önerisi" if report["relations"] else "") + " bulundu. Taslak hazır." + (f" {report['claims_over_limit']} iddia, taslak başına {MAX_DRAFT_CLAIMS} sınırı nedeniyle alınmadı; kaynağı bölerek ayrıca hazırlat." if report.get("claims_over_limit") else "")
    report["change_id"] = str(change_id)
    ctx.finish("completed", summary, report=report, produced_draft=True)
