"""yazar yayımlar politikası (self_publish) — ürün sahibinin kararı 2026-10-18

Var olan projeler "Yazar yayımlar"a geçer; "Bağımsız inceleme" Ayarlar'dan yeniden seçilebilir.

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_projects_policy", "projects", type_="check")
    op.create_check_constraint("ck_projects_policy", "projects", "review_policy in ('independent','owner_review','self_publish')")
    op.execute("UPDATE projects SET review_policy = 'self_publish'")


def downgrade() -> None:
    op.execute("UPDATE projects SET review_policy = 'independent' WHERE review_policy = 'self_publish'")
    op.drop_constraint("ck_projects_policy", "projects", type_="check")
    op.create_check_constraint("ck_projects_policy", "projects", "review_policy in ('independent','owner_review')")
