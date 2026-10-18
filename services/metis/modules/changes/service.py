"""Değişiklik setleri: taslak → inceleme (hash'e bağlı) → atomik yayın; geri çekme, silme + geri al.

İnsan onayı ilkesi: onay, yayın, geri çekme ve silme yalnız `kind='human'` kullanıcılar içindir.
Worker (`metis-worker`) yalnız taslak oluşturabilir ve onu incelemeye gönderebilir.
"""

from __future__ import annotations

import difflib
import re
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from metis.core.access import can_read_page_revision, can_read_source, evidence_access, require_human, require_member
from metis.core.audit import audit
from metis.core.db import utcnow
from metis.core.errors import AppError
from metis.core.models import (
    ChangeSet,
    ChangeSetItem,
    ChangeSetRelation,
    Claim,
    ClaimEvidence,
    IdempotencyKey,
    Page,
    PageRevision,
    PageRevisionFigure,
    Project,
    Relation,
    RelationRevision,
    RelationRevisionEvidence,
    Review,
    Source,
    SourceRevision,
    User,
)
from metis.core.util import hash_json
from metis.modules.changes import schemas
from metis.modules.knowledge import publish as publisher
from metis.modules.knowledge.figures import figure_refs
from metis.modules.knowledge.views import RevisionView, revision_views
from metis.modules.scopes.semantics import DIMENSIONS, WILDCARD, canonical, normalize_scope, same_scope
from metis.modules.scopes.service import lock_project, validate_selection

OPEN_STATES = ("draft", "in_review", "approved")


# ---------------------------------------------------------------- yardımcılar


def scope_covers(source_scope: dict, page_scope: dict) -> bool:
    """Sayfa, kaynağının desteklediğinden daha geniş bir uygulanabilirlik iddia edemez."""
    src, page = canonical(source_scope), canonical(page_scope)
    for dim in DIMENSIONS:
        want = page[dim]
        if not want:
            continue
        have = src[dim]
        if WILDCARD in have:
            continue
        if WILDCARD in want or not set(want) <= set(have):
            return False
    return True


def revision_hash(data: dict) -> str:
    return hash_json(data)


def compute_change_hash(db: Session, change: ChangeSet) -> str:
    items = db.scalars(
        select(ChangeSetItem).where(ChangeSetItem.change_set_id == change.id).order_by(ChangeSetItem.page_id)
    ).all()
    rels = db.scalars(
        select(ChangeSetRelation)
        .where(ChangeSetRelation.change_set_id == change.id)
        .order_by(ChangeSetRelation.relation_id)
    ).all()
    payload = {
        "kind": change.kind,
        "items": [
            {
                "page": i.page_id,
                "base": i.base_revision_id,
                "action": i.action,
                "proposed": i.proposed_revision_id,
                "hash": db.get(PageRevision, i.proposed_revision_id).hash if i.proposed_revision_id else None,
            }
            for i in items
        ],
        "relations": [
            {
                "relation": r.relation_id,
                "base": r.base_revision_id,
                "proposed": r.proposed_revision_id,
                "action": r.action,
            }
            for r in rels
        ],
    }
    return hash_json(payload)


def _origin_people(db: Session, change: ChangeSet) -> tuple[str, str | None]:
    author = db.get(User, change.author_id)
    requester = db.get(User, change.requester_id) if change.requester_id else None
    return (author.display_name if author else ""), (requester.display_name if requester else None)


def _items(db: Session, change: ChangeSet) -> list[ChangeSetItem]:
    return list(
        db.scalars(select(ChangeSetItem).where(ChangeSetItem.change_set_id == change.id).order_by(ChangeSetItem.id))
    )


def _change_title(db: Session, change: ChangeSet, items: list[ChangeSetItem]) -> str:
    for item in items:
        rid = item.proposed_revision_id or item.base_revision_id
        if rid:
            rev = db.get(PageRevision, rid)
            if rev:
                return rev.title
    return change.summary[:120] or "Kayıt"


def accessible_change(db: Session, user: User, change_id: uuid.UUID, include_deleted: bool = False) -> ChangeSet:
    change = db.get(ChangeSet, change_id)
    if not change or (change.deleted_at is not None and not include_deleted):
        raise AppError("NOT_FOUND", "record not found")
    require_member(db, user, change.project_id)
    for item in _items(db, change):
        for rid in (item.proposed_revision_id, item.base_revision_id):
            if rid and not can_read_page_revision(db, user, db.get(PageRevision, rid)):
                raise AppError("NOT_FOUND", "record not found")
    return change


# ---------------------------------------------------------------- doğrulama ve yazma


def _validate_evidence(
    db: Session, actor: User, project_id: uuid.UUID, refs: list[schemas.EvidenceRef], page_scope: dict | None
) -> None:
    for ref in refs:
        ev, rev, src = evidence_access(db, actor, ref.evidence_id)
        if src.project_id != project_id:
            raise AppError("SCOPE_MISMATCH", "evidence belongs to another project")
        if ref.quote not in ev.excerpt:
            raise AppError("QUOTE_NOT_IN_EVIDENCE", "quote not found verbatim in evidence", evidence_id=str(ev.id))
        if page_scope is not None and not scope_covers(rev.scope, page_scope):
            raise AppError("SCOPE_MISMATCH", "page scope is broader than the source scope", source=src.title)


