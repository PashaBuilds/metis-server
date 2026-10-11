from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from metis.core.deps import current_user, get_db
from metis.core.models import User
from metis.modules.scopes import schemas, service

router = APIRouter(tags=["scopes"])


@router.get("/projects/{project_id}/scopes", response_model=schemas.CatalogOut)
def get_catalog(
    project_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> schemas.CatalogOut:
    return service.catalog(db, user, project_id)


@router.post("/projects/{project_id}/scopes", response_model=schemas.ScopeValueOut, status_code=201)
def add_value(
    project_id: uuid.UUID,
    data: schemas.ScopeValueInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
) -> schemas.ScopeValueOut:
    row = service.add_value(db, user, project_id, data)
    return schemas.ScopeValueOut(id=row.id, dimension=row.dimension, value=row.value)  # type: ignore[arg-type]


@router.delete("/projects/{project_id}/scopes/{value_id}", status_code=204)
def delete_value(
    project_id: uuid.UUID, value_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> Response:
    service.delete_value(db, user, project_id, value_id)
    return Response(status_code=204)
