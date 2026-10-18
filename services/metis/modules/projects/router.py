from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from metis.core.deps import current_user, get_db
from metis.core.models import User
from metis.modules.projects import schemas, service

router = APIRouter(tags=["projects"])


@router.get("/projects", response_model=list[schemas.ProjectOut])
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> list[schemas.ProjectOut]:
    return [service.to_out(db, user, p) for p in service.list_projects(db, user)]


@router.post("/projects", response_model=schemas.ProjectOut, status_code=201)
def create_project(
    data: schemas.ProjectCreateInput, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> schemas.ProjectOut:
    return service.to_out(db, user, service.create(db, user, data))


@router.get("/projects/{project_id}", response_model=schemas.ProjectOut)
def get_project(
    project_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> schemas.ProjectOut:
    return service.to_out(db, user, service.get(db, user, project_id))


@router.patch("/projects/{project_id}", response_model=schemas.ProjectOut)
def update_project(
    project_id: uuid.UUID,
    data: schemas.ProjectUpdateInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
) -> schemas.ProjectOut:
    return service.to_out(db, user, service.update(db, user, project_id, data))


@router.get("/projects/{project_id}/members", response_model=list[schemas.MemberOut])
def list_members(
    project_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> list[schemas.MemberOut]:
    return service.members(db, user, project_id)


@router.put("/projects/{project_id}/members", status_code=204)
def set_member(
    project_id: uuid.UUID,
    data: schemas.MemberSetInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
) -> Response:
    service.set_member(db, user, project_id, data)
    return Response(status_code=204)


class UpdatedPage(schemas.BaseModel):  # type: ignore[name-defined]
    page_id: uuid.UUID
    title: str
    by_name: str
    published_at: datetime


class InboxOut(schemas.BaseModel):  # type: ignore[name-defined]
    reviews_waiting: int
    questions_waiting: int
    open_findings: int
    updated_pages: list[UpdatedPage] = []


@router.get("/projects/{project_id}/inbox", response_model=InboxOut)
def inbox(project_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> InboxOut:
    return InboxOut(**service.inbox(db, user, project_id))
