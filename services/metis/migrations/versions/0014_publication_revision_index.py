"""ölçek: publication_pages.revision_id dizini — 2026-10-26

Ölçek denemesi (evals/scale): yayın manifesti her yayında tüm sayfaları taşır; "bu revizyon yayımlandı mı" sorgusu
(yetki denetimi, geçmiş) dizinsiz tüm manifest geçmişini tarıyordu (1 bin sayfada 100 bin satır, yayın başına yüzlerce kez).

Revision ID: 0014
Revises: 0013
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_publication_pages_revision_id", "publication_pages", ["revision_id"])


def downgrade() -> None:
    op.drop_index("ix_publication_pages_revision_id", table_name="publication_pages")
