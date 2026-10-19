"""Sayfa revizyonu görünümleri (iddia + kanıt bağları) — liste/detay/diff ortak kullanır."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from metis.core.models import (
    Attachment,
    Claim,
    ClaimEvidence,
    Evidence,
    Page,
    PageRevision,
    PageRevisionAttachment,
    PageRevisionFigure,
    Source,
    SourceRevision,
    User,
)
from metis.modules.attachments.schemas import AttachmentOut
from metis.modules.sources.locator import locator_label


def attachment_out(a: Attachment) -> AttachmentOut:
    return AttachmentOut(
        id=a.id, filename=a.filename, media_type=a.media_type, size_bytes=a.size_bytes, is_image=a.media_type.startswith("image/")
    )


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


class FigureView(BaseModel):
    """Açıklayıcı görsel (kanıt değil). Dosya: /source-revisions/{source_revision_id}/download."""

    ord: int
    caption: str
    source_revision_id: uuid.UUID
    source_id: uuid.UUID
    source_title: str
    source_revision_number: int
    source_is_current: bool
    media_type: str


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
    figures: list[FigureView] = []
    attachments: list[AttachmentOut] = []
    author_id: uuid.UUID
    author_name: str
    created_at: datetime
    hash: str


def note_source_ids(db: Session, source_ids: set[uuid.UUID]) -> set[uuid.UUID]:
    if not source_ids:
        return set()
    return set(db.scalars(select(Page.note_source_id).where(Page.note_source_id.in_(source_ids))))


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
    # Bilginin kendi notu (pages.note_source_id) için sürüm, sayfa revizyonunun kendisidir: başka bir düzenleme
    # taslağının nota yazdığı yeni revizyon yayındaki iddiaları "güncel değil" yapmaz.
    note_ids = note_source_ids(db, {src.id for *_, src in links})
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
                source_is_current=src.id in note_ids or sr.number == src.current_revision_no,
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


def figure_views(db: Session, revision_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[FigureView]]:
    if not revision_ids:
        return {}
    rows = db.execute(
        select(PageRevisionFigure, SourceRevision, Source)
        .join(SourceRevision, SourceRevision.id == PageRevisionFigure.source_revision_id)
        .join(Source, Source.id == SourceRevision.source_id)
        .where(PageRevisionFigure.page_revision_id.in_(revision_ids))
        .order_by(PageRevisionFigure.ord)
    ).all()
    out: dict[uuid.UUID, list[FigureView]] = {}
    for fig, sr, src in rows:
        out.setdefault(fig.page_revision_id, []).append(
            FigureView(
                ord=fig.ord,
                caption=fig.caption,
                source_revision_id=sr.id,
                source_id=src.id,
                source_title=src.title,
                source_revision_number=sr.number,
                source_is_current=sr.number == src.current_revision_no,
                media_type=sr.media_type,
            )
        )
    return out


def attachment_views(db: Session, revision_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[AttachmentOut]]:
    if not revision_ids:
        return {}
    rows = db.execute(
        select(PageRevisionAttachment.page_revision_id, Attachment)
        .join(Attachment, Attachment.id == PageRevisionAttachment.attachment_id)
        .where(PageRevisionAttachment.page_revision_id.in_(revision_ids))
        .order_by(PageRevisionAttachment.ord)
    ).all()
    out: dict[uuid.UUID, list[AttachmentOut]] = {}
    for rid, a in rows:
        out.setdefault(rid, []).append(attachment_out(a))
    return out


def revision_views(db: Session, revisions: list[PageRevision]) -> dict[uuid.UUID, RevisionView]:
    claims = claim_views(db, [r.id for r in revisions])
    figures = figure_views(db, [r.id for r in revisions])
    attachments = attachment_views(db, [r.id for r in revisions])
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
            figures=figures.get(r.id, []),
            attachments=attachments.get(r.id, []),
            author_id=r.author_id,
            author_name="Metis" if names.get(r.author_id) == "Metis" else names.get(r.author_id, ""),
            created_at=r.created_at,
            hash=r.hash,
        )
        for r in revisions
    }


def revision_view(db: Session, revision: PageRevision) -> RevisionView:
    return revision_views(db, [revision])[revision.id]
