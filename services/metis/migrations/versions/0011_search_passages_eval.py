"""arama: blok düzeyinde indeks ve arama ölçümü — 2026-10-25 (İş 2)

- search_passages: yayındaki her iddia (not bloğu) bir arama satırı; başlık yolu; iki tsvector. Mevcut yayın `metis migrate`
  sonunda indekslenir (search.index.ensure_passage_index).
- search_eval_questions / search_eval_runs: METIS içinde soru seti ve ölçüm koşuları (deterministik, modelsiz).

Revision ID: 0011
Revises: 0010
"""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def _role() -> str:
    role = os.getenv("METIS_APP_ROLE", "metis_app")
    if not role.replace("_", "").isalnum():
        raise RuntimeError("METIS_APP_ROLE yalnız harf, rakam ve alt çizgi içermeli.")
    return role


def _grant(table: str, privileges: str) -> None:
    role = _role()
    op.execute(
        f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
            EXECUTE 'GRANT {privileges} ON {table} TO {role}';
          END IF;
        END $$;
        """
    )


def upgrade() -> None:
    op.create_table(
        "search_passages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("page_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("revision_id", sa.UUID(), nullable=False),
        sa.Column("publication_id", sa.UUID(), nullable=False),
        sa.Column("claim_id", sa.UUID(), nullable=False),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("heading_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_heading", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("symbols", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("scope", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("tsv_simple", TSVECTOR(), nullable=True),
        sa.Column("tsv_turkish", TSVECTOR(), nullable=True),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["revision_id"], ["page_revisions.id"]),
        sa.ForeignKeyConstraint(["publication_id"], ["publications.id"]),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_search_passages_page_id"), "search_passages", ["page_id"])
    op.create_index(op.f("ix_search_passages_project_id"), "search_passages", ["project_id"])
    op.create_index("ix_passage_tsv_simple", "search_passages", ["tsv_simple"], postgresql_using="gin")
    op.create_index("ix_passage_tsv_turkish", "search_passages", ["tsv_turkish"], postgresql_using="gin")
    op.create_index("ix_passage_symbols", "search_passages", ["symbols"], postgresql_using="gin")
    _grant("search_passages", "SELECT, INSERT, UPDATE, DELETE")
    op.create_table(
        "search_eval_questions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_page_ids", ARRAY(sa.UUID()), nullable=False, server_default="{}"),
        sa.Column("expected_quote", sa.Text(), nullable=False, server_default=""),
        sa.Column("kind", sa.String(30), nullable=False, server_default="kavram"),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_search_eval_questions_project_id"), "search_eval_questions", ["project_id"])
    op.create_table(
        "search_eval_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("metrics", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("per_question", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_search_eval_runs_project_id"), "search_eval_runs", ["project_id"])
    _grant("search_eval_questions", "SELECT, INSERT, UPDATE")
    _grant("search_eval_runs", "SELECT, INSERT")


def downgrade() -> None:
    op.drop_table("search_passages")
    op.drop_table("search_eval_runs")
    op.drop_table("search_eval_questions")
