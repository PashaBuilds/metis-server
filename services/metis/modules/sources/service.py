from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from metis.core.access import can_read_source, evidence_access, readable_source_ids, require_human, require_member
from metis.core.audit import audit
from metis.core.blobs import put_blob, read_blob
from metis.core.config import get_settings
from metis.core.db import utcnow
from metis.core.errors import AppError
from metis.core.models import (
    ChangeSet,
    ChangeSetItem,
    Claim,
    ClaimEvidence,
    Evidence,
    Finding,
    FindingPage,
    Page,
    PageRevision,
    PageRevisionFigure,
    ProjectMember,
    Source,
    SourceAcl,
    SourceRevision,
    User,
)
from metis.core.util import fingerprint
from metis.modules.scopes.semantics import overlaps
from metis.modules.scopes.service import lock_project, validate_selection
from metis.modules.sources import schemas
from metis.modules.sources.files import CheckedFile, check_upload
from metis.modules.sources.locator import build_locator, locator_label
from metis.modules.sources.pdf_extract import EXTRACTOR_VERSION, extract_isolated

TEXT_EXTRACTOR = "metis-text-v1"
ANNOTATION = "human-annotation-v1"


@dataclass
class PreparedContent:
    data: bytes
    filename: str
    media_type: str
    text: str
    extraction: str
    extractor_version: str
    pages: list[dict] = field(default_factory=list)  # [{page, start, end}]


def prepare_content(kind: str, text: str, upload: tuple[str, bytes] | None) -> PreparedContent:
    """Yavaş kısım (PDF çıkarımı) DB kilidi alınmadan önce çalışır."""
    if upload is None:
        if not text.strip():
            raise AppError("VALIDATION_ERROR", "text or file required", fields=[{"field": "text", "type": "missing"}])
        body = text.replace("\r\n", "\n")
        return PreparedContent(body.encode("utf-8"), "not.md", "text/markdown", body, "complete", TEXT_EXTRACTOR)
    checked: CheckedFile = check_upload(upload[0], upload[1], get_settings().max_upload_bytes)
    if checked.category == "text":
        return PreparedContent(
            upload[1], checked.filename, checked.media_type, checked.text, "complete", TEXT_EXTRACTOR
        )
    if checked.category == "pdf":
        result = extract_isolated(upload[1])
        if result["status"] in ("complete", "partial") and result["pages"]:
            parts, pages, cursor = [], [], 0
            for p in result["pages"]:
                if parts:
                    cursor += 2
                start = cursor
                parts.append(p["text"])
                cursor += len(p["text"])
                pages.append({"page": p["page"], "start": start, "end": cursor})
            return PreparedContent(
                upload[1],
                checked.filename,
                checked.media_type,
                "\n\n".join(parts),
                result["status"],
                EXTRACTOR_VERSION,
                pages,
            )
        return PreparedContent(
            upload[1], checked.filename, checked.media_type, text.strip(), "annotation_only", ANNOTATION
        )
    # görsel: yalnız insan açıklaması metin olarak kullanılabilir
    return PreparedContent(upload[1], checked.filename, checked.media_type, text.strip(), "annotation_only", ANNOTATION)


def _author_names(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: u.display_name for u in db.scalars(select(User).where(User.id.in_(ids)))}


def revision_out(db: Session, rev: SourceRevision, source: Source, names: dict | None = None) -> schemas.RevisionOut:
    names = names if names is not None else _author_names(db, {rev.author_id})
    page_ev = []
    if rev.meta.get("pages"):
        for ev in db.scalars(
            select(Evidence).where(Evidence.source_revision_id == rev.id, Evidence.locator["auto"].astext == "page")
        ):
            page_ev.append(evidence_out(ev))
    return schemas.RevisionOut(
        id=rev.id,
        number=rev.number,
        sha256=rev.sha256,
        media_type=rev.media_type,
        filename=rev.filename,
        size_bytes=rev.size_bytes,
        extraction=rev.extraction,  # type: ignore[arg-type]
        extractor_version=rev.extractor_version,
        scope=rev.scope,
        meta={k: v for k, v in rev.meta.items() if k != "pages"},
        created_at=rev.created_at,
        author_name=names.get(rev.author_id) if rev.author_id else None,
        is_current=rev.number == source.current_revision_no,
        page_evidence=page_ev,
    )


