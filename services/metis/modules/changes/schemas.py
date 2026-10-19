from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from metis.modules.knowledge.views import RevisionView
from metis.modules.scopes.schemas import ScopeIn

PageKind = Literal["concept", "component", "procedure", "decision", "incident", "validation", "table", "learning_path"]
ClaimKind = Literal[
    "design_intent", "observed_behavior", "tested_result", "expert_statement", "hypothesis", "derived_calculation"
]
Support = Literal["supported", "partial", "conflicting", "unsupported", "not_reviewed"]
Predicate = Literal["depends_on", "implements", "verified_by", "prerequisite_for", "explains", "part_of", "supersedes"]


class EvidenceRef(BaseModel):
    evidence_id: uuid.UUID
    quote: str = Field(min_length=1, max_length=8000)


class ClaimIn(BaseModel):
    statement: str = Field(min_length=1, max_length=4000)
    kind: ClaimKind = "expert_statement"
    support: Support = "supported"
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=20)


class FigureIn(BaseModel):
    """Açıklayıcı görsel: bir görsel kaynak revizyonu + açıklama. Gövdede `{{görsel N}}` satırıyla yerleşir."""

    source_revision_id: uuid.UUID
    caption: str = Field(default="", max_length=500)


class ItemIn(BaseModel):
    # Not tabanlı öğe: gövde (body_md) bilginin dayanağıdır; iddialar sunucuda nottan üretilir, `claims` boş olmalı.
    note: bool = False
    page_id: uuid.UUID | None = None
    base_revision_id: uuid.UUID | None = None
    action: Literal["upsert", "withdraw"] = "upsert"
    title: str = Field(default="", max_length=240)
    summary: str = Field(default="", max_length=4000)
    body_md: str = Field(default="", max_length=200_000)
    kind: PageKind = "concept"
    scope: ScopeIn = Field(default_factory=ScopeIn)
    unknowns: list[str] = Field(default_factory=list, max_length=50)
    aliases: list[str] = Field(default_factory=list, max_length=50)
    claims: list[ClaimIn] = Field(default_factory=list, max_length=200)
    figures: list[FigureIn] = Field(default_factory=list, max_length=20)
    # Ekler (görsel/PDF) — POST /projects/{pid}/attachments ile yüklenen kimlikler, sıralı; en çok 30.
    attachments: list[uuid.UUID] = Field(default_factory=list, max_length=30)


class RelationIn(BaseModel):
    relation_id: uuid.UUID | None = None
    action: Literal["upsert", "remove"] = "upsert"
    subject_page_id: uuid.UUID
    predicate: Predicate
    object_page_id: uuid.UUID
    rationale: str = Field(default="", max_length=2000)
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=10)


class ChangeCreateIn(BaseModel):
    summary: str = Field(default="", max_length=4000)
    items: list[ItemIn] = Field(default_factory=list, max_length=5)
    relations: list[RelationIn] = Field(default_factory=list, max_length=20)
    predecessor_id: uuid.UUID | None = None
    source_answer_id: uuid.UUID | None = None
    submit: bool = False


class ChangeUpdateIn(BaseModel):
    expected_hash: str = Field(min_length=64, max_length=64)
    summary: str = Field(default="", max_length=4000)
    items: list[ItemIn] = Field(default_factory=list, max_length=5)
    relations: list[RelationIn] = Field(default_factory=list, max_length=20)


class ReviewIn(BaseModel):
    decision: Literal["approve", "request_changes", "reject"]
    reason: str = Field(default="", max_length=4000)
    evidence_checked: bool = False
    hash: str = Field(min_length=64, max_length=64)


class PrepublishIssue(BaseModel):
    kind: Literal["conflict", "duplicate", "overlap"]
    page_id: uuid.UUID
    page_title: str
    ours: str = ""
    theirs: str = ""
    reason: str = ""
    detected_by: Literal["rule", "model"]


class PrepublishCheckOut(BaseModel):
    """Yayın öncesi kontrol. model_status: ok | not_configured (uygun model yok) | failed (model yanıt vermedi)."""

    hash: str
    model_status: Literal["ok", "not_configured", "failed"]
    model_name: str | None
    issues: list[PrepublishIssue]
    checked_at: datetime


class PublishDirectIn(BaseModel):
    hash: str = Field(min_length=64, max_length=64)
    acknowledge_issues: bool = False


class ReviewOut(BaseModel):
    id: uuid.UUID
    reviewer_id: uuid.UUID
    reviewer_name: str
    decision: str
    reason: str
    evidence_checked: bool
    policy: str
    hash: str
    hash_matches: bool
    created_at: datetime


class ClaimDiff(BaseModel):
    status: Literal["added", "removed", "changed", "unchanged"]
    before: str | None
    after: str | None
    before_ord: int | None
    after_ord: int | None
    claim_id: uuid.UUID | None


class ItemView(BaseModel):
    id: uuid.UUID
    page_id: uuid.UUID
    action: str
    base: RevisionView | None
    proposed: RevisionView | None
    base_is_current: bool
    current_published_revision_id: uuid.UUID | None
    claim_diff: list[ClaimDiff]
    summary_counts: dict[str, int]
    scope_changed: bool
    checks: list[str]


class RelationView(BaseModel):
    relation_id: uuid.UUID
    action: str
    subject_page_id: uuid.UUID
    subject_title: str
    predicate: str
    object_page_id: uuid.UUID
    object_title: str
    rationale: str


class ChangeOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    summary: str
    state: str
    origin: Literal["human", "metis"]
    kind: str
    author_id: uuid.UUID
    author_name: str
    requester_id: uuid.UUID | None
    requester_name: str | None
    job_id: uuid.UUID | None
    hash: str
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    page_ids: list[uuid.UUID]
    counts: dict[str, int]


class ChangeDetailOut(ChangeOut):
    items: list[ItemView]
    relations: list[RelationView]
    reviews: list[ReviewOut]
    approval_valid: bool
    can_edit: bool
    can_review: bool
    can_publish: bool
    can_publish_direct: bool = False
    prepublish: PrepublishCheckOut | None = None
    can_delete: bool
    approve_blockers: list[str]
    self_review: bool
    review_policy: str
    predecessor_id: uuid.UUID | None
    successor_id: uuid.UUID | None
    published_page_ids: list[uuid.UUID]
    detail: dict


class ChangeListOut(BaseModel):
    items: list[ChangeOut]
    counts: dict[str, int]


class WithdrawIn(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)
