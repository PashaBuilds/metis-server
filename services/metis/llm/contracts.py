"""Model çıktı şemaları (Pydantic). Şema strict json_schema profiline de, json_object + sistem mesajına da gider."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- mentor


class ExplanationSentence(Strict):
    text: str = Field(min_length=1, max_length=600)
    claim_ids: list[str] = Field(max_length=10)


class QuotedClaim(Strict):
    claim_id: str = Field(max_length=120)
    evidence_id: str = Field(max_length=120)
    quote: str = Field(max_length=4000)


class EvidenceAnswer(Strict):
    decision: Literal["SUPPORTED", "PARTIAL", "NO_EVIDENCE", "NEEDS_SCOPE", "CONFLICTING"]
    explanation: list[ExplanationSentence] = Field(max_length=8)
    claims: list[QuotedClaim] = Field(max_length=30)


class SourceReview(Strict):
    page_id: str
    relevance: Literal["relevant", "uncertain", "irrelevant"]
    reason: str = Field(min_length=1, max_length=600)


class SourceSelection(Strict):
    reviews: list[SourceReview] = Field(max_length=40)


# ---------------------------------------------------------------- worker


class ExtractedClaimOut(Strict):
    subject: str = Field(min_length=1, max_length=300)
    attribute: str = Field(min_length=1, max_length=300)
    value: str = Field(min_length=1, max_length=2000)
    condition: str = Field(default="", max_length=600)
    quote: str = Field(min_length=1, max_length=4000)


class OpenDecisionOut(Strict):
    description: str = Field(min_length=1, max_length=1000)
    quote: str = Field(min_length=1, max_length=4000)


class Extraction(Strict):
    claims: list[ExtractedClaimOut] = Field(max_length=60)
    open_decisions: list[OpenDecisionOut] = Field(max_length=30)
    scope_questions: list[str] = Field(max_length=5)


class PageDiff(Strict):
    verdict: Literal["no_change", "addition", "update", "conflict_candidate", "supersede"]
    reason: str = Field(min_length=1, max_length=800)
    new_facts: list[str] = Field(max_length=30)


class ClaimJudgement(Strict):
    verdict: Literal["conflict", "scope_disjoint", "underspecified", "supersede", "compatible"]
    reason: str = Field(min_length=1, max_length=800)


class RelationJudgement(Strict):
    verdict: Literal["relation", "no_relation"]
    predicate: Literal["depends_on", "implements", "verified_by", "prerequisite_for", "explains", "part_of", "supersedes", ""]
    reason: str = Field(min_length=1, max_length=800)


class RefinedParagraph(Strict):
    text: str = Field(min_length=1, max_length=4000)
    claim_indices: list[int] = Field(min_length=1, max_length=100)


class Refinement(Strict):
    title: str = Field(default="", max_length=240)
    summary: str = Field(default="", max_length=600)
    paragraphs: list[RefinedParagraph] = Field(min_length=1, max_length=100)


class ResolutionCitation(Strict):
    evidence_id: str
    quote: str


class ResolutionOption(Strict):
    title: str = Field(min_length=3, max_length=200)
    rationale: str = Field(min_length=8, max_length=1600)
    prerequisite: str = Field(min_length=8, max_length=1600)
    keep_page_ids: list[str] = Field(min_length=1, max_length=8)
    retire_page_ids: list[str] = Field(min_length=1, max_length=8)
    evidence: list[ResolutionCitation] = Field(min_length=2, max_length=20)


class ResolutionAssessment(Strict):
    summary: str = Field(min_length=8, max_length=2400)
    questions: list[str] = Field(max_length=8)
    options: list[ResolutionOption] = Field(max_length=4)


class ProbeOut(Strict):
    ok: bool
    echo: str


# ---------------------------------------------------------------- arama zenginleştirmesi (İş 4)


class EnrichItem(Strict):
    id: str = Field(min_length=1, max_length=12)
    context: str = Field(default="", max_length=400)
    questions: list[str] = Field(default_factory=list, max_length=3)


class PassageEnrichmentOut(Strict):
    items: list[EnrichItem] = Field(max_length=12)
