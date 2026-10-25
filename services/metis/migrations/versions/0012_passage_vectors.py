"""vektör arama — 2026-10-25 (İş 3)

- passage_vectors: model + gömülen metin sha256 → float16 vektör (bytea).
- search_state: proje başına arama indeksi sürümü (API süreçlerinin bellek önbelleği için).
- search_passages.embed_sha256: blokların gömme anahtarı; mevcut satırlar `metis migrate` sonunda doldurulur.

Revision ID: 0012
Revises: 0011
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
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
        "passage_vectors",
        sa.Column("model_id", sa.String(120), nullable=False),
        sa.Column("text_sha256", sa.String(64), nullable=False),
        sa.Column("vector", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("model_id", "text_sha256"),
    )
    op.create_table(
        "search_state",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("vectors_version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("project_id"),
    )
    op.add_column("search_passages", sa.Column("embed_sha256", sa.String(64), nullable=True))
    op.create_index(op.f("ix_search_passages_embed_sha256"), "search_passages", ["embed_sha256"])
    _grant("passage_vectors", "SELECT, INSERT, DELETE")
    _grant("search_state", "SELECT, INSERT, UPDATE")


def downgrade() -> None:
    op.drop_index(op.f("ix_search_passages_embed_sha256"), table_name="search_passages")
    op.drop_column("search_passages", "embed_sha256")
    op.drop_table("search_state")
    op.drop_table("passage_vectors")
