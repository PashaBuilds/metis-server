"""Atomik yayın: proje satır kilidi → yeni publication (manifest) → arama indeksi → aktif yayın işaretçisi.

Hepsi tek transaction'da; arada hata olursa transaction geri alınır ve eski yayın hizmete devam eder.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from metis.core.db import utcnow
from metis.core.models import (
    Page,
    PageRevision,
    Project,
    Publication,
    PublicationPage,
    PublicationRelation,
    Relation,
    Source,
)
from metis.modules.search import index as search_index


def active_manifest(db: Session, project: Project) -> dict[uuid.UUID, uuid.UUID]:
    if not project.active_publication_id:
        return {}
    rows = db.execute(
        select(PublicationPage.page_id, PublicationPage.revision_id).where(
            PublicationPage.publication_id == project.active_publication_id
        )
    ).all()
    return dict(rows)


def active_relations(db: Session, project: Project) -> dict[uuid.UUID, uuid.UUID]:
    if not project.active_publication_id:
        return {}
    rows = db.execute(
        select(PublicationRelation.relation_id, PublicationRelation.revision_id).where(
            PublicationRelation.publication_id == project.active_publication_id
        )
    ).all()
    return dict(rows)


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
    manifest = active_manifest(db, project)
    relations = active_relations(db, project)
    for pid in removals:
        manifest.pop(pid, None)
    manifest.update(upserts)
    # Kaldırılan sayfalara bağlı ilişkiler de yayından çıkar.
    if removals:
        from metis.core.models import RelationRevision

        for rel_id, rev_id in list(relations.items()):
            rr = db.get(RelationRevision, rev_id)
            if rr and (rr.subject_page_id in removals or rr.object_page_id in removals):
                relation_removals.add(rel_id)
    for rid in relation_removals:
        relations.pop(rid, None)
    relations.update(relation_upserts)

    seq = (db.scalar(select(func.max(Publication.seq)).where(Publication.project_id == project.id)) or 0) + 1
    pub = Publication(project_id=project.id, change_set_id=change_set_id, kind=kind, created_by=actor_id, seq=seq)
    db.add(pub)
    db.flush()
    db.add_all([PublicationPage(publication_id=pub.id, page_id=p, revision_id=r) for p, r in manifest.items()])
    db.add_all(
        [PublicationRelation(publication_id=pub.id, relation_id=rel, revision_id=r) for rel, r in relations.items()]
    )
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
