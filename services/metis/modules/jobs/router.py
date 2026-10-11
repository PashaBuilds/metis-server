from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from metis.core.db import reader
from metis.core.deps import current_user, get_db
from metis.core.models import User
from metis.modules.jobs import service

router = APIRouter(tags=["jobs"])


@router.post("/projects/{project_id}/jobs", response_model=service.JobRow, status_code=201)
def create_job(project_id: uuid.UUID, data: service.JobCreateIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> service.JobRow:
    job, _ = service.enqueue(db, user, project_id, data)
    return service.job_row(db, job)


@router.get("/projects/{project_id}/jobs", response_model=list[service.JobRow])
def list_jobs(project_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> list[service.JobRow]:
    return service.list_jobs(db, user, project_id)


@router.get("/jobs/{job_id}", response_model=service.JobDetail)
def get_job(job_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> service.JobDetail:
    return service.job_detail(db, user, job_id)


@router.post("/jobs/{job_id}/cancel", response_model=service.JobDetail)
def cancel(job_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> service.JobDetail:
    service.cancel(db, user, job_id)
    return service.job_detail(db, user, job_id)


@router.post("/jobs/{job_id}/retry", response_model=service.JobDetail)
def retry(job_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> service.JobDetail:
    service.retry(db, user, job_id)
    return service.job_detail(db, user, job_id)


@router.post("/jobs/{job_id}/answer", response_model=service.JobDetail)
def answer(job_id: uuid.UUID, data: service.AnswerIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> service.JobDetail:
    service.answer_question(db, user, job_id, data)
    return service.job_detail(db, user, job_id)


@router.delete("/jobs/{job_id}", status_code=204)
def delete(job_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> Response:
    service.delete_job(db, user, job_id)
    return Response(status_code=204)


@router.get("/jobs/{job_id}/events")
async def events(job_id: uuid.UUID, user: User = Depends(current_user), last_event_id: str | None = Header(default=None, alias="Last-Event-ID")) -> StreamingResponse:
    """SSE: job_events tablosundan; Last-Event-ID ile kaldığı yerden devam eder. 15 sn heartbeat; ters vekilde buffering kapalı."""
    try:
        cursor = int(last_event_id or 0)
    except ValueError:
        cursor = 0
    user_id = user.id

    def fetch(after: int) -> list[tuple[int, str, dict]]:
        with reader() as db:
            u = db.get(User, user_id)
            return [(e.id, e.kind, e.data) for e in service.events_after(db, u, job_id, after)]  # type: ignore[arg-type]

    with reader() as db:
        service.get_job(db, db.get(User, user_id), job_id)  # type: ignore[arg-type]

    async def stream():  # noqa: ANN202
        nonlocal cursor
        idle = 0.0
        while True:
            rows = await asyncio.to_thread(fetch, cursor)
            for eid, kind, data in rows:
                cursor = eid
                yield f"id: {eid}\nevent: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                if kind == "state" and data.get("state") in ("completed", "failed", "cancelled", "budget_exceeded"):
                    yield "event: end\ndata: {}\n\n"
                    return
            await asyncio.sleep(1)
            idle += 1
            if idle >= 15:
                idle = 0
                yield ": heartbeat\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
