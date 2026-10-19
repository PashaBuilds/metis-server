"""Sunucu tarafı yetki denetimi (brief ilke 1, 12).

Kural: erişilemeyen kayıt için 404 (varlığı sızdırma); üye ama rolü yetmiyorsa 403.
LLM/worker hiçbir zaman onaylamaz, yayımlamaz, silmez — bu fonksiyonlar `kind='human'`
şartını ayrıca uygular.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from metis.core.errors import AppError
from metis.core.models import (
    Claim,
    ClaimEvidence,
    Evidence,
    Page,
    PageRevision,
    PageRevisionFigure,
    Project,
    ProjectMember,
    PublicationPage,
    Source,
    SourceAcl,
    SourceRevision,
    User,
)

ROLE_IMPLIES: dict[str, set[str]] = {
    "reader": {"reader"},
    "contributor": {"contributor", "reader"},
    "reviewer": {"reviewer", "reader"},
    "steward": {"steward", "reviewer", "contributor", "reader"},
}
ALL_ROLES = {"reader", "contributor", "reviewer", "steward"}


def require_human(user: User) -> None:
    if user.kind != "human":
        raise AppError("HUMAN_REQUIRED", "human authority required")


def require_admin(user: User) -> None:
    require_human(user)
    if not user.is_admin:
        raise AppError("ADMIN_REQUIRED", "administrator required")


def effective_roles(db: Session, user: User, project_id: uuid.UUID) -> set[str]:
    project = db.get(Project, project_id)
    if not project or project.deleted_at is not None or not user.active:
        return set()
    rows = db.scalars(
        select(ProjectMember.role).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)
    ).all()
    roles: set[str] = set()
    for role in rows:
        roles |= ROLE_IMPLIES.get(role, set())
    if user.is_admin and user.kind == "human":
        roles |= ALL_ROLES
    return roles


def require_member(db: Session, user: User, project_id: uuid.UUID, roles: Iterable[str] | None = None) -> set[str]:
    have = effective_roles(db, user, project_id)
    if not have:
        raise AppError("NOT_FOUND", "project not found")
    wanted = set(roles or [])
    if wanted and not (have & wanted):
        raise AppError("ROLE_REQUIRED", "role not sufficient", required=sorted(wanted))
    return have


def can_read_source(db: Session, user: User, source: Source | None) -> bool:
    if source is None or source.deleted_at is not None:
        return False
    if not effective_roles(db, user, source.project_id):
        return False
    if not _note_draft_visible(db, user, source.id, source.owner_id, source.project_id):
        return False
    acl = db.scalars(select(SourceAcl.user_id).where(SourceAcl.source_id == source.id)).all()
    return not acl or user.id in acl or source.owner_id == user.id


NOTE_DRAFT_READERS = {"steward", "reviewer"}


def _unpublished_note_sources(db: Session, project_id: uuid.UUID) -> set[uuid.UUID]:
    """Henüz yayımlanmamış not tabanlı sayfaların not kaynakları (taslak)."""
    return set(
        db.scalars(
            select(Page.note_source_id).where(
                Page.project_id == project_id, Page.note_source_id.is_not(None), Page.published_revision_id.is_(None)
            )
        )
    )


def _note_draft_visible(db: Session, user: User, source_id: uuid.UUID, owner_id: uuid.UUID, project_id: uuid.UUID) -> bool:
    """Yayımlanmamış notun kaynağını yalnız yazarı, steward ve reviewer okur (bağımsız incelemede taslak açılabilsin)."""
    if source_id not in _unpublished_note_sources(db, project_id) or owner_id == user.id:
        return True
    return bool(effective_roles(db, user, project_id) & NOTE_DRAFT_READERS)


def _is_draft_reader(db: Session, user: User, project_id: uuid.UUID, *owners: uuid.UUID | None) -> bool:
    return user.id in owners or bool(effective_roles(db, user, project_id) & NOTE_DRAFT_READERS)


def _page_revision_published(db: Session, revision_id: uuid.UUID) -> bool:
    return db.scalar(select(PublicationPage.revision_id).where(PublicationPage.revision_id == revision_id).limit(1)) is not None


def can_read_source_revision(db: Session, user: User, source: Source | None, rev: SourceRevision | None) -> bool:
    """Bir bilginin not kaynağında, hiç yayımlanmamış sayfa revizyonunun dayandığı not revizyonu (düzenleme taslağı)
    yalnız taslak okuyucularına görünür; yayındaki bilgi taslak kaydedildi diye değişmez."""
    if rev is None or not can_read_source(db, user, source):
        return False
    assert source is not None
    if db.scalar(select(Page.id).where(Page.note_source_id == source.id).limit(1)) is None:
        return True
    if _is_draft_reader(db, user, source.project_id, source.owner_id, rev.author_id):
        return True
    published = (
        select(Evidence.id)
        .join(ClaimEvidence, ClaimEvidence.evidence_id == Evidence.id)
        .join(Claim, Claim.id == ClaimEvidence.claim_id)
        .join(PublicationPage, PublicationPage.revision_id == Claim.page_revision_id)
        .where(Evidence.source_revision_id == rev.id)
        .limit(1)
    )
    return db.scalar(published) is not None


def source_for_revision(db: Session, revision_id: uuid.UUID) -> tuple[SourceRevision | None, Source | None]:
    rev = db.get(SourceRevision, revision_id)
    return rev, (db.get(Source, rev.source_id) if rev else None)


def evidence_access(db: Session, user: User, evidence_id: uuid.UUID) -> tuple[Evidence, SourceRevision, Source]:
    ev = db.get(Evidence, evidence_id)
    rev, src = source_for_revision(db, ev.source_revision_id) if ev else (None, None)
    if not ev or not can_read_source_revision(db, user, src, rev):
        raise AppError("NOT_FOUND", "evidence not found")
    assert src is not None
    return ev, rev, src


def revision_source_ids(db: Session, revision_id: uuid.UUID) -> set[uuid.UUID]:
    rows = db.execute(
        select(SourceRevision.source_id)
        .join(Evidence, Evidence.source_revision_id == SourceRevision.id)
        .join(ClaimEvidence, ClaimEvidence.evidence_id == Evidence.id)
        .join(Claim, Claim.id == ClaimEvidence.claim_id)
        .where(Claim.page_revision_id == revision_id)
    ).scalars()
    figures = db.execute(
        select(SourceRevision.source_id)
        .join(PageRevisionFigure, PageRevisionFigure.source_revision_id == SourceRevision.id)
        .where(PageRevisionFigure.page_revision_id == revision_id)
    ).scalars()
    return set(rows) | set(figures)


def can_read_page_revision(db: Session, user: User, revision: PageRevision | None) -> bool:
    """Bir sayfa revizyonu, yalnız tüm kanıt kaynakları okunabiliyorsa görünür."""
    if revision is None:
        return False
    page = db.get(Page, revision.page_id)
    if page is None or page.deleted_at is not None or not effective_roles(db, user, page.project_id):
        return False
    # Not tabanlı bilginin hiç yayımlanmamış revizyonu (iddiasız boş not dahil) taslaktır.
    if (
        page.note_source_id is not None
        and not _page_revision_published(db, revision.id)
        and not _is_draft_reader(db, user, page.project_id, page.owner_id, revision.author_id)
    ):
        return False
    for source_id in revision_source_ids(db, revision.id):
        if not can_read_source(db, user, db.get(Source, source_id)):
            return False
    return True


def readable_source_ids(db: Session, user: User, project_id: uuid.UUID) -> set[uuid.UUID]:
    """Toplu erişim kontrolü (N+1'i önler)."""
    if not effective_roles(db, user, project_id):
        return set()
    sources = db.execute(
        select(Source.id, Source.owner_id).where(Source.project_id == project_id, Source.deleted_at.is_(None))
    ).all()
    acl_rows = db.execute(
        select(SourceAcl.source_id, SourceAcl.user_id)
        .join(Source, Source.id == SourceAcl.source_id)
        .where(Source.project_id == project_id)
    ).all()
    acl: dict[uuid.UUID, set[uuid.UUID]] = {}
    for sid, uid in acl_rows:
        acl.setdefault(sid, set()).add(uid)
    hidden = set()
    if not (effective_roles(db, user, project_id) & NOTE_DRAFT_READERS):
        hidden = _unpublished_note_sources(db, project_id)
    return {
        sid
        for sid, owner in sources
        if (sid not in acl or user.id in acl[sid] or owner == user.id) and (sid not in hidden or owner == user.id)
    }


def unreadable_revisions(
    db: Session, user: User, project_id: uuid.UUID, revision_ids: Iterable[uuid.UUID]
) -> set[uuid.UUID]:
    ids = list(set(revision_ids))
    if not ids:
        return set()
    readable = readable_source_ids(db, user, project_id)
    rows = db.execute(
        select(Claim.page_revision_id, SourceRevision.source_id)
        .join(ClaimEvidence, ClaimEvidence.claim_id == Claim.id)
        .join(Evidence, Evidence.id == ClaimEvidence.evidence_id)
        .join(SourceRevision, SourceRevision.id == Evidence.source_revision_id)
        .where(Claim.page_revision_id.in_(ids))
    ).all()
    figure_rows = db.execute(
        select(PageRevisionFigure.page_revision_id, SourceRevision.source_id)
        .join(SourceRevision, SourceRevision.id == PageRevisionFigure.source_revision_id)
        .where(PageRevisionFigure.page_revision_id.in_(ids))
    ).all()
    return {rid for rid, sid in [*rows, *figure_rows] if sid not in readable}
