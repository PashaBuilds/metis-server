"""Ekler: bilgiye eklenen görseller ve PDF'ler (2026-10-19).

Yükleme anında blob yazılır (içerik adresli). Bir taslak, yalnız kendi yüklediği ekleri ya da aynı sayfanın okunabilir
bir revizyonundaki ekleri kullanabilir. İndirme: yükleyen ya da eki içeren okunabilir bir revizyon; değilse 404.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from metis.core.access import can_read_page_revision, require_human, require_member
from metis.core.audit import audit
from metis.core.blobs import put_blob, read_blob
from metis.core.config import get_settings
from metis.core.errors import AppError
from metis.core.models import Attachment, PageRevision, PageRevisionAttachment, User
from metis.modules.attachments.schemas import MAX_PER_DRAFT
from metis.modules.knowledge.views import attachment_out  # noqa: F401 — router kullanır
from metis.modules.sources.files import check_upload

ALLOWED_CATEGORIES = ("image", "pdf")


def upload(db: Session, user: User, project_id: uuid.UUID, files: list[tuple[str, bytes]]) -> list[Attachment]:
    require_human(user)
    require_member(db, user, project_id, ["contributor"])
    if not 1 <= len(files) <= MAX_PER_DRAFT:
        raise AppError("VALIDATION_ERROR", "1-30 files", fields=[{"field": "files", "type": "count"}], limit=MAX_PER_DRAFT)
    limit = get_settings().max_upload_bytes
    checked = []
    for name, data in files:
        c = check_upload(name, data, limit)
        if c.category not in ALLOWED_CATEGORIES:
            raise AppError("UNSUPPORTED_FILE", "only images and PDF files can be attached", extension=name.rsplit(".", 1)[-1])
        checked.append((c, data))
    out = []
    for c, data in checked:
        row = Attachment(
            project_id=project_id, uploader_id=user.id, sha256=put_blob(data), filename=c.filename, media_type=c.media_type, size_bytes=len(data)
        )
        db.add(row)
        out.append(row)
    db.flush()
    audit(db, user.id, "attachment.upload", "project", project_id, attachments=[str(a.id) for a in out])
    return out


def _revisions_with(db: Session, attachment_id: uuid.UUID) -> list[PageRevision]:
    return list(
        db.scalars(
            select(PageRevision)
            .join(PageRevisionAttachment, PageRevisionAttachment.page_revision_id == PageRevision.id)
            .where(PageRevisionAttachment.attachment_id == attachment_id)
        )
    )


def resolve_for_draft(
    db: Session, actor: User, project_id: uuid.UUID, page_id: uuid.UUID | None, ids: list[uuid.UUID]
) -> list[Attachment]:
    """Taslağın başvurduğu ekler: kendi yüklemesi ya da aynı sayfanın okunabilir bir revizyonunda bulunan ek."""
    if len(ids) > MAX_PER_DRAFT:
        raise AppError("VALIDATION_ERROR", "too many attachments", fields=[{"field": "attachments", "type": "too_long"}])
    if len(set(ids)) != len(ids):
        raise AppError("VALIDATION_ERROR", "duplicate attachment", fields=[{"field": "attachments", "type": "duplicate"}])
    out = []
    for aid in ids:
        a = db.get(Attachment, aid)
        if not a or a.project_id != project_id:
            raise AppError("NOT_FOUND", "attachment not found")
        if a.uploader_id != actor.id and not (
            page_id and any(r.page_id == page_id and can_read_page_revision(db, actor, r) for r in _revisions_with(db, aid))
        ):
            raise AppError("NOT_FOUND", "attachment not found")
        out.append(a)
    return out


def download(db: Session, user: User, attachment_id: uuid.UUID) -> tuple[bytes, Attachment]:
    a = db.get(Attachment, attachment_id)
    if not a:
        raise AppError("NOT_FOUND", "attachment not found")
    require_member(db, user, a.project_id)
    if a.uploader_id != user.id and not any(can_read_page_revision(db, user, r) for r in _revisions_with(db, attachment_id)):
        raise AppError("NOT_FOUND", "attachment not found")
    return read_blob(a.sha256), a

