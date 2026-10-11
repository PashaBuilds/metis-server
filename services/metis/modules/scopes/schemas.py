from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

Dimension = Literal["domain", "yatt", "kart", "proje"]


class ScopeIn(BaseModel):
    """Kapsam: her boyutta değer listesi. ["*"] = Bağımsız, [] = Belirlenmemiş."""

    domain: list[str] = Field(default_factory=list, max_length=20)
    yatt: list[str] = Field(default_factory=list, max_length=20)
    kart: list[str] = Field(default_factory=list, max_length=20)
    proje: list[str] = Field(default_factory=list, max_length=20)


class ScopeValueInput(BaseModel):
    dimension: Dimension
    value: str = Field(min_length=1, max_length=120)


class ScopeValueOut(BaseModel):
    id: uuid.UUID
    dimension: Dimension
    value: str


class CatalogOut(BaseModel):
    project_id: uuid.UUID
    domain: list[ScopeValueOut]
    yatt: list[ScopeValueOut]
    kart: list[ScopeValueOut]
    proje: list[ScopeValueOut]
