"""Bilgi havuzu (okuma tarafı): domain listesi, satır listesi, bilgi sayfası, geçmiş, karşılaştırma."""

from __future__ import annotations

import base64
import difflib
import re
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, defer

from metis.core.access import can_read_page_revision, require_member, unreadable_revisions
from metis.core.audit import audit
from metis.core.errors import AppError
from metis.core.models import (
    ChangeSet,
    ChangeSetItem,
    Claim,
    ClaimEvidence,
    Finding,
    FindingPage,
    Page,
    PageRevision,
    Project,
    Publication,
    PublicationPage,
    PublicationRelation,
    Relation,
    RelationRevision,
    Review,
    ScopeValue,
    User,
)
from metis.modules.changes.service import claim_diff
from metis.modules.external.service import origin_for_page
from metis.modules.knowledge import schemas
from metis.modules.knowledge.figures import FIGURE_LINE, isolate_figures
from metis.modules.knowledge.views import revision_view
from metis.modules.scopes.semantics import WILDCARD, matches_scope, normalize_scope

UNSPECIFIED = "__belirlenmemis"


def _active_rows(db: Session, user: User, project_id: uuid.UUID, with_body: bool = True) -> list[tuple[Page, PageRevision]]:
    """Aktif yayındaki okunabilir sayfalar. `with_body=False`: gövde yüklenmez (liste; büyük derlemde her istekte tüm
    sayfa gövdelerini taşımamak için)."""
    project = db.get(Project, project_id)
    if not project or not project.active_publication_id:
        return []
    rows = db.execute(
        select(Page, PageRevision)
        .join(PublicationPage, PublicationPage.page_id == Page.id)
        .join(PageRevision, PageRevision.id == PublicationPage.revision_id)
        .where(
            PublicationPage.publication_id == project.active_publication_id,
            Page.deleted_at.is_(None),
            Page.lifecycle == "active",
        )
        .options(*([] if with_body else [defer(PageRevision.body_md)]))
    ).all()
    hidden = unreadable_revisions(db, user, project_id, [r.id for _, r in rows])
    return [(p, r) for p, r in rows if r.id not in hidden]


