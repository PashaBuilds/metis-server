from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from metis.core.access import effective_roles, require_admin, require_human, require_member
from metis.core.audit import audit
from metis.core.errors import AppError
from metis.core.models import Project, ProjectMember, User
from metis.modules.projects import schemas
from metis.modules.scopes.service import ensure_default_schedule, lock_project


def to_out(db: Session, user: User, project: Project) -> schemas.ProjectOut:
    return schemas.ProjectOut(
        id=project.id,
        name=project.name,
        description=project.description,
        is_demo=project.is_demo,
        review_policy=project.review_policy,  # type: ignore[arg-type]
        review_interval_days=project.review_interval_days,
        enrichment_enabled=project.enrichment_enabled,
        active_publication_id=project.active_publication_id,
        created_at=project.created_at,
        my_roles=sorted(effective_roles(db, user, project.id)),
    )


def get(db: Session, user: User, project_id: uuid.UUID) -> Project:
    require_member(db, user, project_id)
    project = db.get(Project, project_id)
    assert project is not None
    return project


def list_projects(db: Session, user: User) -> list[Project]:
    projects = db.scalars(select(Project).where(Project.deleted_at.is_(None)).order_by(Project.created_at)).all()
    return [p for p in projects if effective_roles(db, user, p.id)]


def create(db: Session, user: User, data: schemas.ProjectCreateInput, is_demo: bool = False) -> Project:
    require_admin(user)
    project = Project(name=data.name.strip(), description=data.description, is_demo=is_demo)
    db.add(project)
    db.flush()
    for role in ("steward", "reviewer", "contributor", "reader"):
        db.add(ProjectMember(project_id=project.id, user_id=user.id, role=role))
    ensure_default_schedule(db, project.id)
    audit(db, user.id, "project.create", "project", project.id, is_demo=is_demo)
    return project


def update(db: Session, user: User, project_id: uuid.UUID, data: schemas.ProjectUpdateInput) -> Project:
    require_human(user)
    require_member(db, user, project_id, ["steward"])
    project = lock_project(db, project_id)
    if data.review_policy is not None and data.review_policy != project.review_policy:
        # İnceleme politikasını yalnız yönetici değiştirir.
        require_admin(user)
        project.review_policy = data.review_policy
    if data.enrichment_enabled is not None and data.enrichment_enabled != project.enrichment_enabled:
        require_admin(user)  # şirket modeline hangi içeriğin gideceği yönetici kararı
        project.enrichment_enabled = data.enrichment_enabled
    if data.name is not None:
        project.name = data.name.strip()
    if data.description is not None:
        project.description = data.description
    if data.review_interval_days is not None:
        project.review_interval_days = data.review_interval_days
    audit(db, user.id, "project.update", "project", project.id, **data.model_dump(exclude_none=True))
    return project


def members(db: Session, user: User, project_id: uuid.UUID) -> list[schemas.MemberOut]:
    require_member(db, user, project_id)
    rows = db.execute(
        select(User, ProjectMember.role)
        .join(ProjectMember, ProjectMember.user_id == User.id)
        .where(ProjectMember.project_id == project_id, User.kind == "human")
        .order_by(User.display_name)
    ).all()
    grouped: dict[uuid.UUID, schemas.MemberOut] = {}
    for u, role in rows:
        entry = grouped.setdefault(
            u.id,
            schemas.MemberOut(
                user_id=u.id, username=u.username, display_name=u.display_name, roles=[], active=u.active
            ),
        )
        entry.roles.append(role)
    for m in grouped.values():
        m.roles.sort()
    return list(grouped.values())


