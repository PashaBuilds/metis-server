from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from metis.core.deps import current_user, get_db
from metis.core.models import User
from metis.modules.knowledge import schemas, service

router = APIRouter(tags=["knowledge"])


@router.get("/projects/{project_id}/domains", response_model=list[schemas.DomainRow])
def domains(
    project_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> list[schemas.DomainRow]:
    return service.domains(db, user, project_id)


@router.get("/projects/{project_id}/pages", response_model=schemas.PageListOut)
def list_pages(
    project_id: uuid.UUID,
    domain: str | None = None,
    yatt: list[str] = Query(default=[]),
    kart: list[str] = Query(default=[]),
    proje: list[str] = Query(default=[]),
    kind: str | None = None,
    freshness: str | None = None,
    q: str | None = Query(default=None, max_length=300),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
) -> schemas.PageListOut:
    return service.list_pages(
        db,
        user,
        project_id,
        domain=domain,
        yatt=yatt,
        kart=kart,
        proje=proje,
        kind=kind,
        freshness=freshness,
        q=q,
        cursor=cursor,
        limit=limit,
    )


@router.get("/pages/{page_id}", response_model=schemas.PageDetailOut)
def page_detail(
    page_id: uuid.UUID, rev: uuid.UUID | None = None, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> schemas.PageDetailOut:
    return service.page_detail(db, user, page_id, rev)


@router.get("/pages/{page_id}/history", response_model=list[schemas.HistoryRow])
def history(
    page_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> list[schemas.HistoryRow]:
    return service.history(db, user, page_id)


@router.get("/pages/{page_id}/compare", response_model=schemas.CompareOut)
def compare(
    page_id: uuid.UUID, a: uuid.UUID, b: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> schemas.CompareOut:
    return service.compare(db, user, page_id, a, b)


@router.post("/pages/{page_id}/report", status_code=201)
def report(
    page_id: uuid.UUID, data: schemas.ReportIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> dict:
    return {"finding_id": str(service.report_issue(db, user, page_id, data.text))}


@router.get("/projects/{project_id}/export.zip", response_class=Response, responses={200: {"content": {"application/zip": {}}}})
def export_zip(project_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> Response:
    from metis.core.audit import audit
    from metis.modules.knowledge.export import export_zip as build

    filename, data = build(db, user, project_id)
    audit(db, user.id, "project.export", "project", project_id, bytes=len(data))
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})
