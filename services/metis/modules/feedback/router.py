from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Response, UploadFile
from sqlalchemy.orm import Session

from metis.core.config import get_settings
from metis.core.deps import current_user, get_db
from metis.core.errors import AppError
from metis.core.models import User
from metis.modules.feedback import schemas, service

router = APIRouter(tags=["feedback"])


@router.get("/feedback", response_model=list[schemas.FeedbackOut])
def list_feedback(user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> list[schemas.FeedbackOut]:
    return service.list_all(db, user)


@router.post("/feedback", status_code=201, response_model=schemas.FeedbackOut)
def create(data: schemas.FeedbackIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> schemas.FeedbackOut:
    return service.outs(db, user, [service.create(db, user, data)])[0]


@router.patch("/feedback/{feedback_id}", response_model=schemas.FeedbackOut)
def update(
    feedback_id: uuid.UUID, data: schemas.FeedbackUpdate, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> schemas.FeedbackOut:
    return service.outs(db, user, [service.update(db, user, feedback_id, data)])[0]


@router.delete("/feedback/{feedback_id}", status_code=204)
def delete(feedback_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> Response:
    service.delete(db, user, feedback_id)
    return Response(status_code=204)


@router.post("/feedback/images", status_code=201, response_model=list[schemas.FeedbackImageOut])
async def upload_images(
    files: list[UploadFile] = File(...), user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> list[schemas.FeedbackImageOut]:
    limit = get_settings().max_upload_bytes
    read = []
    for f in files[: schemas.MAX_IMAGES + 1]:
        data = await f.read(limit + 1)
        if len(data) > limit:
            raise AppError("FILE_TOO_LARGE", "file exceeds size limit", limit=limit)
        read.append((f.filename or "gorsel", data))
    return [schemas.FeedbackImageOut(id=i.id, filename=i.filename, size_bytes=i.size_bytes) for i in service.upload_images(db, user, read)]


@router.get("/feedback/images/{image_id}")
def image(image_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> Response:
    data, img = service.image(db, user, image_id)
    return Response(
        data,
        media_type=img.media_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(img.filename)}",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
        },
    )
