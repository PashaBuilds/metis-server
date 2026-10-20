"""giriş ayarı: parolasız (yalnız kullanıcı adıyla) giriş — ürün sahibinin ve ekip liderinin kararı 2026-10-19

- login_settings: tek satır (id=1). passwordless açıkken yönetici olmayanlar yalnız kullanıcı adıyla girer; yönetici
  hesapları her zaman parolalıdır. Varsayılan kapalı.

Revision ID: 0008
Revises: 0007
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def _role() -> str:
    role = os.getenv("METIS_APP_ROLE", "metis_app")
    if not role.replace("_", "").isalnum():
        raise RuntimeError("METIS_APP_ROLE yalnız harf, rakam ve alt çizgi içermeli.")
    return role


def upgrade() -> None:
    op.create_table(
        "login_settings",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("passwordless", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_login_settings_single"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    role = _role()
    op.execute(
        f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
            EXECUTE 'GRANT SELECT, INSERT, UPDATE ON login_settings TO {role}';
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_table("login_settings")
