"""Deterministik arama: metadata filtresi → birebir sembol → başlık/alias/sözlük → PG FTS (simple + turkish).

`pg_trgm` varsa bulanık sembol eşleşmesi eklenir; yoksa kapalıdır (UI "bulanık arama kullanılamıyor" der).
Erişim: erişilemeyen kaynağa dayanan sayfa sonuçta görünmez (sayıya da girmez).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from metis.core.access import require_member, unreadable_revisions
from metis.core.models import User
from metis.modules.scopes.semantics import matches_scope
from metis.modules.search.index import is_symbol, terminology

TOKEN_RE = re.compile(r"[\w]+(?:\(\))?", re.UNICODE)
STOP = {
    "nasıl",
    "nedir",
    "neden",
    "için",
    "hangi",
    "bir",
    "olarak",
    "ile",
    "ve",
    "veya",
    "mi",
    "mı",
    "mu",
    "mü",
    "ne",
    "the",
    "and",
    "how",
    "what",
}


class SearchHit(BaseModel):
    page_id: uuid.UUID
    revision_id: uuid.UUID
    title: str
    kind: str
    scope: dict
    snippet: str
    score: float
    matched_symbols: list[str]


class SearchOut(BaseModel):
    hits: list[SearchHit]
    fuzzy_available: bool
    query_terms: list[str]


@dataclass
class ParsedQuery:
    words: list[str]
    symbols: list[str]
    expanded: list[str]


def parse_query(q: str) -> ParsedQuery:
    raw = [t for t in TOKEN_RE.findall(q or "")]
    symbols = [t.rstrip("()") for t in raw if is_symbol(t)]
    words = [t.casefold() for t in raw if t.casefold() not in STOP and len(t) >= 2]
    terms = terminology()
    expanded: dict[str, None] = {w: None for w in words}
    lowered = (q or "").casefold()
    for term, syns in terms.items():
        if re.search(rf"(?<!\w){re.escape(term)}", lowered):
            for s in syns:
                for part in s.split():
                    expanded[part] = None
            for part in term.split():
                expanded[part] = None
    return ParsedQuery(words=words, symbols=symbols, expanded=list(expanded))


def _trgm(db: Session) -> bool:
    return bool(db.execute(text("SELECT 1 FROM pg_extension WHERE extname='pg_trgm'")).scalar())


def search(
    db: Session,
    user: User,
    project_id: uuid.UUID,
    q: str,
    scope: dict | None = None,
    kind: str | None = None,
    limit: int = 20,
) -> SearchOut:
    require_member(db, user, project_id)
    parsed = parse_query(q)
    fuzzy = _trgm(db)
    if not parsed.expanded and not parsed.symbols:
        return SearchOut(hits=[], fuzzy_available=fuzzy, query_terms=[])
    or_query = " or ".join(re.sub(r"[^\w]", " ", t) for t in parsed.expanded) or "''"
    like_terms = [f"%{t.replace('%', '').replace('_', r'\_')}%" for t in parsed.expanded[:12]] or ["%%"]
    fuzzy_sql = (
        "+ COALESCE((SELECT max(similarity(s, sym)) FROM unnest(d.symbols) s, unnest(CAST(:symbols AS text[])) sym), 0) * 3"
        if fuzzy and parsed.symbols
        else ""
    )
    sql = text(
        f"""
        WITH q AS (
          SELECT websearch_to_tsquery('simple', :oq) AS qs, websearch_to_tsquery('turkish', :oq) AS qt
        )
        SELECT d.page_id, d.revision_id, d.title, d.kind, d.scope,
               ARRAY(SELECT s FROM unnest(d.symbols) s WHERE s = ANY(CAST(:symbols AS text[]))) AS matched,
               ( CASE WHEN d.symbols && CAST(:symbols AS text[]) THEN 10 ELSE 0 END
               + CASE WHEN d.title ILIKE ANY(CAST(:likes AS text[])) THEN 4 ELSE 0 END
               + CASE WHEN EXISTS (SELECT 1 FROM unnest(d.aliases) a WHERE lower(a) = ANY(CAST(:words AS text[]))) THEN 3 ELSE 0 END
               + ts_rank_cd(d.tsv_simple, q.qs) * 2
               + ts_rank_cd(d.tsv_turkish, q.qt) * 2
               {fuzzy_sql}
               ) AS score,
               ts_headline('simple', d.content, q.qs, 'MaxWords=28, MinWords=12, StartSel=«, StopSel=»') AS snippet
        FROM search_documents d, q
        WHERE d.project_id = :project_id
          AND (d.tsv_simple @@ q.qs OR d.tsv_turkish @@ q.qt OR d.symbols && CAST(:symbols AS text[])
               OR d.title ILIKE ANY(CAST(:likes AS text[]))
               {"OR EXISTS (SELECT 1 FROM unnest(d.symbols) s, unnest(CAST(:symbols AS text[])) sym WHERE similarity(s, sym) > 0.45)" if fuzzy and parsed.symbols else ""})
          {"AND d.kind = :kind" if kind else ""}
        ORDER BY score DESC, d.title
        LIMIT 200
        """
    ).bindparams(bindparam("symbols"), bindparam("likes"), bindparam("words"))
    params = {
        "oq": or_query,
        "symbols": parsed.symbols,
        "likes": like_terms,
        "words": parsed.expanded,
        "project_id": project_id,
    }
    if kind:
        params["kind"] = kind
    rows = db.execute(sql, params).mappings().all()
    hidden = unreadable_revisions(db, user, project_id, [r["revision_id"] for r in rows])
    hits = []
    for r in rows:
        if r["revision_id"] in hidden:
            continue
        if scope and not matches_scope(r["scope"], scope):
            continue
        hits.append(
            SearchHit(
                page_id=r["page_id"],
                revision_id=r["revision_id"],
                title=r["title"],
                kind=r["kind"],
                scope=r["scope"],
                snippet=(r["snippet"] or "")[:400],
                score=round(float(r["score"]), 4),
                matched_symbols=list(r["matched"] or []),
            )
        )
        if len(hits) >= limit:
            break
    return SearchOut(hits=hits, fuzzy_available=fuzzy, query_terms=parsed.expanded + parsed.symbols)
