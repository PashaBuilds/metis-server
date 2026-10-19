from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Response, UploadFile
from sqlalchemy.orm import Session

from metis.core.config import get_settings
from metis.core.deps import current_user, get_db
from metis.core.errors import AppError
from metis.core.models import User
from metis.modules.attachments import service
from metis.modules.attachments.schemas import MAX_PER_DRAFT, AttachmentOut

router = APIRouter(tags=["attachments"])


@router.post("/projects/{project_id}/attachments", status_code=201, response_model=list[AttachmentOut])
async def upload(
    project_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
) -> list[AttachmentOut]:
    if len(files) > MAX_PER_DRAFT:
        raise AppError("VALIDATION_ERROR", "too many files", fields=[{"field": "files", "type": "count"}], limit=MAX_PER_DRAFT)
    limit = get_settings().max_upload_bytes
    read = []
    for f in files:
        data = await f.read(limit + 1)
        if len(data) > limit:
            raise AppError("FILE_TOO_LARGE", "file exceeds size limit", limit=limit)
        read.append((f.filename or "dosya", data))
    return [service.attachment_out(a) for a in service.upload(db, user, project_id, read)]


@router.get("/attachments/{attachment_id}/download")
def download(attachment_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> Response:
    data, a = service.download(db, user, attachment_id)
    return Response(
        data,
        media_type=a.media_type if a.media_type.startswith(("application/pdf", "image/")) else "application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(a.filename)}",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
        },
    )
