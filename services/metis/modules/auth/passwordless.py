"""Parolasız (yalnız kullanıcı adıyla) giriş — ürün sahibinin ve ekip liderinin kararı (2026-10-19, ekip içi kullanım).

Açıkken yönetici olmayan herkes yalnız kullanıcı adıyla girer; ilk girişte hesap açılır ve Okur başlar. Yönetici
hesapları her zaman parolalıdır (PASSWORD_REQUIRED): yoksa biri yöneticinin adını yazıp her şeyi ele geçirirdi.
Bilinen ve kabul edilen risk: ağdaki biri başka bir kullanıcının adını yazarak onun yerine girebilir.
"""

from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from metis.core.access import require_admin
from metis.core.audit import audit
from metis.core.db import utcnow
from metis.core.errors import AppError
from metis.core.models import LoginSettings, Project, ProjectMember, User

_USERNAME = re.compile(r"^[a-z0-9._-]{2,150}$")


def enabled(db: Session) -> bool:
    row = db.get(LoginSettings, 1)
    return bool(row and row.passwordless)


def settings(db: Session, actor: User) -> dict:
    require_admin(actor)
    return {"passwordless": enabled(db)}


def save(db: Session, actor: User, passwordless: bool) -> dict:
    require_admin(actor)
    row = db.get(LoginSettings, 1)
    if row is None:
        row = LoginSettings(id=1)
        db.add(row)
    row.passwordless = passwordless
    row.updated_by = actor.id
    row.updated_at = utcnow()
    db.flush()
    audit(db, actor.id, "login_settings.update", "login_settings", "1", passwordless=passwordless)
    return {"passwordless": passwordless}


def authenticate(db: Session, typed_username: str) -> User | None:
    name = typed_username.strip().lower()
    if not _USERNAME.match(name):
        return None
    user = db.scalar(select(User).where(func.lower(User.username) == name))
    if user is not None:
        if user.kind != "human" or not user.active:
            return None
        if user.is_admin:
            raise AppError("PASSWORD_REQUIRED", "this account requires a password")
        user.must_change_password = False  # parola kullanılmıyor; geçici parolayı değiştirme ekranı anlamsız
        return user
    user = User(username=name, display_name=name, password_hash="", auth_source="local")
    db.add(user)
    db.flush()
    for pid in db.scalars(select(Project.id).where(Project.deleted_at.is_(None), Project.is_demo.is_(False))):
        db.add(ProjectMember(project_id=pid, user_id=user.id, role="reader"))
    audit(db, user.id, "user.passwordless_create", "user", user.id)
    return user
