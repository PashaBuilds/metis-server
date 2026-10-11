from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from metis.core.deps import current_user, get_db
from metis.core.models import User
from metis.modules.search import service

router = APIRouter(tags=["search"])


@router.get("/projects/{project_id}/search", response_model=service.SearchOut)
def search(
    project_id: uuid.UUID,
    q: str = Query(default="", max_length=500),
    kind: str | None = None,
    domain: list[str] = Query(default=[]),
    yatt: list[str] = Query(default=[]),
    kart: list[str] = Query(default=[]),
    proje: list[str] = Query(default=[]),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
) -> service.SearchOut:
    scope = {"domain": domain, "yatt": yatt, "kart": kart, "proje": proje}
    return service.search(db, user, project_id, q, scope, kind, limit)