def set_member(db: Session, user: User, project_id: uuid.UUID, data: schemas.MemberSetInput) -> None:
    require_human(user)
    require_member(db, user, project_id, ["steward"])
    lock_project(db, project_id)
    target = db.get(User, data.user_id)
    if not target or target.kind != "human":
        raise AppError("NOT_FOUND", "user not found")
    if target.id == user.id and "steward" not in data.roles and not user.is_admin:
        raise AppError("INVALID_STATE", "cannot remove your own steward role")
    db.execute(delete(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == target.id))
    for role in sorted(set(data.roles)):
        db.add(ProjectMember(project_id=project_id, user_id=target.id, role=role))
    audit(db, user.id, "member.set", "project", project_id, user_id=target.id, roles=sorted(set(data.roles)))


def inbox(db: Session, user: User, project_id: uuid.UUID) -> dict:
    from sqlalchemy import func, or_

    from metis.core.models import ChangeSet, Finding, Job

    roles = require_member(db, user, project_id)
    project = db.get(Project, project_id)
    assert project is not None
    reviews = 0
    if "reviewer" in roles:
        q = (
            select(func.count())
            .select_from(ChangeSet)
            .where(ChangeSet.project_id == project_id, ChangeSet.state == "in_review", ChangeSet.deleted_at.is_(None))
        )
        if project.review_policy == "independent":
            q = q.where(ChangeSet.author_id != user.id, or_(ChangeSet.requester_id.is_(None), ChangeSet.requester_id != user.id))
        reviews = db.scalar(q) or 0
    questions = (
        db.scalar(
            select(func.count())
            .select_from(Job)
            .where(
                Job.project_id == project_id,
                Job.requester_id == user.id,
                Job.state == "awaiting_input",
                Job.deleted_at.is_(None),
            )
        )
        or 0
    )
    findings = (
        db.scalar(
            select(func.count()).select_from(Finding).where(Finding.project_id == project_id, Finding.state == "open")
        )
        or 0
    )
    return {
        "reviews_waiting": reviews,
        "questions_waiting": questions,
        "open_findings": findings,
        "updated_pages": updated_pages(db, user, project_id),
    }


def updated_pages(db: Session, user: User, project_id: uuid.UUID, limit: int = 10) -> list[dict]:
    """Sahibi olduğun bilgileri başkası yayımladıysa (son 'gördüm'den sonra): 'Bilgilerin güncellendi'."""
    from datetime import datetime

    from metis.core.access import unreadable_revisions
    from metis.core.models import ChangeSetItem, Page, PageRevision, Publication, PublicationPage, UserPreference

    pref = db.scalar(select(UserPreference.value).where(UserPreference.user_id == user.id, UserPreference.key == "updates_seen_at"))
    try:
        seen = datetime.fromisoformat(pref) if isinstance(pref, str) else user.created_at
    except ValueError:
        seen = user.created_at
    rows = db.execute(
        select(Page.id, PageRevision.id, PageRevision.title, Publication.created_by, Publication.created_at)
        .join(PublicationPage, PublicationPage.page_id == Page.id)
        .join(Publication, Publication.id == PublicationPage.publication_id)
        .join(PageRevision, PageRevision.id == PublicationPage.revision_id)
        # Yayın manifestosu tüm sayfaları içerir; yalnız o kayıtta gerçekten değişen sayfa sayılır.
        .join(ChangeSetItem, (ChangeSetItem.change_set_id == Publication.change_set_id) & (ChangeSetItem.page_id == Page.id))
        .where(
            Page.project_id == project_id,
            Page.owner_id == user.id,
            Page.deleted_at.is_(None),
            Publication.kind == "publish",
            Publication.created_by.is_not(None),
            Publication.created_by != user.id,
            Publication.created_at > seen,
        )
        .order_by(Publication.created_at.desc())
    ).all()
    hidden = unreadable_revisions(db, user, project_id, [r[1] for r in rows])
    out, seen_pages = [], set()
    for page_id, rev_id, title, by, at in rows:
        if page_id in seen_pages or rev_id in hidden:
            continue
        seen_pages.add(page_id)
        actor = db.get(User, by)
        out.append({"page_id": page_id, "title": title, "by_name": actor.display_name if actor else "", "published_at": at})
        if len(out) >= limit:
            break
    return out
