"""yayın listesi yalnız değişenler — 2026-10-27 (ürün sahibinin kararı)

Önce her yayın tüm sayfaların (ve ilişkilerin) listesini yazıyordu; 20 bin kurgusal sayfada 40 milyon satır / 6,1 GB
(veritabanının dörtte üçü). Artık:

- `publication_pages` / `publication_relations` yalnız o yayında değişenleri tutar; `revision_id` boş = o yayında çıktı.
  Tablolar değişmez kalır (trigger); bir yayının tam listesi değişikliklerden kurulur (`publish.manifest_at`).
- `active_pages` / `active_relations`: aktif yayındaki güncel liste; yayınla aynı transaction'da güncellenir.

Yükseltme mevcut tam listeleri değişikliklere çevirir (bilgi kaybı yok: her yayının tam listesi aynen geri kurulur);
geri alma tam listeleri yeniden yazar (büyük veritabanında yükseltmeden yavaş: yayın × sayfa satır üretir). Dönüşüm yalnız migration rolüyle, değişmezlik trigger'ı atlanarak (TRUNCATE) yapılır.

Revision ID: 0017
Revises: 0016
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

TABLES = (("publication_pages", "page_id"), ("publication_relations", "relation_id"))


def to_changes(table: str, key: str, pubs: str = "publications") -> list[str]:
    """Tam listeleri değişikliklere çevirir: önceki yayına göre yeni/değişen satırlar + çıkanlar için boş revizyon."""
    return [
        f"""CREATE TEMP TABLE _changes AS
            WITH o AS (SELECT id, lag(id) OVER (PARTITION BY project_id ORDER BY seq, created_at) AS prev FROM {pubs})
            SELECT x.publication_id, x.{key}, x.revision_id FROM {table} x JOIN o ON o.id = x.publication_id
             WHERE o.prev IS NULL OR NOT EXISTS (
                   SELECT 1 FROM {table} y WHERE y.publication_id = o.prev AND y.{key} = x.{key} AND y.revision_id = x.revision_id)
            UNION ALL
            SELECT o.id, y.{key}, NULL::uuid FROM o JOIN {table} y ON y.publication_id = o.prev
             WHERE NOT EXISTS (SELECT 1 FROM {table} x WHERE x.publication_id = o.id AND x.{key} = y.{key})""",
        f"TRUNCATE {table}",
        f"INSERT INTO {table} (publication_id, {key}, revision_id) SELECT * FROM _changes",
        "DROP TABLE _changes",
    ]


def to_full_lists(table: str, key: str, pubs: str = "publications") -> list[str]:
    """Değişikliklerden her yayının tam listesini yeniden yazar (geri alma)."""
    return [
        f"""CREATE TEMP TABLE _full AS
            SELECT o.id AS publication_id, d.{key}, d.revision_id FROM {pubs} o CROSS JOIN LATERAL (
              SELECT DISTINCT ON (x.{key}) x.{key}, x.revision_id FROM {table} x JOIN {pubs} p ON p.id = x.publication_id
               WHERE p.project_id = o.project_id AND (p.seq, p.created_at) <= (o.seq, o.created_at)
               ORDER BY x.{key}, p.seq DESC, p.created_at DESC) d
             WHERE d.revision_id IS NOT NULL""",
        f"TRUNCATE {table}",
        f"INSERT INTO {table} (publication_id, {key}, revision_id) SELECT * FROM _full",
        "DROP TABLE _full",
    ]


def _grant(table: str, privileges: str) -> None:
    role = os.getenv("METIS_APP_ROLE", "metis_app")
    if not role.replace("_", "").isalnum():
        raise RuntimeError("METIS_APP_ROLE yalnız harf, rakam ve alt çizgi içermeli.")
    op.execute(
        f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
            EXECUTE 'GRANT {privileges} ON {table} TO {role}';
          END IF;
        END $$;
        """
    )


def upgrade() -> None:
    op.create_table(
        "active_pages",
        sa.Column("page_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("revision_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["revision_id"], ["page_revisions.id"]),
        sa.PrimaryKeyConstraint("page_id"),
    )
    op.create_index(op.f("ix_active_pages_project_id"), "active_pages", ["project_id"])
    op.create_index(op.f("ix_active_pages_revision_id"), "active_pages", ["revision_id"])
    op.create_table(
        "active_relations",
        sa.Column("relation_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("revision_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["relation_id"], ["relations.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["revision_id"], ["relation_revisions.id"]),
        sa.PrimaryKeyConstraint("relation_id"),
    )
    op.create_index(op.f("ix_active_relations_project_id"), "active_relations", ["project_id"])
    op.create_index(op.f("ix_active_relations_revision_id"), "active_relations", ["revision_id"])
    op.execute(
        "INSERT INTO active_pages (page_id, project_id, revision_id) SELECT x.page_id, p.id, x.revision_id "
        "FROM projects p JOIN publication_pages x ON x.publication_id = p.active_publication_id"
    )
    op.execute(
        "INSERT INTO active_relations (relation_id, project_id, revision_id) SELECT x.relation_id, p.id, x.revision_id "
        "FROM projects p JOIN publication_relations x ON x.publication_id = p.active_publication_id"
    )
    for table, key in TABLES:
        op.alter_column(table, "revision_id", nullable=True)
        for statement in to_changes(table, key):
            op.execute(statement)
    _grant("active_pages", "SELECT, INSERT, UPDATE, DELETE")
    _grant("active_relations", "SELECT, INSERT, UPDATE, DELETE")


def downgrade() -> None:
    for table, key in TABLES:
        for statement in to_full_lists(table, key):
            op.execute(statement)
        op.alter_column(table, "revision_id", nullable=False)
    op.drop_table("active_relations")
    op.drop_table("active_pages")