def _validate_item(db: Session, actor: User, project_id: uuid.UUID, item: schemas.ItemIn) -> tuple[Page | None, dict]:
    page = None
    if item.page_id:
        page = db.get(Page, item.page_id)
        if not page or page.project_id != project_id or page.deleted_at is not None:
            raise AppError("NOT_FOUND", "page not found")
        if page.published_revision_id and not can_read_page_revision(
            db, actor, db.get(PageRevision, page.published_revision_id)
        ):
            raise AppError("NOT_FOUND", "page not found")
        if item.base_revision_id != page.published_revision_id:
            raise AppError(
                "REVISION_CONFLICT",
                "page changed while you were editing",
                page_id=str(page.id),
                expected_revision_id=str(item.base_revision_id) if item.base_revision_id else None,
                current_revision_id=str(page.published_revision_id) if page.published_revision_id else None,
            )
        if page.lifecycle == "withdrawn" and item.action == "upsert" and page.published_revision_id is None:
            raise AppError("WITHDRAWN", "withdrawn page; create a new page")
    elif item.action == "withdraw":
        raise AppError("VALIDATION_ERROR", "withdraw requires page_id")
    if item.action == "withdraw":
        return page, {}
    if not item.title.strip():
        raise AppError("VALIDATION_ERROR", "title required", fields=[{"field": "title", "type": "missing"}])
    scope = validate_selection(db, project_id, item.scope.model_dump())
    for claim in item.claims:
        if not claim.evidence:
            raise AppError(
                "CLAIM_EVIDENCE", "every claim needs at least one evidence quote", claim=claim.statement[:80]
            )
        _validate_evidence(db, actor, project_id, claim.evidence, scope)
    _validate_figures(db, actor, project_id, item)
    return page, scope


def _validate_figures(db: Session, actor: User, project_id: uuid.UUID, item: schemas.ItemIn) -> None:
    """Görsel: projedeki, okunabilir bir görsel kaynak revizyonu; gövdedeki `{{görsel N}}` satırları var olan sıraya işaret eder."""
    for fig in item.figures:
        rev = db.get(SourceRevision, fig.source_revision_id)
        src = db.get(Source, rev.source_id) if rev else None
        if not rev or not src or src.project_id != project_id or not can_read_source(db, actor, src):
            raise AppError("NOT_FOUND", "figure source not found")
        if not rev.media_type.startswith("image/"):
            raise AppError("FIGURE_NOT_IMAGE", "figure source is not an image", source=src.title)
    for n in figure_refs(item.body_md):
        if not 1 <= n <= len(item.figures):
            raise AppError("FIGURE_MISSING", "body refers to a figure that does not exist", figure=n)


def _write_revision(
    db: Session, author: User, project_id: uuid.UUID, page: Page | None, item: schemas.ItemIn, scope: dict
) -> tuple[Page, PageRevision]:
    if page is None:
        page = Page(project_id=project_id, kind=item.kind, owner_id=author.id, current_revision_no=0)
        db.add(page)
        db.flush()
    page.current_revision_no += 1
    claims_payload = [
        {
            "statement": c.statement.strip(),
            "kind": c.kind,
            "support": c.support,
            "evidence": sorted(
                [{"evidence_id": str(e.evidence_id), "quote": e.quote} for e in c.evidence],
                key=lambda x: (x["evidence_id"], x["quote"]),
            ),
        }
        for c in item.claims
    ]
    content = {
        "title": item.title.strip(),
        "summary": item.summary.strip(),
        "body_md": item.body_md,
        "kind": item.kind,
        "scope": normalize_scope(scope),
        "unknowns": [u.strip() for u in item.unknowns if u.strip()],
        "aliases": [a.strip() for a in item.aliases if a.strip()],
        "claims": claims_payload,
    }
    if item.figures:  # görselsiz revizyonların hash'i değişmesin (eski onaylar geçerli kalır)
        content["figures"] = [{"source_revision_id": str(f.source_revision_id), "caption": f.caption.strip()} for f in item.figures]
    rev = PageRevision(
        page_id=page.id,
        number=page.current_revision_no,
        title=content["title"],
        summary=content["summary"],
        body_md=content["body_md"],
        kind=item.kind,
        scope=content["scope"],
        unknowns=content["unknowns"],
        aliases=content["aliases"],
        author_id=author.id,
        hash=revision_hash(content),
    )
    db.add(rev)
    db.flush()
    for ord_, (claim, payload) in enumerate(zip(item.claims, claims_payload, strict=True), start=1):
        row = Claim(
            page_revision_id=rev.id, ord=ord_, statement=payload["statement"], kind=claim.kind, support=claim.support
        )
        db.add(row)
        db.flush()
        seen = set()
        for e in claim.evidence:
            if e.evidence_id in seen:
                continue
            seen.add(e.evidence_id)
            db.add(ClaimEvidence(claim_id=row.id, evidence_id=e.evidence_id, quote=e.quote))
    for ord_, fig in enumerate(item.figures, start=1):
        db.add(
            PageRevisionFigure(
                page_revision_id=rev.id, ord=ord_, source_revision_id=fig.source_revision_id, caption=fig.caption.strip()
            )
        )
    db.flush()
    return page, rev


