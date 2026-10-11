"""FastAPI bağımlılıkları: istek başına DB oturumu, oturumdan aktör, CSRF."""

from __future__ import annotations

import hmac
from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from metis.core.db import session_factory, utcnow
from metis.core.errors import AppError
from metis.core.models import User, UserSession
from metis.core.security import digest

SESSION_COOKIE = "metis_session"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_db() -> Iterator[Session]:
    """İstek oturumu. Daima `Depends(get_db, scope="function")` ile kullanılır: commit/rollback yanıt GÖNDERİLMEDEN
    önce çalışır (varsayılan "request" kapsamında yanıt gittikten sonra çalışır; commit hatası 200 ile kaybolurdu)."""
    db = session_factory()()
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def load_session(db: Session, request: Request) -> tuple[UserSession, User] | None:
    raw = request.cookies.get(SESSION_COOKIE, "")
    if not raw:
        return None
    sess = db.scalar(select(UserSession).where(UserSession.token_digest == digest(raw)))
    if not sess or sess.expires_at <= utcnow():
        return None
    user = db.get(User, sess.user_id)
    if not user or not user.active or user.kind != "human":
        return None
    return sess, user


def current_session(request: Request, db: Session = Depends(get_db, scope="function")) -> tuple[UserSession, User]:
    loaded = load_session(db, request)
    if not loaded:
        raise AppError("UNAUTHENTICATED", "login required")
    sess, user = loaded
    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        if not sent or not hmac.compare_digest(sent, sess.csrf):
            raise AppError("CSRF_REJECTED", "csrf token missing or invalid")
    request.state.actor_id = str(user.id)
    return sess, user


def current_user_any(pair: tuple[UserSession, User] = Depends(current_session)) -> User:
    """Parola değişimi zorunlu olsa bile erişilebilen uçlar için."""
    return pair[1]


def current_user(pair: tuple[UserSession, User] = Depends(current_session)) -> User:
    user = pair[1]
    if user.must_change_password:
        raise AppError("PASSWORD_CHANGE_REQUIRED", "password change required")
    return user
