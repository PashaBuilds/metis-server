"""METIS veri modeli (brief 5.3).

Tüm ID'ler UUID, zamanlar timestamptz. Silme = deleted_at + deleted_by. Değişmez
tablolar `metis.core.db.IMMUTABLE_TABLES` içinde; PostgreSQL trigger'ı ve ORM kancası
ikisi birden korur.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from metis.core.db import Base, new_id, utcnow

UUIDPK = UUID(as_uuid=True)


def pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUIDPK, primary_key=True, default=new_id)


def fk(target: str, nullable: bool = False, index: bool = True, ondelete: str | None = None) -> Mapped[Any]:
    return mapped_column(UUIDPK, ForeignKey(target, ondelete=ondelete), nullable=nullable, index=index)


def ts(nullable: bool = False, default: bool = True) -> Mapped[Any]:
    if default and not nullable:
        return mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, server_default=text("now()"))
    return mapped_column(DateTime(timezone=True), nullable=nullable)


def jsonb(default: Any = dict) -> Mapped[Any]:
    server = "'[]'::jsonb" if default is list else "'{}'::jsonb"
    return mapped_column(JSONB, nullable=False, default=default, server_default=text(server))


# ---------------------------------------------------------------- kimlik ve proje


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = pk()
    username: Mapped[str] = mapped_column(String(150), nullable=False)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="human")
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 'local': METIS parolası · 'directory': şirket dizini (parola METIS'te tutulmaz; password_hash boş).
    auth_source: Mapped[str] = mapped_column(String(20), nullable=False, default="local", server_default="local")
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)  # dizinde objectGUID
    created_at: Mapped[datetime] = ts()
    __table_args__ = (
        Index("ux_users_username", text("lower(username)"), unique=True),
        CheckConstraint("kind in ('human','worker')", name="ck_users_kind"),
        CheckConstraint("auth_source in ('local','directory')", name="ck_users_auth_source"),
        Index("ux_users_external_id", "external_id", unique=True, postgresql_where=text("external_id IS NOT NULL")),
    )


class UserSession(Base):
    __tablename__ = "sessions"
    id: Mapped[uuid.UUID] = pk()
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_id: Mapped[uuid.UUID] = fk("users.id", ondelete="CASCADE")
    csrf: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = ts()
    expires_at: Mapped[datetime] = ts(nullable=False, default=False)
    ip: Mapped[str] = mapped_column(String(64), nullable=False, default="")


class SetupCode(Base):
    __tablename__ = "setup_codes"
    id: Mapped[uuid.UUID] = pk()
    code_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = ts()
    expires_at: Mapped[datetime] = ts(nullable=False, default=False)
    used_at: Mapped[datetime | None] = ts(nullable=True)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    id: Mapped[uuid.UUID] = pk()
    username: Mapped[str] = mapped_column(String(150), nullable=False)
    ip: Mapped[str] = mapped_column(String(64), nullable=False)
    at: Mapped[datetime] = ts()
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    __table_args__ = (
        Index("ix_login_attempts_user_at", "username", "at"),
        Index("ix_login_attempts_ip_at", "ip", "at"),
    )


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # self_publish: yazar yayımlar (yayın öncesi otomatik kontrol); independent: başka bir inceleyici onaylar;
    # owner_review: eski "kişisel pilot incelemesi" (aktarılan veriler için geçerli kalır).
    review_policy: Mapped[str] = mapped_column(String(20), nullable=False, default="self_publish")
    # Model zenginleştirmesi (bağlam + soru; yalnız yayımlanmış bloklar, model varsa): proje başına açık/kapalı.
    enrichment_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    review_interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    active_publication_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDPK, ForeignKey("publications.id", use_alter=True, name="fk_projects_active_publication"), nullable=True
    )
    created_at: Mapped[datetime] = ts()
    deleted_at: Mapped[datetime | None] = ts(nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, nullable=True)
    __table_args__ = (CheckConstraint("review_policy in ('independent','owner_review','self_publish')", name="ck_projects_policy"),)


class ProjectMember(Base):
    __tablename__ = "project_members"
    project_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "user_id", "role"),
        CheckConstraint("role in ('reader','contributor','reviewer','steward')", name="ck_member_role"),
    )


# ---------------------------------------------------------------- kapsam


class ScopeValue(Base):
    __tablename__ = "scope_values"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id", ondelete="CASCADE")
    dimension: Mapped[str] = mapped_column(String(10), nullable=False)
    value: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = ts()
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, nullable=True)
    deleted_at: Mapped[datetime | None] = ts(nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, nullable=True)
    __table_args__ = (
        CheckConstraint("dimension in ('domain','yatt','kart','proje')", name="ck_scope_dimension"),
        Index(
            "ux_scope_values_live",
            "project_id",
            "dimension",
            text("lower(value)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


# ---------------------------------------------------------------- kaynak ve kanıt


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    owner_id: Mapped[uuid.UUID] = fk("users.id")
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    current_revision_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = ts()
    deleted_at: Mapped[datetime | None] = ts(nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, nullable=True)
    __table_args__ = (
        CheckConstraint("kind in ('note','code','document','image','table','test')", name="ck_source_kind"),
    )


class SourceAcl(Base):
    __tablename__ = "source_acl"
    source_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("users.id"), primary_key=True, index=True)


class SourceRevision(Base):
    __tablename__ = "source_revisions"
    id: Mapped[uuid.UUID] = pk()
    source_id: Mapped[uuid.UUID] = fk("sources.id")
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    filename: Mapped[str] = mapped_column(String(240), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    meta: Mapped[dict] = jsonb()
    scope: Mapped[dict] = jsonb()
    extraction: Mapped[str] = mapped_column(String(20), nullable=False, default="complete")
    extractor_version: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    author_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, index=False)
    created_at: Mapped[datetime] = ts()
    __table_args__ = (
        UniqueConstraint("source_id", "number", name="uq_source_revision_number"),
        CheckConstraint("extraction in ('complete','partial','annotation_only')", name="ck_source_extraction"),
        Index("ix_source_revisions_scope", "scope", postgresql_using="gin"),
    )


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[uuid.UUID] = pk()
    source_revision_id: Mapped[uuid.UUID] = fk("source_revisions.id")
    locator: Mapped[dict] = jsonb()
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = ts()


# ---------------------------------------------------------------- bilgi


class Page(Base):
    __tablename__ = "pages"
    # Not tabanlı bilgi (2026-10-19): sayfanın dayanağı olan uzman notu kaynağı (1:1). Eski sayfalarda boş.
    note_source_id: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, ForeignKey("sources.id"), nullable=True, index=True)
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default="concept")
    owner_id: Mapped[uuid.UUID] = fk("users.id")
    lifecycle: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    freshness: Mapped[str] = mapped_column(String(30), nullable=False, default="unknown")
    current_revision_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    published_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDPK, ForeignKey("page_revisions.id", use_alter=True, name="fk_pages_published_revision"), nullable=True
    )
    published_at: Mapped[datetime | None] = ts(nullable=True)
    reviewed_at: Mapped[datetime | None] = ts(nullable=True)
    created_at: Mapped[datetime] = ts()
    deleted_at: Mapped[datetime | None] = ts(nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, nullable=True)
    __table_args__ = (
        CheckConstraint("lifecycle in ('active','deprecated','withdrawn')", name="ck_page_lifecycle"),
        CheckConstraint(
            "freshness in ('current','review_due','dependency_changed','unknown')", name="ck_page_freshness"
        ),
    )


class PageRevision(Base):
    __tablename__ = "page_revisions"
    id: Mapped[uuid.UUID] = pk()
    page_id: Mapped[uuid.UUID] = fk("pages.id")
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default="concept")
    scope: Mapped[dict] = jsonb()
    unknowns: Mapped[list] = jsonb(list)
    aliases: Mapped[list] = jsonb(list)
    author_id: Mapped[uuid.UUID] = fk("users.id", index=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    legacy_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = ts()
    __table_args__ = (
        UniqueConstraint("page_id", "number", name="uq_page_revision_number"),
        Index("ix_page_revisions_scope", "scope", postgresql_using="gin"),
    )


class Claim(Base):
    __tablename__ = "claims"
    id: Mapped[uuid.UUID] = pk()
    page_revision_id: Mapped[uuid.UUID] = fk("page_revisions.id")
    ord: Mapped[int] = mapped_column(Integer, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default="expert_statement")
    support: Mapped[str] = mapped_column(String(20), nullable=False, default="not_reviewed")
    __table_args__ = (
        UniqueConstraint("page_revision_id", "ord", name="uq_claim_ord"),
        CheckConstraint(
            "kind in ('design_intent','observed_behavior','tested_result','expert_statement','hypothesis','derived_calculation')",
            name="ck_claim_kind",
        ),
        CheckConstraint(
            "support in ('supported','partial','conflicting','unsupported','not_reviewed')", name="ck_claim_support"
        ),
    )


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"
    claim_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("claims.id"), primary_key=True)
    evidence_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("evidence.id"), primary_key=True, index=True)
    quote: Mapped[str] = mapped_column(Text, nullable=False)


class PageRevisionFigure(Base):
    """Açıklayıcı görsel: revizyona bağlı, değişmez. Kanıt değildir; gövdede `{{görsel N}}` satırıyla yerleşir."""

    __tablename__ = "page_revision_figures"
    id: Mapped[uuid.UUID] = pk()
    page_revision_id: Mapped[uuid.UUID] = fk("page_revisions.id")
    ord: Mapped[int] = mapped_column(Integer, nullable=False)
    source_revision_id: Mapped[uuid.UUID] = fk("source_revisions.id")
    caption: Mapped[str] = mapped_column(Text, nullable=False, default="")
    __table_args__ = (UniqueConstraint("page_revision_id", "ord", name="uq_figure_ord"),)


class Attachment(Base):
    """Bilgiye eklenen dosya (görsel ya da PDF). Yalnız açılır/indirilir: okunmaz, aranmaz, modele gitmez (değişmez)."""

    __tablename__ = "attachments"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    uploader_id: Mapped[uuid.UUID] = fk("users.id")
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = ts()


class PageRevisionAttachment(Base):
    """Bilgi revizyonunun ekleri (sıralı, değişmez; revizyon hash'ine girer)."""

    __tablename__ = "page_revision_attachments"
    page_revision_id: Mapped[uuid.UUID] = fk("page_revisions.id")
    ord: Mapped[int] = mapped_column(Integer, nullable=False)
    attachment_id: Mapped[uuid.UUID] = fk("attachments.id")
    __table_args__ = (PrimaryKeyConstraint("page_revision_id", "ord"),)


class Relation(Base):
    __tablename__ = "relations"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    current_revision_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    published_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDPK, ForeignKey("relation_revisions.id", use_alter=True, name="fk_relations_published"), nullable=True
    )
    created_at: Mapped[datetime] = ts()
    deleted_at: Mapped[datetime | None] = ts(nullable=True)


