"""arayüzden izin verilen model adresleri (allowed_endpoints) — ürün sahibinin kararı 2026-10-19

Geçerli izin listesi = METIS_ENDPOINT_ALLOWLIST (metis.env) + bu tablo. Ağ aralığı ve https şartı değişmez.

Revision ID: 0005
Revises: 0004
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _role() -> str:
    role = os.getenv("METIS_APP_ROLE", "metis_app")
    if not role.replace("_", "").isalnum():
        raise RuntimeError("METIS_APP_ROLE yalnız harf, rakam ve alt çizgi içermeli.")
    return role


def upgrade() -> None:
    op.create_table(
        "allowed_endpoints",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url"),
    )
    op.create_index(op.f("ix_allowed_endpoints_created_by"), "allowed_endpoints", ["created_by"])
    role = _role()
    op.execute(
        f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
            EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON allowed_endpoints TO {role}';
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_table("allowed_endpoints")
