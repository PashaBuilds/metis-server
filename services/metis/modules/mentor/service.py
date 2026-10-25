"""Kaynaklı mentor hattı (brief 5.6).

kimlik → kapsam → aktif yayın → arama (top-k, deterministik)
  → [aday > 8 ise] kaynak seçimi çağrısı
  → kanıt paketi: yalnız onaylı, desteklenen, kanıt metninde birebir geçen iddialar
  → cevap çağrısı (evidence-explain-v1) → deterministik doğrulama
  → yetki/geri çekme yeniden kontrolü → kaydet

Epistemik sonuçlar (NO_EVIDENCE vb.) HTTP hatası değildir. RETRIEVAL_UNAVAILABLE / MODEL_UNAVAILABLE
asla NO_EVIDENCE ile karıştırılmaz. Sessiz fallback yok: seçilen model uygun değilse neden yazılır.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from metis.core.access import evidence_access, require_member
from metis.core.audit import audit
from metis.core.config import get_settings
from metis.core.db import reader, transaction, utcnow
from metis.core.errors import AppError
from metis.core.models import (
    Answer,
    AnswerCitation,
    AnswerFeedback,
    Claim,
    ClaimEvidence,
    Evidence,
    Finding,
    FindingPage,
    Model,
    Page,
    PageRevision,
    Project,
    Provider,
    Source,
    SourceRevision,
    User,
)
from metis.llm import contracts, prompts
from metis.llm.client import ModelClient
from metis.llm.validators import valid_source_selection, validate_answer
from metis.modules.lab.service import eligibility, route
from metis.modules.mentor import schemas
from metis.modules.scopes.semantics import DIMENSIONS, matches_scope, mismatched_dimensions, normalize_scope
from metis.modules.search.index import is_heading_block
from metis.modules.sources.locator import locator_label

TOP_K = 12
SHORT_PAGE = 8  # bu kadar bloğu olan sayfa pakete olduğu gibi girer
BEST_PER_PAGE = 6
MAX_BUNDLE = 40
RELATED_PASSAGES = 5
SELECTION_THRESHOLD = 8
EXCLUDED_SUPPORT = ("unsupported", "conflicting")

Emit = Callable[[str, dict], None]


def _noop(_e: str, _d: dict) -> None:
    return None


def block_priority(rows: list[dict], best: list[str]) -> list[dict]:
    """Sayfanın paket adayı bloklarını öncelik sırasıyla döner: her en iyi blok için önce kendisi, sonra önündeki en yakın
    başlık, sonra komşuları (ord±1); en çok 6 en iyi blok. Kısa sayfa (≤ 8 blok) sırasıyla; blok sıralaması yoksa
    (yalnız başlık/alias eşleşmesi) ilk 8 blok."""
    if len(rows) <= SHORT_PAGE:
        return list(rows)
    by_id = {r["claim_id"]: r for r in rows}
    by_ord = {r["ord"]: r for r in rows}
    headings = sorted(o for o, r in by_ord.items() if is_heading_block(r["statement"]))
    out: list[dict] = []
    seen: set[int] = set()

    def take(o: int) -> None:
        if o in by_ord and o not in seen:
            seen.add(o)
            out.append(by_ord[o])

    for cid in best[:BEST_PER_PAGE]:
        r = by_id.get(cid)
        if r is None:
            continue
        o = r["ord"]
        take(o)
        prev = [h for h in headings if h <= o]
        if prev:
            take(prev[-1])
        take(o - 1)
        take(o + 1)
    if not out:
        return sorted(rows, key=lambda r: r["ord"])[:SHORT_PAGE]
    return out


def select_blocks(rows: list[dict], best: list[str]) -> list[dict]:
    """Tek sayfanın seçilen blokları, not sırasıyla."""
    return sorted(block_priority(rows, best), key=lambda r: r["ord"])


def allocate(pages: list[tuple[list[dict], list[str]]], cap: int = MAX_BUNDLE) -> list[list[dict]]:
    """Paket payını sayfalara sırayla birer blok dağıtır (önce her sayfanın en iyi bloğu): sıralamada geride kalan sayfanın
    cevap bloğu, öndeki uzun sayfalar yüzünden paketten düşmez. Her sayfanın seçimi not sırasıyla döner."""
    queues = [block_priority(rows, best) for rows, best in pages]
    chosen: list[list[dict]] = [[] for _ in pages]
    total, round_ = 0, 0
    while total < cap and any(round_ < len(q) for q in queues):
        for i, q in enumerate(queues):
            if round_ < len(q) and total < cap:
                chosen[i].append(q[round_])
                total += 1
        round_ += 1
    return [sorted(c, key=lambda r: r["ord"]) for c in chosen]


def _bundle_for(db: Session, user: User, page: Page, rev: PageRevision) -> list[dict]:
    rows = db.execute(
        select(Claim, ClaimEvidence, Evidence, SourceRevision, Source)
        .join(ClaimEvidence, ClaimEvidence.claim_id == Claim.id)
        .join(Evidence, Evidence.id == ClaimEvidence.evidence_id)
        .join(SourceRevision, SourceRevision.id == Evidence.source_revision_id)
        .join(Source, Source.id == SourceRevision.source_id)
        .where(Claim.page_revision_id == rev.id)
        .order_by(Claim.ord)
    ).all()
    out, seen = [], set()
    for claim, _ce, ev, _sr, src in rows:
        if claim.id in seen or claim.support in EXCLUDED_SUPPORT:
            continue
        if claim.statement not in ev.excerpt:  # kanıt metninde birebir geçmeyen iddia pakete girmez
            continue
        try:
            evidence_access(db, user, ev.id)
        except AppError:
            continue
        seen.add(claim.id)
        out.append(
            {
                "ord": claim.ord,
                "claim_id": str(claim.id),
                "evidence_id": str(ev.id),
                "statement": claim.statement,
                "scope": normalize_scope(rev.scope),
                "page_id": str(page.id),
                "page_title": rev.title,
                "revision_id": str(rev.id),
                "source_title": src.title,
                "locator_label": locator_label({k: v for k, v in ev.locator.items() if k != "auto"}),
            }
        )
    return out


def _force_conflict(state: dict, pending: dict) -> None:
    state["decision"] = "CONFLICTING"
    state["conflict_finding_id"] = pending["finding_id"]
    state["conflict_sides"] = pending["sides"]


def _open_conflict(db: Session, project_id: uuid.UUID, page_ids: list[uuid.UUID]) -> Finding | None:
    if not page_ids:
        return None
    return db.scalar(
        select(Finding)
        .join(FindingPage, FindingPage.finding_id == Finding.id)
        .where(Finding.project_id == project_id, Finding.kind == "conflict", Finding.state == "open", FindingPage.page_id.in_(page_ids))
        .limit(1)
    )


def _conflict_sides(db: Session, user: User, finding: Finding) -> list[schemas.ConflictSide]:
    sides = []
    for side in finding.detail.get("sides", [])[:2]:
        try:
            ev_id = uuid.UUID(side["evidence_id"]) if side.get("evidence_id") else None
            if ev_id:
                evidence_access(db, user, ev_id)
        except (AppError, ValueError, KeyError):
            continue
        sides.append(
            schemas.ConflictSide(
                page_id=uuid.UUID(side["page_id"]) if side.get("page_id") else None,
                page_title=side.get("page_title", ""),
                quote=side.get("quote", ""),
                evidence_id=ev_id,
            )
        )
    return sides


def ask(user_id: uuid.UUID, project_id: uuid.UUID, req: schemas.AskIn, emit: Emit = _noop) -> schemas.AnswerOut:
    started = time.perf_counter()
    timings: dict[str, float | None] = {"retrieval_ms": None, "selection_ms": None, "generation_ms": None, "validation_ms": None, "total_ms": None}
    selector = normalize_scope(req.scope.model_dump() if req.scope else {})
    state: dict[str, Any] = {
        "decision": "NO_EVIDENCE",
        "explanation": [],
        "citations": [],
        "related": [],
        "unknowns": [],
        "conflict_sides": [],
        "conflict_finding_id": None,
        "needs_scope_dimensions": [],
        "model": None,
        "model_unavailable_reason": None,
        "alternatives": [],
        "dropped": [],
        "selection": None,
        "error": None,
    }
    bundle: list[dict] = []
    pending: list[tuple[schemas.RelatedPage, list[dict], list[str]]] = []  # pakete aday sayfalar (arama sırasıyla)
    passages: list[dict] = []  # model yokken gösterilecek ilgili yayımlanmış bölümler (cevap değildir)
    candidate_revisions: list[uuid.UUID] = []
    pending_conflict: dict | None = None

    with reader() as db:
        user = db.get(User, user_id)
        if not user or not user.active:
            raise AppError("UNAUTHENTICATED", "user inactive")
        require_member(db, user, project_id)
        project = db.get(Project, project_id)
        assert project is not None
        publication_id = project.active_publication_id
        emit("progress", {"step": "searching"})

        if get_settings().retrieval_disabled:
            state["decision"] = "RETRIEVAL_UNAVAILABLE"
        else:
            try:
                from metis.modules.search.service import search

                hits = search(db, user, project_id, req.question, None, None, TOP_K * 2).hits
            except AppError:
                raise
            except Exception:  # noqa: BLE001 — arama hatası "bilgi yok" sayılmaz
                hits = None
                state["decision"] = "RETRIEVAL_UNAVAILABLE"
            if hits is not None:
                timings["retrieval_ms"] = round((time.perf_counter() - started) * 1000, 2)
                matching, mismatch_dims = [], set()
                for h in hits:
                    if matches_scope(h.scope, selector):
                        matching.append(h)
                    else:
                        mismatch_dims.update(mismatched_dimensions(h.scope, selector))
                if hits and not matching:
                    state["decision"] = "NEEDS_SCOPE"
                    state["needs_scope_dimensions"] = [d for d in DIMENSIONS if d in mismatch_dims]
                for h in matching[:TOP_K]:
                    page = db.get(Page, h.page_id)
                    rev = db.get(PageRevision, h.revision_id)
                    if not page or not rev:
                        continue
                    candidate_revisions.append(rev.id)
                    related = schemas.RelatedPage(page_id=page.id, title=rev.title, revision_id=rev.id, freshness=page.freshness, scope=rev.scope)
                    if page.freshness == "dependency_changed":
                        related.excluded = "dependency_changed"  # kaynağı değişen sayfa mentor tarafından kullanılmaz
                        state["related"].append(related)
                        continue
                    claims = _bundle_for(db, user, page, rev)
                    if not claims:
                        related.excluded = "no_verbatim_claims"
                    else:
                        pending.append((related, claims, [str(c) for c in h.best_claims]))
                    if h.passage_text and h.best_claims and len(passages) < RELATED_PASSAGES:
                        passages.append(
                            {"page_id": str(page.id), "title": rev.title, "heading_path": h.heading_path, "text": h.passage_text, "claim_id": str(h.best_claims[0]), "revision_id": str(rev.id)}
                        )
                    state["related"].append(related)
                    state["unknowns"].extend(u for u in (rev.unknowns or []) if u not in state["unknowns"])
                for (related, _rows, _best), chosen in zip(pending, allocate([(r, b) for _, r, b in pending]), strict=True):
                    if chosen:
                        bundle.extend(chosen)
                    else:
                        related.excluded = "bundle_limit"  # paket sınırı: daha ilgili sayfalar öncelikli
                emit("sources", {"related": [r.model_dump(mode="json") for r in state["related"]]})
                conflict = _open_conflict(db, project_id, [r.page_id for r in state["related"] if not r.excluded])
                if conflict is not None and bundle:
                    conflict_pages = set(db.scalars(select(FindingPage.page_id).where(FindingPage.finding_id == conflict.id)))
                    for r in state["related"]:
                        r.open_conflict = r.page_id in conflict_pages
                    pending_conflict = {
                        "finding_id": conflict.id,
                        "sides": _conflict_sides(db, user, conflict),
                        "pages": {str(p) for p in conflict_pages},
                    }
                    if all(b["page_id"] in pending_conflict["pages"] for b in bundle):
                        _force_conflict(state, pending_conflict)  # yalnız çelişkili sayfalar bulundu
                        bundle, pending_conflict = [], None
                    else:
                        # Brief 5.6: çelişkili sayfa *seçilirse* karar CONFLICTING. Yanında başka sayfalar da varsa
                        # hangilerinin soruyla ilgili olduğuna kaynak seçimi karar verir (aşağıda, model ile).
                        state["decision"] = "MODEL_UNAVAILABLE"
                elif bundle:
                    state["decision"] = "MODEL_UNAVAILABLE"

        model = provider = None
        if state["decision"] == "MODEL_UNAVAILABLE":
            if req.model_id:
                model = db.get(Model, req.model_id)
                ok, reason = eligibility(db, model, project) if model else (False, "not_found")
                if not ok:
                    state["model_unavailable_reason"] = reason
                    model = None
            else:
                model, reasons = route(db, project)
                if model is None:
                    state["model_unavailable_reason"] = next((r["reason"] for r in reasons), "no_models")
            _, reasons = route(db, project)
            state["alternatives"] = [{"id": r["model_id"], "display_name": r["display_name"]} for r in reasons if r["eligible"] and (not req.model_id or r["model_id"] != str(req.model_id))]
            if model is not None:
                provider = db.get(Provider, model.provider_id)
                state["model"] = {"id": str(model.id), "display_name": model.display_name, "remote_id": model.remote_id, "provider": provider.name if provider else "", "is_fixture": model.is_fixture}
                # Alternatif = kullanılan modelden başkası (çağrı başarısız olursa aynı model önerilmez).
                state["alternatives"] = [a for a in state["alternatives"] if a["id"] != str(model.id)]
                db.expunge(model)
                if provider:
                    db.expunge(provider)

    if pending_conflict is not None and model is None:
        # Model yok: çelişkili sayfanın soruyla ilgisi ayırt edilemez; karar dürüstçe MODEL_UNAVAILABLE kalır
        # (ilgili sayfalarda açık çelişki işareti görünür). Yalnız çelişkili sayfalar bulunduysa yukarıda CONFLICTING.
        bundle, pending_conflict = [], None

    # ---------------------------------------------------------------- model çağrıları (oturum dışı)
    if model is not None and provider is not None:
        client = ModelClient()
        pages = list(dict.fromkeys(b["page_id"] for b in bundle))
        if len(pages) > SELECTION_THRESHOLD or pending_conflict is not None:
            t0 = time.perf_counter()
            payload = {
                "question": req.question,
                "scope": selector,
                "pages": [{"page_id": p, "title": next(b["page_title"] for b in bundle if b["page_id"] == p), "statements": [b["statement"] for b in bundle if b["page_id"] == p][:20]} for p in pages],
            }
            sel = client.call(model, provider, prompt_id=prompts.SOURCE_SELECTION, payload=payload, schema=contracts.SourceSelection, validator=lambda o: valid_source_selection(o, pages), purpose="mentor")
            timings["selection_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            if not sel.ok:
                state["error"] = sel.error
                state["model_unavailable_reason"] = "call_failed"
                bundle = []
            else:
                verdicts = {r["page_id"]: r["relevance"] for r in sel.output["reviews"]}
                bundle = [b for b in bundle if verdicts.get(b["page_id"]) != "irrelevant"]
                for r in state["related"]:
                    r.relevance = verdicts.get(str(r.page_id))
                state["selection"] = {"call_id": str(sel.call_id), "candidates": len(pages)}
                if pending_conflict is not None and any(b["page_id"] in pending_conflict["pages"] for b in bundle):
                    _force_conflict(state, pending_conflict)  # çelişkili sayfa seçildi
                    bundle = []
                elif not bundle:
                    state["decision"] = "NO_EVIDENCE"
        if bundle:
            emit("progress", {"step": "verifying"})
            t1 = time.perf_counter()
            payload = {
                "question": req.question,
                "scope": selector,
                "level": req.level,
                "conflict": False,
                "evidence": [{k: b[k] for k in ("claim_id", "evidence_id", "statement", "scope")} for b in bundle],
            }
            res = client.call(model, provider, prompt_id=prompts.EVIDENCE, payload=payload, schema=contracts.EvidenceAnswer, purpose="mentor", cache=True)
            timings["generation_ms"] = round((time.perf_counter() - t1) * 1000, 2)
            if not res.ok:
                state["decision"] = "VALIDATION_FAILED" if res.error in ("INVALID_RESPONSE", "VALIDATION") else "MODEL_UNAVAILABLE"
                state["error"] = res.error
                if state["decision"] == "MODEL_UNAVAILABLE":
                    state["model_unavailable_reason"] = "call_failed"
            else:
                t2 = time.perf_counter()
                v = validate_answer(res.output, bundle, req.level, scope=selector)
                timings["validation_ms"] = round((time.perf_counter() - t2) * 1000, 3)
                if not v.structure_ok:
                    state["decision"] = "VALIDATION_FAILED"
                    state["error"] = v.error
                else:
                    state["decision"] = v.decision
                    if v.decision in ("SUPPORTED", "PARTIAL"):
                        by_id = {b["claim_id"]: b for b in bundle}
                        order: list[str] = [c["claim_id"] for c in v.claims]
                        for s in v.kept:
                            for cid in s.claim_ids:
                                if cid not in order:
                                    order.append(cid)
                        state["citations"] = [by_id[c] for c in order]
                        idx = {cid: i + 1 for i, cid in enumerate(order)}
                        state["explanation"] = [schemas.Sentence(text=s.text, refs=[idx[c] for c in s.claim_ids]) for s in v.kept]
                        state["dropped"] = [{"text": s.text, "reasons": s.reasons} for s in v.dropped]

    # ---------------------------------------------------------------- yetki/geri çekme yeniden kontrolü + kayıt
    with transaction() as db:
        user = db.get(User, user_id)
        if not user or not user.active:
            raise AppError("UNAUTHENTICATED", "session closed")
        require_member(db, user, project_id)
        from metis.core.access import can_read_page_revision

        for rid in candidate_revisions:
            if not can_read_page_revision(db, user, db.get(PageRevision, rid)):
                raise AppError("SOURCE_ACCESS_CHANGED", "source access changed during the answer; ask again")
        for c in state["citations"]:
            evidence_access(db, user, uuid.UUID(c["evidence_id"]))
            page = db.get(Page, uuid.UUID(c["page_id"]))
            if not page or page.deleted_at is not None or page.lifecycle != "active" or str(page.published_revision_id) != c["revision_id"] or page.freshness == "dependency_changed":
                state["decision"] = "VALIDATION_FAILED"
                state["citations"], state["explanation"] = [], []
                break
        if state["decision"] not in ("SUPPORTED", "PARTIAL"):
            state["citations"], state["explanation"] = [], []
        timings["total_ms"] = round((time.perf_counter() - started) * 1000, 2)
        answer = Answer(
            owner_id=user.id,
            project_id=project_id,
            question=req.question,
            scope=selector,
            level=req.level,
            decision=state["decision"],
            publication_id=publication_id,
            model_id=uuid.UUID(state["model"]["id"]) if state["model"] else None,
            prompt_version=prompts.EVIDENCE,
            explanation=[s.model_dump() for s in state["explanation"]],
            explanation_dropped=len(state["dropped"]) if state["citations"] else 0,
            timings=timings,
            detail={
                "related": [r.model_dump(mode="json") for r in state["related"]],
                "unknowns": state["unknowns"][:20],
                "conflict_sides": [c.model_dump(mode="json") for c in state["conflict_sides"]],
                "conflict_finding_id": str(state["conflict_finding_id"]) if state["conflict_finding_id"] else None,
                "needs_scope_dimensions": state["needs_scope_dimensions"],
                "model": state["model"],
                "model_unavailable_reason": state["model_unavailable_reason"],
                "alternatives": state["alternatives"],
                "dropped_sentences": state["dropped"],
                "selection": state["selection"],
                "error": state["error"],
                "explanation_dropped_all": bool(state["dropped"]) and not state["explanation"] and bool(state["citations"]),
                "related_passages": passages if state["decision"] == "MODEL_UNAVAILABLE" else [],
            },
        )
        db.add(answer)
        db.flush()
        for i, c in enumerate(state["citations"], start=1):
            db.add(AnswerCitation(answer_id=answer.id, ord=i, claim_id=uuid.UUID(c["claim_id"]), evidence_id=uuid.UUID(c["evidence_id"]), page_id=uuid.UUID(c["page_id"]), quote=c["statement"]))
        audit(db, user.id, "answer.complete", "answer", answer.id, decision=state["decision"], publication_id=publication_id, model_id=state["model"]["id"] if state["model"] else None)
        db.flush()
        out = answer_out(db, user, answer)
    emit("result", out.model_dump(mode="json"))
    return out


def answer_out(db: Session, user: User, answer: Answer) -> schemas.AnswerOut:
    cits = db.scalars(select(AnswerCitation).where(AnswerCitation.answer_id == answer.id).order_by(AnswerCitation.ord)).all()
    citations = []
    for c in cits:
        try:
            ev, _rev, src = evidence_access(db, user, c.evidence_id)
        except AppError:
            continue  # erişimi kalmayan kaynağın alıntısı gösterilmez
        page = db.get(Page, c.page_id) if c.page_id else None
        prev = db.get(PageRevision, page.published_revision_id) if page and page.published_revision_id else None
        citations.append(
            schemas.Citation(
                n=c.ord,
                claim_id=c.claim_id or uuid.UUID(int=0),
                evidence_id=c.evidence_id,
                page_id=c.page_id or uuid.UUID(int=0),
                page_title=prev.title if prev else "",
                quote=c.quote,
                source_title=src.title,
                locator_label=locator_label({k: v for k, v in ev.locator.items() if k != "auto"}),
                scope=prev.scope if prev else {},
            )
        )
    d = answer.detail or {}
    from metis.core.access import can_read_page_revision

    passages = [
        schemas.RelatedPassage(**{k: v for k, v in p.items() if k != "revision_id"})
        for p in d.get("related_passages", [])
        if can_read_page_revision(db, user, db.get(PageRevision, uuid.UUID(p["revision_id"])))
    ]
    return schemas.AnswerOut(
        id=answer.id,
        project_id=answer.project_id,
        question=answer.question,
        scope=answer.scope,
        level=answer.level,
        decision=answer.decision,  # type: ignore[arg-type]
        explanation=[schemas.Sentence(**s) for s in answer.explanation],
        citations=citations,
        related=[schemas.RelatedPage(**r) for r in d.get("related", [])],
        related_passages=passages,
        unknowns=d.get("unknowns", []),
        conflict_sides=[schemas.ConflictSide(**c) for c in d.get("conflict_sides", [])],
        conflict_finding_id=uuid.UUID(d["conflict_finding_id"]) if d.get("conflict_finding_id") else None,
        needs_scope_dimensions=d.get("needs_scope_dimensions", []),
        model=d.get("model"),
        model_unavailable_reason=d.get("model_unavailable_reason"),
        alternatives=d.get("alternatives", []),
        prompt_version=answer.prompt_version,
        publication_id=answer.publication_id,
        timings=answer.timings,
        explanation_dropped=answer.explanation_dropped,
        dropped_sentences=d.get("dropped_sentences", []),
        legacy=answer.legacy,
        created_at=answer.created_at,
    )


def get_answer(db: Session, user: User, answer_id: uuid.UUID) -> Answer:
    answer = db.get(Answer, answer_id)
    if not answer or answer.deleted_at is not None or answer.owner_id != user.id:
        raise AppError("NOT_FOUND", "answer not found")
    require_member(db, user, answer.project_id)
    return answer


def list_answers(db: Session, user: User, project_id: uuid.UUID) -> list[schemas.AnswerListItem]:
    require_member(db, user, project_id)
    rows = db.scalars(
        select(Answer).where(Answer.project_id == project_id, Answer.owner_id == user.id, Answer.deleted_at.is_(None)).order_by(Answer.created_at.desc()).limit(40)
    ).all()
    out = []
    for a in rows:
        # Silinen kayıtların mentor cevapları aktif görünümlerden kaybolur.
        cited_pages = db.scalars(select(AnswerCitation.page_id).where(AnswerCitation.answer_id == a.id)).all()
        if any((p := db.get(Page, pid)) is None or p.deleted_at is not None for pid in cited_pages if pid):
            continue
        out.append(schemas.AnswerListItem(id=a.id, question=a.question, decision=a.decision, created_at=a.created_at, legacy=a.legacy))
    return out


def delete_answer(db: Session, user: User, answer_id: uuid.UUID) -> None:
    answer = get_answer(db, user, answer_id)
    answer.deleted_at = utcnow()
    audit(db, user.id, "answer.delete", "answer", answer.id)


def feedback(db: Session, user: User, answer_id: uuid.UUID, data: schemas.FeedbackIn) -> None:
    answer = get_answer(db, user, answer_id)
    db.add(AnswerFeedback(answer_id=answer.id, user_id=user.id, rating=data.rating, comment=data.comment))
