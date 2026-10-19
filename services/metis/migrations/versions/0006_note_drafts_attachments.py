"""not tabanlı bilgi ve ekler (2026-10-19, ürün sahibinin kararı)

- pages.note_source_id: sayfanın dayanağı olan uzman notu kaynağı (1:1; eski sayfalarda boş).
- attachments, page_revision_attachments: bilgi revizyonunun ekleri (görsel/PDF; değişmez).

Revision ID: 0006
Revises: 0005
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def _role() -> str:
    role = os.getenv("METIS_APP_ROLE", "metis_app")
    if not role.replace("_", "").isalnum():
        raise RuntimeError("METIS_APP_ROLE yalnız harf, rakam ve alt çizgi içermeli.")
    return role


def upgrade() -> None:
    op.add_column("pages", sa.Column("note_source_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_pages_note_source_id", "pages", "sources", ["note_source_id"], ["id"])
    op.create_index(op.f("ix_pages_note_source_id"), "pages", ["note_source_id"])
    op.create_table(
        "attachments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("uploader_id", sa.UUID(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["uploader_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("project_id", "uploader_id", "sha256"):
        op.create_index(op.f(f"ix_attachments_{col}"), "attachments", [col])
    op.create_table(
        "page_revision_attachments",
        sa.Column("page_revision_id", sa.UUID(), nullable=False),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("attachment_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["page_revision_id"], ["page_revisions.id"]),
        sa.ForeignKeyConstraint(["attachment_id"], ["attachments.id"]),
        sa.PrimaryKeyConstraint("page_revision_id", "ord"),
    )
    op.create_index(op.f("ix_page_revision_attachments_page_revision_id"), "page_revision_attachments", ["page_revision_id"])
    op.create_index(op.f("ix_page_revision_attachments_attachment_id"), "page_revision_attachments", ["attachment_id"])
    role = _role()
    for table in ("attachments", "page_revision_attachments"):
        op.execute(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION metis_immutable()")
        op.execute(
            f"""
            DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                EXECUTE 'GRANT SELECT, INSERT ON {table} TO {role}';
              END IF;
            END $$;
            """
        )


def downgrade() -> None:
    for table in ("page_revision_attachments", "attachments"):
        op.execute(f"DROP TRIGGER IF EXISTS immutable_{table} ON {table}")
        op.drop_table(table)
    op.drop_index(op.f("ix_pages_note_source_id"), table_name="pages")
    op.drop_constraint("fk_pages_note_source_id", "pages", type_="foreignkey")
    op.drop_column("pages", "note_source_id")
