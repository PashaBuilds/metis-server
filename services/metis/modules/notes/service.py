"""Not tabanlı bilgi: taslağın notu sayfaya bağlı bir uzman notu kaynağına yazılır, her blok bir iddia olur.

Kaynak ↔ sayfa 1:1 (`pages.note_source_id`). Not değişmedikçe yeni kaynak revizyonu açılmaz. Notun kendi yeni
revizyonu "kaynak değişti" sayılmaz (`mark_dependents` çağrılmaz; bakım taraması bu kaynağı atlar).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from metis.core.models import Evidence, Page, Source, SourceRevision, User
from metis.modules.changes import schemas
from metis.modules.notes.blocks import note_blocks
from metis.modules.scopes.semantics import normalize_scope
from metis.modules.sources.locator import build_locator
from metis.modules.sources.service import TEXT_EXTRACTOR, PreparedContent, _write_revision, current_revision


def _note_revision(db: Session, author: User, source: Source, text: str, scope: dict) -> SourceRevision:
    latest = current_revision(db, source)
    if latest is not None and latest.text == text and normalize_scope(latest.scope) == normalize_scope(scope):
        return latest
    content = PreparedContent(text.encode("utf-8"), "not.md", "text/markdown", text, "complete", TEXT_EXTRACTOR)
    return _write_revision(db, author, source, content, scope, {})


def _span_evidence(db: Session, rev: SourceRevision, start: int, end: int) -> Evidence:
    existing = db.scalar(
        select(Evidence).where(Evidence.source_revision_id == rev.id, Evidence.char_start == start, Evidence.char_end == end)
    )
    if existing:
        return existing
    ev = Evidence(
        source_revision_id=rev.id,
        locator=build_locator(rev.text, start, end, rev.meta),
        excerpt=rev.text[start:end],
        char_start=start,
        char_end=end,
    )
    db.add(ev)
    db.flush()
    return ev


def materialize_note(
    db: Session, author: User, project_id: uuid.UUID, page: Page | None, item: schemas.ItemIn, scope: dict
) -> tuple[Page, list[schemas.ClaimIn]]:
    """Not tabanlı öğe için sayfayı (gerekirse) ve not kaynağı revizyonunu hazırlar; nottan üretilen iddiaları döner."""
    if page is None:
        page = Page(project_id=project_id, kind=item.kind, owner_id=author.id, current_revision_no=0)
        db.add(page)
        db.flush()
    source = db.get(Source, page.note_source_id) if page.note_source_id else None
    if source is None:
        source = Source(project_id=project_id, owner_id=author.id, title=item.title.strip(), kind="note")
        db.add(source)
        db.flush()
        page.note_source_id = source.id
    elif source.title != item.title.strip():
        source.title = item.title.strip()
    text = item.body_md.replace("\r\n", "\n")
    rev = _note_revision(db, author, source, text, scope)
    claims = []
    for start, end in note_blocks(rev.text):
        ev = _span_evidence(db, rev, start, end)
        claims.append(
            schemas.ClaimIn(statement=ev.excerpt, kind="expert_statement", evidence=[schemas.EvidenceRef(evidence_id=ev.id, quote=ev.excerpt)])
        )
    return page, claims
