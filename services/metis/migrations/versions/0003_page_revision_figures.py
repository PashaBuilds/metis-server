"""açıklayıcı görseller: page_revision_figures (değişmez)

Revision ID: 0003
Revises: 0002
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _role() -> str:
    role = os.getenv("METIS_APP_ROLE", "metis_app")
    if not role.replace("_", "").isalnum():
        raise RuntimeError("METIS_APP_ROLE yalnız harf, rakam ve alt çizgi içermeli.")
    return role


def upgrade() -> None:
    op.create_table(
        "page_revision_figures",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("page_revision_id", sa.UUID(), nullable=False),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("source_revision_id", sa.UUID(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["page_revision_id"], ["page_revisions.id"]),
        sa.ForeignKeyConstraint(["source_revision_id"], ["source_revisions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("page_revision_id", "ord", name="uq_figure_ord"),
    )
    op.create_index(op.f("ix_page_revision_figures_page_revision_id"), "page_revision_figures", ["page_revision_id"])
    op.create_index(op.f("ix_page_revision_figures_source_revision_id"), "page_revision_figures", ["source_revision_id"])
    op.execute(
        "CREATE TRIGGER immutable_page_revision_figures BEFORE UPDATE OR DELETE ON page_revision_figures "
        "FOR EACH ROW EXECUTE FUNCTION metis_immutable()"
    )
    role = _role()
    op.execute(
        f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
            EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON page_revision_figures TO {role}';
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS immutable_page_revision_figures ON page_revision_figures")
    op.drop_table("page_revision_figures")
