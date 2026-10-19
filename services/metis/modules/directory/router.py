from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from metis.core.deps import current_user, get_db
from metis.core.models import User
from metis.modules.directory import schemas, service

router = APIRouter(tags=["directory"])


@router.get("/auth/methods", response_model=schemas.AuthMethodsOut)
def methods(db: Session = Depends(get_db, scope="function")) -> schemas.AuthMethodsOut:
    """Giriş ekranı için (oturum gerekmez): şirket hesabıyla giriş açık mı."""
    return schemas.AuthMethodsOut(directory=service.enabled(db))


@router.get("/directory", response_model=schemas.DirectorySettingsOut)
def get_settings(user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> schemas.DirectorySettingsOut:
    return service.settings_out(db, user)


@router.put("/directory", response_model=schemas.DirectorySettingsOut)
def put_settings(
    data: schemas.DirectorySettingsIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> schemas.DirectorySettingsOut:
    return service.save(db, user, data)


@router.post("/directory/test", response_model=schemas.DirectoryTestOut)
def test(data: schemas.DirectoryTestIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> schemas.DirectoryTestOut:
    return service.test(db, user, data)
