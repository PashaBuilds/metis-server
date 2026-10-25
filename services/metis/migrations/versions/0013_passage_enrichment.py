"""model zenginleştirmesi — 2026-10-25 (İş 4)

- passage_enrichments: blok temel metni sha256 + istem sürümü → bağlam cümlesi ve sorular (kanıt değildir).
- search_passages.base_sha256: zenginleştirme anahtarı; projects.enrichment_enabled (varsayılan açık).

Revision ID: 0013
Revises: 0012
"""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def _grant(table: str, privileges: str) -> None:
    role = os.getenv("METIS_APP_ROLE", "metis_app")
    if not role.replace("_", "").isalnum():
        raise RuntimeError("METIS_APP_ROLE yalnız harf, rakam ve alt çizgi içermeli.")
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
        "passage_enrichments",
        sa.Column("base_sha256", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(80), nullable=False),
        sa.Column("model_id", sa.UUID(), nullable=True),
        sa.Column("context", sa.Text(), nullable=False, server_default=""),
        sa.Column("questions", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="ok"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("base_sha256", "prompt_version"),
    )
    op.add_column("search_passages", sa.Column("base_sha256", sa.String(64), nullable=True))
    op.create_index(op.f("ix_search_passages_base_sha256"), "search_passages", ["base_sha256"])
    op.add_column("projects", sa.Column("enrichment_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    _grant("passage_enrichments", "SELECT, INSERT, UPDATE")


def downgrade() -> None:
    op.drop_column("projects", "enrichment_enabled")
    op.drop_index(op.f("ix_search_passages_base_sha256"), table_name="search_passages")
    op.drop_column("search_passages", "base_sha256")
    op.drop_table("passage_enrichments")
