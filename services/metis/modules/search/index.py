"""Arama indeksi: yalnız aktif yayındaki güncel revizyonlar (search_documents).

- Semboller asla normalize edilmez (`XAxiPcie_IntrEnable`, `INIT_BUS`); `symbols text[]` + GIN.
- `tsv_simple` (semboller/İngilizce) + `tsv_turkish` (Türkçe kök).
- Alias: sayfa alias'ları + domain paketi terminolojisi (kesme ↔ interrupt ↔ ISR).
"""

from __future__ import annotations

import json
import re
import uuid
from functools import lru_cache
from pathlib import Path

from sqlalchemy import delete, func, literal_column, select
from sqlalchemy.orm import Session

from metis.core.config import ROOT
from metis.core.models import Claim, Page, PageRevision, PageRevisionFigure, SearchDocument, SearchPassage
from metis.modules.knowledge.figures import strip_figures
from metis.modules.search.text import fold
from metis.modules.search.vectors import bump, embed_hash

SYMBOL_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}(?:\(\))?")
HEX_RE = re.compile(r"\b0[xX][0-9A-Fa-f]+\b")


def is_symbol(token: str) -> bool:
    """Büyük harf (ilk harf dışında), alt çizgi veya rakam içeren tanımlayıcılar sembol sayılır."""
    core = token.rstrip("()")
    if len(core) < 3:
        return False
    return "_" in core or any(c.isdigit() for c in core) or any(c.isupper() for c in core[1:]) or token.endswith("()")


def extract_symbols(*texts: str) -> list[str]:
    found: dict[str, None] = {}
    for text in texts:
        for m in SYMBOL_RE.finditer(text or ""):
            tok = m.group(0)
            if is_symbol(tok):
                found[tok.rstrip("()")] = None
        for m in HEX_RE.finditer(text or ""):
            found[m.group(0)] = None
    return list(found)[:400]


@lru_cache(maxsize=1)
def terminology() -> dict[str, list[str]]:
    """domain paketi terminolojisi: her terim → eş anlamlılar (iki yönlü)."""
    path = ROOT / "domain-packs" / "embedded-software" / "manifest.json"
    alt = Path(__file__).resolve().parents[2] / "domain_packs" / "embedded-software.json"
    for candidate in (path, alt):
        if candidate.is_file():
            data = json.loads(candidate.read_text(encoding="utf-8"))
            break
    else:
        return {}
    groups: dict[str, set[str]] = {}
    for term, syns in data.get("terminology", {}).items():
        group = {term.casefold(), *(s.casefold() for s in syns)}
        for word in group:
            groups.setdefault(word, set()).update(group - {word})
    return {k: sorted(v) for k, v in groups.items()}


def aliases_for(title: str, explicit: list[str], text: str) -> list[str]:
    terms = terminology()
    hay = f"{title}\n{text}".casefold()
    out: dict[str, None] = {a.strip(): None for a in explicit if a.strip()}
    for term, syns in terms.items():
        if re.search(rf"(?<!\w){re.escape(term)}", hay):
            for s in syns:
                out[s] = None
    return list(out)[:100]


_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def is_heading_block(statement: str) -> bool:
    return "\n" not in statement.strip() and bool(_HEADING.match(statement))


def heading_paths(statements: list[str]) -> list[str]:
    """Not bloklarının başlık yolu ("PCIe › Saat › Sıfırlama"). Tek satırlık `#` bloğu başlıktır ve kendi yolunu taşır."""
    stack: list[tuple[int, str]] = []
    out = []
    for s in statements:
        m = _HEADING.match(s) if "\n" not in s.strip() else None
        if m:
            level = len(m.group(1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, m.group(2)))
        out.append(" › ".join(t for _, t in stack))
    return out


def _weighted(config: str, title: str, heading: str, body: str):  # noqa: ANN202
    return (
        func.setweight(func.to_tsvector(config, title), literal_column("'A'"))
        .op("||")(func.setweight(func.to_tsvector(config, heading), literal_column("'B'")))
        .op("||")(func.setweight(func.to_tsvector(config, body), literal_column("'C'")))
    )