def _write_relation(db: Session, author: User, actor: User, change: ChangeSet, rel: schemas.RelationIn) -> None:
    pages = []
    for pid in (rel.subject_page_id, rel.object_page_id):
        page = db.get(Page, pid)
        if (
            not page
            or page.project_id != change.project_id
            or page.deleted_at is not None
            or not page.published_revision_id
            or not can_read_page_revision(db, actor, db.get(PageRevision, page.published_revision_id))
        ):
            raise AppError("NOT_FOUND", "relation page not found")
        pages.append(page)
    if rel.subject_page_id == rel.object_page_id:
        raise AppError("VALIDATION_ERROR", "a page cannot relate to itself")
    _validate_evidence(db, actor, change.project_id, rel.evidence, None)
    relation = db.get(Relation, rel.relation_id) if rel.relation_id else None
    if rel.relation_id and (not relation or relation.project_id != change.project_id):
        raise AppError("NOT_FOUND", "relation not found")
    if relation is None:
        relation = Relation(project_id=change.project_id)
        db.add(relation)
        db.flush()
    relation.current_revision_no += 1
    subject_rev = db.get(PageRevision, pages[0].published_revision_id)
    rr = RelationRevision(
        relation_id=relation.id,
        number=relation.current_revision_no,
        subject_page_id=rel.subject_page_id,
        predicate=rel.predicate,
        object_page_id=rel.object_page_id,
        scope=subject_rev.scope if subject_rev else {},
        rationale=rel.rationale,
        review_state="proposed",
        author_id=author.id,
    )
    db.add(rr)
    db.flush()
    for e in rel.evidence:
        db.add(RelationRevisionEvidence(relation_revision_id=rr.id, evidence_id=e.evidence_id, quote=e.quote))
    db.add(
        ChangeSetRelation(
            change_set_id=change.id,
            relation_id=relation.id,
            base_revision_id=relation.published_revision_id,
            proposed_revision_id=rr.id if rel.action == "upsert" else None,
            action=rel.action,
        )
    )


def _write_contents(
    db: Session,
    author: User,
    actor: User,
    change: ChangeSet,
    items: list[schemas.ItemIn],
    relations: list[schemas.RelationIn],
) -> None:
    seen: set[uuid.UUID] = set()
    for item in items:
        page, scope = _validate_item(db, actor, change.project_id, item)
        if page and page.id in seen:
            raise AppError("VALIDATION_ERROR", "a page may appear only once")
        if item.action == "withdraw":
            assert page is not None
            db.add(
                ChangeSetItem(
                    change_set_id=change.id,
                    page_id=page.id,
                    base_revision_id=page.published_revision_id,
                    proposed_revision_id=None,
                    action="withdraw",
                )
            )
            seen.add(page.id)
            continue
        page, rev = _write_revision(db, author, change.project_id, page, item, scope)
        seen.add(page.id)
        db.add(
            ChangeSetItem(
                change_set_id=change.id,
                page_id=page.id,
                base_revision_id=item.base_revision_id,
                base_revision_no=db.get(PageRevision, item.base_revision_id).number if item.base_revision_id else 0,
                proposed_revision_id=rev.id,
                action="upsert",
            )
        )
    for rel in relations:
        _write_relation(db, author, actor, change, rel)
    db.flush()
    change.hash = compute_change_hash(db, change)
    change.updated_at = utcnow()


def create_change(
    db: Session,
    author: User,
    project_id: uuid.UUID,
    data: schemas.ChangeCreateIn,
    *,
    requester: User | None = None,
    job_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
    kind: str = "edit",
) -> ChangeSet:
    actor = requester or author
    require_member(db, actor, project_id, ["contributor"])
    if author.kind == "worker" and requester is None:
        raise AppError("FORBIDDEN", "worker changes need a requester")
    if author.kind == "human" and requester is not None:
        raise AppError("FORBIDDEN", "requester only for worker changes")
    lock_project(db, project_id)
    payload_hash = hash_json({"project": project_id, "data": data.model_dump(mode="json"), "job": job_id})
    if idempotency_key:
        prev = db.get(IdempotencyKey, (author.id, idempotency_key[:200]))
        if prev:
            if prev.payload_hash != payload_hash:
                raise AppError("IDEMPOTENCY_CONFLICT", "idempotency key reused with different payload")
            existing = db.get(ChangeSet, uuid.UUID(prev.result_ref))
            if not existing or existing.deleted_at is not None:
                raise AppError("NOT_FOUND", "record deleted")
            return existing
    if not data.items and not data.relations:
        raise AppError("VALIDATION_ERROR", "record needs at least one page or relation")
    change = ChangeSet(
        project_id=project_id,
        author_id=author.id,
        requester_id=requester.id if requester else None,
        origin="metis" if author.kind == "worker" else "human",
        job_id=job_id,
        kind=kind,
        summary=data.summary.strip(),
        state="draft",
        source_answer_id=data.source_answer_id,
    )
    if data.predecessor_id:
        pred = accessible_change(db, actor, data.predecessor_id)
        if pred.project_id != project_id:
            raise AppError("VALIDATION_ERROR", "predecessor in another project")
        change.predecessor_id = pred.id
    db.add(change)
    db.flush()
    _write_contents(db, author, actor, change, data.items, data.relations)
    if idempotency_key:
        db.add(
            IdempotencyKey(
                user_id=author.id, key=idempotency_key[:200], payload_hash=payload_hash, result_ref=str(change.id)
            )
        )
    if data.predecessor_id:
        pred = db.get(ChangeSet, data.predecessor_id)
        if pred and pred.state in OPEN_STATES:
            pred.state = "superseded"
            pred.detail = {**pred.detail, "successor_id": str(change.id)}
    audit(
        db,
        author.id,
        "change.create",
        "change_set",
        change.id,
        hash=change.hash,
        origin=change.origin,
        job_id=job_id,
        requester_id=actor.id,
    )
    if data.submit:
        _submit(db, author, change)
    return change


