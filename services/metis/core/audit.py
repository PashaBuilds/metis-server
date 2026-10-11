"""Değişmez denetim kaydı ve correlation ID."""

from __future__ import annotations

import contextvars
import uuid
from typing import Any

from sqlalchemy.orm import Session

from metis.core.models import AuditEvent

correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")


def current_correlation() -> str:
    value = correlation_id.get()
    if not value:
        value = uuid.uuid4().hex
        correlation_id.set(value)
    return value


def _jsonable(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_jsonable(v) for v in value]
    return value


def audit(
    db: Session, actor_id: uuid.UUID | None, op: str, target_type: str = "", target_id: Any = "", **detail: Any
) -> None:
    db.add(
        AuditEvent(
            actor_id=actor_id,
            op=op,
            target_type=target_type,
            target_id=str(target_id) if target_id else "",
            detail=_jsonable(detail),
            correlation_id=current_correlation(),
        )
    )
