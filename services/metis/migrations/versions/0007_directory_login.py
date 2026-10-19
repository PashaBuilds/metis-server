"""şirket hesabıyla giriş (Active Directory / LDAPS) — ürün sahibinin isteği 2026-10-19

- users.auth_source: 'local' (METIS parolası) | 'directory' (şirket dizini; parola METIS'te tutulmaz).
- users.external_id: dizindeki değişmez kimlik (objectGUID); dizin kullanıcısı bununla eşleşir.
- directory_settings: tek satırlık dizin ayarı (sunucu, etki alanı, arama kökü, izinli grup, yeni gelen rolü;
  varsayılan 'reader': ürün sahibinin kararı, yeni gelen Okur başlar).
  Hiçbir parola ya da hizmet hesabı bilgisi tutulmaz.

Revision ID: 0007
Revises: 0006
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _role() -> str:
    role = os.getenv("METIS_APP_ROLE", "metis_app")
    if not role.replace("_", "").isalnum():
        raise RuntimeError("METIS_APP_ROLE yalnız harf, rakam ve alt çizgi içermeli.")
    return role


def upgrade() -> None:
    op.add_column("users", sa.Column("auth_source", sa.String(20), nullable=False, server_default="local"))
    op.add_column("users", sa.Column("external_id", sa.String(200), nullable=True))
    op.create_check_constraint("ck_users_auth_source", "users", "auth_source in ('local','directory')")
    op.create_index("ux_users_external_id", "users", ["external_id"], unique=True, postgresql_where=sa.text("external_id IS NOT NULL"))
    op.create_table(
        "directory_settings",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("server_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("domain", sa.String(200), nullable=False, server_default=""),
        sa.Column("base_dn", sa.Text(), nullable=False, server_default=""),
        sa.Column("group_dn", sa.Text(), nullable=False, server_default=""),
        sa.Column("new_user_role", sa.String(20), nullable=False, server_default="reader"),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_directory_settings_single"),
        sa.CheckConstraint("new_user_role in ('none','reader')", name="ck_directory_settings_role"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    role = _role()
    op.execute(
        f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
            EXECUTE 'GRANT SELECT, INSERT, UPDATE ON directory_settings TO {role}';
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_table("directory_settings")
    op.drop_index("ux_users_external_id", table_name="users")
    op.drop_constraint("ck_users_auth_source", "users", type_="check")
    op.drop_column("users", "external_id")
    op.drop_column("users", "auth_source")
