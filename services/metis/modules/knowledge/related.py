"""Deterministik bağlantılar (İş 5, tasarım bölüm 8): bilgi sayfası için "Bağlantılı bilgiler" ve içe aktarma önerileri.

Modelsiz, istek anında hesaplanır:
- reference: yayındaki notta geçen Confluence/GitLab adresi (ya da GitLab issue'sundan alınmış bilgide `#123`; kod içi
  hariç) bu projede içe aktarılmış ve silinmemiş bir bilgiye karşılık geliyorsa.
- shared_symbols: iki bilginin paylaştığı nadir tanımlayıcılar (proje içinde en çok max(2, sayfaların %5'i) bilgide geçen;
  yalnız adreslerin içinde geçenler sayılmaz), nadirlik ağırlıklı (IDF) sıralı, okunabilenlerden en çok 5.
- missing: bir bağlantının adres biçimine ve izinli alanına/projesine uyan ama bu projede içe aktarılmamış öğe → "İçe aktar"
  önerisi (yalnız katkı verebilene, en çok 20).
Okunamayan sayfa listelenmez; Mentor paketine kendiliğinden girmez.
"""

from __future__ import annotations

import math
import re
import uuid

from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from metis.core.access import can_read_page_revision, require_member, unreadable_revisions
from metis.core.errors import AppError
from metis.core.models import ExternalConnection, ExternalOrigin, Page, PageRevision, SearchDocument, User
from metis.modules.external import confluence, gitlab
from metis.modules.search.index import extract_symbols

# Adres; Türkçe ek kesmesi (’de), tırnak ve Markdown vurgusu adrese dahil değildir.
URL_RE = re.compile(r"https?://[^\s<>()\[\]`\"'’‘”“*]+")
HASH_REF_RE = re.compile(r"(?<![\w&/#])#(\d{1,7})\b")
CODE_RE = re.compile(r"```.*?```|~~~.*?~~~|`[^`\n]*`", re.S)
MAX_SYMBOL_LINKS = 5
MAX_REFS = 20


class RelatedLink(BaseModel):
    page_id: uuid.UUID
    title: str
    reason: str  # reference | shared_symbols
    symbols: list[str] = []


class MissingRef(BaseModel):
    url: str
    kind: str  # confluence | gitlab
    connection_id: uuid.UUID


class RelatedOut(BaseModel):
    links: list[RelatedLink]
    missing: list[MissingRef]


def _ref(conn: ExternalConnection, url: str) -> tuple[tuple, str | None] | None:
    """Adres → (bağlantıdan bağımsız kimlik, izin denetimi için alan/proje): ("c", kök, sayfa id) ya da ("g", kök, proje, iid).
    Confluence'ta yalnız sayfa kimliği olan adresin alanı bilinmez (None)."""
    base = conn.base_url.rstrip("/")
    try:
        if conn.kind == "confluence":
            ref = confluence.parse_ref(conn.base_url, url)
            return (("c", base, ref.page_id), ref.space) if ref.page_id else None
        g = gitlab.parse_ref(conn.base_url, url)
        return ("g", base, g.project_path, g.iid), g.project_path
    except AppError:
        return None


def _canonical(conns: list[ExternalConnection], url: str) -> tuple | None:
    for c in conns:
        hit = _ref(c, url)
        if hit:
            return hit[0]
    return None


def _importer(conns: list[ExternalConnection], url: str) -> ExternalConnection | None:
    """Öneri için bağlantı: açık, adresi tanıyan ve alanı/projesi izinli ilk bağlantı (oluşturulma sırasıyla)."""
    for c in conns:
        hit = _ref(c, url)
        if hit and c.enabled and (hit[1] is None or hit[1] in c.allowed_scopes):
            return c
    return None


def _clean(url: str) -> str:
    return url.rstrip(".,;:!?_")