def update_change(db: Session, user: User, change_id: uuid.UUID, data: schemas.ChangeUpdateIn) -> ChangeSet:
    require_human(user)
    change = accessible_change(db, user, change_id)
    lock_project(db, change.project_id)
    db.refresh(change, with_for_update=True)
    if not _can_edit(db, user, change):
        raise AppError("INVALID_STATE", "only drafts can be edited by their author or a steward")
    if change.hash != data.expected_hash:
        raise AppError("REVISION_CONFLICT", "record changed while you were editing", current_hash=change.hash)
    # Eski önerilen revizyonlar değişmez kalır; yeni revizyonlar yazılır.
    for item in _items(db, change):
        db.delete(item)
    for rel in db.scalars(select(ChangeSetRelation).where(ChangeSetRelation.change_set_id == change.id)):
        db.delete(rel)
    db.flush()
    change.summary = data.summary.strip()
    _write_contents(db, user, user, change, data.items, data.relations)
    audit(db, user.id, "change.update", "change_set", change.id, hash=change.hash)
    return change


def _submit(db: Session, actor: User, change: ChangeSet) -> None:
    if change.state != "draft":
        raise AppError("INVALID_STATE", "only drafts can be submitted")
    change.state = "in_review"
    change.submitted_at = utcnow()
    change.updated_at = utcnow()
    audit(db, actor.id, "change.submit", "change_set", change.id, hash=change.hash)


def submit(db: Session, user: User, change_id: uuid.UUID) -> ChangeSet:
    require_human(user)
    change = accessible_change(db, user, change_id)
    lock_project(db, change.project_id)
    if not _can_edit(db, user, change):
        raise AppError("ROLE_REQUIRED", "only the author or a steward can submit")
    _submit(db, user, change)
    return change


# ---------------------------------------------------------------- izinler ve kontroller


def _roles(db: Session, user: User, change: ChangeSet) -> set[str]:
    from metis.core.access import effective_roles

    return effective_roles(db, user, change.project_id)


def _is_owner(user: User, change: ChangeSet) -> bool:
    return user.id in (change.author_id, change.requester_id)


def _can_edit(db: Session, user: User, change: ChangeSet) -> bool:
    if user.kind != "human" or change.state != "draft" or change.deleted_at is not None:
        return False
    roles = _roles(db, user, change)
    return (_is_owner(user, change) and "contributor" in roles) or "steward" in roles


def _can_delete(db: Session, user: User, change: ChangeSet) -> bool:
    if user.kind != "human" or change.deleted_at is not None:
        return False
    roles = _roles(db, user, change)
    if roles & {"reviewer", "steward"}:
        return True
    return change.state == "draft" and "contributor" in roles and _is_owner(user, change)


def approve_blockers(db: Session, user: User, change: ChangeSet) -> list[str]:
    blockers = []
    project = db.get(Project, change.project_id)
    assert project is not None
    if change.state != "in_review":
        blockers.append("not_in_review")
    if project.review_policy == "independent" and _is_owner(user, change):
        blockers.append("self_review")
    if "reviewer" not in _roles(db, user, change) or user.kind != "human":
        blockers.append("role")
    for item in _items(db, change):
        page = db.get(Page, item.page_id)
        if page and item.base_revision_id != page.published_revision_id:
            blockers.append("base_outdated")
        if item.action == "upsert" and item.proposed_revision_id:
            claims = db.scalars(select(Claim).where(Claim.page_revision_id == item.proposed_revision_id)).all()
            if not claims:
                blockers.append("no_claims")
            for claim in claims:
                links = db.scalars(select(ClaimEvidence).where(ClaimEvidence.claim_id == claim.id)).all()
                if not links:
                    blockers.append("claim_without_evidence")
                for link in links:
                    try:
                        evidence_access(db, user, link.evidence_id)
                    except AppError:
                        blockers.append("evidence_unavailable")
    return list(dict.fromkeys(blockers))


def _valid_approval(db: Session, change: ChangeSet) -> Review | None:
    return db.scalar(
        select(Review)
        .where(Review.change_set_id == change.id, Review.hash == change.hash, Review.decision == "approve")
        .order_by(Review.created_at.desc())
        .limit(1)
    )


# ---------------------------------------------------------------- inceleme ve yayın


