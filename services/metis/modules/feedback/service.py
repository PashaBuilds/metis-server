"""Geri bildirim (2026-10-23, ürün sahibinin isteği): hata ya da istek, isteğe bağlı ekran görüntüleriyle.

Herkes (okur dahil, yalnız insan) yazar; giriş yapmış herkes tümünü görür. Durum ve cevap notu yalnız yöneticide.
Yazan kendi bildirimini, yönetici her bildirimi siler (deleted_at). Görseller tek tek yüklenir; bağlanmamış görsel
yalnız yükleyene görünür, silinmiş bildirimin görseli kimseye görünmez (404).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from metis.core.access import require_admin, require_human
from metis.core.audit import audit
from metis.core.blobs import put_blob, read_blob
from metis.core.config import get_settings
from metis.core.db import utcnow
from metis.core.errors import AppError
from metis.core.models import Feedback, FeedbackImage, User
from metis.modules.feedback import schemas
from metis.modules.sources.files import check_upload


def upload_images(db: Session, user: User, files: list[tuple[str, bytes]]) -> list[FeedbackImage]:
    require_human(user)
    if not 1 <= len(files) <= schemas.MAX_IMAGES:
        raise AppError("VALIDATION_ERROR", "1-5 files", fields=[{"field": "files", "type": "count"}], limit=schemas.MAX_IMAGES)
    limit = get_settings().max_upload_bytes
    checked = []
    for name, data in files:
        c = check_upload(name, data, limit)
        if c.category != "image":
            raise AppError("UNSUPPORTED_FILE", "only images can be attached", extension=name.rsplit(".", 1)[-1])
        checked.append((c, data))
    out = []
    for c, data in checked:
        row = FeedbackImage(uploader_id=user.id, sha256=put_blob(data), filename=c.filename, media_type=c.media_type, size_bytes=len(data))
        db.add(row)
        out.append(row)
    db.flush()
    return out


def create(db: Session, user: User, data: schemas.FeedbackIn) -> Feedback:
    require_human(user)
    if len(data.image_ids) > schemas.MAX_IMAGES or len(set(data.image_ids)) != len(data.image_ids):
        raise AppError("VALIDATION_ERROR", "too many images", fields=[{"field": "image_ids", "type": "too_long"}], limit=schemas.MAX_IMAGES)
    images = []
    for iid in data.image_ids:
        img = db.get(FeedbackImage, iid)
        if not img or img.uploader_id != user.id or img.feedback_id is not None:
            raise AppError("NOT_FOUND", "image not found")
        images.append(img)
    row = Feedback(kind=data.kind, body=data.text, author_id=user.id)
    db.add(row)
    db.flush()
    for i, img in enumerate(images):
        img.feedback_id, img.ord = row.id, i
    db.flush()
    audit(db, user.id, "feedback.create", "feedback", row.id, kind=data.kind, images=len(images))
    return row


def _live(db: Session, feedback_id: uuid.UUID) -> Feedback:
    row = db.get(Feedback, feedback_id)
    if not row or row.deleted_at is not None:
        raise AppError("NOT_FOUND", "feedback not found")
    return row


def update(db: Session, user: User, feedback_id: uuid.UUID, data: schemas.FeedbackUpdate) -> Feedback:
    require_admin(user)
    row = _live(db, feedback_id)
    if data.status is not None:
        row.status = data.status
    if data.reply is not None:
        row.reply = data.reply.strip()
    row.reply_by, row.reply_at = user.id, utcnow()
    db.flush()
    audit(db, user.id, "feedback.update", "feedback", row.id, status=row.status)
    return row


def delete(db: Session, user: User, feedback_id: uuid.UUID) -> None:
    require_human(user)
    row = _live(db, feedback_id)
    if row.author_id != user.id and not user.is_admin:
        raise AppError("FORBIDDEN", "only the author or an administrator can delete")
    row.deleted_at, row.deleted_by = utcnow(), user.id
    db.flush()
    audit(db, user.id, "feedback.delete", "feedback", row.id)


def list_all(db: Session, user: User) -> list[schemas.FeedbackOut]:
    rows = list(db.scalars(select(Feedback).where(Feedback.deleted_at.is_(None)).order_by(Feedback.seq.desc())))
    return outs(db, user, rows)


def outs(db: Session, user: User, rows: list[Feedback]) -> list[schemas.FeedbackOut]:
    ids = [r.id for r in rows]
    images: dict[uuid.UUID, list[FeedbackImage]] = {}
    if ids:
        for img in db.scalars(select(FeedbackImage).where(FeedbackImage.feedback_id.in_(ids)).order_by(FeedbackImage.ord)):
            images.setdefault(img.feedback_id, []).append(img)  # type: ignore[arg-type]
    user_ids = {r.author_id for r in rows} | {r.reply_by for r in rows if r.reply_by}
    names = {u.id: u.display_name for u in db.scalars(select(User).where(User.id.in_(user_ids)))} if user_ids else {}
    return [
        schemas.FeedbackOut(
            id=r.id,
            kind=r.kind,  # type: ignore[arg-type]
            text=r.body,
            status=r.status,  # type: ignore[arg-type]
            reply=r.reply,
            reply_by_name=names.get(r.reply_by) if r.reply_by else None,
            reply_at=r.reply_at,
            author_name=names.get(r.author_id, ""),
            created_at=r.created_at,
            images=[schemas.FeedbackImageOut(id=i.id, filename=i.filename, size_bytes=i.size_bytes) for i in images.get(r.id, [])],
            can_delete=r.author_id == user.id or (user.is_admin and user.kind == "human"),
        )
        for r in rows
    ]


def image(db: Session, user: User, image_id: uuid.UUID) -> tuple[bytes, FeedbackImage]:
    img = db.get(FeedbackImage, image_id)
    if not img:
        raise AppError("NOT_FOUND", "image not found")
    if img.feedback_id is None:
        if img.uploader_id != user.id:
            raise AppError("NOT_FOUND", "image not found")
    else:
        fb = db.get(Feedback, img.feedback_id)
        if not fb or fb.deleted_at is not None:
            raise AppError("NOT_FOUND", "image not found")
    return read_blob(img.sha256), img
