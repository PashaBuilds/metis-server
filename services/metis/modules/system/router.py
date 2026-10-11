"""Sağlık uçları (/health/live, /health/ready) ve yönetici için sistem durumu."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from metis import __version__
from metis.core.access import require_admin
from metis.core.deps import current_user, get_db
from metis.core.errors import AppError
from metis.core.models import LegacyImportRun, User
from metis.modules.system import service

router = APIRouter(tags=["system"])


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "live", "version": __version__}


@router.get("/health/ready")
def ready(db: Session = Depends(get_db, scope="function")) -> JSONResponse:
    try:
        db.execute(text("SELECT 1"))
        revision = service.migration_revision(db)
    except Exception:  # noqa: BLE001
        return JSONResponse({"status": "not_ready", "reason": "database"}, status_code=503)
    if revision != service.expected_revision():
        return JSONResponse({"status": "not_ready", "reason": "migration", "revision": revision}, status_code=503)
    return JSONResponse({"status": "ready", "revision": revision, "version": __version__})


@router.get("/system/status", response_model=service.SystemStatus)
def system_status(user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> service.SystemStatus:
    return service.status(db, user)


@router.post("/demo", status_code=201)
def create_demo(user: User = Depends(current_user)) -> dict:
    """Kurgusal çalışma alanını oluşturur — yalnız geliştirme profili ve yönetici."""
    from metis.core.access import require_admin
    from metis.seed.demo import create_demo_workspace

    require_admin(user)
    return create_demo_workspace(admin_username=user.username)


class LegacyRunRow(BaseModel):
    id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None
    mode: str
    state: str
    source_sha256: str
    summary: dict


class LegacyRunDetail(LegacyRunRow):
    report_md: str
    report: dict


def _run_summary(run: LegacyImportRun) -> dict:
    report = run.report or {}
    v = report.get("verification", {})
    return {
        "target_counts": report.get("target_counts", {}),
        "skipped": len(report.get("skipped", [])),
        "verification_ok": report.get("verification_ok"),
        "active_pages": v.get("active_pages", {}).get("count"),
    }


@router.get("/legacy-import/runs", response_model=list[LegacyRunRow])
def legacy_runs(user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> list[LegacyRunRow]:
    require_admin(user)
    runs = db.scalars(select(LegacyImportRun).order_by(LegacyImportRun.started_at.desc()).limit(50)).all()
    return [LegacyRunRow(id=r.id, started_at=r.started_at, finished_at=r.finished_at, mode=r.mode, state=r.state, source_sha256=r.source_sha256, summary=_run_summary(r)) for r in runs]


@router.get("/legacy-import/runs/{run_id}", response_model=LegacyRunDetail)
def legacy_run(run_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> LegacyRunDetail:
    require_admin(user)
    r = db.get(LegacyImportRun, run_id)
    if r is None:
        raise AppError("NOT_FOUND", "import run not found")
    return LegacyRunDetail(id=r.id, started_at=r.started_at, finished_at=r.finished_at, mode=r.mode, state=r.state, source_sha256=r.source_sha256, summary=_run_summary(r), report_md=r.report_md, report=r.report)
