from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from metis.core.deps import current_user, get_db
from metis.core.models import User
from metis.modules.health import service

router = APIRouter(tags=["health"])


@router.get("/projects/{project_id}/findings", response_model=service.FindingListOut)
def findings(
    project_id: uuid.UUID,
    state: str = Query(default="open", pattern="^(open|resolved)$"),
    kind: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
) -> service.FindingListOut:
    return service.list_findings(db, user, project_id, state, kind)


@router.get("/findings/{finding_id}", response_model=service.FindingOut)
def finding(finding_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> service.FindingOut:
    out = service.finding_out(db, user, service.get_finding(db, user, finding_id))
    assert out is not None
    return out


@router.post("/findings/{finding_id}/resolve", response_model=service.FindingOut)
def resolve(finding_id: uuid.UUID, data: service.ResolveIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> service.FindingOut:
    f = service.resolve(db, user, finding_id, data.reason)
    out = service.finding_out(db, user, f)
    assert out is not None
    return out


@router.post("/projects/{project_id}/health/scan", status_code=202)
def scan(project_id: uuid.UUID, data: service.ScanIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> dict:
    return {"job_id": str(service.scan_now(db, user, project_id, data))}


@router.get("/projects/{project_id}/schedule", response_model=service.ScheduleOut)
def get_schedule(project_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> service.ScheduleOut:
    return service.get_schedule(db, user, project_id)


@router.put("/projects/{project_id}/schedule", response_model=service.ScheduleOut)
def set_schedule(project_id: uuid.UUID, data: service.ScheduleIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> service.ScheduleOut:
    return service.set_schedule(db, user, project_id, data)


@router.post("/findings/{finding_id}/case", response_model=service.CaseOut)
def open_case(finding_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> service.CaseOut:
    return service.open_case(db, user, finding_id)


@router.post("/conflict-cases/{case_id}/choose", response_model=service.CaseOut)
def choose(case_id: uuid.UUID, data: service.ChooseIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> service.CaseOut:
    return service.choose(db, user, case_id, data)
