"""İçerik adresli blob deposu: <data>/blobs/<ilk 2>/<sha256>. Yazma atomik (tmp + replace)."""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from pathlib import Path

from metis.core.config import get_settings

HEX64 = re.compile(r"^[0-9a-f]{64}$")


def blob_path(digest: str, root: Path | None = None) -> Path:
    if not HEX64.match(digest):
        raise ValueError("invalid sha256")
    base = root or get_settings().blob_dir
    return base / digest[:2] / digest


def put_blob(data: bytes, root: Path | None = None) -> str:
    digest = hashlib.sha256(data).hexdigest()
    target = blob_path(digest, root)
    if target.exists():
        return digest
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{digest}.{uuid.uuid4().hex}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, target)
    return digest


def read_blob(digest: str, root: Path | None = None) -> bytes:
    data = blob_path(digest, root).read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("blob integrity failure")
    return data


def blob_exists(digest: str, root: Path | None = None) -> bool:
    return blob_path(digest, root).is_file()
