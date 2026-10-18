"""refine_draft — 'Taslağı düzenle ve karşılaştır': ≤5 sayfalık taslağı paragraf→iddia indeksiyle yeniden yazar.

Tüm iddialar kapsanmalı; kanıt ID'leri ve kapsam korunur. Başlık/özet önerisi iddialarla deterministik denetlenir.
İlk taslak değişmez; sonuç ayrı bir kayıt olarak hazırlanır (yayımlamak yine bir insanın işidir).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from metis.core.db import transaction
from metis.core.models import Claim, JobOutput, PageRevision, User
from metis.llm import contracts, prompts
from metis.llm.validators import check_sentence, has_negation
from metis.modules.changes import schemas as cs
from metis.modules.changes import service as changes
from metis.modules.knowledge.figures import strip_figures
from metis.modules.knowledge.views import revision_views
from metis.worker.prepare import call, load_model
from metis.worker.runtime import JobContext, JobFailed, worker_identity


def grounded(text: str, statements: list[str]) -> bool:
    """Önerilen başlık/özet yalnız iddialarda geçen sayı, sembol, sürüm ve olumsuzlukları kullanır mı?
    (Mentor açıklama cümleleriyle aynı deterministik denetim; olumsuzluk yalnız *eklenirse* sorun.)"""
    text = text.strip()
    if not text:
        return False
    ids = [str(i) for i in range(len(statements))]
    reasons = set(check_sentence(text, ids, dict(zip(ids, statements, strict=True))).reasons)
    if not has_negation(text):
        reasons.discard("negation")  # iddialardaki olumsuzluğu özetlememek uydurma değildir
    return not reasons


def run_refine(ctx: JobContext) -> None:
    with transaction() as db:
        job = ctx.guard(db)
        requester = ctx.requester(db)
        model, provider = load_model(db, job)
        change = changes.accessible_change(db, requester, uuid.UUID(job.inputs["draft_change_id"]))
        if change.state not in ("draft", "in_review") or change.hash != job.inputs.get("draft_hash"):
            raise JobFailed("DRAFT_CHANGED", "Seçilen taslak değişti; güncel taslakla yeniden başlat.")
        items = changes._items(db, change)
        if len(items) > 5:
            raise JobFailed("TOO_MANY_PAGES", "Taslak en fazla 5 sayfa içerebilir.")
        views = revision_views(db, [db.get(PageRevision, i.proposed_revision_id) for i in items if i.proposed_revision_id])
        drafts = []
        for item in items:
            if item.action != "upsert" or not item.proposed_revision_id:
                continue
            v = views[item.proposed_revision_id]
            if not v.claims or any(not c.evidence for c in v.claims):
                raise JobFailed("EVIDENCE_REQUIRED", "Taslağın her iddiası kaynak alıntısına bağlı olmalı.")
            drafts.append({"item": item, "view": v})
        project_id, requester_id, job_id, instructions = job.project_id, requester.id, job.id, job.inputs.get("instructions", "")
        summary = change.summary

    proposals = []
    report = {"pages": []}
    for d in drafts:
        v = d["view"]
        ctx.step("refine", page=v.title)
        payload = {"draft": {"title": v.title, "summary": v.summary, "body": strip_figures(v.body_md), "claims": [{"statement": c.statement} for c in v.claims]}, "evidence": {str(e.evidence_id): e.quote for c in v.claims for e in c.evidence}, "instructions": instructions}
        n = len(v.claims)

        def covers(out: dict, n: int = n) -> bool:
            idx = [i for p in out["paragraphs"] for i in p["claim_indices"]]
            return set(idx) == set(range(n)) and all(0 <= i < n for i in idx)

        out = call(ctx, model, provider, prompts.REFINE, payload, contracts.Refinement, validator=covers, output_tokens=3000)
        ctx.step("compare", page=v.title)
        with transaction() as db:
            ctx.guard(db)
            from metis.modules.search.service import search

            req = db.get(User, requester_id)
            hits = [h for h in search(db, req, project_id, v.body_md[:4000] or v.title, None, None, 6).hits if h.page_id != d["item"].page_id][:3]  # type: ignore[arg-type]
            cands = [{"page_id": str(h.page_id), "title": h.title, "statements": list(db.scalars(select(Claim.statement).where(Claim.page_revision_id == h.revision_id)))} for h in hits]
        comparisons = []
        for cand in cands:
            res = call(ctx, model, provider, prompts.PAGE_DIFF, {"kayit_a": v.body_md[:8000], "kayit_b": "\n".join([cand["title"], *cand["statements"]])}, contracts.PageDiff, output_tokens=1000)
            comparisons.append({"page_id": cand["page_id"], "page_title": cand["title"], "verdict": res["verdict"], "reason": res["reason"]})
        statements = [c.statement for c in v.claims]
        # Model başlık/özet önerir; iddialarla desteklenmeyen öneri kullanılmaz, eskisi korunur.
        title = out.get("title", "").strip()
        title = title if title and grounded(title, [*statements, v.title]) else v.title
        summary = out.get("summary", "").strip()
        summary = summary if summary and grounded(summary, statements) else v.summary
        report["pages"].append({"title": title, "claims": n, "paragraphs": len(out["paragraphs"]), "comparisons": comparisons, "title_changed": title != v.title, "summary_changed": summary != v.summary})
        item = d["item"]
        proposals.append(
            cs.ItemIn(
                page_id=item.page_id if item.base_revision_id else None,
                base_revision_id=item.base_revision_id,
                title=title,
                summary=summary,
                # Görseller modelden geçmez; aynen taşınır ve gövdenin sonuna yerleşir (inceleyen yerini değiştirebilir).
                body_md="\n\n".join([*(p["text"] for p in out["paragraphs"]), *(f"{{{{görsel {f.ord}}}}}" for f in v.figures)]),
                kind=v.kind,  # type: ignore[arg-type]
                scope=v.scope,  # type: ignore[arg-type]
                unknowns=v.unknowns,
                aliases=v.aliases,
                claims=[cs.ClaimIn(statement=c.statement, kind=c.kind, support=c.support, evidence=[cs.EvidenceRef(evidence_id=e.evidence_id, quote=e.quote) for e in c.evidence]) for c in v.claims],  # type: ignore[arg-type]
                figures=[cs.FigureIn(source_revision_id=f.source_revision_id, caption=f.caption) for f in v.figures],
            )
        )
    ctx.step("draft")
    with transaction() as db:
        job = ctx.guard(db)
        requester = db.get(User, requester_id)
        worker = worker_identity(db)
        new = changes.create_change(db, worker, project_id, cs.ChangeCreateIn(summary=f"Seçili taslaktan Metis düzenlemesi: {summary}"[:4000], items=proposals, submit=True), requester=requester, job_id=job_id, idempotency_key=f"job:{job_id}")
        new.detail = {**new.detail, "job_report": report, "source_change_id": job.inputs["draft_change_id"]}
        if not db.get(JobOutput, (job_id, new.id)):
            db.add(JobOutput(job_id=job_id, change_set_id=new.id))
    ctx.finish("completed", "Düzenlenen taslak ayrı bir kayıt olarak hazır. İlk taslak korundu.", report=report, produced_draft=True)
