from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from metis.modules.changes.schemas import ClaimDiff
from metis.modules.knowledge.views import RevisionView


class PageRow(BaseModel):
    page_id: uuid.UUID
    revision_id: uuid.UUID
    title: str
    summary: str
    kind: str
    scope: dict
    freshness: str
    lifecycle: str
    published_at: datetime | None
    evidence_count: int
    claim_count: int


class PageListOut(BaseModel):
    items: list[PageRow]
    total: int
    next_cursor: str | None


class DomainRow(BaseModel):
    key: str
    label: str
    page_count: int
    last_published_at: datetime | None


class Paragraph(BaseModel):
    text: str
    claim_ords: list[int]


class RelationRow(BaseModel):
    relation_id: uuid.UUID
    predicate: str
    direction: str
    other_page_id: uuid.UUID
    other_title: str
    other_kind: str


class SourceRow(BaseModel):
    source_id: uuid.UUID
    title: str
    kind: str
    revision_number: int
    is_current: bool
    first_evidence_id: uuid.UUID
    claim_ords: list[int]


class FindingBrief(BaseModel):
    id: uuid.UUID
    kind: str
    severity: str
    created_at: datetime
    detail: dict


class HistoryRow(BaseModel):
    revision_id: uuid.UUID
    number: int
    title: str
    published_at: datetime
    change_set_id: uuid.UUID | None
    publication_kind: str
    is_current: bool


class PageDetailOut(BaseModel):
    page_id: uuid.UUID
    project_id: uuid.UUID
    lifecycle: str
    freshness: str
    is_published_revision: bool
    published_revision_id: uuid.UUID | None
    revision: RevisionView
    paragraphs: list[Paragraph]
    relations: list[RelationRow]
    sources: list[SourceRow]
    findings: list[FindingBrief]
    approved_by: str | None
    approved_at: datetime | None
    change_set_id: uuid.UUID | None
    review_policy_badge: str | None
    open_change_ids: list[uuid.UUID]


class CompareOut(BaseModel):
    a: RevisionView
    b: RevisionView
    claim_diff: list[ClaimDiff]
    body_diff: list[dict]


class ReportIn(BaseModel):
    text: str = Field(min_length=3, max_length=2000)