def review(db: Session, user: User, change_id: uuid.UUID, data: schemas.ReviewIn) -> ChangeSet:
    require_human(user)
    change = accessible_change(db, user, change_id)
    require_member(db, user, change.project_id, ["reviewer"])
    project = lock_project(db, change.project_id)
    db.refresh(change, with_for_update=True)
    if data.hash != change.hash:
        raise AppError("HASH_MISMATCH", "record content changed after you opened it", current_hash=change.hash)
    if change.state != "in_review":
        raise AppError("INVALID_STATE", "record is not in review", state=change.state)
    if data.decision == "approve":
        if project.review_policy == "independent" and _is_owner(user, change):
            raise AppError("SELF_REVIEW_FORBIDDEN", "independent review policy: you cannot approve your own record")
        if not data.evidence_checked:
            raise AppError("REVIEW_CHECK_REQUIRED", "confirm claims and evidence were checked")
        blockers = [b for b in approve_blockers(db, user, change) if b not in ("self_review",)]
        if blockers:
            if "base_outdated" in blockers:
                raise AppError("REVISION_CONFLICT", "record is based on an outdated revision", blockers=blockers)
            raise AppError("EVIDENCE_REQUIRED", "record does not satisfy approval checks", blockers=blockers)
    elif not data.reason.strip():
        raise AppError(
            "REASON_REQUIRED", "reason required for this decision", fields=[{"field": "reason", "type": "missing"}]
        )
    policy = "owner_review" if (project.review_policy == "owner_review" and _is_owner(user, change)) else "independent"
    db.add(
        Review(
            change_set_id=change.id,
            hash=change.hash,
            reviewer_id=user.id,
            decision=data.decision,
            reason=data.reason.strip(),
            evidence_checked=data.evidence_checked,
            policy=policy,
        )
    )
    change.state = {"approve": "approved", "request_changes": "draft", "reject": "rejected"}[data.decision]
    change.updated_at = utcnow()
    audit(
        db, user.id, "change.review", "change_set", change.id, decision=data.decision, hash=change.hash, policy=policy
    )
    return change


def publish_change(db: Session, user: User, change_id: uuid.UUID) -> ChangeSet:
    require_human(user)
    change = accessible_change(db, user, change_id)
    require_member(db, user, change.project_id, ["reviewer", "steward"])
    project = lock_project(db, change.project_id)
    db.refresh(change, with_for_update=True)
    if change.state != "approved":
        raise AppError("INVALID_STATE", "record must be approved before publishing", state=change.state)
    current_hash = compute_change_hash(db, change)
    if current_hash != change.hash or not _valid_approval(db, change):
        raise AppError("HASH_MISMATCH", "approval does not match current content; review again")
    upserts: dict[uuid.UUID, uuid.UUID] = {}
    removals: set[uuid.UUID] = set()
    for item in _items(db, change):
        page = db.get(Page, item.page_id)
        assert page is not None
        db.refresh(page, with_for_update=True)
        if page.deleted_at is not None:
            raise AppError("DELETED_REFERENCE", "page was deleted")
        if item.base_revision_id != page.published_revision_id:
            raise AppError(
                "REVISION_CONFLICT", "page was published by another record; rebase this record", page_id=str(page.id)
            )
        if item.action == "withdraw":
            removals.add(page.id)
        else:
            assert item.proposed_revision_id is not None
            for link in db.scalars(
                select(ClaimEvidence)
                .join(Claim, Claim.id == ClaimEvidence.claim_id)
                .where(Claim.page_revision_id == item.proposed_revision_id)
            ):
                evidence_access(db, user, link.evidence_id)
            upserts[page.id] = item.proposed_revision_id
    rel_up: dict[uuid.UUID, uuid.UUID] = {}
    rel_rm: set[uuid.UUID] = set()
    for rel in db.scalars(select(ChangeSetRelation).where(ChangeSetRelation.change_set_id == change.id)):
        if rel.action == "remove":
            rel_rm.add(rel.relation_id)
        elif rel.proposed_revision_id:
            rel_up[rel.relation_id] = rel.proposed_revision_id
    pub = publisher.publish(
        db,
        project,
        actor_id=user.id,
        change_set_id=change.id,
        kind="publish",
        upserts=upserts,
        removals=removals,
        relation_upserts=rel_up,
        relation_removals=rel_rm,
    )
    change.state = "published"
    change.published_at = utcnow()
    change.updated_at = utcnow()
    from metis.modules.health.service import auto_resolve_on_publish

    auto_resolve_on_publish(db, user, change, set(upserts))
    audit(
        db,
        user.id,
        "change.publish",
        "change_set",
        change.id,
        publication_id=pub.id,
        hash=change.hash,
        pages=list(upserts),
        removed=list(removals),
    )
    return change


def rebase(db: Session, user: User, change_id: uuid.UUID) -> ChangeSet:
    """Eski tabana dayanan taslağı güncel yayına göre yeni bir kayıt olarak yeniden temellendir."""
    require_human(user)
    change = accessible_change(db, user, change_id)
    if change.state not in OPEN_STATES and change.state != "rejected":
        raise AppError("INVALID_STATE", "only open records can be rebased")
    if not (_is_owner(user, change) or "steward" in _roles(db, user, change)):
        raise AppError("ROLE_REQUIRED", "only the author or a steward can rebase")
    items = []
    views = revision_views(
        db, [db.get(PageRevision, i.proposed_revision_id) for i in _items(db, change) if i.proposed_revision_id]
    )
    for item in _items(db, change):
        page = db.get(Page, item.page_id)
        assert page is not None
        if item.action == "withdraw":
            items.append(
                schemas.ItemIn(page_id=page.id, base_revision_id=page.published_revision_id, action="withdraw")
            )
            continue
        v = views[item.proposed_revision_id]
        items.append(
            schemas.ItemIn(
                page_id=page.id if page.published_revision_id or item.base_revision_id else None,
                base_revision_id=page.published_revision_id
                if (page.published_revision_id or item.base_revision_id)
                else None,
                title=v.title,
                summary=v.summary,
                body_md=v.body_md,
                kind=v.kind,  # type: ignore[arg-type]
                scope=v.scope,  # type: ignore[arg-type]
                unknowns=v.unknowns,
                aliases=v.aliases,
                claims=[
                    schemas.ClaimIn(
                        statement=c.statement,
                        kind=c.kind,  # type: ignore[arg-type]
                        support=c.support,  # type: ignore[arg-type]
                        evidence=[schemas.EvidenceRef(evidence_id=e.evidence_id, quote=e.quote) for e in c.evidence],
                    )
                    for c in v.claims
                ],
            )
        )
    new = create_change(
        db,
        user,
        change.project_id,
        schemas.ChangeCreateIn(summary=change.summary, items=items, predecessor_id=change.id),
    )
    return new


