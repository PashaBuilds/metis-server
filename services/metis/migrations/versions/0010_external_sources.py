"""dış kaynaklar: Confluence ve GitLab'dan taslak — ürün sahibinin isteği 2026-10-25

- external_connections: yöneticinin tanımladığı bağlantı (şifreli token, izinli kapsamlar).
- external_imports: önizleme kaydı (çekilen ve dönüştürülen içerik); bir kez, önizleyen kullanıcı kullanır.
- external_origins: bilginin dış kökeni (proje başına dış anahtar tekil, sayfa başına bir köken).

Revision ID: 0010
Revises: 0009
"""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def _role() -> str:
    role = os.getenv("METIS_APP_ROLE", "metis_app")
    if not role.replace("_", "").isalnum():
        raise RuntimeError("METIS_APP_ROLE yalnız harf, rakam ve alt çizgi içermeli.")
    return role


def _now() -> sa.Column:
    return sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "external_connections",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("secret_enc", sa.Text(), nullable=False, server_default=""),
        sa.Column("allowed_scopes", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind in ('confluence','gitlab')", name="ck_external_connection_kind"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "external_imports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("connection_id", sa.UUID(), nullable=False),
        sa.Column("external_key", sa.String(300), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("version", sa.String(80), nullable=False, server_default=""),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False, server_default=""),
        sa.Column("body_sha256", sa.String(64), nullable=False),
        sa.Column("attachment_ids", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("skipped", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["connection_id"], ["external_connections.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_external_imports_project_id"), "external_imports", ["project_id"])
    op.create_index(op.f("ix_external_imports_user_id"), "external_imports", ["user_id"])
    op.create_table(
        "external_origins",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("page_id", sa.UUID(), nullable=False),
        sa.Column("connection_id", sa.UUID(), nullable=False),
        sa.Column("external_key", sa.String(300), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("version", sa.String(80), nullable=False, server_default=""),
        sa.Column("imported_body_sha256", sa.String(64), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.Column("imported_by", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"]),
        sa.ForeignKeyConstraint(["connection_id"], ["external_connections.id"]),
        sa.ForeignKeyConstraint(["imported_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "external_key", name="uq_external_origin_key"),
        sa.UniqueConstraint("page_id", name="uq_external_origin_page"),
    )
    op.create_index(op.f("ix_external_origins_project_id"), "external_origins", ["project_id"])
    op.create_index(op.f("ix_external_origins_page_id"), "external_origins", ["page_id"])
    role = _role()
    for table in ("external_connections", "external_imports", "external_origins"):
        op.execute(
            f"""
            DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                EXECUTE 'GRANT SELECT, INSERT, UPDATE ON {table} TO {role}';
              END IF;
            END $$;
            """
        )


def downgrade() -> None:
    op.drop_table("external_origins")
    op.drop_table("external_imports")
    op.drop_table("external_connections")