class RelationRevision(Base):
    __tablename__ = "relation_revisions"
    id: Mapped[uuid.UUID] = pk()
    relation_id: Mapped[uuid.UUID] = fk("relations.id")
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    subject_page_id: Mapped[uuid.UUID] = fk("pages.id")
    predicate: Mapped[str] = mapped_column(String(30), nullable=False)
    object_page_id: Mapped[uuid.UUID] = fk("pages.id")
    scope: Mapped[dict] = jsonb()
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    review_state: Mapped[str] = mapped_column(String(20), nullable=False, default="proposed")
    author_id: Mapped[uuid.UUID] = fk("users.id", index=False)
    created_at: Mapped[datetime] = ts()
    __table_args__ = (
        CheckConstraint(
            "predicate in ('depends_on','implements','verified_by','prerequisite_for','explains','part_of','supersedes')",
            name="ck_relation_predicate",
        ),
    )


class RelationRevisionEvidence(Base):
    __tablename__ = "relation_revision_evidence"
    relation_revision_id: Mapped[uuid.UUID] = mapped_column(
        UUIDPK, ForeignKey("relation_revisions.id"), primary_key=True
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("evidence.id"), primary_key=True)
    quote: Mapped[str] = mapped_column(Text, nullable=False, default="")


# ---------------------------------------------------------------- değişiklik ve yayın


