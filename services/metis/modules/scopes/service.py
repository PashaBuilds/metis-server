from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from metis.core.access import require_human, require_member
from metis.core.audit import audit
from metis.core.db import utcnow
from metis.core.errors import AppError
from metis.core.models import Project, Schedule, ScopeValue, User
from metis.modules.scopes import schemas
from metis.modules.scopes.semantics import DIMENSIONS, WILDCARD, normalize_scope


def lock_project(db: Session, project_id: uuid.UUID) -> Project:
    project = db.scalar(select(Project).where(Project.id == project_id).with_for_update())
    if not project or project.deleted_at is not None:
        raise AppError("NOT_FOUND", "project not found")
    return project


def catalog(db: Session, user: User, project_id: uuid.UUID) -> schemas.CatalogOut:
    require_member(db, user, project_id)
    rows = db.scalars(
        select(ScopeValue)
        .where(ScopeValue.project_id == project_id, ScopeValue.deleted_at.is_(None))
        .order_by(func.lower(ScopeValue.value))
    ).all()
    out: dict[str, list[schemas.ScopeValueOut]] = {d: [] for d in DIMENSIONS}
    for row in rows:
        out[row.dimension].append(schemas.ScopeValueOut(id=row.id, dimension=row.dimension, value=row.value))  # type: ignore[arg-type]
    return schemas.CatalogOut(project_id=project_id, **out)


def add_value(db: Session, user: User, project_id: uuid.UUID, data: schemas.ScopeValueInput) -> ScopeValue:
    require_human(user)
    require_member(db, user, project_id, ["contributor", "steward"])
    lock_project(db, project_id)
    value = data.value.strip()
    if value == WILDCARD:
        raise AppError("SCOPE_INVALID", "'*' is reserved for Bağımsız", field="value")
    existing = db.scalar(
        select(ScopeValue).where(
            ScopeValue.project_id == project_id,
            ScopeValue.dimension == data.dimension,
            func.lower(ScopeValue.value) == value.lower(),
            ScopeValue.deleted_at.is_(None),
        )
    )
    if existing:
        return existing
    row = ScopeValue(project_id=project_id, dimension=data.dimension, value=value, created_by=user.id)
    db.add(row)
    db.flush()
    audit(db, user.id, "scope.add", "scope_value", row.id, dimension=data.dimension, value=value)
    return row


def delete_value(db: Session, user: User, project_id: uuid.UUID, value_id: uuid.UUID) -> None:
    require_human(user)
    require_member(db, user, project_id, ["contributor", "steward"])
    lock_project(db, project_id)
    row = db.get(ScopeValue, value_id)
    if not row or row.project_id != project_id:
        raise AppError("NOT_FOUND", "scope value not found")
    if row.deleted_at is not None:
        return  # idempotent
    row.deleted_at = utcnow()
    row.deleted_by = user.id
    audit(db, user.id, "scope.delete", "scope_value", row.id, dimension=row.dimension, value=row.value)


def validate_selection(db: Session, project_id: uuid.UUID, scope: dict) -> dict[str, list[str]]:
    """Yeni kayıtta kullanılan kapsam değerleri katalogda tanımlı olmalı ('*' her zaman geçerli)."""
    normalized = normalize_scope(scope)
    rows = db.execute(
        select(ScopeValue.dimension, ScopeValue.value).where(
            ScopeValue.project_id == project_id, ScopeValue.deleted_at.is_(None)
        )
    ).all()
    known: dict[str, dict[str, str]] = {d: {} for d in DIMENSIONS}
    for dim, value in rows:
        known[dim][value.casefold()] = value
    result: dict[str, list[str]] = {}
    for dim in DIMENSIONS:
        vals = []
        for value in normalized[dim]:
            if value == WILDCARD:
                vals = [WILDCARD]
                break
            canonical_value = known[dim].get(value.casefold())
            if canonical_value is None:
                raise AppError("SCOPE_INVALID", "scope value is not defined in the catalog", dimension=dim, value=value)
            vals.append(canonical_value)
        result[dim] = vals
    return result


def ensure_default_schedule(db: Session, project_id: uuid.UUID) -> Schedule:
    sched = db.scalar(select(Schedule).where(Schedule.project_id == project_id, Schedule.kind == "maintenance"))
    if not sched:
        sched = Schedule(
            project_id=project_id,
            kind="maintenance",
            interval_days=7,
            enabled=False,
            next_run_at=utcnow() + timedelta(days=7),
        )
        db.add(sched)
        db.flush()
    return sched
