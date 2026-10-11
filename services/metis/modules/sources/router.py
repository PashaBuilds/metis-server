from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy.orm import Session

from metis.core.config import get_settings
from metis.core.deps import current_user, get_db
from metis.core.errors import AppError
from metis.core.models import User
from metis.modules.sources import schemas, service

router = APIRouter(tags=["sources"])


async def _read_upload(file: UploadFile | None) -> tuple[str, bytes] | None:
    if file is None or not file.filename:
        return None
    limit = get_settings().max_upload_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise AppError("FILE_TOO_LARGE", "file exceeds size limit", limit=limit)
    return file.filename, data


def _parse(model, raw: str):  # noqa: ANN001, ANN202
    try:
        return model.model_validate_json(raw)
    except ValidationError as exc:
        fields = [{"field": ".".join(str(p) for p in e["loc"]), "type": e["type"]} for e in exc.errors()]
        raise AppError("VALIDATION_ERROR", "invalid metadata", fields=fields) from exc


@router.get("/projects/{project_id}/sources", response_model=schemas.SourceListOut)
def list_sources(
    project_id: uuid.UUID,
    q: str = Query(default="", max_length=200),
    kind: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
) -> schemas.SourceListOut:
    return service.list_sources(db, user, project_id, q, kind, cursor, limit)


@router.post("/projects/{project_id}/sources", response_model=schemas.SourceRevisionCreated, status_code=201)
async def create_source(
    project_id: uuid.UUID,
    meta: str = Form(...),
    file: UploadFile | None = File(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
) -> schemas.SourceRevisionCreated:
    data: schemas.SourceMetaIn = _parse(schemas.SourceMetaIn, meta)
    upload = await _read_upload(file)
    from starlette.concurrency import run_in_threadpool

    content = await run_in_threadpool(service.prepare_content, data.kind, data.text, upload)

    def write() -> schemas.SourceRevisionCreated:
        source, rev = service.create_source(db, user, project_id, data, content)
        return schemas.SourceRevisionCreated(
            source=service.source_out(db, source), revision=service.revision_out(db, rev, source), affected_pages=[]
        )

    return await run_in_threadpool(write)


@router.get("/sources/{source_id}", response_model=schemas.SourceDetailOut)
def get_source(
    source_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> schemas.SourceDetailOut:
    return service.source_detail(db, user, source_id)


@router.post("/sources/{source_id}/revisions", response_model=schemas.SourceRevisionCreated, status_code=201)
async def add_revision(
    source_id: uuid.UUID,
    meta: str = Form(...),
    file: UploadFile | None = File(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
) -> schemas.SourceRevisionCreated:
    from starlette.concurrency import run_in_threadpool

    data: schemas.RevisionMetaIn = _parse(schemas.RevisionMetaIn, meta)
    upload = await _read_upload(file)
    kind = (await run_in_threadpool(service.get_source, db, user, source_id)).kind
    content = await run_in_threadpool(service.prepare_content, kind, data.text, upload)

    def write() -> schemas.SourceRevisionCreated:
        source, rev, affected = service.add_revision(db, user, source_id, data, content)
        return schemas.SourceRevisionCreated(
            source=service.source_out(db, source),
            revision=service.revision_out(db, rev, source),
            affected_pages=affected,
        )

    return await run_in_threadpool(write)


@router.delete("/sources/{source_id}", status_code=204)
def delete_source(source_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> Response:
    service.delete_source(db, user, source_id)
    return Response(status_code=204)


@router.post("/sources/{source_id}/restore", status_code=204)
def restore_source(source_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> Response:
    service.restore_source(db, user, source_id)
    return Response(status_code=204)


@router.get("/source-revisions/{revision_id}/download")
def download(revision_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> Response:
    data, rev = service.download(db, user, revision_id)
    return Response(
        data,
        media_type=rev.media_type
        if rev.media_type.startswith(("text/", "application/pdf", "image/"))
        else "application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(rev.filename)}",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
        },
    )


@router.post("/source-revisions/{revision_id}/evidence", response_model=schemas.EvidenceOut, status_code=201)
def create_evidence(
    revision_id: uuid.UUID,
    data: schemas.EvidenceCreateIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
) -> schemas.EvidenceOut:
    return service.evidence_out(service.create_evidence(db, user, revision_id, data))


@router.get("/evidence/{evidence_id}", response_model=schemas.EvidenceViewOut)
def evidence_view(
    evidence_id: uuid.UUID,
    claim_id: uuid.UUID | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
) -> schemas.EvidenceViewOut:
    return service.evidence_view(db, user, evidence_id, claim_id)
