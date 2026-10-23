"""geri bildirim: kullanıcıların hata ve istekleri, ekran görüntüleriyle — ürün sahibinin isteği 2026-10-23

- feedback: hata ya da istek; giriş yapmış herkes görür. Durum ve cevap yalnız yöneticide. Silme = deleted_at.
- feedback_images: görseller; önce yüklenir (feedback_id boş), bildirim gönderilince bağlanır.

Revision ID: 0009
Revises: 0008
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def _role() -> str:
    role = os.getenv("METIS_APP_ROLE", "metis_app")
    if not role.replace("_", "").isalnum():
        raise RuntimeError("METIS_APP_ROLE yalnız harf, rakam ve alt çizgi içermeli.")
    return role


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="new"),
        sa.Column("reply", sa.Text(), nullable=False, server_default=""),
        sa.Column("reply_by", sa.UUID(), nullable=True),
        sa.Column("reply_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.UUID(), nullable=True),
        sa.CheckConstraint("kind in ('bug','request')", name="ck_feedback_kind"),
        sa.CheckConstraint("status in ('new','in_progress','done','wontfix')", name="ck_feedback_status"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reply_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["deleted_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("seq", name="uq_feedback_seq"),
    )
    op.create_index(op.f("ix_feedback_author_id"), "feedback", ["author_id"])
    op.create_table(
        "feedback_images",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("uploader_id", sa.UUID(), nullable=False),
        sa.Column("feedback_id", sa.UUID(), nullable=True),
        sa.Column("ord", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["uploader_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["feedback_id"], ["feedback.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_feedback_images_uploader_id"), "feedback_images", ["uploader_id"])
    op.create_index(op.f("ix_feedback_images_feedback_id"), "feedback_images", ["feedback_id"])
    role = _role()
    for table in ("feedback", "feedback_images"):
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
    op.drop_table("feedback_images")
    op.drop_table("feedback")