class ChangeSet(Base):
    __tablename__ = "change_sets"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    author_id: Mapped[uuid.UUID] = fk("users.id")
    requester_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, index=False)
    origin: Mapped[str] = mapped_column(String(10), nullable=False, default="human")
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDPK, ForeignKey("jobs.id", use_alter=True, name="fk_change_sets_job"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="edit")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    legacy_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    predecessor_id: Mapped[uuid.UUID | None] = fk("change_sets.id", nullable=True)
    source_answer_id: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, nullable=True)
    detail: Mapped[dict] = jsonb()
    created_at: Mapped[datetime] = ts()
    updated_at: Mapped[datetime] = ts()
    submitted_at: Mapped[datetime | None] = ts(nullable=True)
    published_at: Mapped[datetime | None] = ts(nullable=True)
    deleted_at: Mapped[datetime | None] = ts(nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, nullable=True)
    __table_args__ = (
        CheckConstraint("origin in ('human','metis')", name="ck_change_origin"),
        CheckConstraint(
            "state in ('draft','in_review','approved','rejected','published','superseded')", name="ck_change_state"
        ),
        CheckConstraint("kind in ('edit','withdrawal','resolution','legacy')", name="ck_change_kind"),
        Index("ix_change_sets_project_state", "project_id", "state"),
    )


class ChangeSetItem(Base):
    __tablename__ = "change_set_items"
    id: Mapped[uuid.UUID] = pk()
    change_set_id: Mapped[uuid.UUID] = fk("change_sets.id")
    page_id: Mapped[uuid.UUID] = fk("pages.id")
    base_revision_id: Mapped[uuid.UUID | None] = fk("page_revisions.id", nullable=True, index=False)
    base_revision_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proposed_revision_id: Mapped[uuid.UUID | None] = fk("page_revisions.id", nullable=True, index=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False, default="upsert")
    __table_args__ = (
        UniqueConstraint("change_set_id", "page_id", name="uq_change_item_page"),
        CheckConstraint("action in ('upsert','withdraw')", name="ck_change_item_action"),
    )


