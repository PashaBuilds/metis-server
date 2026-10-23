from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

MAX_IMAGES = 5

Kind = Literal["bug", "request"]
Status = Literal["new", "in_progress", "done", "wontfix"]


class FeedbackIn(BaseModel):
    kind: Kind
    text: str = Field(max_length=5000)
    image_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("text is empty")
        return v


class FeedbackUpdate(BaseModel):
    """Yalnız yönetici: durum ve/veya cevap notu."""

    status: Status | None = None
    reply: str | None = Field(default=None, max_length=2000)


class FeedbackImageOut(BaseModel):
    """Görsel /feedback/images/{id} ile açılır."""

    id: uuid.UUID
    filename: str
    size_bytes: int


class FeedbackOut(BaseModel):
    id: uuid.UUID
    kind: Kind
    text: str
    status: Status
    reply: str
    reply_by_name: str | None
    reply_at: datetime | None
    author_name: str
    created_at: datetime
    images: list[FeedbackImageOut]
    can_delete: bool
