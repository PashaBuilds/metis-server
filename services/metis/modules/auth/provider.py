"""Kimlik doğrulama sağlayıcı arayüzü.

v2 ilk sürüm yalnız yerel hesap kullanır. Şirket AD/LDAP entegrasyonu ileride bu
arayüzün yeni bir uygulamasıyla eklenir; çağıran kod değişmez.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from metis.core.models import User
from metis.core.security import hash_password, verify_password


class AuthProvider(Protocol):
    name: str

    def authenticate(self, db: Session, username: str, password: str) -> User | None: ...


class LocalAuthProvider:
    name = "local"

    def authenticate(self, db: Session, username: str, password: str) -> User | None:
        user = db.scalar(select(User).where(func.lower(User.username) == username.strip().lower()))
        if not user or user.kind != "human" or not user.active:
            # Zamanlama farkını azaltmak için yine de bir hash hesapla.
            verify_password(password, "scrypt$32768$8$1$AAAAAAAAAAAAAAAAAAAAAA==$AAAA")
            return None
        ok, rehash = verify_password(password, user.password_hash)
        if not ok:
            return None
        if rehash:
            user.password_hash = hash_password(password)
        return user


def get_provider() -> AuthProvider:
    return LocalAuthProvider()
