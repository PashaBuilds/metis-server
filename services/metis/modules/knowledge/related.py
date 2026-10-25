"""Deterministik bağlantılar (İş 5, tasarım bölüm 8): bilgi sayfası için "İlgili bilgiler" ve içe aktarma önerileri.

Modelsiz, istek anında hesaplanır:
- reference: yayındaki notta geçen Confluence/GitLab adresi (ya da GitLab issue'sundan alınmış bilgide `#123`) bu projede
  içe aktarılmış bir bilgiye karşılık geliyorsa.
- shared_symbols: iki bilginin paylaştığı nadir tanımlayıcılar (proje içinde en çok max(2, sayfaların %5'i) bilgide geçen),
  nadirlik ağırlıklı (IDF) sıralı, en çok 5.
- missing: tanımlı bir bağlantının adres biçimine uyan ama bu projede içe aktarılmamış öğe → "İçe aktar" önerisi (yalnız
  katkı verebilene).
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

URL_RE = re.compile(r"https?://[^\s<>()\[\]`\"']+")
HASH_REF_RE = re.compile(r"(?<![\w&/#])#(\d{1,7})\b")
MAX_SYMBOL_LINKS = 5


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


def _canonical(conns: list[ExternalConnection], url: str) -> tuple[tuple, ExternalConnection] | None:
    """Adres → bağlantıdan bağımsız kimlik: ("c", kök, sayfa id) ya da ("g", kök, proje yolu, iid)."""
    for c in conns:
        try:
            if c.kind == "confluence":
                ref = confluence.parse_ref(c.base_url, url)
                if ref.page_id:
                    return ("c", c.base_url, ref.page_id), c
            else:
                g = gitlab.parse_ref(c.base_url, url)
                return ("g", c.base_url, g.project_path, g.iid), c
        except AppError:
            continue
    return None


def _clean(url: str) -> str:
    return url.rstrip(".,;:!?")


def related(db: Session, user: User, page_id: uuid.UUID) -> RelatedOut:
    page = db.get(Page, page_id)
    if not page or page.deleted_at is not None or not page.published_revision_id:
        raise AppError("NOT_FOUND", "page not found")
    can_import = "contributor" in require_member(db, user, page.project_id)
    rev = db.get(PageRevision, page.published_revision_id)
    if not can_read_page_revision(db, user, rev):
        raise AppError("NOT_FOUND", "page not found")
    assert rev is not None
    conns = list(db.scalars(select(ExternalConnection).where(ExternalConnection.deleted_at.is_(None))))

    # Projede içe aktarılmış öğeler: kimlik → sayfa
    origins: dict[tuple, uuid.UUID] = {}
    own: tuple | None = None
    for o in db.scalars(select(ExternalOrigin).where(ExternalOrigin.project_id == page.project_id)):
        hit = _canonical(conns, o.url)
        if hit:
            origins[hit[0]] = o.page_id
            if o.page_id == page.id:
                own = hit[0]

    refs: dict[tuple, tuple[str, ExternalConnection]] = {}
    for raw in URL_RE.findall(rev.body_md or ""):
        url = _clean(raw)
        hit = _canonical(conns, url)
        if hit and hit[0] not in refs:
            refs[hit[0]] = (url, hit[1])
    if own and own[0] == "g":  # GitLab issue'sundan alınmış bilgi: #123 aynı projenin issue'su
        conn = next((c for c in conns if c.base_url == own[1]), None)
        for n in HASH_REF_RE.findall(rev.body_md or ""):
            key = ("g", own[1], own[2], int(n))
            if conn and key not in refs:
                refs[key] = (f"{own[1]}/{own[2]}/-/issues/{n}", conn)

    linked: dict[uuid.UUID, RelatedLink] = {}
    missing: list[MissingRef] = []
    for key, (url, conn) in refs.items():
        target = origins.get(key)
        if target == page.id:
            continue
        if target is not None:
            linked.setdefault(target, RelatedLink(page_id=target, title="", reason="reference"))
        elif conn.enabled and can_import:
            missing.append(MissingRef(url=url, kind=conn.kind, connection_id=conn.id))

    # Ortak nadir tanımlayıcılar (yalnız yayındaki bilgiler: search_documents)
    doc = db.get(SearchDocument, page.id)
    if doc and doc.symbols:
        n_docs = db.scalar(text("SELECT count(*) FROM search_documents WHERE project_id = :p"), {"p": page.project_id}) or 1
        cap = max(2, math.ceil(n_docs * 0.05))
        df = dict(
            db.execute(
                text(
                    "SELECT s, count(*) FROM search_documents, unnest(symbols) s WHERE project_id = :p AND s = ANY(:syms) GROUP BY s"
                ),
                {"p": page.project_id, "syms": list(doc.symbols)},
            ).all()
        )
        rare = [s for s in doc.symbols if 2 <= df.get(s, 0) <= cap]
        if rare:
            rows = db.execute(
                text("SELECT page_id, symbols FROM search_documents WHERE project_id = :p AND page_id <> :me AND symbols && :rare"),
                {"p": page.project_id, "me": page.id, "rare": rare},
            ).all()
            scored = []
            for pid, syms in rows:
                shared = [s for s in rare if s in syms]
                scored.append((sum(math.log(n_docs / df[s]) + 1 for s in shared), pid, shared))
            for _score, pid, shared in sorted(scored, key=lambda x: (-x[0], str(x[1])))[:MAX_SYMBOL_LINKS]:
                linked.setdefault(pid, RelatedLink(page_id=pid, title="", reason="shared_symbols", symbols=shared))

    # Yalnız yayındaki, okunabilir bilgiler; başlık yayındaki revizyondan
    docs = {d.page_id: d for d in db.scalars(select(SearchDocument).where(SearchDocument.page_id.in_(list(linked))))}
    hidden = unreadable_revisions(db, user, page.project_id, [d.revision_id for d in docs.values()])
    links = []
    for pid, link in linked.items():
        d = docs.get(pid)
        if d is None or d.revision_id in hidden:
            continue
        link.title = d.title
        links.append(link)
    return RelatedOut(links=links, missing=missing)

