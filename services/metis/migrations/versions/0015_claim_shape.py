"""ölçek: iddia biçim özeti (claims.shape_md5) — 2026-10-26

Yayın öncesi kural kontrolü ve bakım taraması "aynı biçimli (sayılar #) fakat farklı değerli" iddiaları arar. Büyük
derlemde (20 bin sayfa, 230 bin iddia) her kontrol tüm iddiaları uygulamaya taşıyordu; özet PostgreSQL'de hesaplanır
(yazma yolları değişmez; revizyonlar değişmez kalır) ve dizinlenir. Küçültme ICU ile (yerel ayardan bağımsız); ICU'suz
PostgreSQL'de yerel ayarın `lower`'ı kullanılır ("İ" gibi harflerde aday kaçabilir; yükseltme durmaz).

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


# metis.core.models.claim_shape_sql("statement") ile aynı (migration uygulama koduna bağlı kalmasın diye sabit)
SHAPE = r"""regexp_replace(regexp_replace(translate(replace(lower(statement COLLATE "und-x-icu"), 'ß', 'ss'), 'µς', 'μσ'), '\d+([.,]\d+)?', '#', 'g'), '^\s+|\s+$', '', 'g')"""


def upgrade() -> None:
    shape = SHAPE
    if not op.get_bind().scalar(sa.text("SELECT 1 FROM pg_collation WHERE collname = 'und-x-icu'")):
        # Uygulama bunu görür (maintenance.shape_prefilter) ve ön süzgeci kullanmaz: sonuç aynı, yalnız daha yavaş.
        print("UYARI: PostgreSQL'de ICU yok; iddia biçim özeti yerel ayarla hesaplanır, ön süzgeç kapalı kalır.")  # noqa: T201
        shape = shape.replace(' COLLATE "und-x-icu"', "")
    # Tablo yeniden yazılır; satır tetikleyicileri (revizyon değişmezliği) çalışmaz, içerik değişmez.
    op.execute(f"ALTER TABLE claims ADD COLUMN shape_md5 text GENERATED ALWAYS AS (md5({shape})) STORED")
    op.create_index("ix_claims_shape_md5", "claims", ["shape_md5"])


def downgrade() -> None:
    op.drop_index("ix_claims_shape_md5", table_name="claims")
    op.drop_column("claims", "shape_md5")