class ChangeSetRelation(Base):
    __tablename__ = "change_set_relations"
    id: Mapped[uuid.UUID] = pk()
    change_set_id: Mapped[uuid.UUID] = fk("change_sets.id")
    relation_id: Mapped[uuid.UUID] = fk("relations.id")
    base_revision_id: Mapped[uuid.UUID | None] = fk("relation_revisions.id", nullable=True, index=False)
    proposed_revision_id: Mapped[uuid.UUID | None] = fk("relation_revisions.id", nullable=True, index=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False, default="upsert")


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[uuid.UUID] = pk()
    change_set_id: Mapped[uuid.UUID] = fk("change_sets.id")
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewer_id: Mapped[uuid.UUID] = fk("users.id", index=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_checked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    policy: Mapped[str] = mapped_column(String(40), nullable=False)
    legacy_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = ts()
    __table_args__ = (CheckConstraint("decision in ('approve','request_changes','reject')", name="ck_review_decision"),)


class Publication(Base):
    __tablename__ = "publications"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    change_set_id: Mapped[uuid.UUID | None] = fk("change_sets.id", nullable=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="publish")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, nullable=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = ts()


class PublicationPage(Base):
    __tablename__ = "publication_pages"
    publication_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("publications.id"), primary_key=True)
    page_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("pages.id"), primary_key=True, index=True)
    revision_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("page_revisions.id"), nullable=False)


class PublicationRelation(Base):
    __tablename__ = "publication_relations"
    publication_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("publications.id"), primary_key=True)
    relation_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("relations.id"), primary_key=True)
    revision_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("relation_revisions.id"), nullable=False)


class SearchDocument(Base):
    __tablename__ = "search_documents"
    page_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("pages.id"), primary_key=True)
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    revision_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("page_revisions.id"), nullable=False)
    publication_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("publications.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    symbols: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scope: Mapped[dict] = jsonb()
    tsv_simple: Mapped[Any] = mapped_column(TSVECTOR, nullable=True)
    tsv_turkish: Mapped[Any] = mapped_column(TSVECTOR, nullable=True)
    __table_args__ = (
        Index("ix_search_symbols", "symbols", postgresql_using="gin"),
        Index("ix_search_tsv_simple", "tsv_simple", postgresql_using="gin"),
        Index("ix_search_tsv_turkish", "tsv_turkish", postgresql_using="gin"),
        Index("ix_search_scope", "scope", postgresql_using="gin"),
    )


# ---------------------------------------------------------------- worker ve hazırlık


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    requester_id: Mapped[uuid.UUID] = fk("users.id")
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    inputs: Mapped[dict] = jsonb()
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    model_id: Mapped[uuid.UUID | None] = fk("models.id", nullable=True, index=False)
    worker_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_until: Mapped[datetime | None] = ts(nullable=True)
    checkpoint: Mapped[dict] = jsonb()
    budget_used: Mapped[dict] = jsonb()
    result_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = ts()
    started_at: Mapped[datetime | None] = ts(nullable=True)
    finished_at: Mapped[datetime | None] = ts(nullable=True)
    updated_at: Mapped[datetime] = ts()
    deleted_at: Mapped[datetime | None] = ts(nullable=True)
    legacy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (
        CheckConstraint(
            "state in ('queued','running','awaiting_input','completed','failed','cancelled','budget_exceeded')",
            name="ck_job_state",
        ),
        Index("ix_jobs_claim", "state", "priority", "created_at"),
        Index(
            "ux_jobs_active_fingerprint",
            "project_id",
            "input_fingerprint",
            unique=True,
            postgresql_where=text("state in ('queued','running','awaiting_input') AND input_fingerprint <> ''"),
        ),
    )


class JobEvent(Base):
    __tablename__ = "job_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = fk("jobs.id", ondelete="CASCADE")
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    data: Mapped[dict] = jsonb()
    created_at: Mapped[datetime] = ts()


class JobMessage(Base):
    __tablename__ = "job_messages"
    id: Mapped[uuid.UUID] = pk()
    job_id: Mapped[uuid.UUID] = fk("jobs.id", ondelete="CASCADE")
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict] = jsonb()
    author_id: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, nullable=True)
    created_at: Mapped[datetime] = ts()
    answered_at: Mapped[datetime | None] = ts(nullable=True)
    __table_args__ = (CheckConstraint("role in ('metis','user')", name="ck_job_message_role"),)


class JobOutput(Base):
    __tablename__ = "job_outputs"
    job_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    change_set_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("change_sets.id"), primary_key=True)


