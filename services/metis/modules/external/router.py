from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from metis.core.deps import current_user, get_db
from metis.core.models import User
from metis.modules.external import schemas, service

router = APIRouter(tags=["external"])


@router.get("/external/connections", response_model=list[schemas.ConnectionOut], response_model_exclude_none=True)
def list_connections(user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> list[schemas.ConnectionOut]:
    """Yönetici tüm bağlantıları görür; diğer kullanıcılar yalnız etkin olanların adını ve izinli kapsamlarını."""
    return service.list_connections(db, user)


@router.post("/external/connections", response_model=schemas.ConnectionOut, status_code=201)
def create_connection(data: schemas.ConnectionIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> schemas.ConnectionOut:
    return service.create_connection(db, user, data)


@router.put("/external/connections/{connection_id}", response_model=schemas.ConnectionOut)
def update_connection(
    connection_id: uuid.UUID, data: schemas.ConnectionIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> schemas.ConnectionOut:
    return service.update_connection(db, user, connection_id, data)


@router.delete("/external/connections/{connection_id}", status_code=204)
def delete_connection(connection_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> Response:
    service.delete_connection(db, user, connection_id)
    return Response(status_code=204)


@router.post("/external/connections/test", response_model=schemas.ConnectionTestOut)
def test_connection(data: schemas.ConnectionTestIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> schemas.ConnectionTestOut:
    """Kaydetmeden dener; hiçbir şey içe aktarmaz."""
    return service.test_connection(db, user, data)


@router.get("/projects/{project_id}/external/search", response_model=list[schemas.SearchItemOut])
def search(
    project_id: uuid.UUID,
    connection_id: uuid.UUID,
    q: str = Query(min_length=1, max_length=200),
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
) -> list[schemas.SearchItemOut]:
    return service.search(db, user, project_id, connection_id, q)


@router.post("/projects/{project_id}/external/preview", response_model=schemas.PreviewOut, status_code=201)
def preview(project_id: uuid.UUID, data: schemas.PreviewIn, user: User = Depends(current_user)) -> schemas.PreviewOut:
    """Çeker, dönüştürür, ekleri kullanıcı adına yükler; taslak oluşturmaz. Sonuç taslak formunu doldurur."""
    return service.preview(user.id, project_id, data)
