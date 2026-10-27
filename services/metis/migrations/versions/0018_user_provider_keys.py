"""kişisel API anahtarı + model çağrısının kimin adına yapıldığı — 2026-10-27 (ürün sahibinin kararı)

Herkes modelleri kendi anahtarıyla çağırır; sağlayıcının anahtarı (yöneticinin) ortak anahtar olarak benchmark, zamanlanmış
bakım ve arama zenginleştirmesinde kalır. `model_calls.user_id` + `key_source` kullanım dökümü içindir (kişi kendi
kullanımını, yönetici kişi başına toplamları görür). Eski çağrılar `shared`, kişisiz kalır.

Revision ID: 0018
Revises: 0017
"""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018"
down_revision = "0017"
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
        "user_provider_keys",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("providers.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("secret_enc", sa.Text(), nullable=False),
        sa.Column("secret_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_ok", sa.Boolean(), nullable=True),
        sa.Column("check_error", sa.String(60), nullable=True),
    )
    _grant("user_provider_keys", "SELECT, INSERT, UPDATE, DELETE")
    op.add_column("model_calls", sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    op.add_column("model_calls", sa.Column("key_source", sa.String(10), nullable=False, server_default="shared"))
    op.create_index("ix_model_calls_user_id", "model_calls", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_model_calls_user_id", table_name="model_calls")
    op.drop_column("model_calls", "key_source")
    op.drop_column("model_calls", "user_id")
    op.drop_table("user_provider_keys")
