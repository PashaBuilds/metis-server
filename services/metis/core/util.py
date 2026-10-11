"""Küçük saf yardımcılar."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any


def _default(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=_default)


def hash_json(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode()).hexdigest()


def parse_uuid(value: Any) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def fingerprint(*parts: object) -> str:
    """Tekilleştirme parmak izi (64 karakter)."""
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
