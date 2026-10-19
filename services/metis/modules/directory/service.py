"""Şirket hesabıyla giriş: ayarlar, bağlantı denemesi ve ilk girişte hesap oluşturma.

Kurallar (tasarım: docs/superpowers/specs/2026-10-19-sirket-hesabi-giris-design.md):
- Yalnız METIS_PUBLIC_URL https iken açılır (şirket parolası tarayıcıdan METIS'e gelir) ve yalnız LDAPS.
- Parola saklanmaz; dizin kullanıcısının password_hash'i boştur, METIS'te değiştirilemez.
- Yerel hesap (auth_source='local') aynı adlı bir dizin hesabıyla ele geçirilemez.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from metis.core.access import require_admin
from metis.core.audit import audit
from metis.core.config import get_settings
from metis.core.db import utcnow
from metis.core.errors import AppError
from metis.core.models import DirectorySettings, Project, ProjectMember, User
from metis.modules.directory import ldap, schemas


def https_ok() -> bool:
    return get_settings().public_url.startswith("https://")


def _row(db: Session) -> DirectorySettings | None:
    return db.get(DirectorySettings, 1)


def _config(data: schemas.DirectorySettingsIn | DirectorySettings) -> ldap.DirectoryConfig:
    return ldap.DirectoryConfig(server_url=data.server_url, domain=data.domain, base_dn=data.base_dn, group_dn=data.group_dn)


def enabled(db: Session) -> bool:
    row = _row(db)
    return bool(row and row.enabled and https_ok())


def settings_out(db: Session, actor: User) -> schemas.DirectorySettingsOut:
    require_admin(actor)
    row = _row(db)
    base = schemas.DirectorySettingsIn() if row is None else schemas.DirectorySettingsIn.model_validate(row, from_attributes=True)
    return schemas.DirectorySettingsOut(**base.model_dump(), https_ok=https_ok(), updated_at=row.updated_at if row else None)


def _validate(data: schemas.DirectorySettingsIn) -> schemas.DirectorySettingsIn:
    url = ldap.validate_server_url(data.server_url) if (data.server_url.strip() or data.enabled) else ""
    domain = data.domain.strip()
    if data.enabled and not domain:
        raise AppError("VALIDATION_ERROR", "domain required", fields=[{"field": "domain", "type": "missing"}])
    clean = data.model_copy(update={"server_url": url, "domain": domain, "base_dn": data.base_dn.strip(), "group_dn": data.group_dn.strip()})
    if data.enabled and not ldap.search_base(_config(clean)):
        raise AppError("VALIDATION_ERROR", "base_dn required for a NetBIOS domain", fields=[{"field": "base_dn", "type": "missing"}])
    return clean


def save(db: Session, actor: User, data: schemas.DirectorySettingsIn) -> schemas.DirectorySettingsOut:
    require_admin(actor)
    clean = _validate(data)
    if clean.enabled and not https_ok():
        raise AppError("HTTPS_REQUIRED", "directory login requires METIS_PUBLIC_URL https")
    row = _row(db)
    if row is None:
        row = DirectorySettings(id=1)
        db.add(row)
    for key, value in clean.model_dump().items():
        setattr(row, key, value)
    row.updated_by = actor.id
    row.updated_at = utcnow()
    db.flush()
    audit(db, actor.id, "directory.update", "directory_settings", "1", **clean.model_dump())
    return settings_out(db, actor)


def test(db: Session, actor: User, data: schemas.DirectoryTestIn) -> schemas.DirectoryTestOut:
    """Kaydetmeden dener; hesap açmaz. Girilen parola yalnız bu denemede kullanılır."""
    require_admin(actor)
    if not https_ok():
        return schemas.DirectoryTestOut(ok=False, error="HTTPS_REQUIRED")
    cfg = _config(_validate(data.settings.model_copy(update={"enabled": True})))
    try:
        entry = ldap.verify(cfg, data.username, data.password, check_group=False)
    except ldap.DirectoryUnavailable:
        return schemas.DirectoryTestOut(ok=False, error="DIRECTORY_UNAVAILABLE")
    if entry is None:
        return schemas.DirectoryTestOut(ok=False, error="INVALID_CREDENTIALS")
    in_group = None if not cfg.group_dn else cfg.group_dn.lower() in {g.lower() for g in entry.groups}
    return schemas.DirectoryTestOut(ok=True, username=entry.username, display_name=entry.display_name, email=entry.email, in_group=in_group)


def authenticate(db: Session, typed_username: str, password: str) -> User | None:
    row = _row(db)
    if row is None:
        return None
    try:
        entry = ldap.verify(_config(row), typed_username, password)
    except ldap.DirectoryUnavailable as exc:
        raise AppError("DIRECTORY_UNAVAILABLE", "company directory unreachable") from exc
    if entry is None:
        return None
    user = db.scalar(select(User).where(User.external_id == entry.external_id))
    if user is None:
        same = db.scalar(select(User).where(func.lower(User.username) == entry.username))
        if same is not None:
            if same.auth_source != "directory" or same.external_id:
                return None  # yerel hesap ya da başka bir dizin kimliği: ele geçirilemez
            user = same
            user.external_id = entry.external_id
        else:
            user = User(
                username=entry.username,
                display_name=entry.display_name[:150],
                password_hash="",
                auth_source="directory",
                external_id=entry.external_id,
            )
            db.add(user)
            db.flush()
            if row.new_user_role == "reader":
                for pid in db.scalars(select(Project.id).where(Project.deleted_at.is_(None), Project.is_demo.is_(False))):
                    db.add(ProjectMember(project_id=pid, user_id=user.id, role="reader"))
            audit(db, user.id, "user.directory_create", "user", user.id, role=row.new_user_role)
    if user.kind != "human" or not user.active or user.auth_source != "directory":
        return None
    if entry.display_name and user.display_name != entry.display_name[:150]:
        user.display_name = entry.display_name[:150]
    return user
