"""Dış kaynaktan taslak: bağlantılar (yönetici), arama ve önizleme (katkı sahibi), taslağa bağlama.

Tasarım: docs/superpowers/specs/2026-10-25-dis-kaynak-ve-hibrit-arama-design.md (bölüm 4).
- Token şifreli saklanır, hiçbir yanıtta, logda, audit'te yer almaz.
- Yalnız izinli kapsamlardan; kısıtlı Confluence sayfası ve gizli GitLab issue'su alınmaz.
- Önizleme: dış çağrılar veritabanı oturumu dışında; sonra yetki yeniden denetlenir, ekler ve kayıt yazılır.
- İçe aktarma yalnız taslak üretir; yayımlayan insandır. Mentor yalnız yayımlanmış bilgiyi kullanır.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from pathlib import PurePath
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from metis.core.access import require_admin, require_human, require_member
from metis.core.audit import audit
from metis.core.blobs import put_blob
from metis.core.config import get_settings
from metis.core.db import transaction, utcnow
from metis.core.errors import AppError
from metis.core.models import Attachment, ExternalConnection, ExternalImport, ExternalOrigin, Page, PageRevision, User
from metis.core.security import decrypt_secret, encrypt_secret, validate_endpoint
from metis.modules.attachments.schemas import MAX_PER_DRAFT
from metis.modules.external import confluence, gitlab, schemas
from metis.modules.external.http import ExternalHttp
from metis.modules.external.storage_md import storage_to_markdown
from metis.modules.knowledge.views import attachment_out
from metis.modules.sources.files import check_upload

MAX_NOTE = 200_000  # changes.schemas.ItemIn.body_md
ATTACHABLE = {".png", ".jpg", ".jpeg", ".pdf"}


def body_hash(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- bağlantılar


def _check_scopes(kind: str, scopes: list[str]) -> list[str]:
    clean = [s.strip() for s in scopes]
    pattern = confluence.SPACE_RE if kind == "confluence" else gitlab.PROJECT_RE
    if not clean or any(not s or not pattern.match(s) for s in clean):
        raise AppError("VALIDATION_ERROR", "invalid allowed scopes", fields=[{"field": "allowed_scopes", "type": "invalid"}])
    return list(dict.fromkeys(clean))


def connection_out(c: ExternalConnection, admin: bool) -> schemas.ConnectionOut:
    out = schemas.ConnectionOut(id=c.id, kind=c.kind, name=c.name, allowed_scopes=list(c.allowed_scopes))  # type: ignore[arg-type]
    if admin:
        out.base_url, out.enabled, out.secret_configured, out.updated_at = c.base_url, c.enabled, bool(c.secret_enc), c.updated_at
    return out


def list_connections(db: Session, user: User) -> list[schemas.ConnectionOut]:
    q = select(ExternalConnection).where(ExternalConnection.deleted_at.is_(None)).order_by(ExternalConnection.created_at)
    if not user.is_admin:
        q = q.where(ExternalConnection.enabled.is_(True))
    return [connection_out(c, user.is_admin) for c in db.scalars(q)]


def _get(db: Session, connection_id: uuid.UUID) -> ExternalConnection:
    c = db.get(ExternalConnection, connection_id)
    if not c or c.deleted_at is not None:
        raise AppError("NOT_FOUND", "connection not found")
    return c


def create_connection(db: Session, user: User, data: schemas.ConnectionIn) -> schemas.ConnectionOut:
    require_admin(user)
    c = ExternalConnection(
        kind=data.kind,
        name=data.name.strip(),
        base_url=validate_endpoint(data.base_url, check_allowlist=False),
        secret_enc=encrypt_secret(data.token.strip()) if data.token.strip() else "",
        allowed_scopes=_check_scopes(data.kind, data.allowed_scopes),
        enabled=data.enabled,
        created_by=user.id,
    )
    db.add(c)
    db.flush()
    audit(db, user.id, "external.connection.create", "external_connection", c.id, kind=c.kind, base_url=c.base_url, scopes=c.allowed_scopes)
    return connection_out(c, True)


def update_connection(db: Session, user: User, connection_id: uuid.UUID, data: schemas.ConnectionIn) -> schemas.ConnectionOut:
    require_admin(user)
    c = _get(db, connection_id)
    c.kind, c.name = data.kind, data.name.strip()
    c.base_url = validate_endpoint(data.base_url, check_allowlist=False)
    c.allowed_scopes = _check_scopes(data.kind, data.allowed_scopes)
    c.enabled = data.enabled
    if data.token.strip():
        c.secret_enc = encrypt_secret(data.token.strip())
    c.updated_at = utcnow()
    audit(db, user.id, "external.connection.update", "external_connection", c.id, kind=c.kind, base_url=c.base_url, scopes=c.allowed_scopes, enabled=c.enabled, token_changed=bool(data.token.strip()))
    return connection_out(c, True)


def delete_connection(db: Session, user: User, connection_id: uuid.UUID) -> None:
    require_admin(user)
    c = _get(db, connection_id)
    c.deleted_at = utcnow()
    c.enabled = False
    audit(db, user.id, "external.connection.delete", "external_connection", c.id)


def _client(kind: str, base_url: str, secret_enc: str) -> ExternalHttp:
    return ExternalHttp(kind, base_url, decrypt_secret(secret_enc))


def test_connection(db: Session, user: User, data: schemas.ConnectionTestIn) -> schemas.ConnectionTestOut:
    """Kaydetmeden dener. Token boşsa ve bağlantı verilmişse kayıtlı token kullanılır."""
    require_admin(user)
    url = validate_endpoint(data.base_url, check_allowlist=False)
    token = data.token.strip()
    if not token and data.connection_id:
        token = decrypt_secret(_get(db, data.connection_id).secret_enc)
    http = ExternalHttp(data.kind, url, token)
    try:
        who = confluence.current_user(http) if data.kind == "confluence" else gitlab.current_user(http)
    except AppError as exc:
        return schemas.ConnectionTestOut(ok=False, error=exc.code)
    return schemas.ConnectionTestOut(ok=True, user=who)


# ---------------------------------------------------------------- arama


def search(db: Session, user: User, project_id: uuid.UUID, connection_id: uuid.UUID, q: str) -> list[schemas.SearchItemOut]:
    require_human(user)
    require_member(db, user, project_id, ["contributor"])
    c = _get(db, connection_id)
    if not c.enabled:
        raise AppError("NOT_FOUND", "connection not found")
    term = q.strip()
    if not 2 <= len(term) <= 200:
        raise AppError("VALIDATION_ERROR", "query 2-200 characters", fields=[{"field": "q", "type": "length"}])
    http = _client(c.kind, c.base_url, c.secret_enc)
    items = confluence.search(http, list(c.allowed_scopes), term) if c.kind == "confluence" else gitlab.search(http, list(c.allowed_scopes), term)
    return [schemas.SearchItemOut(key=i.key, title=i.title, url=i.url, container=i.container) for i in items]


# ---------------------------------------------------------------- önizleme


@dataclass
class _Conn:
    id: uuid.UUID
    kind: str
    name: str
    base_url: str
    secret_enc: str
    scopes: list[str]


@dataclass
class _Candidate:
    name: str
    size: int
    url: str
    fetch: object  # () -> bytes


@dataclass
class _Fetched:
    title: str
    body: str
    key: str
    url: str
    version: str
    candidates: list[_Candidate]
    skipped: list[schemas.SkippedOut]


def _host_key(base_url: str) -> str:
    p = urlsplit(base_url)
    return f"{(p.hostname or '').lower()}{':' + str(p.port) if p.port else ''}{p.path.rstrip('/')}"


def _fetch_confluence(conn: _Conn, url: str, limit: int) -> _Fetched:
    http = _client(conn.kind, conn.base_url, conn.secret_enc)
    ref = confluence.parse_ref(conn.base_url, url)
    if ref.space is not None and ref.space not in conn.scopes:
        raise AppError("EXTERNAL_SCOPE_NOT_ALLOWED", "space is not allowed for this connection")
    page = confluence.fetch(http, ref)
    if page.space not in conn.scopes:
        raise AppError("EXTERNAL_SCOPE_NOT_ALLOWED", "space is not allowed for this connection")
    if page.restricted:
        raise AppError("EXTERNAL_RESTRICTED", "page has view restrictions")
    conv = storage_to_markdown(page.storage)
    files = confluence.attachments(http, page.id)
    order = {name: i for i, name in enumerate(conv.images)}
    files.sort(key=lambda f: order.get(f.filename, len(order)))
    candidates = [
        _Candidate(f.filename, f.size, http.url(f.download), (lambda d=f.download: http.get_bytes(d, limit))) for f in files if f.download
    ]
    skipped = [schemas.SkippedOut(name=m, reason="macro") for m in conv.skipped_macros]
    return _Fetched(page.title, conv.markdown, f"confluence:{_host_key(conn.base_url)}:{page.id}", page.url, str(page.version), candidates, skipped)


def _fetch_gitlab(conn: _Conn, url: str, limit: int) -> _Fetched:
    http = _client(conn.kind, conn.base_url, conn.secret_enc)
    ref = gitlab.parse_ref(conn.base_url, url)
    if ref.project_path not in conn.scopes:
        raise AppError("EXTERNAL_SCOPE_NOT_ALLOWED", "project is not allowed for this connection")
    issue = gitlab.fetch(http, ref)
    if issue.confidential:
        raise AppError("EXTERNAL_RESTRICTED", "issue is confidential")
    body = gitlab.issue_markdown(issue)
    candidates = [
        _Candidate(
            name,
            0,
            f"{conn.base_url}/{ref.project_path}/uploads/{secret}/{name}",
            (lambda s=secret, n=name: gitlab.download_upload(http, issue.project_id, s, n, limit)),
        )
        for secret, name in gitlab.upload_refs(body)
    ]
    body = gitlab.replace_uploads(body)
    web = issue.web_url if issue.web_url.startswith(conn.base_url) else f"{conn.base_url}/{ref.project_path}/-/issues/{issue.iid}"
    key = f"gitlab:{_host_key(conn.base_url)}:{issue.project_id}#{issue.iid}"
    return _Fetched(issue.title, body, key, web, issue.updated_at, candidates, [])


def _download(fetched: _Fetched, limit: int) -> list[tuple[str, str, bytes]]:
    kept: list[tuple[str, str, bytes]] = []
    for cand in fetched.candidates:
        ext = PurePath(cand.name).suffix.lower()
        if ext not in ATTACHABLE:
            fetched.skipped.append(schemas.SkippedOut(name=cand.name, reason="type", url=cand.url))
            continue
        if cand.size > limit:
            fetched.skipped.append(schemas.SkippedOut(name=cand.name, reason="size", url=cand.url))
            continue
        if len(kept) >= MAX_PER_DRAFT:
            fetched.skipped.append(schemas.SkippedOut(name=cand.name, reason="limit", url=cand.url))
            continue
        try:
            data = cand.fetch()  # type: ignore[operator]
            checked = check_upload(cand.name, data, limit)
        except AppError as exc:
            reason = "size" if exc.code in ("EXTERNAL_TOO_LARGE", "FILE_TOO_LARGE") else "type" if exc.code == "UNSUPPORTED_FILE" else "fetch"
            fetched.skipped.append(schemas.SkippedOut(name=cand.name, reason=reason, url=cand.url))  # type: ignore[arg-type]
            continue
        kept.append((checked.filename, checked.media_type, data))
    return kept


def _latest_title(db: Session, page_id: uuid.UUID) -> str | None:
    return db.scalar(select(PageRevision.title).where(PageRevision.page_id == page_id).order_by(PageRevision.number.desc()).limit(1))


def preview(user_id: uuid.UUID, project_id: uuid.UUID, data: schemas.PreviewIn) -> schemas.PreviewOut:
    with transaction() as db:
        user = db.get(User, user_id)
        if not user or not user.active:
            raise AppError("UNAUTHENTICATED", "user inactive")
        require_human(user)
        require_member(db, user, project_id, ["contributor"])
        c = _get(db, data.connection_id)
        if not c.enabled:
            raise AppError("NOT_FOUND", "connection not found")
        conn = _Conn(c.id, c.kind, c.name, c.base_url, c.secret_enc, list(c.allowed_scopes))

    limit = get_settings().max_upload_bytes
    fetched = (_fetch_confluence if conn.kind == "confluence" else _fetch_gitlab)(conn, data.url, limit)
    fetched.body = re.sub(r"\n{3,}", "\n\n", fetched.body.replace("\r\n", "\n")).strip()
    if len(fetched.body) > MAX_NOTE:
        raise AppError("EXTERNAL_TOO_LARGE", "note would exceed the limit", characters=len(fetched.body), limit=MAX_NOTE)
    files = _download(fetched, limit)

    # Yavaş dış çağrılardan sonra yetki ve bağlantı yeniden denetlenir.
    with transaction() as db:
        user = db.get(User, user_id)
        if not user or not user.active:
            raise AppError("UNAUTHENTICATED", "user inactive")
        require_member(db, user, project_id, ["contributor"])
        c = _get(db, conn.id)
        if not c.enabled:
            raise AppError("NOT_FOUND", "connection not found")
        rows = []
        for name, media, blob in files:
            a = Attachment(project_id=project_id, uploader_id=user.id, sha256=put_blob(blob), filename=name, media_type=media, size_bytes=len(blob))
            db.add(a)
            rows.append(a)
        db.flush()
        imp = ExternalImport(
            project_id=project_id,
            user_id=user.id,
            connection_id=conn.id,
            external_key=fetched.key,
            url=fetched.url,
            version=fetched.version[:80],
            title=(fetched.title or fetched.key)[:240],
            body_md=fetched.body,
            body_sha256=body_hash(fetched.body),
            attachment_ids=[str(a.id) for a in rows],
            skipped=[s.model_dump() for s in fetched.skipped],
        )
        db.add(imp)
        db.flush()
        origin = db.scalar(select(ExternalOrigin).where(ExternalOrigin.project_id == project_id, ExternalOrigin.external_key == fetched.key))
        existing_title, edited = None, False
        if origin is not None:
            existing_title = _latest_title(db, origin.page_id)
            page = db.get(Page, origin.page_id)
            if page and page.published_revision_id:
                rev = db.get(PageRevision, page.published_revision_id)
                edited = rev is not None and body_hash(rev.body_md) != origin.imported_body_sha256
        audit(db, user.id, "external.import.preview", "external_import", imp.id, key=fetched.key, url=fetched.url, attachments=len(rows))
        return schemas.PreviewOut(
            import_id=imp.id,
            kind=conn.kind,  # type: ignore[arg-type]
            title=imp.title,
            body_md=imp.body_md,
            attachments=[attachment_out(a) for a in rows],
            skipped=fetched.skipped,
            origin=schemas.OriginOut(kind=conn.kind, url=fetched.url, version=imp.version, connection_name=conn.name),  # type: ignore[arg-type]
            existing_page_id=origin.page_id if origin else None,
            existing_title=existing_title,
            edited_since_import=edited,
        )


# ---------------------------------------------------------------- taslağa bağlama ve köken


def bind_import(db: Session, actor: User, project_id: uuid.UUID, page: Page, import_id: uuid.UUID, note: str) -> None:
    """Taslak kaydında çağrılır (aynı transaction). Önizleme bu kullanıcıya ve projeye ait olmalı; bir sayfaya bağlanır.

    Aynı taslak yeniden kaydedilince (aynı sayfa) köken güncellenir; başka sayfa için kullanılamaz (IMPORT_USED).
    Köken hash'i taslakta kaydedilen not metnidir: sonradan METIS'teki değişiklik "içe aktarmadan sonra düzenlendi" sayılır.
    """
    imp = db.get(ExternalImport, import_id)
    if not imp or imp.user_id != actor.id or imp.project_id != project_id:
        raise AppError("NOT_FOUND", "import not found")
    origin = db.scalar(select(ExternalOrigin).where(ExternalOrigin.project_id == project_id, ExternalOrigin.external_key == imp.external_key))
    if imp.used_at is not None and (origin is None or origin.page_id != page.id):
        raise AppError("IMPORT_USED", "this preview was already used for another draft")
    if origin is not None and origin.page_id != page.id:
        raise AppError("VALIDATION_ERROR", "this source is already linked to another page", fields=[{"field": "import_id", "type": "already_imported"}], page_id=str(origin.page_id))
    if origin is None:
        other = db.scalar(select(ExternalOrigin).where(ExternalOrigin.page_id == page.id))
        if other is not None:
            raise AppError("VALIDATION_ERROR", "page already has another source", fields=[{"field": "import_id", "type": "page_has_origin"}])
        origin = ExternalOrigin(project_id=project_id, page_id=page.id, external_key=imp.external_key, connection_id=imp.connection_id, url=imp.url, imported_by=actor.id, imported_body_sha256="")
        db.add(origin)
    origin.connection_id, origin.url, origin.version = imp.connection_id, imp.url, imp.version
    origin.imported_body_sha256 = body_hash(note)
    origin.imported_at, origin.imported_by = utcnow(), actor.id
    imp.used_at = imp.used_at or utcnow()
    db.flush()


def origin_for_page(db: Session, page_id: uuid.UUID) -> schemas.OriginOut | None:
    origin = db.scalar(select(ExternalOrigin).where(ExternalOrigin.page_id == page_id))
    if origin is None:
        return None
    c = db.get(ExternalConnection, origin.connection_id)
    kind = c.kind if c else ("confluence" if origin.external_key.startswith("confluence:") else "gitlab")
    return schemas.OriginOut(kind=kind, url=origin.url, version=origin.version, connection_name=c.name if c else "", imported_at=origin.imported_at)  # type: ignore[arg-type]
