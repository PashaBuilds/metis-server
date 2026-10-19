"""Not tabanlı bilgi: taslağın notu sayfaya bağlı bir uzman notu kaynağına yazılır, her blok bir iddia olur.

Kaynak ↔ sayfa 1:1 (`pages.note_source_id`). Not değişmedikçe yeni kaynak revizyonu açılmaz. Notun kendi yeni
revizyonu "kaynak değişti" sayılmaz (`mark_dependents` çağrılmaz; bakım taraması bu kaynağı atlar).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from pydantic import ValidationError
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


@dataclass
class ConversionReport:
    created: int = 0
    skipped: list[dict] = field(default_factory=list)  # [{source_id, title, reason}]


def convert_standalone_sources(db: Session) -> ConversionReport:
    """Eski yöntemden kalan bağımsız kaynakları (hiçbir bilgiye dayanak olmamış) yazarı adına not taslağına çevirir.

    Yazarın kendi metni (not ya da görsel/PDF açıklaması) → not; görsel/PDF dosyası → ek. PDF'ten çıkarılmış metin
    nota konmaz (Metis yalnız yazılı notu okur). Kaynak silinmez. İdempotent: dönüştürülen kaynak taslağın
    `detail.converted_from_source` alanında işaretlenir. Dönüştürülemeyen kaynak (ör. yazarın artık katkı rolü yok)
    olduğu gibi kalır ve nedeniyle raporlanır.
    """
    from metis.core.errors import AppError
    from metis.core.models import Attachment, ChangeSet, Claim, ClaimEvidence, PageRevisionFigure
    from metis.modules.changes.service import create_change
    from metis.modules.scopes.schemas import ScopeIn

    used = (
        set(db.scalars(select(Page.note_source_id).where(Page.note_source_id.is_not(None))))
        | set(
            db.scalars(
                select(SourceRevision.source_id)
                .join(Evidence, Evidence.source_revision_id == SourceRevision.id)
                .join(ClaimEvidence, ClaimEvidence.evidence_id == Evidence.id)
                .join(Claim, Claim.id == ClaimEvidence.claim_id)
            )
        )
        | set(db.scalars(select(SourceRevision.source_id).join(PageRevisionFigure, PageRevisionFigure.source_revision_id == SourceRevision.id)))
    )
    done = {c.detail.get("converted_from_source") for c in db.scalars(select(ChangeSet)) if c.detail.get("converted_from_source")}
    report = ConversionReport()
    for source in db.scalars(select(Source).where(Source.deleted_at.is_(None)).order_by(Source.created_at)).all():
        if source.id in used or str(source.id) in done:
            continue
        rev = current_revision(db, source)
        author = db.get(User, source.owner_id)
        if rev is None or author is None:
            report.skipped.append({"source_id": str(source.id), "title": source.title, "reason": "revision or author missing"})
            continue
        pdf_text = rev.media_type == "application/pdf" and rev.extraction != "annotation_only"
        note = "" if pdf_text else rev.text  # PDF'ten çıkarılmış metin yazarın notu değildir
        try:
            with db.begin_nested():  # başarısızlıkta ek satırı da geri alınır
                attachments = []
                if rev.media_type.startswith("image/") or rev.media_type == "application/pdf":
                    att = Attachment(
                        project_id=source.project_id,
                        uploader_id=author.id,
                        sha256=rev.sha256,
                        filename=rev.filename,
                        media_type=rev.media_type,
                        size_bytes=rev.size_bytes,
                    )
                    db.add(att)
                    db.flush()
                    attachments.append(att.id)
                item = schemas.ItemIn(note=True, title=source.title, body_md=note, scope=ScopeIn(**rev.scope), attachments=attachments)
                change = create_change(db, author, source.project_id, schemas.ChangeCreateIn(summary=source.title, items=[item]))
        except (AppError, ValidationError) as exc:
            reason = exc.code if isinstance(exc, AppError) else "validation_error"
            report.skipped.append({"source_id": str(source.id), "title": source.title, "reason": reason})
            continue
        change.detail = {**change.detail, "converted_from_source": str(source.id)}
        report.created += 1
    return report


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
    elif page.published_revision_id is None and source.title != item.title.strip():
        source.title = item.title.strip()  # yayındaki bilginin başlığı ancak yayımlanınca değişir (knowledge.publish)
    text = item.body_md.replace("\r\n", "\n")
    rev = _note_revision(db, author, source, text, scope)
    claims = []
    for start, end in note_blocks(rev.text):
        ev = _span_evidence(db, rev, start, end)
        claims.append(
            schemas.ClaimIn(statement=ev.excerpt, kind="expert_statement", evidence=[schemas.EvidenceRef(evidence_id=ev.id, quote=ev.excerpt)])
        )
    return page, claims
