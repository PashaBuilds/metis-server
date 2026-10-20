from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from metis.core.access import require_admin
from metis.core.audit import audit
from metis.core.config import get_settings
from metis.core.db import utcnow
from metis.core.errors import AppError
from metis.core.models import (
    LoginAttempt,
    Project,
    ProjectMember,
    SetupCode,
    User,
    UserPreference,
    UserSession,
)
from metis.core.security import check_password_strength, digest, hash_password, setup_code, token, verify_password
from metis.modules.auth import schemas
from metis.modules.auth.provider import get_provider

MAX_USER_FAILURES = 5
MAX_IP_FAILURES = 30
WINDOW = timedelta(minutes=15)


def needs_setup(db: Session) -> bool:
    return db.scalar(select(func.count()).select_from(User).where(User.kind == "human")) == 0


def issue_setup_code(db: Session) -> str:
    if not needs_setup(db):
        raise AppError("SETUP_ALREADY_DONE", "an administrator already exists")
    code = setup_code()
    db.execute(delete(SetupCode).where(SetupCode.used_at.is_(None)))
    db.add(SetupCode(code_digest=digest(code.replace("-", "").upper()), expires_at=utcnow() + timedelta(hours=24)))
    return code


def ensure_worker_identity(db: Session) -> User:
    worker = db.scalar(select(User).where(User.kind == "worker", User.username == "metis-worker"))
    if not worker:
        worker = User(username="metis-worker", display_name="Metis", kind="worker", password_hash="")
        db.add(worker)
        db.flush()
    return worker


def complete_setup(db: Session, data: schemas.SetupInput) -> User:
    # Aynı anda iki kurulum denemesini seri hâle getir.
    db.execute(select(func.pg_advisory_xact_lock(72_001)))
    if not needs_setup(db):
        raise AppError("SETUP_ALREADY_DONE", "an administrator already exists")
    code = db.scalar(
        select(SetupCode)
        .where(SetupCode.code_digest == digest(data.code.replace("-", "").strip().upper()))
        .with_for_update()
    )
    if not code or code.used_at is not None or code.expires_at <= utcnow():
        raise AppError("SETUP_CODE_INVALID", "setup code invalid, used or expired")
    check_password_strength(data.password)
    if data.mode == "empty" and not data.project_name.strip():
        raise AppError(
            "VALIDATION_ERROR", "project name required", fields=[{"field": "project_name", "type": "missing"}]
        )
    code.used_at = utcnow()
    user = User(
        username=data.username.strip(),
        display_name=data.display_name.strip(),
        password_hash=hash_password(data.password),
        is_admin=True,
    )
    db.add(user)
    db.flush()
    ensure_worker_identity(db)
    if data.mode == "empty":
        project = Project(name=data.project_name.strip())
        db.add(project)
        db.flush()
        for role in ("steward", "reviewer", "contributor", "reader"):
            db.add(ProjectMember(project_id=project.id, user_id=user.id, role=role))
        from metis.modules.scopes.service import ensure_default_schedule

        ensure_default_schedule(db, project.id)
    audit(db, user.id, "setup.complete", "user", user.id, mode=data.mode)
    return user


def _rate_limited(db: Session, username: str, ip: str) -> bool:
    since = utcnow() - WINDOW
    user_failures = db.scalar(
        select(func.count())
        .select_from(LoginAttempt)
        .where(
            func.lower(LoginAttempt.username) == username.lower(),
            LoginAttempt.at >= since,
            LoginAttempt.success.is_(False),
        )
    )
    ip_failures = db.scalar(
        select(func.count())
        .select_from(LoginAttempt)
        .where(LoginAttempt.ip == ip, LoginAttempt.at >= since, LoginAttempt.success.is_(False))
    )
    return (user_failures or 0) >= MAX_USER_FAILURES or (ip_failures or 0) >= MAX_IP_FAILURES


def create_session(db: Session, user: User, ip: str) -> tuple[str, UserSession]:
    raw = token()
    sess = UserSession(
        token_digest=digest(raw),
        user_id=user.id,
        csrf=token()[:48],
        expires_at=utcnow() + timedelta(hours=get_settings().session_hours),
        ip=ip[:64],
    )
    db.add(sess)
    db.flush()
    return raw, sess


def login(db: Session, data: schemas.LoginInput, ip: str) -> tuple[str, UserSession, User]:
    if _rate_limited(db, data.username, ip):
        raise AppError(
            "RATE_LIMITED", "too many failed attempts; try again later", retry_after_s=int(WINDOW.total_seconds())
        )
    user = get_provider().authenticate(db, data.username, data.password)
    db.add(LoginAttempt(username=data.username[:150], ip=ip[:64], success=user is not None))
    if not user:
        db.commit()  # başarısız deneme kaydı, hata zarfından önce kalıcı olmalı
        raise AppError("INVALID_CREDENTIALS", "username or password incorrect")
    db.execute(delete(UserSession).where(UserSession.user_id == user.id, UserSession.expires_at <= utcnow()))
    raw, sess = create_session(db, user, ip)
    audit(db, user.id, "auth.login", "user", user.id)
    return raw, sess, user


def logout(db: Session, sess: UserSession) -> None:
    db.delete(sess)