def evidence_out(ev: Evidence) -> schemas.EvidenceOut:
    return schemas.EvidenceOut(
        id=ev.id,
        source_revision_id=ev.source_revision_id,
        locator={k: v for k, v in ev.locator.items() if k != "auto"},
        locator_label=locator_label({k: v for k, v in ev.locator.items() if k != "auto"}),
        excerpt=ev.excerpt,
        char_start=ev.char_start,
        char_end=ev.char_end,
    )


def current_revision(db: Session, source: Source) -> SourceRevision | None:
    return db.scalar(
        select(SourceRevision).where(
            SourceRevision.source_id == source.id, SourceRevision.number == source.current_revision_no
        )
    )


def source_out(db: Session, source: Source, names: dict | None = None) -> schemas.SourceOut:
    rev = current_revision(db, source)
    names = names if names is not None else _author_names(db, {source.owner_id, rev.author_id if rev else None})
    restricted = db.scalar(select(func.count()).select_from(SourceAcl).where(SourceAcl.source_id == source.id)) or 0
    return schemas.SourceOut(
        id=source.id,
        project_id=source.project_id,
        title=source.title,
        kind=source.kind,  # type: ignore[arg-type]
        owner_id=source.owner_id,
        owner_name=names.get(source.owner_id, ""),
        current_revision_no=source.current_revision_no,
        current_revision=revision_out(db, rev, source, names) if rev else None,
        restricted=bool(restricted),
        created_at=source.created_at,
    )


def _write_revision(
    db: Session, user: User, source: Source, content: PreparedContent, scope: dict, meta: dict
) -> SourceRevision:
    digest = put_blob(content.data)
    source.current_revision_no += 1
    rev = SourceRevision(
        source_id=source.id,
        number=source.current_revision_no,
        sha256=digest,
        media_type=content.media_type,
        filename=content.filename,
        size_bytes=len(content.data),
        text=content.text,
        meta={**meta, "pages": len(content.pages)},
        scope=scope,
        extraction=content.extraction,
        extractor_version=content.extractor_version,
        author_id=user.id,
    )
    db.add(rev)
    db.flush()
    for p in content.pages:
        db.add(
            Evidence(
                source_revision_id=rev.id,
                locator={"page": p["page"], "auto": "page"},
                excerpt=content.text[p["start"] : p["end"]],
                char_start=p["start"],
                char_end=p["end"],
            )
        )
    return rev


def create_source(
    db: Session, user: User, project_id: uuid.UUID, data: schemas.SourceMetaIn, content: PreparedContent
) -> tuple[Source, SourceRevision]:
    require_human(user)
    require_member(db, user, project_id, ["contributor"])
    lock_project(db, project_id)
    scope = validate_selection(db, project_id, data.scope.model_dump())
    members = set(db.scalars(select(ProjectMember.user_id).where(ProjectMember.project_id == project_id)))
    for uid in data.acl:
        if uid not in members:
            raise AppError(
                "VALIDATION_ERROR", "ACL users must be project members", fields=[{"field": "acl", "type": "member"}]
            )
    source = Source(project_id=project_id, owner_id=user.id, title=data.title.strip(), kind=data.kind)
    db.add(source)
    db.flush()
    for uid in sorted(set(data.acl) | ({user.id} if data.acl else set())):
        db.add(SourceAcl(source_id=source.id, user_id=uid))
    meta = {
        k: getattr(data, k) for k in ("source_version", "repository", "commit", "path", "symbol") if getattr(data, k)
    }
    rev = _write_revision(db, user, source, content, scope, meta)
    audit(
        db,
        user.id,
        "source.create",
        "source",
        source.id,
        revision_id=rev.id,
        sha256=rev.sha256,
        extraction=rev.extraction,
    )
    return source, rev


def get_source(db: Session, user: User, source_id: uuid.UUID) -> Source:
    source = db.get(Source, source_id)
    if not can_read_source(db, user, source):
        raise AppError("NOT_FOUND", "source not found")
    assert source is not None
    return source