def _counts(db: Session, revision_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
    if not revision_ids:
        return {}
    rows = db.execute(
        select(
            Claim.page_revision_id,
            func.count(func.distinct(Claim.id)),
            func.count(func.distinct(ClaimEvidence.evidence_id)),
        )
        .outerjoin(ClaimEvidence, ClaimEvidence.claim_id == Claim.id)
        .where(Claim.page_revision_id.in_(revision_ids))
        .group_by(Claim.page_revision_id)
    ).all()
    return {rid: (claims, evs) for rid, claims, evs in rows}


def domains(db: Session, user: User, project_id: uuid.UUID) -> list[schemas.DomainRow]:
    require_member(db, user, project_id)
    rows = _active_rows(db, user, project_id, with_body=False)
    catalog = db.scalars(
        select(ScopeValue.value).where(
            ScopeValue.project_id == project_id, ScopeValue.dimension == "domain", ScopeValue.deleted_at.is_(None)
        )
    ).all()
    names: dict[str, str] = {v.casefold(): v for v in catalog}
    for _, rev in rows:
        for v in normalize_scope(rev.scope)["domain"]:
            if v != WILDCARD:
                names.setdefault(v.casefold(), v)
    out = []
    for _key, label in sorted(names.items(), key=lambda x: x[1].casefold()):
        matching = [(p, r) for p, r in rows if matches_scope(r.scope, {"domain": [label]})]
        last = max((p.published_at for p, _ in matching if p.published_at), default=None)
        out.append(schemas.DomainRow(key=label, label=label, page_count=len(matching), last_published_at=last))
    unspecified = [(p, r) for p, r in rows if not normalize_scope(r.scope)["domain"]]
    if unspecified:
        out.append(
            schemas.DomainRow(
                key=UNSPECIFIED,
                label="Belirlenmemiş",
                page_count=len(unspecified),
                last_published_at=max((p.published_at for p, _ in unspecified if p.published_at), default=None),
            )
        )
    return out


def list_pages(
    db: Session,
    user: User,
    project_id: uuid.UUID,
    *,
    domain: str | None,
    yatt: list[str],
    kart: list[str],
    proje: list[str],
    kind: str | None,
    freshness: str | None,
    q: str | None,
    cursor: str | None,
    limit: int,
) -> schemas.PageListOut:
    require_member(db, user, project_id)
    rows = _active_rows(db, user, project_id, with_body=False)
    selector = {
        "yatt": yatt,
        "kart": kart,
        "proje": proje,
        "domain": [domain] if domain and domain != UNSPECIFIED else [],
    }
    rows = [(p, r) for p, r in rows if matches_scope(r.scope, selector)]
    if domain == UNSPECIFIED:
        rows = [(p, r) for p, r in rows if not normalize_scope(r.scope)["domain"]]
    if kind:
        rows = [(p, r) for p, r in rows if r.kind == kind]
    if freshness:
        rows = [(p, r) for p, r in rows if p.freshness == freshness]
    order: dict[uuid.UUID, float] = {}
    if q and q.strip():
        from metis.modules.search.service import search

        hits = search(db, user, project_id, q, None, None, 100, dense=False).hits  # "bu metni içeren" süzgeç
        order = {h.page_id: h.score for h in hits}
        rows = [(p, r) for p, r in rows if p.id in order]
        rows.sort(key=lambda x: -order[x[0].id])
    else:
        rows.sort(
            key=lambda x: (x[0].published_at or datetime.min).timestamp() if x[0].published_at else 0, reverse=True
        )
    offset = 0
    if cursor:
        try:
            offset = int(base64.urlsafe_b64decode(cursor.encode()).decode())
        except ValueError as exc:
            raise AppError("VALIDATION_ERROR", "bad cursor") from exc
    page = rows[offset : offset + limit]
    counts = _counts(db, [r.id for _, r in page])
    items = [
        schemas.PageRow(
            page_id=p.id,
            revision_id=r.id,
            title=r.title,
            summary=r.summary,
            kind=r.kind,
            scope=r.scope,
            freshness=p.freshness,
            lifecycle=p.lifecycle,
            published_at=p.published_at,
            claim_count=counts.get(r.id, (0, 0))[0],
            evidence_count=counts.get(r.id, (0, 0))[1],
        )
        for p, r in page
    ]
    nxt = base64.urlsafe_b64encode(str(offset + limit).encode()).decode() if offset + limit < len(rows) else None
    return schemas.PageListOut(items=items, total=len(rows), next_cursor=nxt)


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"\w+", text.casefold()) if len(t) > 2}


def paragraphs_for(body: str, claims: list) -> list[schemas.Paragraph]:
    """Gövde paragraflarını iddialarla eşler (kanıt şeridi + ●n işaretleri için)."""
    body = isolate_figures(body)
    blocks = [b.strip() for b in re.split(r"\n\s*\n", body.strip()) if b.strip()] if body.strip() else []
    used: set[int] = set()
    out = []
    for block in blocks:
        if FIGURE_LINE.fullmatch(block):
            out.append(schemas.Paragraph(text=block, claim_ords=[]))
            continue
        norm = re.sub(r"\s+", " ", block.casefold())
        btoks = _tokens(block)
        ords = []
        for c in claims:
            stmt = re.sub(r"\s+", " ", c.statement.casefold()).strip(" .")
            ctoks = _tokens(c.statement)
            if (stmt and stmt in norm) or (ctoks and len(ctoks & btoks) / len(ctoks) >= 0.7):
                ords.append(c.ord)
                used.add(c.ord)
        out.append(schemas.Paragraph(text=block, claim_ords=ords))
    return out