# ---------------------------------------------------------------- geri çekme, silme, geri al


def withdraw_page(db: Session, user: User, page_id: uuid.UUID, reason: str) -> ChangeSet:
    require_human(user)
    page = db.get(Page, page_id)
    if not page or page.deleted_at is not None or not page.published_revision_id:
        raise AppError("NOT_FOUND", "page not found")
    if not can_read_page_revision(db, user, db.get(PageRevision, page.published_revision_id)):
        raise AppError("NOT_FOUND", "page not found")
    require_member(db, user, page.project_id, ["reviewer", "steward"])
    project = lock_project(db, page.project_id)
    change = ChangeSet(
        project_id=page.project_id,
        author_id=user.id,
        origin="human",
        kind="withdrawal",
        summary=reason.strip(),
        state="approved",
    )
    db.add(change)
    db.flush()
    db.add(
        ChangeSetItem(
            change_set_id=change.id, page_id=page.id, base_revision_id=page.published_revision_id, action="withdraw"
        )
    )
    db.flush()
    change.hash = compute_change_hash(db, change)
    db.add(
        Review(
            change_set_id=change.id,
            hash=change.hash,
            reviewer_id=user.id,
            decision="approve",
            reason=reason.strip(),
            evidence_checked=True,
            policy="direct_withdrawal",
        )
    )
    pub = publisher.publish(db, project, actor_id=user.id, change_set_id=change.id, kind="withdraw", removals={page.id})
    change.state = "published"
    change.published_at = utcnow()
    audit(
        db, user.id, "page.withdraw", "page", page.id, reason=reason.strip(), publication_id=pub.id, change_id=change.id
    )
    return change


def delete_change(db: Session, user: User, change_id: uuid.UUID) -> dict:
    require_human(user)
    change = accessible_change(db, user, change_id)
    if not _can_delete(db, user, change):
        raise AppError("ROLE_REQUIRED", "you cannot delete this record")
    project = lock_project(db, change.project_id)
    pruned: dict[str, str] = {}
    if change.state == "published":
        removals = set()
        for item in _items(db, change):
            page = db.get(Page, item.page_id)
            if (
                page
                and item.proposed_revision_id
                and page.published_revision_id == item.proposed_revision_id
                and page.lifecycle == "active"
            ):
                removals.add(page.id)
                pruned[str(page.id)] = str(item.proposed_revision_id)
        if removals:
            publisher.publish(db, project, actor_id=user.id, change_set_id=change.id, kind="prune", removals=removals)
    # Yalnız bu kayıtla oluşmuş (hiç başka kayıtta geçmeyen) sayfalar da silinmiş sayılır.
    deleted_pages = []
    for item in _items(db, change):
        others = db.scalar(
            select(func.count())
            .select_from(ChangeSetItem)
            .join(ChangeSet, ChangeSet.id == ChangeSetItem.change_set_id)
            .where(ChangeSetItem.page_id == item.page_id, ChangeSet.id != change.id, ChangeSet.deleted_at.is_(None))
        )
        page = db.get(Page, item.page_id)
        if page and not others and page.deleted_at is None:
            page.deleted_at = utcnow()
            page.deleted_by = user.id
            deleted_pages.append(str(page.id))
    change.deleted_at = utcnow()
    change.deleted_by = user.id
    change.detail = {**change.detail, "pruned": pruned, "deleted_pages": deleted_pages}
    audit(db, user.id, "change.delete", "change_set", change.id, pruned=pruned, deleted_pages=deleted_pages)
    return {"pruned_pages": list(pruned), "deleted_pages": deleted_pages}


def restore_change(db: Session, user: User, change_id: uuid.UUID) -> ChangeSet:
    require_human(user)
    change = db.get(ChangeSet, change_id)
    if not change or change.deleted_at is None:
        raise AppError("NOT_FOUND", "record not found")
    require_member(db, user, change.project_id)
    if not (change.deleted_by == user.id or "steward" in _roles(db, user, change)):
        raise AppError("ROLE_REQUIRED", "only the person who deleted or a steward can restore")
    project = lock_project(db, change.project_id)
    for pid in change.detail.get("deleted_pages", []):
        page = db.get(Page, uuid.UUID(pid))
        if page:
            page.deleted_at = None
            page.deleted_by = None
    upserts = {}
    for pid, rid in change.detail.get("pruned", {}).items():
        page = db.get(Page, uuid.UUID(pid))
        if page and page.lifecycle == "withdrawn" and page.published_revision_id == uuid.UUID(rid):
            upserts[page.id] = uuid.UUID(rid)
    change.deleted_at = None
    change.deleted_by = None
    if upserts:
        publisher.publish(db, project, actor_id=user.id, change_set_id=change.id, kind="restore", upserts=upserts)
    audit(db, user.id, "change.restore", "change_set", change.id, republished=list(upserts))
    return change


