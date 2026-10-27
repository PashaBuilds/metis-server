"""Atomik yayın: proje satır kilidi → yeni publication (değişenler) → güncel liste → arama indeksi → aktif yayın işaretçisi.

Hepsi tek transaction'da; arada hata olursa transaction geri alınır ve eski yayın hizmete devam eder.

Yayın yalnız değişen sayfa/ilişkileri yazar (`revision_id` boş = çıktı); şu an yayında olan liste `active_pages` /
`active_relations`'tadır. Bir yayının tam listesi `manifest_at` ile değişikliklerden kurulur (ürün sahibinin kararı
2026-10-27: tam liste 20 bin sayfada 40 milyon satır / 6,1 GB etmişti).
"""

from __future__ import annotations

import uuid

from sqlalchemy import any_, bindparam, delete, func, literal, select, tuple_
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from metis.core.db import utcnow
from metis.core.models import (
    ActivePage,
    ActiveRelation,
    Page,
    PageRevision,
    Project,
    Publication,
    PublicationPage,
    PublicationRelation,
    Relation,
    RelationRevision,
    Source,
)
from metis.modules.search import index as search_index


def manifest_at(db: Session, publication: Publication) -> tuple[dict[uuid.UUID, uuid.UUID], dict[uuid.UUID, uuid.UUID]]:
    """Yayın anındaki tam liste (sayfa → revizyon, ilişki → revizyon): her öğenin o yayına kadarki son değişikliği."""
    # Sıra (seq, created_at): migration 0017 ile aynı; seq tekil kısıtlı değil.
    upto = select(Publication.id, Publication.seq, Publication.created_at).where(
        Publication.project_id == publication.project_id,
        tuple_(Publication.seq, Publication.created_at) <= tuple_(literal(publication.seq), literal(publication.created_at)),
    ).subquery()

    def latest(table, key) -> dict[uuid.UUID, uuid.UUID]:  # noqa: ANN001
        rows = db.execute(
            select(key, table.revision_id)
            .join(upto, upto.c.id == table.publication_id)
            .distinct(key)
            .order_by(key, upto.c.seq.desc(), upto.c.created_at.desc())
        ).all()
        return {k: r for k, r in rows if r is not None}

    return latest(PublicationPage, PublicationPage.page_id), latest(PublicationRelation, PublicationRelation.relation_id)


def _ids(name: str, ids: set[uuid.UUID] | list[uuid.UUID]):  # noqa: ANN202
    """Dizi parametresi: büyük kümede `in_()` PostgreSQL'in 65535 parametre sınırına takılır."""
    return any_(bindparam(name, list(ids), type_=ARRAY(PG_UUID(as_uuid=True))))


def _upsert(db: Session, model, key, rows: list[dict]) -> None:  # noqa: ANN001
    """Güncel listeye tek sorguda ekle/güncelle (satır başına SELECT yok)."""
    if rows:
        stmt = pg_insert(model).values(rows)
        db.execute(stmt.on_conflict_do_update(index_elements=[key], set_={"revision_id": stmt.excluded.revision_id}))


def _changes(
    current: dict[uuid.UUID, uuid.UUID], removals: set[uuid.UUID], upserts: dict[uuid.UUID, uuid.UUID]
) -> dict[uuid.UUID, uuid.UUID | None]:
    out: dict[uuid.UUID, uuid.UUID | None] = {k: None for k in removals if k in current}
    for k, r in upserts.items():
        if current.get(k) == r:
            out.pop(k, None)
        else:
            out[k] = r
    return out


