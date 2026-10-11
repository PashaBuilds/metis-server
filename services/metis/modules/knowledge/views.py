"""Sayfa revizyonu görünümleri (iddia + kanıt bağları) — liste/detay/diff ortak kullanır."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from metis.core.models import Claim, ClaimEvidence, Evidence, PageRevision, Source, SourceRevision, User
from metis.modules.sources.locator import locator_label


class ClaimEvidenceView(BaseModel):
    evidence_id: uuid.UUID
    quote: str
    source_id: uuid.UUID
    source_title: str
    source_kind: str
    source_revision_id: uuid.UUID
    source_revision_number: int
    source_is_current: bool
    locator_label: str
    verbatim: bool


class ClaimView(BaseModel):
    id: uuid.UUID
    ord: int
    statement: str
    kind: str
    support: str
    evidence: list[ClaimEvidenceView]
    verbatim: bool


class RevisionView(BaseModel):
    id: uuid.UUID
    page_id: uuid.UUID
    number: int
    title: str
    summary: str
    body_md: str
    kind: str
    scope: dict
    unknowns: list
    aliases: list
    claims: list[ClaimView]
    author_id: uuid.UUID
    author_name: str
    created_at: datetime
    hash: str


def claim_views(db: Session, revision_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[ClaimView]]:
    if not revision_ids:
        return {}
    claims = db.scalars(select(Claim).where(Claim.page_revision_id.in_(revision_ids)).order_by(Claim.ord)).all()
    links = db.execute(
        select(ClaimEvidence, Evidence, SourceRevision, Source)
        .join(Evidence, Evidence.id == ClaimEvidence.evidence_id)
        .join(SourceRevision, SourceRevision.id == Evidence.source_revision_id)
        .join(Source, Source.id == SourceRevision.source_id)
        .where(ClaimEvidence.claim_id.in_([c.id for c in claims] or [uuid.uuid4()]))
    ).all()
    by_claim: dict[uuid.UUID, list[ClaimEvidenceView]] = {}
    for ce, ev, sr, src in links:
        loc = {k: v for k, v in ev.locator.items() if k != "auto"}
        by_claim.setdefault(ce.claim_id, []).append(
            ClaimEvidenceView(
                evidence_id=ev.id,
                quote=ce.quote,
                source_id=src.id,
                source_title=src.title,
                source_kind=src.kind,
                source_revision_id=sr.id,
                source_revision_number=sr.number,
                source_is_current=sr.number == src.current_revision_no,
                locator_label=locator_label(loc),
                verbatim=bool(ce.quote) and ce.quote in ev.excerpt,
            )
        )
    out: dict[uuid.UUID, list[ClaimView]] = {}
    for c in claims:
        evs = sorted(by_claim.get(c.id, []), key=lambda e: (e.source_title, str(e.evidence_id)))
        out.setdefault(c.page_revision_id, []).append(
            ClaimView(
                id=c.id,
                ord=c.ord,
                statement=c.statement,
                kind=c.kind,
                support=c.support,
                evidence=evs,
                verbatim=any(c.statement in e.quote or e.quote == c.statement for e in evs),
            )
        )
    return out


def revision_views(db: Session, revisions: list[PageRevision]) -> dict[uuid.UUID, RevisionView]:
    claims = claim_views(db, [r.id for r in revisions])
    names = {
        u.id: u.display_name
        for u in db.scalars(select(User).where(User.id.in_({r.author_id for r in revisions} or {uuid.uuid4()})))
    }
    return {
        r.id: RevisionView(
            id=r.id,
            page_id=r.page_id,
            number=r.number,
            title=r.title,
            summary=r.summary,
            body_md=r.body_md,
            kind=r.kind,
            scope=r.scope,
            unknowns=r.unknowns or [],
            aliases=r.aliases or [],
            claims=claims.get(r.id, []),
            author_id=r.author_id,
            author_name="Metis" if names.get(r.author_id) == "Metis" else names.get(r.author_id, ""),
            created_at=r.created_at,
            hash=r.hash,
        )
        for r in revisions
    }


def revision_view(db: Session, revision: PageRevision) -> RevisionView:
    return revision_views(db, [revision])[revision.id]