def delete_page(db: Session, user: User, page_id: uuid.UUID) -> dict:
    """Bilgi havuzundan doğrudan 'Bilgiyi sil'."""
    require_human(user)
    page = db.get(Page, page_id)
    if not page or page.deleted_at is not None:
        raise AppError("NOT_FOUND", "page not found")
    if page.published_revision_id and not can_read_page_revision(
        db, user, db.get(PageRevision, page.published_revision_id)
    ):
        raise AppError("NOT_FOUND", "page not found")
    require_member(db, user, page.project_id, ["reviewer", "steward"])
    project = lock_project(db, page.project_id)
    was_active = page.lifecycle == "active" and page.published_revision_id is not None
    if was_active:
        publisher.publish(db, project, actor_id=user.id, change_set_id=None, kind="prune", removals={page.id})
    page.deleted_at = utcnow()
    page.deleted_by = user.id
    audit(db, user.id, "page.delete", "page", page.id, was_active=was_active, revision_id=page.published_revision_id)
    return {"was_active": was_active}


def restore_page(db: Session, user: User, page_id: uuid.UUID) -> None:
    require_human(user)
    page = db.get(Page, page_id)
    if not page or page.deleted_at is None:
        raise AppError("NOT_FOUND", "page not found")
    require_member(db, user, page.project_id, ["reviewer", "steward"])
    project = lock_project(db, page.project_id)
    page.deleted_at = None
    page.deleted_by = None
    if page.published_revision_id and page.lifecycle == "withdrawn":
        publisher.publish(
            db,
            project,
            actor_id=user.id,
            change_set_id=None,
            kind="restore",
            upserts={page.id: page.published_revision_id},
        )
    audit(db, user.id, "page.restore", "page", page.id)


# ---------------------------------------------------------------- görünümler


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().casefold())


def claim_diff(before: RevisionView | None, after: RevisionView | None) -> list[schemas.ClaimDiff]:
    old = list(before.claims) if before else []
    new = list(after.claims) if after else []
    out: list[schemas.ClaimDiff] = []
    used_old: set[int] = set()
    pairs: dict[int, int] = {}
    for j, c in enumerate(new):
        for i, o in enumerate(old):
            if i not in used_old and _norm(o.statement) == _norm(c.statement):
                pairs[j] = i
                used_old.add(i)
                break
    for j, c in enumerate(new):
        if j in pairs:
            continue
        best, best_score = None, 0.0
        for i, o in enumerate(old):
            if i in used_old:
                continue
            score = difflib.SequenceMatcher(None, _norm(o.statement), _norm(c.statement)).ratio()
            shared = {e.evidence_id for e in o.evidence} & {e.evidence_id for e in c.evidence}
            if shared:
                score += 0.2
            if score > best_score:
                best, best_score = i, score
        if best is not None and best_score >= 0.6:
            pairs[j] = best
            used_old.add(best)
    for j, c in enumerate(new):
        if j in pairs:
            o = old[pairs[j]]
            status = "unchanged" if _norm(o.statement) == _norm(c.statement) else "changed"
            out.append(
                schemas.ClaimDiff(
                    status=status,
                    before=o.statement,
                    after=c.statement,
                    before_ord=o.ord,
                    after_ord=c.ord,
                    claim_id=c.id,
                )
            )
        else:
            out.append(
                schemas.ClaimDiff(
                    status="added", before=None, after=c.statement, before_ord=None, after_ord=c.ord, claim_id=c.id
                )
            )
    for i, o in enumerate(old):
        if i not in used_old:
            out.append(
                schemas.ClaimDiff(
                    status="removed", before=o.statement, after=None, before_ord=o.ord, after_ord=None, claim_id=o.id
                )
            )
    return out


def change_out(db: Session, change: ChangeSet) -> schemas.ChangeOut:
    items = _items(db, change)
    author, requester = _origin_people(db, change)
    counts = {"pages": len(items), "added": 0, "changed": 0, "removed": 0}
    return schemas.ChangeOut(
        id=change.id,
        project_id=change.project_id,
        title=_change_title(db, change, items),
        summary=change.summary,
        state=change.state,
        origin=change.origin,  # type: ignore[arg-type]
        kind=change.kind,
        author_id=change.author_id,
        author_name=author,
        requester_id=change.requester_id,
        requester_name=requester,
        job_id=change.job_id,
        hash=change.hash,
        created_at=change.created_at,
        updated_at=change.updated_at,
        published_at=change.published_at,
        page_ids=[i.page_id for i in items],
        counts=counts,
    )