class ExtractedClaim(Base):
    __tablename__ = "extracted_claims"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    source_revision_id: Mapped[uuid.UUID] = fk("source_revisions.id")
    job_id: Mapped[uuid.UUID | None] = fk("jobs.id", nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    attribute: Mapped[str] = mapped_column(String(300), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    condition: Mapped[str] = mapped_column(Text, nullable=False, default="")
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    quote_start: Mapped[int] = mapped_column(Integer, nullable=False)
    quote_end: Mapped[int] = mapped_column(Integer, nullable=False)
    scope: Mapped[dict] = jsonb()
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    page_revision_id: Mapped[uuid.UUID | None] = fk("page_revisions.id", nullable=True)
    created_at: Mapped[datetime] = ts()


class OpenDecision(Base):
    __tablename__ = "open_decisions"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    source_revision_id: Mapped[uuid.UUID] = fk("source_revisions.id")
    job_id: Mapped[uuid.UUID | None] = fk("jobs.id", nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    quote_start: Mapped[int] = mapped_column(Integer, nullable=False)
    quote_end: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    created_at: Mapped[datetime] = ts()


# ---------------------------------------------------------------- sağlık


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    state: Mapped[str] = mapped_column(String(10), nullable=False, default="open")
    detail: Mapped[dict] = jsonb()
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    resolution_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, nullable=True)
    resolved_at: Mapped[datetime | None] = ts(nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, nullable=True)
    created_at: Mapped[datetime] = ts()
    __table_args__ = (
        CheckConstraint(
            "kind in ('conflict','source_changed','review_due','broken_ref','missing_owner','reported')",
            name="ck_finding_kind",
        ),
        CheckConstraint("state in ('open','resolved')", name="ck_finding_state"),
        CheckConstraint("severity in ('low','medium','high')", name="ck_finding_severity"),
        Index(
            "ux_findings_open_fingerprint",
            "project_id",
            "fingerprint",
            unique=True,
            postgresql_where=text("state = 'open' AND fingerprint <> ''"),
        ),
    )


class FindingPage(Base):
    __tablename__ = "finding_pages"
    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUIDPK, ForeignKey("findings.id", ondelete="CASCADE"), primary_key=True
    )
    page_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("pages.id"), primary_key=True, index=True)


class ConflictCase(Base):
    __tablename__ = "conflict_cases"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    finding_id: Mapped[uuid.UUID | None] = fk("findings.id", nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    questions: Mapped[list] = jsonb(list)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    model_call_id: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, nullable=True)
    created_at: Mapped[datetime] = ts()


class ConflictOption(Base):
    __tablename__ = "conflict_options"
    id: Mapped[uuid.UUID] = pk()
    case_id: Mapped[uuid.UUID] = fk("conflict_cases.id", ondelete="CASCADE")
    ord: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prerequisite: Mapped[str] = mapped_column(Text, nullable=False, default="")
    keep_page_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUIDPK), nullable=False, default=list)
    retire_page_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUIDPK), nullable=False, default=list)
    evidence: Mapped[list] = jsonb(list)


class ConflictResolution(Base):
    __tablename__ = "conflict_resolutions"
    id: Mapped[uuid.UUID] = pk()
    case_id: Mapped[uuid.UUID] = fk("conflict_cases.id")
    option_id: Mapped[uuid.UUID | None] = fk("conflict_options.id", nullable=True)
    chosen_by: Mapped[uuid.UUID] = fk("users.id", index=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    change_set_id: Mapped[uuid.UUID | None] = fk("change_sets.id", nullable=True)
    created_at: Mapped[datetime] = ts()


class Schedule(Base):
    __tablename__ = "schedules"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="maintenance")
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    next_run_at: Mapped[datetime | None] = ts(nullable=True)
    last_run_at: Mapped[datetime | None] = ts(nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    model_id: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, nullable=True)
    __table_args__ = (UniqueConstraint("project_id", "kind", name="uq_schedule_project_kind"),)


# ---------------------------------------------------------------- model


class Provider(Base):
    __tablename__ = "providers"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    secret_enc: Mapped[str] = mapped_column(Text, nullable=False, default="")
    secret_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    secret_updated_at: Mapped[datetime | None] = ts(nullable=True)
    ca_bundle_ref: Mapped[str] = mapped_column(Text, nullable=False, default="")
    max_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    timeout_s: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    created_at: Mapped[datetime] = ts()
    deleted_at: Mapped[datetime | None] = ts(nullable=True)


class DirectorySettings(Base):
    """Şirket hesabıyla giriş ayarı (tek satır, id=1). Parola ya da hizmet hesabı tutulmaz: doğrulama kullanıcının kendi
    bilgileriyle LDAPS bağlanmasıdır."""

    __tablename__ = "directory_settings"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    server_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    domain: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    base_dn: Mapped[str] = mapped_column(Text, nullable=False, default="")
    group_dn: Mapped[str] = mapped_column(Text, nullable=False, default="")
    new_user_role: Mapped[str] = mapped_column(String(20), nullable=False, default="reader")  # yeni gelen Okur başlar
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_directory_settings_single"),
        CheckConstraint("new_user_role in ('none','reader')", name="ck_directory_settings_role"),
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = ts()


class LoginSettings(Base):
    """Giriş ayarı (tek satır, id=1): parolasız giriş (yönetici olmayanlar yalnız kullanıcı adıyla; yönetici parolalı)."""

    __tablename__ = "login_settings"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    passwordless: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = ts()
    __table_args__ = (CheckConstraint("id = 1", name="ck_login_settings_single"),)


