from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from metis.modules.scopes.schemas import ScopeIn

Decision = Literal["SUPPORTED", "PARTIAL", "NEEDS_SCOPE", "CONFLICTING", "NO_EVIDENCE", "RETRIEVAL_UNAVAILABLE", "MODEL_UNAVAILABLE", "VALIDATION_FAILED"]


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    scope: ScopeIn | None = None
    level: Literal["short", "steps", "detailed"] = "short"
    model_id: uuid.UUID | None = None


class Citation(BaseModel):
    n: int
    claim_id: uuid.UUID
    evidence_id: uuid.UUID
    page_id: uuid.UUID
    page_title: str
    quote: str
    source_title: str
    locator_label: str
    scope: dict


class Sentence(BaseModel):
    text: str
    refs: list[int]


class RelatedPage(BaseModel):
    page_id: uuid.UUID
    title: str
    revision_id: uuid.UUID
    freshness: str
    scope: dict
    open_conflict: bool = False
    excluded: str | None = None
    relevance: str | None = None


class ConflictSide(BaseModel):
    page_id: uuid.UUID | None
    page_title: str
    quote: str
    evidence_id: uuid.UUID | None


class AnswerOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    question: str
    scope: dict
    level: str
    decision: Decision
    explanation: list[Sentence]
    citations: list[Citation]
    related: list[RelatedPage]
    unknowns: list[str]
    conflict_sides: list[ConflictSide]
    conflict_finding_id: uuid.UUID | None
    needs_scope_dimensions: list[str]
    model: dict | None
    model_unavailable_reason: str | None
    alternatives: list[dict]
    prompt_version: str
    publication_id: uuid.UUID | None
    timings: dict
    explanation_dropped: int
    dropped_sentences: list[dict]
    legacy: bool
    created_at: datetime


class AnswerListItem(BaseModel):
    id: uuid.UUID
    question: str
    decision: str
    created_at: datetime
    legacy: bool


class FeedbackIn(BaseModel):
    rating: Literal["helpful", "not_helpful"]
    comment: str = Field(default="", max_length=2000)


class DraftPrefill(BaseModel):
    title: str
    scope: dict
    body_md: str
    claims: list[dict]
    source_answer_id: uuid.UUID