def index_pages(db: Session, project_id: uuid.UUID, publication_id: uuid.UUID, page_ids: set[uuid.UUID]) -> None:
    """Etkilenen sayfaların indeks satırlarını aktif yayına göre yeniden kurar (aynı transaction)."""
    if not page_ids:
        return
    db.execute(delete(SearchDocument).where(SearchDocument.page_id.in_(page_ids)))
    db.execute(delete(SearchPassage).where(SearchPassage.page_id.in_(page_ids)))
    rows = db.execute(
        select(Page, PageRevision)
        .join(PageRevision, PageRevision.id == Page.published_revision_id)
        .where(Page.id.in_(page_ids), Page.lifecycle == "active", Page.deleted_at.is_(None))
    ).all()
    for page, rev in rows:
        claim_rows = db.scalars(select(Claim).where(Claim.page_revision_id == rev.id).order_by(Claim.ord)).all()
        claims = [c.statement for c in claim_rows]
        claim_text = "\n".join(claims)
        for c, path in zip(claim_rows, heading_paths(claims), strict=True):
            db.add(
                SearchPassage(
                    page_id=page.id,
                    project_id=project_id,
                    revision_id=rev.id,
                    publication_id=publication_id,
                    claim_id=c.id,
                    ord=c.ord,
                    heading_path=path,
                    is_heading=is_heading_block(c.statement),
                    body=c.statement,
                    embed_sha256=embed_hash(rev.title, path, c.statement),
                    symbols=extract_symbols(c.statement),
                    scope=rev.scope,
                    kind=rev.kind,
                    tsv_simple=_weighted("simple", fold(rev.title), fold(path), fold(c.statement)),
                    tsv_turkish=_weighted("turkish", rev.title, path, c.statement),
                )
            )
        captions = db.scalars(
            select(PageRevisionFigure.caption).where(PageRevisionFigure.page_revision_id == rev.id).order_by(PageRevisionFigure.ord)
        ).all()
        content = f"{rev.summary}\n{strip_figures(rev.body_md, list(captions))}\n{claim_text}"
        aliases = aliases_for(rev.title, rev.aliases or [], content)
        symbols = extract_symbols(rev.title, content)
        alias_text = " ".join(aliases)
        doc = SearchDocument(
            page_id=page.id,
            project_id=project_id,
            revision_id=rev.id,
            publication_id=publication_id,
            title=rev.title,
            kind=rev.kind,
            aliases=aliases,
            symbols=symbols,
            content=content,
            scope=rev.scope,
            tsv_simple=func.setweight(func.to_tsvector("simple", rev.title), literal_column("'A'"))
            .op("||")(
                func.setweight(func.to_tsvector("simple", alias_text + " " + " ".join(symbols)), literal_column("'B'"))
            )
            .op("||")(func.setweight(func.to_tsvector("simple", content), literal_column("'C'"))),
            tsv_turkish=func.setweight(func.to_tsvector("turkish", rev.title), literal_column("'A'"))
            .op("||")(func.setweight(func.to_tsvector("turkish", alias_text), literal_column("'B'")))
            .op("||")(func.setweight(func.to_tsvector("turkish", content), literal_column("'C'"))),
        )
        db.add(doc)
    db.flush()
    bump(db, {project_id})


def ensure_passage_index(db: Session) -> int:
    """Yayını olup blok indeksi boş olan projelerin bloklarını kurar (`metis migrate` sonunda; idempotent).
    Dönen: kurulan proje sayısı."""
    from metis.core.models import Project

    built = 0
    for project in db.scalars(select(Project).where(Project.active_publication_id.is_not(None))):
        if db.scalar(select(SearchPassage.id).where(SearchPassage.project_id == project.id).limit(1)) is not None:
            continue
        page_ids = set(db.scalars(select(SearchDocument.page_id).where(SearchDocument.project_id == project.id)))
        if page_ids:
            index_pages(db, project.id, project.active_publication_id, page_ids)
            built += 1
    return built


def fill_embed_hashes(db: Session) -> int:
    """2.0.19'da kurulan blokların gömme anahtarını doldurur (`metis migrate` sonunda; idempotent). Dönen: satır sayısı."""
    rows = db.execute(
        select(SearchPassage, SearchDocument.title)
        .join(SearchDocument, SearchDocument.page_id == SearchPassage.page_id)
        .where(SearchPassage.embed_sha256.is_(None))
    ).all()
    for p, title in rows:
        p.embed_sha256 = embed_hash(title, p.heading_path, p.body)
    return len(rows)