class Feedback(Base):
    """Kullanıcı geri bildirimi (hata ya da istek). Giriş yapmış herkes görür; durum ve cevabı yönetici verir."""

    __tablename__ = "feedback"
    id: Mapped[uuid.UUID] = pk()
    # Eklenme sırası: "yeniden eskiye" listesi buna göre (zaman damgaları Windows saatinde eşit çıkabiliyor).
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[uuid.UUID] = fk("users.id")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new", server_default="new")
    reply: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    reply_by: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, index=False)
    reply_at: Mapped[datetime | None] = ts(nullable=True)
    created_at: Mapped[datetime] = ts()
    deleted_at: Mapped[datetime | None] = ts(nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, index=False)
    __table_args__ = (
        CheckConstraint("kind in ('bug','request')", name="ck_feedback_kind"),
        CheckConstraint("status in ('new','in_progress','done','wontfix')", name="ck_feedback_status"),
    )


class FeedbackImage(Base):
    """Geri bildirimin görseli (ekran görüntüsü). Önce yüklenir (feedback_id boş), bildirim gönderilince bağlanır."""

    __tablename__ = "feedback_images"
    id: Mapped[uuid.UUID] = pk()
    uploader_id: Mapped[uuid.UUID] = fk("users.id")
    feedback_id: Mapped[uuid.UUID | None] = fk("feedback.id", nullable=True)
    ord: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = ts()


class AllowedEndpoint(Base):
    """Yöneticinin arayüzden izin verdiği model adresi. Geçerli liste = METIS_ENDPOINT_ALLOWLIST (sunucu ayarı) + bunlar.
    Ağ aralığı (METIS_ENDPOINT_NETWORKS) ve üretimde https şartı yine geçerlidir (ürün sahibinin kararı 2026-10-19)."""

    __tablename__ = "allowed_endpoints"
    id: Mapped[uuid.UUID] = pk()
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_by: Mapped[uuid.UUID] = fk("users.id")
    created_at: Mapped[datetime] = ts()


class Model(Base):
    __tablename__ = "models"
    id: Mapped[uuid.UUID] = pk()
    provider_id: Mapped[uuid.UUID] = fk("providers.id")
    remote_id: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    transport_profile: Mapped[dict] = jsonb()
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    circuit_until: Mapped[datetime | None] = ts(nullable=True)
    created_at: Mapped[datetime] = ts()
    deleted_at: Mapped[datetime | None] = ts(nullable=True)


class ModelProbe(Base):
    __tablename__ = "model_probes"
    id: Mapped[uuid.UUID] = pk()
    model_id: Mapped[uuid.UUID] = fk("models.id", ondelete="CASCADE")
    capability: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    detail: Mapped[dict] = jsonb()
    at: Mapped[datetime] = ts()


class ProviderSlot(Base):
    __tablename__ = "provider_slots"
    id: Mapped[uuid.UUID] = pk()
    provider_id: Mapped[uuid.UUID] = fk("providers.id", ondelete="CASCADE")
    expires_at: Mapped[datetime] = ts(nullable=False, default=False)


class BenchmarkDataset(Base):
    __tablename__ = "benchmark_datasets"
    id: Mapped[uuid.UUID] = pk()
    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = ts()


class BenchmarkCase(Base):
    __tablename__ = "benchmark_cases"
    id: Mapped[uuid.UUID] = pk()
    dataset_id: Mapped[uuid.UUID] = fk("benchmark_datasets.id", ondelete="CASCADE")
    case_key: Mapped[str] = mapped_column(String(120), nullable=False)
    task: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict] = jsonb()
    expected: Mapped[dict] = jsonb()
    __table_args__ = (UniqueConstraint("dataset_id", "case_key", name="uq_benchmark_case_key"),)


class BenchmarkRun(Base):
    __tablename__ = "benchmark_runs"
    id: Mapped[uuid.UUID] = pk()
    model_id: Mapped[uuid.UUID] = fk("models.id", ondelete="CASCADE")
    dataset_id: Mapped[uuid.UUID] = fk("benchmark_datasets.id")
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    metrics: Mapped[dict] = jsonb()
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, nullable=True)
    created_at: Mapped[datetime] = ts()
    finished_at: Mapped[datetime | None] = ts(nullable=True)
    hidden_at: Mapped[datetime | None] = ts(nullable=True)


class BenchmarkResult(Base):
    __tablename__ = "benchmark_results"
    id: Mapped[uuid.UUID] = pk()
    run_id: Mapped[uuid.UUID] = fk("benchmark_runs.id", ondelete="CASCADE")
    case_id: Mapped[uuid.UUID] = fk("benchmark_cases.id", index=False)
    decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    critical_kind: Mapped[str | None] = mapped_column(String(40), nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(String(60), nullable=True)
    output: Mapped[dict] = jsonb()
    created_at: Mapped[datetime] = ts()


class ModelQualification(Base):
    __tablename__ = "model_qualifications"
    id: Mapped[uuid.UUID] = pk()
    model_id: Mapped[uuid.UUID] = fk("models.id", ondelete="CASCADE")
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    task_class: Mapped[str] = mapped_column(String(40), nullable=False, default="evidence_answer")
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    critical_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    run_id: Mapped[uuid.UUID | None] = fk("benchmark_runs.id", nullable=True, index=False)
    at: Mapped[datetime] = ts()
    hidden_at: Mapped[datetime | None] = ts(nullable=True)


class ModelCall(Base):
    __tablename__ = "model_calls"
    id: Mapped[uuid.UUID] = pk()
    model_id: Mapped[uuid.UUID] = fk("models.id", ondelete="CASCADE")
    prompt_id: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    purpose: Mapped[str] = mapped_column(String(30), nullable=False, default="mentor")
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_output: Mapped[str] = mapped_column(Text, nullable=False, default="")
    parsed_output: Mapped[dict] = jsonb()
    usage: Mapped[dict] = jsonb()
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(String(60), nullable=True)
    cached_from: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, nullable=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, nullable=True, index=True)
    answer_id: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, nullable=True, index=True)
    created_at: Mapped[datetime] = ts()