def related(db: Session, user: User, page_id: uuid.UUID) -> RelatedOut:
    page = db.get(Page, page_id)
    if not page or page.deleted_at is not None or not page.published_revision_id:
        raise AppError("NOT_FOUND", "page not found")
    can_import = "contributor" in require_member(db, user, page.project_id)
    rev = db.get(PageRevision, page.published_revision_id)
    if not can_read_page_revision(db, user, rev):
        raise AppError("NOT_FOUND", "page not found")
    assert rev is not None
    body = rev.body_md or ""
    conns = list(db.scalars(select(ExternalConnection).where(ExternalConnection.deleted_at.is_(None)).order_by(ExternalConnection.created_at)))

    # Projede içe aktarılmış ve sayfası silinmemiş öğeler: kimlik → sayfa (silinen sayfanın kökeni yeniden alınabilir)
    origins: dict[tuple, uuid.UUID] = {}
    own: tuple | None = None
    live = select(ExternalOrigin).join(Page, Page.id == ExternalOrigin.page_id).where(ExternalOrigin.project_id == page.project_id, Page.deleted_at.is_(None))
    for o in db.scalars(live):
        key = _canonical(conns, o.url)
        if key:
            origins[key] = o.page_id
            if o.page_id == page.id:
                own = key

    refs: dict[tuple, str] = {}
    for raw in URL_RE.findall(body):
        url = _clean(raw)
        key = _canonical(conns, url)
        if key and key not in refs:
            refs[key] = url
    if own and own[0] == "g":  # GitLab issue'sundan alınmış bilgi: #123 aynı projenin issue'su (kod içindekiler hariç)
        for n in HASH_REF_RE.findall(CODE_RE.sub(" ", body)):
            key = ("g", own[1], own[2], int(n))
            refs.setdefault(key, f"{own[1]}/{own[2]}/-/issues/{n}")

    linked: dict[uuid.UUID, RelatedLink] = {}
    missing: list[MissingRef] = []
    for key, url in refs.items():
        target = origins.get(key)
        if target == page.id:
            continue
        if target is not None:
            if len(linked) < MAX_REFS:
                linked.setdefault(target, RelatedLink(page_id=target, title="", reason="reference"))
        elif can_import and len(missing) < MAX_REFS:
            conn = _importer(conns, url)
            if conn is not None:
                missing.append(MissingRef(url=url, kind=conn.kind, connection_id=conn.id))

    # Okunabilir, yayındaki bilgiler (search_documents) ve başlıkları
    def readable(pids: list[uuid.UUID]) -> dict[uuid.UUID, SearchDocument]:
        if not pids:
            return {}
        docs = {d.page_id: d for d in db.scalars(select(SearchDocument).where(SearchDocument.page_id.in_(pids)))}
        hidden = unreadable_revisions(db, user, page.project_id, [d.revision_id for d in docs.values()])
        return {pid: d for pid, d in docs.items() if d.revision_id not in hidden}

    shown = readable(list(linked))
    links = [link.model_copy(update={"title": shown[pid].title}) for pid, link in linked.items() if pid in shown]

    # Ortak nadir tanımlayıcılar; yalnız adresin içinde geçen parça (ör. `pageId`) tanımlayıcı sayılmaz
    doc = db.get(SearchDocument, page.id)
    if doc and doc.symbols:
        url_only = set(extract_symbols(" ".join(URL_RE.findall(body)))) - set(extract_symbols(URL_RE.sub(" ", body)))
        syms = [s for s in doc.symbols if s not in url_only]
        n_docs = db.scalar(text("SELECT count(*) FROM search_documents WHERE project_id = :p"), {"p": page.project_id}) or 1
        cap = max(2, math.ceil(n_docs * 0.05))
        df = dict(
            db.execute(
                text(
                    """SELECT s, (SELECT count(*) FROM search_documents d WHERE d.project_id = :p AND d.symbols @> ARRAY[s])
                       FROM unnest(CAST(:syms AS text[])) AS s"""
                ),
                {"p": page.project_id, "syms": syms},
            ).all()
        )
        rare = [s for s in syms if 2 <= df.get(s, 0) <= cap]
        if rare:
            rows = db.execute(
                text(
                    """SELECT page_id, symbols FROM search_documents
                       WHERE project_id = :p AND page_id <> :me AND symbols && CAST(:rare AS text[])"""
                ),
                {"p": page.project_id, "me": page.id, "rare": rare},
            ).all()
            scored = []
            for pid, other in rows:
                if pid in linked:
                    continue
                shared = [s for s in rare if s in other]
                scored.append((sum(math.log(n_docs / df[s]) + 1 for s in shared), pid, shared))
            ok = readable([pid for _, pid, _ in scored])
            best = [x for x in sorted(scored, key=lambda x: (-x[0], str(x[1]))) if x[1] in ok][:MAX_SYMBOL_LINKS]
            links += [RelatedLink(page_id=pid, title=ok[pid].title, reason="shared_symbols", symbols=shared) for _, pid, shared in best]
    return RelatedOut(links=links, missing=missing)
