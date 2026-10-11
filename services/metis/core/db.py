"""SQLAlchemy motoru, oturum fabrikası ve değişmezlik (immutability) ORM kancası."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from metis.core.config import get_settings


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> uuid.UUID:
    return uuid.uuid4()


_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def engine() -> Engine:
    global _engine, _factory
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=10,
            connect_args={"options": "-c timezone=UTC"},
        )
        _factory = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def session_factory() -> sessionmaker[Session]:
    engine()
    assert _factory is not None
    return _factory


def dispose_engine() -> None:
    global _engine, _factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _factory = None


@contextmanager
def transaction() -> Iterator[Session]:
    """Tek transaction: başarılıysa commit, hata olursa rollback."""
    with session_factory().begin() as db:
        yield db


@contextmanager
def reader() -> Iterator[Session]:
    db = session_factory()()
    try:
        yield db
    finally:
        db.close()


IMMUTABLE_TABLES: tuple[str, ...] = (
    "source_revisions",
    "evidence",
    "page_revisions",
    "claims",
    "claim_evidence",
    "relation_revisions",
    "relation_revision_evidence",
    "reviews",
    "publications",
    "publication_pages",
    "publication_relations",
    "audit_events",
)


class ImmutableRecordError(RuntimeError):
    pass


@event.listens_for(Session, "before_flush")
def _guard_immutable(session: Session, _context, _instances) -> None:  # noqa: ANN001
    for obj in list(session.dirty) + list(session.deleted):
        table = getattr(obj, "__tablename__", None)
        if table in IMMUTABLE_TABLES and (obj in session.deleted or session.is_modified(obj)):
            raise ImmutableRecordError(f"{table} kayıtları değiştirilemez veya silinemez.")