class ModelCache(Base):
    __tablename__ = "model_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    call_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("model_calls.id", ondelete="CASCADE"), nullable=False)
    output: Mapped[dict] = jsonb()
    created_at: Mapped[datetime] = ts()


# ---------------------------------------------------------------- mentor ve çapraz kesen


class Answer(Base):
    __tablename__ = "answers"
    id: Mapped[uuid.UUID] = pk()
    owner_id: Mapped[uuid.UUID] = fk("users.id")
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    question: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[dict] = jsonb()
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="short")
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    publication_id: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, nullable=True)
    model_id: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    explanation: Mapped[list] = jsonb(list)
    explanation_dropped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timings: Mapped[dict] = jsonb()
    detail: Mapped[dict] = jsonb()
    legacy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = ts()
    deleted_at: Mapped[datetime | None] = ts(nullable=True)


class AnswerCitation(Base):
    __tablename__ = "answer_citations"
    id: Mapped[uuid.UUID] = pk()
    answer_id: Mapped[uuid.UUID] = fk("answers.id", ondelete="CASCADE")
    ord: Mapped[int] = mapped_column(Integer, nullable=False)
    claim_id: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, ForeignKey("claims.id"), nullable=True)
    evidence_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("evidence.id"), nullable=False)
    page_id: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, nullable=True)
    quote: Mapped[str] = mapped_column(Text, nullable=False)


class AnswerFeedback(Base):
    __tablename__ = "answer_feedback"
    id: Mapped[uuid.UUID] = pk()
    answer_id: Mapped[uuid.UUID] = fk("answers.id", ondelete="CASCADE")
    user_id: Mapped[uuid.UUID] = fk("users.id", index=False)
    rating: Mapped[str] = mapped_column(String(20), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = ts()


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[uuid.UUID] = pk()
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, nullable=True, index=True)
    op: Mapped[str] = mapped_column(String(80), nullable=False)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    target_id: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    detail: Mapped[dict] = jsonb()
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = ts()
    __table_args__ = (Index("ix_audit_target", "target_type", "target_id"),)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    user_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("users.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_ref: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = ts()


class UserPreference(Base):
    __tablename__ = "user_preferences"
    user_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)


class LegacyImportRun(Base):
    __tablename__ = "legacy_import_runs"
    id: Mapped[uuid.UUID] = pk()
    started_at: Mapped[datetime] = ts()
    finished_at: Mapped[datetime | None] = ts(nullable=True)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    report: Mapped[dict] = jsonb()
    report_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="running")


# ---------------------------------------------------------------- dış kaynaklar (Confluence, GitLab)


class ExternalConnection(Base):
    """Yöneticinin tanımladığı dış kaynak bağlantısı. Token şifreli (AES-GCM); yalnız izinli kapsamlardan alınır."""

    __tablename__ = "external_connections"
    id: Mapped[uuid.UUID] = pk()
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    secret_enc: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Confluence: alan anahtarları; GitLab: proje yolları (grup/proje)
    allowed_scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = fk("users.id", index=False)
    created_at: Mapped[datetime] = ts()
    updated_at: Mapped[datetime] = ts()
    deleted_at: Mapped[datetime | None] = ts(nullable=True)
    __table_args__ = (CheckConstraint("kind in ('confluence','gitlab')", name="ck_external_connection_kind"),)


class ExternalImport(Base):
    """Bir önizleme: çekilen ve dönüştürülen içerik. Yalnız önizleyen kullanıcı, aynı projede, bir kez kullanır."""

    __tablename__ = "external_imports"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    user_id: Mapped[uuid.UUID] = fk("users.id")
    connection_id: Mapped[uuid.UUID] = fk("external_connections.id", index=False)
    external_key: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    attachment_ids: Mapped[list[str]] = jsonb(list)
    skipped: Mapped[list[dict]] = jsonb(list)
    used_at: Mapped[datetime | None] = ts(nullable=True)
    created_at: Mapped[datetime] = ts()


