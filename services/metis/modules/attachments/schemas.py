from __future__ import annotations

import uuid

from pydantic import BaseModel

MAX_PER_DRAFT = 30


class AttachmentOut(BaseModel):
    """Ek: dosya /attachments/{id}/download ile açılır. Yalnız ulaşılabilir; okunmaz, aranmaz, modele gitmez."""

    id: uuid.UUID
    filename: str
    media_type: str
    size_bytes: int
    is_image: bool
