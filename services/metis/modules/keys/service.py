"""Kişisel API anahtarı ve kullanım dökümü (2.0.28, ürün sahibinin kararı 2026-10-27).

- Herkes modelleri kendi anahtarıyla çağırır: Mentor, yayın öncesi kontrol ve kişinin başlattığı Metis görevleri.
  Anahtarı olmayan kişi model kullanamaz (Mentor ilgili bölümleri gösterir, cevap yazmaz).
- Sağlayıcının anahtarı (yöneticinin) ortak anahtardır: benchmark/probe, zamanlanmış bakım ve arama zenginleştirmesi onunla
  çalışır; model yeterliliği (benchmark referansı) yalnız onunla ölçülür. Yönetici kişisel anahtar eklemediyse kendi
  sorularında da ortak anahtarı (kendi anahtarını) kullanır.
- Anahtar şifreli saklanır (AES-GCM, AAD kişi + sağlayıcı), hiçbir yanıtta, logda ya da denetim kaydında yer almaz.
- Kullanım: kişi kendi çağrılarını görür; yönetici kişi başına yalnız toplamları görür (soru içerikleri değil).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import Integer, func, select
from sqlalchemy.orm import Session

from metis.core.access import require_admin, require_human
from metis.core.audit import audit
from metis.core.db import transaction, utcnow
from metis.core.errors import AppError
from metis.core.models import Model, ModelCall, Provider, User, UserProviderKey
from metis.core.security import encrypt_secret, user_key_aad
from metis.llm import contracts
from metis.llm.client import KeyRef, ModelClient

USAGE_DAYS = 30


def key_for(db: Session, user: User, provider_id: uuid.UUID) -> KeyRef | None:
    """Kişinin bu sağlayıcıdaki anahtarı; yoksa yönetici için ortak anahtar (kendi anahtarı), diğerleri için None."""
    if user.kind != "human":
        return None
    if db.get(UserProviderKey, (user.id, provider_id)) is not None:
        return KeyRef(user_id=user.id, personal=True)
    if user.is_admin:
        return KeyRef(user_id=user.id, personal=False)
    return None


def _provider(db: Session, provider_id: uuid.UUID) -> Provider:
    p = db.get(Provider, provider_id)
    if p is None or p.deleted_at is not None:
        raise AppError("NOT_FOUND", "provider not found")
    return p


def my_keys(db: Session, user: User) -> list[dict]:
    require_human(user)
    rows = {k.provider_id: k for k in db.scalars(select(UserProviderKey).where(UserProviderKey.user_id == user.id))}
    out = []
    for p in db.scalars(select(Provider).where(Provider.deleted_at.is_(None)).order_by(Provider.name, Provider.id)):
        models = list(db.scalars(select(Model.display_name).where(Model.provider_id == p.id, Model.deleted_at.is_(None), Model.enabled.is_(True)).order_by(Model.display_name)))
        k = rows.get(p.id)
        out.append(
            {
                "provider_id": p.id,
                "provider_name": p.name,
                "models": models,
                "has_key": k is not None,
                "updated_at": k.updated_at if k else None,
                "checked_at": k.checked_at if k else None,
                "check_ok": k.check_ok if k else None,
                "check_error": k.check_error if k else None,
                "uses_shared": k is None and user.is_admin,
            }
        )
    return out


def set_key(db: Session, user: User, provider_id: uuid.UUID, api_key: str) -> None:
    require_human(user)
    _provider(db, provider_id)
    secret = api_key.strip()
    if len(secret) < 8:
        raise AppError("VALIDATION_ERROR", "api key too short", fields=[{"field": "api_key", "type": "too_short"}])
    enc = encrypt_secret(secret, aad=user_key_aad(user.id, provider_id))
    row = db.get(UserProviderKey, (user.id, provider_id))
    now = utcnow()
    if row is None:
        db.add(UserProviderKey(user_id=user.id, provider_id=provider_id, secret_enc=enc, secret_version=1, created_at=now, updated_at=now))
    else:
        row.secret_enc = enc
        row.secret_version += 1
        row.updated_at = now
        row.checked_at = row.check_ok = row.check_error = None
    audit(db, user.id, "user_key.set", "provider", provider_id)


def delete_key(db: Session, user: User, provider_id: uuid.UUID) -> None:
    require_human(user)
    row = db.get(UserProviderKey, (user.id, provider_id))
    if row is None:
        raise AppError("NOT_FOUND", "key not found")
    db.delete(row)
    audit(db, user.id, "user_key.delete", "provider", provider_id)


def check_key(user_id: uuid.UUID, provider_id: uuid.UUID) -> dict:
    """Anahtarı küçük bir bağlantı isteğiyle dener (probe istemi, önbelleksiz). Model yeterliliğini değiştirmez:
    yeterlilik yöneticinin ortak anahtarıyla ölçülür."""
    with transaction() as db:
        user = db.get(User, user_id)
        assert user is not None
        require_human(user)
        provider = _provider(db, provider_id)
        if db.get(UserProviderKey, (user_id, provider_id)) is None:
            raise AppError("NOT_FOUND", "key not found")
        model = db.scalars(select(Model).where(Model.provider_id == provider_id, Model.deleted_at.is_(None), Model.enabled.is_(True)).order_by(Model.display_name, Model.id)).first()
        if model is None:
            raise AppError("NOT_FOUND", "provider has no enabled model")
        db.expunge(model)
        db.expunge(provider)
    res = ModelClient().call(
        model, provider, prompt_id="probe-v1", payload={"echo": "connection"}, schema=contracts.ProbeOut, purpose="key_check",
        cache=False, repairs=0, max_tokens=200, key=KeyRef(user_id=user_id, personal=True),
    )
    # Bağlantı ve kimlik geçtiyse anahtar çalışıyor; modelin biçim hatası anahtarın sorunu değildir.
    ok = res.ok or res.error in ("INVALID_RESPONSE", "VALIDATION")
    with transaction() as db:
        row = db.get(UserProviderKey, (user_id, provider_id))
        if row is not None:
            row.checked_at = utcnow()
            row.check_ok = ok
            row.check_error = None if ok else res.error
    return {"ok": ok, "error": None if ok else res.error, "latency_ms": res.latency_ms, "model": model.display_name}


def _token(name: str):  # noqa: ANN202
    return func.coalesce(func.sum(func.cast(ModelCall.usage[name].astext, Integer)), 0)


def _since():  # noqa: ANN202
    return utcnow() - timedelta(days=USAGE_DAYS)


def my_usage(db: Session, user: User) -> dict:
    require_human(user)
    q = (
        select(ModelCall.purpose, ModelCall.key_source, func.count(), func.count().filter(ModelCall.state == "cached"), _token("prompt_tokens"), _token("completion_tokens"))
        .where(ModelCall.user_id == user.id, ModelCall.created_at >= _since())
        .group_by(ModelCall.purpose, ModelCall.key_source)
        .order_by(ModelCall.purpose, ModelCall.key_source)
    )
    rows = [{"purpose": p, "key_source": k, "calls": n, "cached": c, "prompt_tokens": pt, "completion_tokens": ct} for p, k, n, c, pt, ct in db.execute(q)]
    return {"days": USAGE_DAYS, "rows": rows}


def usage_by_user(db: Session, admin: User) -> dict:
    """Yönetici: kişi başına toplam çağrı ve token (içerik yok). Kişisiz satır = sistem işleri (ortak anahtar)."""
    require_admin(admin)
    q = (
        select(ModelCall.user_id, User.display_name, User.username, ModelCall.key_source, func.count(), _token("prompt_tokens"), _token("completion_tokens"))
        .outerjoin(User, User.id == ModelCall.user_id)
        .where(ModelCall.created_at >= _since(), ModelCall.state != "cached")
        .group_by(ModelCall.user_id, User.display_name, User.username, ModelCall.key_source)
        .order_by(func.count().desc())
    )
    rows = [
        {"user_id": uid, "name": (dn or un) if uid else None, "key_source": k, "calls": n, "prompt_tokens": pt, "completion_tokens": ct}
        for uid, dn, un, k, n, pt, ct in db.execute(q)
    ]
    return {"days": USAGE_DAYS, "rows": rows}