def change_detail(db: Session, user: User, change_id: uuid.UUID) -> schemas.ChangeDetailOut:
    change = accessible_change(db, user, change_id)
    project = db.get(Project, change.project_id)
    assert project is not None
    items = _items(db, change)
    revs = [db.get(PageRevision, rid) for i in items for rid in (i.base_revision_id, i.proposed_revision_id) if rid]
    views = revision_views(db, [r for r in revs if r])
    item_views = []
    totals = {"added": 0, "changed": 0, "removed": 0}
    for item in items:
        page = db.get(Page, item.page_id)
        base = views.get(item.base_revision_id) if item.base_revision_id else None
        proposed = views.get(item.proposed_revision_id) if item.proposed_revision_id else None
        diff = claim_diff(base, proposed if item.action == "upsert" else None)
        counts = {k: sum(1 for d in diff if d.status == k) for k in ("added", "changed", "removed", "unchanged")}
        for k in totals:
            totals[k] += counts[k]
        checks = []
        if proposed and not proposed.claims:
            checks.append("no_claims")
        if proposed and any(not c.evidence for c in proposed.claims):
            checks.append("claim_without_evidence")
        if proposed and any(not c.verbatim for c in proposed.claims):
            checks.append("claim_not_verbatim")
        if proposed and any(not e.source_is_current for c in proposed.claims for e in c.evidence):
            checks.append("source_not_current")
        item_views.append(
            schemas.ItemView(
                id=item.id,
                page_id=item.page_id,
                action=item.action,
                base=base,
                proposed=proposed,
                base_is_current=bool(page) and item.base_revision_id == page.published_revision_id,
                current_published_revision_id=page.published_revision_id if page else None,
                claim_diff=diff,
                summary_counts=counts,
                scope_changed=bool(base and proposed and not same_scope(base.scope, proposed.scope)),
                checks=checks,
            )
        )
    rel_views = []
    for rel in db.scalars(select(ChangeSetRelation).where(ChangeSetRelation.change_set_id == change.id)):
        rr = (
            db.get(RelationRevision, rel.proposed_revision_id or rel.base_revision_id)
            if (rel.proposed_revision_id or rel.base_revision_id)
            else None
        )
        if not rr:
            continue
        titles = {}
        for pid in (rr.subject_page_id, rr.object_page_id):
            page = db.get(Page, pid)
            prev = db.get(PageRevision, page.published_revision_id) if page and page.published_revision_id else None
            titles[pid] = prev.title if prev else ""
        rel_views.append(
            schemas.RelationView(
                relation_id=rel.relation_id,
                action=rel.action,
                subject_page_id=rr.subject_page_id,
                subject_title=titles[rr.subject_page_id],
                predicate=rr.predicate,
                object_page_id=rr.object_page_id,
                object_title=titles[rr.object_page_id],
                rationale=rr.rationale,
            )
        )
    reviews = db.scalars(select(Review).where(Review.change_set_id == change.id).order_by(Review.created_at)).all()
    names = {
        u.id: u.display_name
        for u in db.scalars(select(User).where(User.id.in_({r.reviewer_id for r in reviews} or {uuid.uuid4()})))
    }
    review_out = [
        schemas.ReviewOut(
            id=r.id,
            reviewer_id=r.reviewer_id,
            reviewer_name=names.get(r.reviewer_id, ""),
            decision=r.decision,
            reason=r.reason,
            evidence_checked=r.evidence_checked,
            policy=r.policy,
            hash=r.hash,
            hash_matches=r.hash == change.hash,
            created_at=r.created_at,
        )
        for r in reviews
    ]
    roles = _roles(db, user, change)
    blockers = approve_blockers(db, user, change)
    successor = change.detail.get("successor_id")
    base = change_out(db, change)
    base.counts = {**base.counts, **totals}
    return schemas.ChangeDetailOut(
        **base.model_dump(),
        items=item_views,
        relations=rel_views,
        reviews=review_out,
        approval_valid=_valid_approval(db, change) is not None,
        can_edit=_can_edit(db, user, change),
        can_review=user.kind == "human" and "reviewer" in roles and change.state == "in_review",
        can_publish=user.kind == "human"
        and bool(roles & {"reviewer", "steward"})
        and change.state == "approved"
        and _valid_approval(db, change) is not None,
        can_delete=_can_delete(db, user, change),
        approve_blockers=blockers,
        self_review=_is_owner(user, change),
        review_policy=project.review_policy,
        predecessor_id=change.predecessor_id,
        successor_id=uuid.UUID(successor) if successor else None,
        published_page_ids=[i.page_id for i in items if change.state == "published" and i.action == "upsert"],
        detail={k: v for k, v in change.detail.items() if k in ("job_report", "source_answer", "resolution")},
    )


def list_changes(db: Session, user: User, project_id: uuid.UUID, tab: str, origin: str | None) -> schemas.ChangeListOut:
    roles = require_member(db, user, project_id)
    project = db.get(Project, project_id)
    assert project is not None
    base = select(ChangeSet).where(ChangeSet.project_id == project_id, ChangeSet.deleted_at.is_(None))
    if origin in ("human", "metis"):
        base = base.where(ChangeSet.origin == origin)
    mine = or_(ChangeSet.author_id == user.id, ChangeSet.requester_id == user.id)

    def review_q():  # noqa: ANN202
        q = base.where(ChangeSet.state == "in_review")
        if "reviewer" not in roles:
            return q.where(False)  # noqa: FBT003
        if project.review_policy == "independent":
            q = q.where(ChangeSet.author_id != user.id, or_(ChangeSet.requester_id.is_(None), ChangeSet.requester_id != user.id))
        return q

    def drafts_q():  # noqa: ANN202
        q = base.where(ChangeSet.state.in_(["draft", "in_review", "approved", "rejected"]))
        if not roles & {"reviewer", "steward"}:
            q = q.where(mine)
        return q

    def published_q():  # noqa: ANN202
        return base.where(ChangeSet.state == "published")

    queries = {"review": review_q(), "drafts": drafts_q(), "published": published_q()}
    counts = {k: db.scalar(select(func.count()).select_from(q.subquery())) or 0 for k, q in queries.items()}
    stmt = queries.get(tab, queries["drafts"]).order_by(ChangeSet.updated_at.desc()).limit(200)
    rows = db.scalars(stmt).all()
    visible = []
    for change in rows:
        try:
            accessible_change(db, user, change.id)
        except AppError:
            continue
        visible.append(change_out(db, change))
    return schemas.ChangeListOut(items=visible, counts=counts)