def add_revision(
    db: Session, user: User, source_id: uuid.UUID, data: schemas.RevisionMetaIn, content: PreparedContent
) -> tuple[Source, SourceRevision, list[uuid.UUID]]:
    require_human(user)
    source = get_source(db, user, source_id)
    require_member(db, user, source.project_id, ["contributor"])
    lock_project(db, source.project_id)
    db.refresh(source, with_for_update=True)
    if data.expected_revision != source.current_revision_no:
        raise AppError(
            "REVISION_CONFLICT",
            "source changed",
            expected_revision=data.expected_revision,
            current_revision=source.current_revision_no,
        )
    previous = current_revision(db, source)
    assert previous is not None
    scope = validate_selection(db, source.project_id, data.scope.model_dump()) if data.scope else previous.scope
    meta = {k: v for k, v in previous.meta.items() if k != "pages"}
    meta.update({k: getattr(data, k) for k in ("source_version", "commit", "path", "symbol") if getattr(data, k)})
    rev = _write_revision(db, user, source, content, scope, meta)
    affected = mark_dependents(db, user, source, rev)
    audit(
        db,
        user.id,
        "source.revision",
        "source",
        source.id,
        revision_id=rev.id,
        sha256=rev.sha256,
        affected_pages=affected,
    )
    return source, rev, affected


def mark_dependents(db: Session, actor: User, source: Source, new_rev: SourceRevision) -> list[uuid.UUID]:
    """Kaynak yeni revizyon alınca, eski revizyonlara dayanan yayımlanmış sayfaları işaretle."""
    rows = db.execute(
        select(Page.id, PageRevision.id, PageRevision.scope)
        .join(PageRevision, PageRevision.id == Page.published_revision_id)
        .join(Claim, Claim.page_revision_id == PageRevision.id)
        .join(ClaimEvidence, ClaimEvidence.claim_id == Claim.id)
        .join(Evidence, Evidence.id == ClaimEvidence.evidence_id)
        .join(SourceRevision, SourceRevision.id == Evidence.source_revision_id)
        .where(
            SourceRevision.source_id == source.id,
            SourceRevision.id != new_rev.id,
            Page.deleted_at.is_(None),
            Page.lifecycle == "active",
        )
        .distinct()
    ).all()
    # Açıklayıcı görsel olarak bu kaynağın eski bir revizyonunu kullanan sayfalar da işaretlenir.
    figure_rows = db.execute(
        select(Page.id, PageRevision.id, PageRevision.scope)
        .join(PageRevision, PageRevision.id == Page.published_revision_id)
        .join(PageRevisionFigure, PageRevisionFigure.page_revision_id == PageRevision.id)
        .join(SourceRevision, SourceRevision.id == PageRevisionFigure.source_revision_id)
        .where(
            SourceRevision.source_id == source.id,
            SourceRevision.id != new_rev.id,
            Page.deleted_at.is_(None),
            Page.lifecycle == "active",
        )
        .distinct()
    ).all()
    seen_pages: set[uuid.UUID] = set()
    affected = []
    for page_id, rev_id, page_scope in [*rows, *figure_rows]:
        if page_id in seen_pages:
            continue
        seen_pages.add(page_id)
        page = db.get(Page, page_id)
        assert page is not None
        same = overlaps(page_scope, new_rev.scope)
        if same:
            page.freshness = "dependency_changed"
        fp = fingerprint("source_changed", page_id, new_rev.id)
        if not db.scalar(
            select(Finding.id).where(
                Finding.project_id == source.project_id, Finding.fingerprint == fp, Finding.state == "open"
            )
        ):
            finding = Finding(
                project_id=source.project_id,
                kind="source_changed",
                severity="high" if same else "medium",
                fingerprint=fp,
                created_by=actor.id,
                detail={
                    "source_id": str(source.id),
                    "source_title": source.title,
                    "page_revision_id": str(rev_id),
                    "new_source_revision_id": str(new_rev.id),
                    "new_revision_number": new_rev.number,
                    "scope_overlaps": same,
                },
            )
            db.add(finding)
            db.flush()
            db.add(FindingPage(finding_id=finding.id, page_id=page_id))
        affected.append(page_id)
    return affected


