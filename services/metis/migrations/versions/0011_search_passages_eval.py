"""arama: blok düzeyinde indeks ve arama ölçümü — 2026-10-25 (İş 2)

- search_eval_questions / search_eval_runs: METIS içinde soru seti ve ölçüm koşuları (deterministik, modelsiz).

Revision ID: 0011
Revises: 0010
"""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

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
    op.drop_table("search_eval_runs")
    op.drop_table("search_eval_questions")