def change_password(db: Session, user: User, data: schemas.PasswordChangeInput, keep_session: uuid.UUID) -> None:
    if user.auth_source == "directory":
        raise AppError("PASSWORD_MANAGED_BY_DIRECTORY", "password is managed by the company directory")
    ok, _ = verify_password(data.current_password, user.password_hash)
    if not ok:
        raise AppError("INVALID_CREDENTIALS", "current password incorrect", field="current_password")
    if data.new_password == data.current_password:
        raise AppError("WEAK_PASSWORD", "new password must differ", field="new_password")
    check_password_strength(data.new_password)
    user.password_hash = hash_password(data.new_password)
    user.must_change_password = False
    db.execute(delete(UserSession).where(UserSession.user_id == user.id, UserSession.id != keep_session))
    audit(db, user.id, "auth.password_change", "user", user.id)


def memberships(db: Session, user: User) -> list[schemas.MembershipOut]:
    if user.is_admin:
        projects = db.scalars(select(Project).where(Project.deleted_at.is_(None)).order_by(Project.created_at)).all()
    else:
        projects = db.scalars(
            select(Project)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(ProjectMember.user_id == user.id, Project.deleted_at.is_(None))
            .distinct()
            .order_by(Project.created_at)
        ).all()
    rows = db.execute(
        select(ProjectMember.project_id, ProjectMember.role).where(ProjectMember.user_id == user.id)
    ).all()
    roles: dict[uuid.UUID, list[str]] = {}
    for pid, role in rows:
        roles.setdefault(pid, []).append(role)
    return [
        schemas.MembershipOut(
            project_id=p.id, project_name=p.name, is_demo=p.is_demo, roles=sorted(roles.get(p.id, []))
        )
        for p in projects
    ]


def preferences(db: Session, user: User) -> dict[str, object]:
    return {p.key: p.value for p in db.scalars(select(UserPreference).where(UserPreference.user_id == user.id))}


PREFERENCE_KEYS = {
    "theme",
    "density",
    "rail_collapsed",
    "active_project_id",
    "active_scope",
    "mentor_model_id",
    "updates_seen_at",
    "filters.library",
    "filters.records",
    "filters.health",
    "filters.tasks",
}


def set_preference(db: Session, user: User, key: str, value: object) -> None:
    if key not in PREFERENCE_KEYS:
        raise AppError("VALIDATION_ERROR", "unknown preference key", fields=[{"field": "key", "type": "enum"}])
    pref = db.get(UserPreference, (user.id, key))
    if pref:
        pref.value = value
    else:
        db.add(UserPreference(user_id=user.id, key=key, value=value))


# ---------------------------------------------------------------- kullanıcı yönetimi (yönetici)


def to_out(user: User) -> schemas.UserOut:
    return schemas.UserOut.model_validate(user, from_attributes=True)


def list_users(db: Session, actor: User) -> list[schemas.UserOut]:
    require_admin(actor)
    with_roles = set(db.scalars(select(ProjectMember.user_id).distinct()))
    out = []
    for u in db.scalars(select(User).where(User.kind == "human").order_by(func.lower(User.username))):
        row = to_out(u)
        row.pending_role = u.auth_source == "directory" and not u.is_admin and u.id not in with_roles
        out.append(row)
    return out


def create_user(db: Session, actor: User, data: schemas.UserCreateInput) -> User:
    require_admin(actor)
    if db.scalar(select(User.id).where(func.lower(User.username) == data.username.lower())):
        raise AppError("ALREADY_EXISTS", "username taken", field="username")
    check_password_strength(data.temporary_password)
    user = User(
        username=data.username,
        display_name=data.display_name,
        password_hash=hash_password(data.temporary_password),
        is_admin=data.is_admin,
        must_change_password=True,
    )
    db.add(user)
    db.flush()
    audit(db, actor.id, "user.create", "user", user.id, is_admin=data.is_admin)
    return user


def update_user(db: Session, actor: User, user_id: uuid.UUID, data: schemas.UserUpdateInput) -> User:
    require_admin(actor)
    user = db.get(User, user_id)
    if not user or user.kind != "human":
        raise AppError("NOT_FOUND", "user not found")
    if user.id == actor.id and (data.active is False or data.is_admin is False):
        raise AppError("INVALID_STATE", "cannot remove your own administrator access")
    if data.is_admin and not user.is_admin and user.auth_source == "local" and not user.password_hash and data.temporary_password is None:
        # Parolasız girişle açılmış hesap: yönetici yapılırken parola şart (yönetici hesabı parolasız girilemez).
        raise AppError("ADMIN_NEEDS_PASSWORD", "set a temporary password when granting administrator access")
    if data.display_name is not None:
        user.display_name = data.display_name
    if data.active is not None:
        user.active = data.active
        if not data.active:
            db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    if data.is_admin is not None:
        user.is_admin = data.is_admin
    if data.temporary_password is not None:
        if user.auth_source == "directory":
            raise AppError("PASSWORD_MANAGED_BY_DIRECTORY", "password is managed by the company directory")
        check_password_strength(data.temporary_password)
        user.password_hash = hash_password(data.temporary_password)
        user.must_change_password = True
        db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    audit(
        db,
        actor.id,
        "user.update",
        "user",
        user.id,
        fields=sorted(data.model_dump(exclude_none=True, exclude={"temporary_password"})),
        password_reset=data.temporary_password is not None,
    )
    return user