class ExternalOrigin(Base):
    """Bilginin dış kökeni: hangi Confluence sayfası / GitLab issue'su, hangi sürüm. Proje başına dış anahtar tekil."""

    __tablename__ = "external_origins"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    page_id: Mapped[uuid.UUID] = fk("pages.id")
    connection_id: Mapped[uuid.UUID] = fk("external_connections.id", index=False)
    external_key: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    imported_body_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    imported_at: Mapped[datetime] = ts()
    imported_by: Mapped[uuid.UUID] = fk("users.id", index=False)
    __table_args__ = (
        UniqueConstraint("project_id", "external_key", name="uq_external_origin_key"),
        UniqueConstraint("page_id", name="uq_external_origin_page"),
    )


# ---------------------------------------------------------------- arama ölçümü


class SearchEvalQuestion(Base):
    """Arama ölçümü sorusu: soru + beklenen bilgi(ler) + isteğe bağlı beklenen alıntı. Gerçek sorular yalnız veritabanında."""

    __tablename__ = "search_eval_questions"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_page_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUIDPK), nullable=False, default=list)
    expected_quote: Mapped[str] = mapped_column(Text, nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default="kavram")
    created_by: Mapped[uuid.UUID] = fk("users.id", index=False)
    created_at: Mapped[datetime] = ts()
    deleted_at: Mapped[datetime | None] = ts(nullable=True)


class SearchEvalRun(Base):
    """Bir ölçüm koşusu: o anki aramayla tüm sorular; metrikler ve soru başına sonuç (deterministik, modelsiz)."""

    __tablename__ = "search_eval_runs"
    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    created_by: Mapped[uuid.UUID] = fk("users.id", index=False)
    created_at: Mapped[datetime] = ts()
    metrics: Mapped[dict] = jsonb()
    per_question: Mapped[list[dict]] = jsonb(list)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")


class SearchPassage(Base):
    """Blok düzeyinde arama indeksi: yayındaki her iddia (not bloğu) bir satır. `index_pages` sayfa satırıyla birlikte
    aynı transaction'da yeniden kurar. `simple` tsvector Türkçe harfleri katlanmış metinden üretilir (search.text.fold)."""

    __tablename__ = "search_passages"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    page_id: Mapped[uuid.UUID] = fk("pages.id")
    project_id: Mapped[uuid.UUID] = fk("projects.id")
    revision_id: Mapped[uuid.UUID] = fk("page_revisions.id", index=False)
    publication_id: Mapped[uuid.UUID] = fk("publications.id", index=False)
    claim_id: Mapped[uuid.UUID] = fk("claims.id", index=False)
    ord: Mapped[int] = mapped_column(Integer, nullable=False)
    heading_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Başlık bloğu (`## …`) puana katılır ama gösterilen/alıntılanan en iyi blok olarak seçilmez.
    is_heading: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Bloğun temel metni (sayfa başlığı + başlık yolu + gövde) sha256'sı: zenginleştirme anahtarı.
    base_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # Vektör için gömülen metnin (temel metin + varsa zenginleştirme) sha256'sı; passage_vectors anahtarı.
    embed_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    symbols: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    scope: Mapped[dict] = jsonb()
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    tsv_simple: Mapped[Any] = mapped_column(TSVECTOR, nullable=True)
    tsv_turkish: Mapped[Any] = mapped_column(TSVECTOR, nullable=True)
    __table_args__ = (
        Index("ix_passage_tsv_simple", "tsv_simple", postgresql_using="gin"),
        Index("ix_passage_tsv_turkish", "tsv_turkish", postgresql_using="gin"),
        Index("ix_passage_symbols", "symbols", postgresql_using="gin"),
    )


class PassageVector(Base):
    """Blok vektörü: model + gömülen metnin (başlık, başlık yolu, gövde) sha256'sı → float16 vektör. Aynı metin aynı modelle
    yeniden hesaplanmaz; yayın değişse de metin aynıysa vektör yeniden kullanılır. Kanıt değildir."""

    __tablename__ = "passage_vectors"
    model_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    text_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    vector: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = ts()


class SearchState(Base):
    """Proje başına arama indeksi sürümü: blok indeksi ya da vektörler değişince artar; API süreçleri bellekteki vektör
    matrisini buna göre tazeler."""

    __tablename__ = "search_state"
    project_id: Mapped[uuid.UUID] = mapped_column(UUIDPK, ForeignKey("projects.id"), primary_key=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    vectors_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class PassageEnrichment(Base):
    """Model zenginleştirmesi (İş 4): yayımlanmış bir bloğun bağlam cümlesi ve cevapladığı sorular. Anahtar: bloğun temel
    metni (başlık + başlık yolu + gövde) sha256'sı + istem sürümü. Kanıt değildir; yalnız aramada (tsv D, gömme) kullanılır.
    status: ok | rejected (süzgeçten hiçbir şey geçmedi)."""

    __tablename__ = "passage_enrichments"
    base_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    prompt_version: Mapped[str] = mapped_column(String(80), primary_key=True)
    model_id: Mapped[uuid.UUID | None] = mapped_column(UUIDPK, nullable=True)
    context: Mapped[str] = mapped_column(Text, nullable=False, default="")
    questions: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    created_at: Mapped[datetime] = ts()
