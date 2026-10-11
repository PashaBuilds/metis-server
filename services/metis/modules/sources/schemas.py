from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from metis.modules.scopes.schemas import ScopeIn

SourceKind = Literal["note", "code", "document", "image", "table", "test"]


class SourceMetaIn(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    kind: SourceKind = "note"
    text: str = Field(default="", max_length=400_000)
    scope: ScopeIn = Field(default_factory=ScopeIn)
    source_version: str = Field(default="", max_length=120)
    repository: str = Field(default="", max_length=300)
    commit: str = Field(default="", max_length=80)
    path: str = Field(default="", max_length=500)
    symbol: str = Field(default="", max_length=200)
    acl: list[uuid.UUID] = Field(default_factory=list, max_length=200)


class RevisionMetaIn(BaseModel):
    expected_revision: int = Field(ge=1)
    text: str = Field(default="", max_length=400_000)
    scope: ScopeIn | None = None
    source_version: str = Field(default="", max_length=120)
    commit: str = Field(default="", max_length=80)
    path: str = Field(default="", max_length=500)
    symbol: str = Field(default="", max_length=200)


class EvidenceCreateIn(BaseModel):
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    excerpt: str | None = Field(default=None, min_length=1, max_length=8000)
    section: str = Field(default="", max_length=200)


class EvidenceOut(BaseModel):
    id: uuid.UUID
    source_revision_id: uuid.UUID
    locator: dict
    locator_label: str
    excerpt: str
    char_start: int | None
    char_end: int | None


class RevisionOut(BaseModel):
    id: uuid.UUID
    number: int
    sha256: str
    media_type: str
    filename: str
    size_bytes: int
    extraction: Literal["complete", "partial", "annotation_only"]
    extractor_version: str
    scope: dict
    meta: dict
    created_at: datetime
    author_name: str | None
    is_current: bool
    page_evidence: list[EvidenceOut] = []


class SourceOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    kind: SourceKind
    owner_id: uuid.UUID
    owner_name: str
    current_revision_no: int
    current_revision: RevisionOut | None
    restricted: bool
    created_at: datetime


class SourceDetailOut(SourceOut):
    revisions: list[RevisionOut]
    text: str
    acl: list[uuid.UUID]


class SourceListOut(BaseModel):
    items: list[SourceOut]
    next_cursor: str | None


class SourceRevisionCreated(BaseModel):
    source: SourceOut
    revision: RevisionOut
    affected_pages: list[uuid.UUID]


class EvidenceViewOut(BaseModel):
    evidence_id: uuid.UUID
    source: dict
    revision: dict
    locator: dict
    locator_label: str
    excerpt: str
    text: str
    highlight: dict | None
    can_download: bool
    project_id: uuid.UUID
