"""model zenginleştirmesi varsayılan kapalı — 2026-10-26 (ürün sahibinin kararı)

Kurgusal 20 bin sayfalık ölçümde gerçek modelle (DeepSeek flash) arama kalitesine ölçülebilir katkı görülmedi; bölüm başına
model token'ı harcar. Yeni projeler kapalı başlar. Yükseltmede henüz hiç zenginleştirilmemiş projeler kapatılır (2.0.21
öncesinden gelen kurulumlarda 0013 ile 0016 aynı yükseltmede uygulanır: hepsi kapanır). Zenginleştirmesi saklanmış proje
açık kalır, çünkü blokları zenginleştirmeyle indekslidir; kapatmak (Ayarlar → İnceleme politikası) indeksi yeniden kurar.

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


FLIP = """UPDATE projects p SET enrichment_enabled = false
           WHERE p.enrichment_enabled
             AND NOT EXISTS (SELECT 1 FROM passage_enrichments pe WHERE pe.project_id = p.id AND pe.status = 'ok')"""


def upgrade() -> None:
    op.alter_column("projects", "enrichment_enabled", server_default=sa.false())
    op.execute(FLIP)


def downgrade() -> None:
    op.alter_column("projects", "enrichment_enabled", server_default=sa.true())