def page_detail(db: Session, user: User, page_id: uuid.UUID, rev_id: uuid.UUID | None = None) -> schemas.PageDetailOut:
    page = db.get(Page, page_id)
    if not page or page.deleted_at is not None:
        raise AppError("NOT_FOUND", "page not found")
    require_member(db, user, page.project_id)
    if rev_id:
        rev = db.get(PageRevision, rev_id)
        if not rev or rev.page_id != page.id:
            raise AppError("NOT_FOUND", "revision not found")
        published_ever = db.scalar(
            select(func.count()).select_from(PublicationPage).where(PublicationPage.revision_id == rev.id)
        )
        if not published_ever:
            # Taslak revizyonları kayıt detayından görülür; burada yalnız yayımlanmış geçmiş.
            raise AppError("NOT_FOUND", "revision not found")
    else:
        if not page.published_revision_id:
            raise AppError("NOT_FOUND", "page not published")
        rev = db.get(PageRevision, page.published_revision_id)
    if not can_read_page_revision(db, user, rev):
        raise AppError("NOT_FOUND", "page not found")
    assert rev is not None
    view = revision_view(db, rev)
    project = db.get(Project, page.project_id)
    assert project is not None

    relations = []
    if project.active_publication_id:
        rows = db.execute(
            select(RelationRevision, PublicationRelation.relation_id)
            .join(PublicationRelation, PublicationRelation.revision_id == RelationRevision.id)
            .where(
                PublicationRelation.publication_id == project.active_publication_id,
                (RelationRevision.subject_page_id == page.id) | (RelationRevision.object_page_id == page.id),
            )
        ).all()
        for rr, rel_id in rows:
            other_id = rr.object_page_id if rr.subject_page_id == page.id else rr.subject_page_id
            other = db.get(Page, other_id)
            if (
                not other
                or other.deleted_at is not None
                or other.lifecycle != "active"
                or not other.published_revision_id
            ):
                continue
            orev = db.get(PageRevision, other.published_revision_id)
            if not can_read_page_revision(db, user, orev):
                continue  # erişilemeyen düğüm/ilişki sızmaz
            relations.append(
                schemas.RelationRow(
                    relation_id=rel_id,
                    predicate=rr.predicate,
                    direction="out" if rr.subject_page_id == page.id else "in",
                    other_page_id=other.id,
                    other_title=orev.title,
                    other_kind=orev.kind,
                )
            )

    sources: dict[uuid.UUID, schemas.SourceRow] = {}
    for c in view.claims:
        for e in c.evidence:
            row = sources.get(e.source_id)
            if not row:
                sources[e.source_id] = schemas.SourceRow(
                    source_id=e.source_id,
                    title=e.source_title,
                    kind=e.source_kind,
                    revision_number=e.source_revision_number,
                    is_current=e.source_is_current,
                    first_evidence_id=e.evidence_id,
                    claim_ords=[c.ord],
                )
            elif c.ord not in row.claim_ords:
                row.claim_ords.append(c.ord)

    findings = db.scalars(
        select(Finding)
        .join(FindingPage, FindingPage.finding_id == Finding.id)
        .where(FindingPage.page_id == page.id, Finding.state == "open")
        .order_by(Finding.created_at.desc())
    ).all()

    change = db.scalar(
        select(ChangeSet)
        .join(ChangeSetItem, ChangeSetItem.change_set_id == ChangeSet.id)
        .where(ChangeSetItem.proposed_revision_id == rev.id, ChangeSet.state == "published")
        .limit(1)
    )
    approved_by = approved_at = None
    badge = None
    if change:
        review = db.scalar(
            select(Review)
            .where(Review.change_set_id == change.id, Review.decision == "approve")
            .order_by(Review.created_at.desc())
            .limit(1)
        )
        if review:
            reviewer = db.get(User, review.reviewer_id)
            approved_by = reviewer.display_name if reviewer else None
            approved_at = review.created_at
            if review.policy in ("owner_review", "self_publish"):
                badge = review.policy
    open_changes = db.scalars(
        select(ChangeSet.id)
        .join(ChangeSetItem, ChangeSetItem.change_set_id == ChangeSet.id)
        .where(
            ChangeSetItem.page_id == page.id,
            ChangeSet.state.in_(["draft", "in_review", "approved"]),
            ChangeSet.deleted_at.is_(None),
        )
    ).all()
    return schemas.PageDetailOut(
        page_id=page.id,
        project_id=page.project_id,
        lifecycle=page.lifecycle,
        freshness=page.freshness,
        is_published_revision=rev.id == page.published_revision_id,
        published_revision_id=page.published_revision_id,
        revision=view,
        paragraphs=paragraphs_for(view.body_md, view.claims),
        relations=relations,
        sources=list(sources.values()),
        findings=[
            schemas.FindingBrief(id=f.id, kind=f.kind, severity=f.severity, created_at=f.created_at, detail=f.detail)
            for f in findings
        ],
        approved_by=approved_by,
        approved_at=approved_at,
        change_set_id=change.id if change else None,
        review_policy_badge=badge,
        open_change_ids=list(open_changes),
        note_based=page.note_source_id is not None,
        origin=origin_for_page(db, page.id),
    )


