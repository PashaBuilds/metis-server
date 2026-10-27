from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from metis.core.deps import current_user, get_db
from metis.core.models import User
from metis.modules.keys import service

router = APIRouter(tags=["keys"])


class MyKeyOut(BaseModel):
    provider_id: uuid.UUID
    provider_name: str
    models: list[str]
    has_key: bool
    updated_at: datetime | None
    checked_at: datetime | None
    check_ok: bool | None
    check_error: str | None
    uses_shared: bool


class KeySetIn(BaseModel):
    api_key: str = Field(min_length=1, max_length=2000)


class KeyCheckOut(BaseModel):
    ok: bool
    error: str | None
    latency_ms: float
    model: str


class UsageRow(BaseModel):
    purpose: str
    key_source: str
    calls: int
    cached: int
    prompt_tokens: int
    completion_tokens: int


class MyUsageOut(BaseModel):
    days: int
    rows: list[UsageRow]


class UserUsageRow(BaseModel):
    user_id: uuid.UUID | None
    name: str | None
    key_source: str
    calls: int
    prompt_tokens: int
    completion_tokens: int


class UsageByUserOut(BaseModel):
    days: int
    rows: list[UserUsageRow]


@router.get("/me/keys", response_model=list[MyKeyOut])
def my_keys(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    return service.my_keys(db, user)


@router.put("/me/keys/{provider_id}", status_code=204)
def set_key(provider_id: uuid.UUID, data: KeySetIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    service.set_key(db, user, provider_id, data.api_key)
    return Response(status_code=204)


@router.delete("/me/keys/{provider_id}", status_code=204)
def delete_key(provider_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    service.delete_key(db, user, provider_id)
    return Response(status_code=204)


@router.post("/me/keys/{provider_id}/check", response_model=KeyCheckOut)
def check_key(provider_id: uuid.UUID, user: User = Depends(current_user)) -> dict:
    return service.check_key(user.id, provider_id)


@router.get("/me/usage", response_model=MyUsageOut)
def my_usage(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return service.my_usage(db, user)


@router.get("/usage/users", response_model=UsageByUserOut)
def usage_by_user(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return service.usage_by_user(db, user)