def publish(
    db: Session,
    project: Project,
    *,
    actor_id: uuid.UUID | None,
    change_set_id: uuid.UUID | None,
    kind: str,
    upserts: dict[uuid.UUID, uuid.UUID] | None = None,
    removals: set[uuid.UUID] | None = None,
    relation_upserts: dict[uuid.UUID, uuid.UUID] | None = None,
    relation_removals: set[uuid.UUID] | None = None,
) -> Publication:
    """`project` çağıran tarafından FOR UPDATE ile kilitlenmiş olmalı."""
    upserts = upserts or {}
    removals = removals or set()
    relation_upserts = relation_upserts or {}
    relation_removals = set(relation_removals or set())
    touched = set(upserts) | removals
    current = (
        dict(db.execute(select(ActivePage.page_id, ActivePage.revision_id).where(ActivePage.page_id == _ids("touched", touched))).all())
        if touched
        else {}
    )
    # Kaldırılan sayfalara bağlı ilişkiler de yayından çıkar.
    if removals:
        relation_removals |= set(
            db.scalars(
                select(ActiveRelation.relation_id)
                .join(RelationRevision, RelationRevision.id == ActiveRelation.revision_id)
                .where(
                    ActiveRelation.project_id == project.id,
                    (RelationRevision.subject_page_id == _ids("rs", removals)) | (RelationRevision.object_page_id == _ids("ro", removals)),
                )
            )
        )
    rel_touched = set(relation_upserts) | relation_removals
    current_rel = (
        dict(
            db.execute(
                select(ActiveRelation.relation_id, ActiveRelation.revision_id).where(ActiveRelation.relation_id == _ids("rel_touched", rel_touched))
            ).all()
        )
        if rel_touched
        else {}
    )
    # Öğe başına sonuç: kaldırma önce, ekleme/güncelleme sonra (ikisi birden verilirse güncelleme kazanır).
    page_changes = _changes(current, removals, upserts)
    rel_changes = _changes(current_rel, relation_removals, relation_upserts)

    seq = (db.scalar(select(func.max(Publication.seq)).where(Publication.project_id == project.id)) or 0) + 1
    pub = Publication(project_id=project.id, change_set_id=change_set_id, kind=kind, created_by=actor_id, seq=seq)
    db.add(pub)
    db.flush()
    db.add_all([PublicationPage(publication_id=pub.id, page_id=p, revision_id=r) for p, r in page_changes.items()])
    db.add_all([PublicationRelation(publication_id=pub.id, relation_id=x, revision_id=r) for x, r in rel_changes.items()])
    gone = [p for p, r in page_changes.items() if r is None]
    if gone:
        db.execute(delete(ActivePage).where(ActivePage.page_id == _ids("gone", gone)))
    _upsert(db, ActivePage, ActivePage.page_id, [{"page_id": p, "project_id": project.id, "revision_id": r} for p, r in page_changes.items() if r is not None])
    gone_rel = [x for x, r in rel_changes.items() if r is None]
    if gone_rel:
        db.execute(delete(ActiveRelation).where(ActiveRelation.relation_id == _ids("gone_rel", gone_rel)))
    _upsert(db, ActiveRelation, ActiveRelation.relation_id, [{"relation_id": x, "project_id": project.id, "revision_id": r} for x, r in rel_changes.items() if r is not None])
    db.flush()

    now = utcnow()
    for pid, rid in upserts.items():
        page = db.get(Page, pid)
        assert page is not None
        page.published_revision_id = rid
        page.lifecycle = "active"
        if page.note_source_id is not None:  # bilginin notu yayımlanan başlığı taşır
            note, prev = db.get(Source, page.note_source_id), db.get(PageRevision, rid)
            if note is not None and prev is not None:
                note.title = prev.title
        page.freshness = "current"
        page.published_at = now
        page.reviewed_at = now
    for pid in removals:
        page = db.get(Page, pid)
        if page is not None and page.lifecycle == "active":
            page.lifecycle = "withdrawn"
    for rel_id, rev_id in relation_upserts.items():
        rel = db.get(Relation, rel_id)
        if rel:
            rel.published_revision_id = rev_id
    for rel_id in relation_removals:
        rel = db.get(Relation, rel_id)
        if rel:
            rel.published_revision_id = None

    search_index.index_pages(db, project.id, pub.id, set(upserts) | removals)
    project.active_publication_id = pub.id
    db.flush()
    return pub