def list_sources(
    db: Session,
    user: User,
    project_id: uuid.UUID,
    q: str = "",
    kind: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> schemas.SourceListOut:
    require_member(db, user, project_id)
    readable = readable_source_ids(db, user, project_id)
    note_sources = select(Page.note_source_id).where(Page.note_source_id.is_not(None))
    stmt = select(Source).where(
        Source.project_id == project_id,
        Source.deleted_at.is_(None),
        Source.id.in_(readable or [uuid.uuid4()]),
        Source.id.not_in(note_sources),  # not tabanlı bilgilerin notları ayrı kaynak olarak listelenmez
    )
    if q:
        stmt = stmt.where(Source.title.ilike(f"%{q.replace('%', '').replace('_', ' ')}%"))
    if kind:
        stmt = stmt.where(Source.kind == kind)
    if cursor:
        try:
            ts, sid = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
            stmt = stmt.where(tuple_(Source.created_at, Source.id) < (datetime.fromisoformat(ts), uuid.UUID(sid)))
        except (ValueError, TypeError) as exc:
            raise AppError("VALIDATION_ERROR", "bad cursor") from exc
    rows = db.scalars(stmt.order_by(Source.created_at.desc(), Source.id.desc()).limit(limit + 1)).all()
    names = _author_names(db, {r.owner_id for r in rows})
    items = [source_out(db, s, names) for s in rows[:limit]]
    nxt = None
    if len(rows) > limit:
        last = rows[limit - 1]
        nxt = base64.urlsafe_b64encode(f"{last.created_at.isoformat()}|{last.id}".encode()).decode()
    return schemas.SourceListOut(items=items, next_cursor=nxt)


def source_detail(db: Session, user: User, source_id: uuid.UUID) -> schemas.SourceDetailOut:
    source = get_source(db, user, source_id)
    revs = db.scalars(
        select(SourceRevision).where(SourceRevision.source_id == source.id).order_by(SourceRevision.number.desc())
    ).all()
    names = _author_names(db, {source.owner_id, *(r.author_id for r in revs)})
    base = source_out(db, source, names)
    current = next((r for r in revs if r.number == source.current_revision_no), None)
    acl = list(db.scalars(select(SourceAcl.user_id).where(SourceAcl.source_id == source.id)))
    return schemas.SourceDetailOut(
        **base.model_dump(),
        revisions=[revision_out(db, r, source, names) for r in revs],
        text=current.text if current else "",
        acl=acl,
    )


def get_revision(db: Session, user: User, revision_id: uuid.UUID) -> tuple[SourceRevision, Source]:
    rev = db.get(SourceRevision, revision_id)
    source = db.get(Source, rev.source_id) if rev else None
    if not rev or not can_read_source(db, user, source):
        raise AppError("NOT_FOUND", "revision not found")
    assert source is not None
    return rev, source


def download(db: Session, user: User, revision_id: uuid.UUID) -> tuple[bytes, SourceRevision]:
    rev, _ = get_revision(db, user, revision_id)
    return read_blob(rev.sha256), rev


def create_evidence(db: Session, user: User, revision_id: uuid.UUID, data: schemas.EvidenceCreateIn) -> Evidence:
    require_human(user)
    rev, source = get_revision(db, user, revision_id)
    require_member(db, user, source.project_id, ["contributor"])
    text = rev.text
    if data.char_start is not None and data.char_end is not None:
        start, end = data.char_start, data.char_end
        if not (0 <= start < end <= len(text)):
            raise AppError("VALIDATION_ERROR", "span outside text", fields=[{"field": "char_start", "type": "range"}])
    elif data.excerpt:
        start = text.find(data.excerpt)
        if start < 0:
            raise AppError("QUOTE_NOT_IN_EVIDENCE", "excerpt not found verbatim in source text")
        end = start + len(data.excerpt)
    else:
        raise AppError("VALIDATION_ERROR", "span or excerpt required")
    if end - start > 8000:
        raise AppError("VALIDATION_ERROR", "span too long", fields=[{"field": "char_end", "type": "too_long"}])
    page = None
    for ev in db.scalars(
        select(Evidence).where(Evidence.source_revision_id == rev.id, Evidence.locator["auto"].astext == "page")
    ):
        if ev.char_start is not None and ev.char_end is not None and ev.char_start <= start < ev.char_end:
            page = ev.locator.get("page")
    existing = db.scalar(
        select(Evidence).where(
            Evidence.source_revision_id == rev.id, Evidence.char_start == start, Evidence.char_end == end
        )
    )
    if existing:
        return existing
    ev = Evidence(
        source_revision_id=rev.id,
        locator=build_locator(text, start, end, rev.meta, page=page, section=data.section),
        excerpt=text[start:end],
        char_start=start,
        char_end=end,
    )
    db.add(ev)
    db.flush()
    return ev


def evidence_view(
    db: Session, user: User, evidence_id: uuid.UUID, claim_id: uuid.UUID | None = None
) -> schemas.EvidenceViewOut:
    ev, rev, source = evidence_access(db, user, evidence_id)
    highlight = None
    if ev.char_start is not None and ev.char_end is not None:
        highlight = {"start": ev.char_start, "end": ev.char_end}
    if claim_id:
        ce = db.get(ClaimEvidence, (claim_id, evidence_id))
        if ce and ce.quote:
            idx = ev.excerpt.find(ce.quote)
            base = ev.char_start or 0
            if idx >= 0 and ev.char_start is not None:
                highlight = {"start": base + idx, "end": base + idx + len(ce.quote)}
            elif idx < 0:
                pos = rev.text.find(ce.quote)
                if pos >= 0:
                    highlight = {"start": pos, "end": pos + len(ce.quote)}
    elif highlight is None:
        pos = rev.text.find(ev.excerpt)
        if pos >= 0:
            highlight = {"start": pos, "end": pos + len(ev.excerpt)}
    names = _author_names(db, {rev.author_id})
    loc = {k: v for k, v in ev.locator.items() if k != "auto"}
    return schemas.EvidenceViewOut(
        evidence_id=ev.id,
        source={"id": str(source.id), "title": source.title, "kind": source.kind},
        revision={
            "id": str(rev.id),
            "number": rev.number,
            "created_at": rev.created_at.isoformat(),
            "author_name": names.get(rev.author_id) if rev.author_id else None,
            "filename": rev.filename,
            "media_type": rev.media_type,
            "sha256": rev.sha256,
            "extraction": rev.extraction,
            "is_current": rev.number == source.current_revision_no,
        },
        locator=loc,
        locator_label=locator_label(loc),
        excerpt=ev.excerpt,
        text=rev.text,
        highlight=highlight,
        can_download=True,
        project_id=source.project_id,
    )


def delete_source(db: Session, user: User, source_id: uuid.UUID) -> None:
    require_human(user)
    source = get_source(db, user, source_id)
    roles = require_member(db, user, source.project_id, ["contributor"])
    if source.owner_id != user.id and "steward" not in roles:
        raise AppError("ROLE_REQUIRED", "only the owner or a steward can delete a source")
    lock_project(db, source.project_id)
    in_use = db.scalar(
        select(func.count())
        .select_from(ClaimEvidence)
        .join(Evidence, Evidence.id == ClaimEvidence.evidence_id)
        .join(SourceRevision, SourceRevision.id == Evidence.source_revision_id)
        .join(Claim, Claim.id == ClaimEvidence.claim_id)
        .join(PageRevision, PageRevision.id == Claim.page_revision_id)
        .join(Page, Page.id == PageRevision.page_id)
        .outerjoin(ChangeSetItem, ChangeSetItem.proposed_revision_id == PageRevision.id)
        .outerjoin(ChangeSet, ChangeSet.id == ChangeSetItem.change_set_id)
        .where(
            SourceRevision.source_id == source.id,
            Page.deleted_at.is_(None),
            ((Page.published_revision_id == PageRevision.id) & (Page.lifecycle == "active"))
            | (ChangeSet.deleted_at.is_(None) & ChangeSet.state.in_(["draft", "in_review", "approved"])),
        )
    )
    if in_use:
        raise AppError("INVALID_STATE", "source is used by published knowledge or open records", references=in_use)
    source.deleted_at = utcnow()
    source.deleted_by = user.id
    audit(db, user.id, "source.delete", "source", source.id)


def restore_source(db: Session, user: User, source_id: uuid.UUID) -> None:
    require_human(user)
    source = db.get(Source, source_id)
    if not source or source.deleted_at is None:
        raise AppError("NOT_FOUND", "source not found")
    roles = require_member(db, user, source.project_id, ["contributor"])
    if source.owner_id != user.id and "steward" not in roles:
        raise AppError("ROLE_REQUIRED", "only the owner or a steward can restore a source")
    source.deleted_at = None
    source.deleted_by = None
    audit(db, user.id, "source.restore", "source", source.id)
