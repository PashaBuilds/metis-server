"""not tabanlı bilgi ve ekler (2026-10-19, ürün sahibinin kararı)

- pages.note_source_id: sayfanın dayanağı olan uzman notu kaynağı (1:1; eski sayfalarda boş).

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pages", sa.Column("note_source_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_pages_note_source_id", "pages", "sources", ["note_source_id"], ["id"])
    op.create_index(op.f("ix_pages_note_source_id"), "pages", ["note_source_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_pages_note_source_id"), table_name="pages")
    op.drop_constraint("fk_pages_note_source_id", "pages", type_="foreignkey")
    op.drop_column("pages", "note_source_id")
