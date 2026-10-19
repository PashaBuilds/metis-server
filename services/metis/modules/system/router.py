"""Sağlık uçları (/health/live, /health/ready) ve yönetici için sistem durumu."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from metis import __version__
from metis.core.access import require_admin
from metis.core.deps import current_user, get_db
from metis.core.models import User
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
    from metis.seed.demo import create_demo_workspace

    require_admin(user)
    return create_demo_workspace(admin_username=user.username)
