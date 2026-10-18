from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field  # noqa: F401

Role = Literal["reader", "contributor", "reviewer", "steward"]


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    is_demo: bool
    review_policy: Literal["independent", "owner_review", "self_publish"]
    review_interval_days: int
    active_publication_id: uuid.UUID | None
    created_at: datetime
    my_roles: list[str]


class ProjectCreateInput(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=4000)


class ProjectUpdateInput(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=4000)
    review_policy: Literal["independent", "owner_review", "self_publish"] | None = None
    review_interval_days: int | None = Field(default=None, ge=7, le=730)


class MemberOut(BaseModel):
    user_id: uuid.UUID
    username: str
    display_name: str
    roles: list[Role]
    active: bool


class MemberSetInput(BaseModel):
    user_id: uuid.UUID
    roles: list[Role] = Field(max_length=4)
