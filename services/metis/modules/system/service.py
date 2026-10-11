from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from metis import __version__
from metis.core.access import require_admin
from metis.core.config import get_settings
from metis.core.db import utcnow
from metis.core.models import Job, Model, ModelCall, ModelProbe, User

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


@lru_cache(maxsize=1)
def expected_revision() -> str:
    cfg = Config(str(MIGRATIONS / "alembic.ini"))
    cfg.set_main_option("script_location", str(MIGRATIONS))
    return ScriptDirectory.from_config(cfg).get_current_head() or ""


def migration_revision(db: Session) -> str:
    return db.execute(text("SELECT version_num FROM alembic_version")).scalar() or ""


class ModelEndpointStatus(BaseModel):
    model_id: str
    display_name: str
    connection: str
    checked_at: datetime | None


class SystemStatus(BaseModel):
    version: str
    profile: str
    migration_revision: str
    migration_expected: str
    queue_waiting: int
    queue_oldest_wait_s: float | None
    running_jobs: int
    expired_leases: int
    failed_jobs_24h: int
    model_calls_24h: int
    model_error_rate_24h: float | None
    disk_free_bytes: int | None
    disk_total_bytes: int | None
    last_backup: dict | None
    fuzzy_search_available: bool
    model_endpoints: list[ModelEndpointStatus]


def last_backup_info() -> dict | None:
    marker = get_settings().data_dir / "backups" / "last-backup.json"
    if not marker.is_file():
        return None
    try:
        return json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def trgm_available(db: Session) -> bool:
    return bool(db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")).scalar())


def status(db: Session, user: User) -> SystemStatus:
    require_admin(user)
    now = utcnow()
    waiting = db.scalar(select(func.count()).select_from(Job).where(Job.state == "queued")) or 0
    oldest = db.scalar(select(func.min(Job.created_at)).where(Job.state == "queued"))
    running = db.scalar(select(func.count()).select_from(Job).where(Job.state == "running")) or 0
    expired = db.scalar(select(func.count()).select_from(Job).where(Job.state == "running", Job.lease_until < now)) or 0
    since = now - timedelta(hours=24)
    failed = (
        db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.state.in_(["failed", "budget_exceeded"]), Job.updated_at >= since)
        )
        or 0
    )
    calls = (
        db.scalar(
            select(func.count())
            .select_from(ModelCall)
            .where(ModelCall.created_at >= since, ModelCall.state != "cached")
        )
        or 0
    )
    errors = (
        db.scalar(
            select(func.count())
            .select_from(ModelCall)
            .where(ModelCall.created_at >= since, ModelCall.state == "failed")
        )
        or 0
    )
    try:
        usage = shutil.disk_usage(get_settings().data_dir)
        free, total = usage.free, usage.total
    except OSError:
        free = total = None
    endpoints = []
    for model in db.scalars(select(Model).where(Model.deleted_at.is_(None)).order_by(Model.display_name)):
        probe = db.scalar(
            select(ModelProbe)
            .where(ModelProbe.model_id == model.id, ModelProbe.capability == "connection")
            .order_by(ModelProbe.at.desc())
            .limit(1)
        )
        endpoints.append(
            ModelEndpointStatus(
                model_id=str(model.id),
                display_name=model.display_name,
                connection=probe.status if probe else "unknown",
                checked_at=probe.at if probe else None,
            )
        )
    return SystemStatus(
        version=__version__,
        profile=get_settings().env,
        migration_revision=migration_revision(db),
        migration_expected=expected_revision(),
        queue_waiting=waiting,
        queue_oldest_wait_s=(now - oldest).total_seconds() if oldest else None,
        running_jobs=running,
        expired_leases=expired,
        failed_jobs_24h=failed,
        model_calls_24h=calls,
        model_error_rate_24h=(errors / calls) if calls else None,
        disk_free_bytes=free,
        disk_total_bytes=total,
        last_backup=last_backup_info(),
        fuzzy_search_available=trgm_available(db),
        model_endpoints=endpoints,
    )