def history(db: Session, user: User, page_id: uuid.UUID) -> list[schemas.HistoryRow]:
    page = db.get(Page, page_id)
    if not page or page.deleted_at is not None:
        raise AppError("NOT_FOUND", "page not found")
    require_member(db, user, page.project_id)
    if page.published_revision_id and not can_read_page_revision(
        db, user, db.get(PageRevision, page.published_revision_id)
    ):
        raise AppError("NOT_FOUND", "page not found")
    rows = db.execute(
        select(PageRevision, func.min(Publication.created_at), func.min(Publication.kind))
        .join(PublicationPage, PublicationPage.revision_id == PageRevision.id)
        .join(Publication, Publication.id == PublicationPage.publication_id)
        .where(PageRevision.page_id == page.id)
        .group_by(PageRevision.id)
        .order_by(PageRevision.number.desc())
    ).all()
    out = []
    for rev, first_at, kind in rows:
        if not can_read_page_revision(db, user, rev):
            continue
        change_id = db.scalar(
            select(ChangeSetItem.change_set_id).where(ChangeSetItem.proposed_revision_id == rev.id).limit(1)
        )
        out.append(
            schemas.HistoryRow(
                revision_id=rev.id,
                number=rev.number,
                title=rev.title,
                published_at=first_at,
                change_set_id=change_id,
                publication_kind=kind,
                is_current=rev.id == page.published_revision_id,
            )
        )
    return out


def compare(db: Session, user: User, page_id: uuid.UUID, a: uuid.UUID, b: uuid.UUID) -> schemas.CompareOut:
    ids = {r.revision_id for r in history(db, user, page_id)}
    if a not in ids or b not in ids:
        raise AppError("NOT_FOUND", "revision not found")
    ra, rb = db.get(PageRevision, a), db.get(PageRevision, b)
    assert ra and rb
    va, vb = revision_view(db, ra), revision_view(db, rb)
    lines = []
    for line in difflib.ndiff(va.body_md.splitlines(), vb.body_md.splitlines()):
        if line.startswith("? "):
            continue
        lines.append({"op": {"+": "add", "-": "del", " ": "same"}[line[0]], "text": line[2:]})
    return schemas.CompareOut(a=va, b=vb, claim_diff=claim_diff(va, vb), body_diff=lines)


def report_issue(db: Session, user: User, page_id: uuid.UUID, text: str) -> uuid.UUID:
    detail = page_detail(db, user, page_id)
    finding = Finding(
        project_id=detail.project_id,
        kind="reported",
        severity="medium",
        created_by=user.id,
        detail={"text": text.strip(), "revision_id": str(detail.revision.id)},
    )
    db.add(finding)
    db.flush()
    db.add(FindingPage(finding_id=finding.id, page_id=page_id))
    audit(db, user.id, "finding.report", "page", page_id, finding_id=finding.id)
    return finding.id


def relation_exists(db: Session, relation_id: uuid.UUID) -> bool:
    return db.get(Relation, relation_id) is not None
