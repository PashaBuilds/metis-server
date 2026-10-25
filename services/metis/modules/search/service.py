"""Deterministik arama: metadata filtresi → birebir sembol → başlık/alias/sözlük → PG FTS (simple + turkish).

FTS blok düzeyindedir (search_passages, 2026-10-25): sayfa puanı en iyi bloğundan (+ ikinci blok × 0.25) gelir; uzun
sayfada isabetli paragraf sayfanın geri kalanı içinde erimez. `simple` kanalı Türkçe harfleri katlar (search.text.fold).
Sayfa düzeyi FTS (özet, görsel açıklamaları, alias'lar) düşük ağırlıklı yedektir (× 0.5). Gösterilen en iyi blok başlık
satırı değil, başlığın altındaki bloktur.

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
from metis.modules.search.text import fold, lower_tr
from metis.modules.search.vectors import RRF_K, DenseResult, dense_search

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
    # En iyi bloklar (iddia kimlikleri, puan sırasıyla, en çok 8) ve en iyi bloğun başlık yolu ile metni.
    best_claims: list[uuid.UUID] = []
    heading_path: str = ""
    passage_text: str | None = None


class SearchOut(BaseModel):
    hits: list[SearchHit]
    fuzzy_available: bool
    query_terms: list[str]
    # Vektör kanalı: available (tüm bloklar vektörlü) · partial (bir kısmı henüz hesaplanmadı) · unavailable (model yok)
    dense: str = "unavailable"


@dataclass
class ParsedQuery:
    words: list[str]
    symbols: list[str]
    expanded: list[str]


def parse_query(q: str) -> ParsedQuery:
    raw = [t for t in TOKEN_RE.findall(q or "")]
    symbols = [t.rstrip("()") for t in raw if is_symbol(t)]
    words = [lower_tr(t) for t in raw if lower_tr(t) not in STOP and len(t) >= 2]
    terms = terminology()
    expanded: dict[str, None] = {w: None for w in words}
    lowered = lower_tr(q or "")
    for term, syns in terms.items():
        if re.search(rf"(?<!\w){re.escape(term)}", lowered):
            for s in syns:
                for part in s.split():
                    expanded[part] = None
            for part in term.split():
                expanded[part] = None
    return ParsedQuery(words=words, symbols=symbols, expanded=list(expanded))


def _fuse(db: Session, project_id: uuid.UUID, rows: list[dict], dense: DenseResult, kind: str | None) -> list[dict]:
    """Kelime ve vektör sayfa sıralamalarını RRF (k=60) ile birleştirir. Birebir sembol isabeti olan sayfalar üstte kalır
    (vektör tanımlayıcıyı aşağı itemez). Yalnız vektörle bulunan sayfanın satırı search_documents'tan gelir."""
    if not dense.pages:
        return rows
    lex_rank = {r["page_id"]: i + 1 for i, r in enumerate(rows)}
    dense_rank = {p.page_id: i + 1 for i, p in enumerate(dense.pages)}
    by_page = {r["page_id"]: r for r in rows}
    # Yalnız vektörle bulunan sayfa ancak benzerliği admit_score'u geçerse girer (konu dışı soruda "kanıt yok" korunur).
    missing = [p.page_id for p in dense.pages if p.page_id not in by_page and p.admit]
    if missing:
        extra = db.execute(
            text(
                f"""SELECT page_id, revision_id, title, kind, scope FROM search_documents
                    WHERE project_id = :p AND page_id = ANY(:ids) {"AND kind = :kind" if kind else ""}"""
            ).bindparams(bindparam("ids")),
            {"p": project_id, "ids": missing, **({"kind": kind} if kind else {})},
        ).mappings()
        for e in extra:
            by_page[e["page_id"]] = {**dict(e), "matched": [], "best_claims": [], "best_body": None, "best_heading": None, "snippet": "", "score": 0.0}
    for p in dense.pages:
        r = by_page.get(p.page_id)
        if r is None:
            continue
        claims = list(r.get("best_claims") or [])
        if p.claim_id not in claims:
            claims.insert(1 if claims else 0, p.claim_id)
        r["best_claims"] = claims[:8]
        if not r.get("best_body"):
            r["best_body"], r["best_heading"], r["snippet"] = p.body, p.heading_path, p.body[:400]

    def rrf(page_id: uuid.UUID) -> float:
        s = 0.0
        if page_id in lex_rank:
            s += 1 / (RRF_K + lex_rank[page_id])
        if page_id in dense_rank:
            s += 1 / (RRF_K + dense_rank[page_id])
        return s

    fused = sorted(by_page.values(), key=lambda r: (not r.get("matched"), -rrf(r["page_id"]), r["title"]))
    for r in fused:
        r["score"] = round(rrf(r["page_id"]), 6)
    return fused


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
    dense: bool = True,
) -> SearchOut:
    """`dense=False`: yalnız kelime kanalı (liste süzgeci gibi "bu metni içeren" aramalar; ölçümde karşılaştırma)."""
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
          SELECT websearch_to_tsquery('simple', :oqs) AS qs, websearch_to_tsquery('turkish', :oq) AS qt,
                 websearch_to_tsquery('simple', :oq) AS qsr
        ),
        p AS (
          SELECT sp.page_id, sp.claim_id, sp.ord, sp.heading_path, sp.body, sp.is_heading,
                 ts_rank_cd(sp.tsv_simple, q.qs) * 2 + ts_rank_cd(sp.tsv_turkish, q.qt) * 2
                 + CASE WHEN sp.symbols && CAST(:symbols AS text[]) THEN 5 ELSE 0 END AS ps
          FROM search_passages sp, q
          WHERE sp.project_id = :project_id
            AND (sp.tsv_simple @@ q.qs OR sp.tsv_turkish @@ q.qt OR sp.symbols && CAST(:symbols AS text[]))
        ),
        ranked AS (
          SELECT p.*, row_number() OVER (PARTITION BY page_id ORDER BY ps DESC, ord) AS rn,
                 row_number() OVER (PARTITION BY page_id ORDER BY is_heading, ps DESC, ord) AS dn FROM p
        ),
        agg AS (
          SELECT page_id,
                 max(ps) FILTER (WHERE rn = 1) AS best,
                 coalesce(max(ps) FILTER (WHERE rn = 2), 0) AS second,
                 (array_agg(claim_id ORDER BY is_heading, ps DESC, ord))[1:8] AS best_claims,
                 max(body) FILTER (WHERE dn = 1) AS best_body,
                 max(heading_path) FILTER (WHERE dn = 1) AS best_heading
          FROM ranked GROUP BY page_id
        )
        SELECT d.page_id, d.revision_id, d.title, d.kind, d.scope,
               ARRAY(SELECT s FROM unnest(d.symbols) s WHERE s = ANY(CAST(:symbols AS text[]))) AS matched,
               ( CASE WHEN d.symbols && CAST(:symbols AS text[]) THEN 10 ELSE 0 END
               + CASE WHEN d.title ILIKE ANY(CAST(:likes AS text[])) THEN 4 ELSE 0 END
               + CASE WHEN EXISTS (SELECT 1 FROM unnest(d.aliases) a WHERE lower(a) = ANY(CAST(:words AS text[]))) THEN 3 ELSE 0 END
               + coalesce(a.best, 0) + 0.25 * coalesce(a.second, 0)
               + 0.5 * (ts_rank_cd(d.tsv_simple, q.qsr) + ts_rank_cd(d.tsv_turkish, q.qt))
               {fuzzy_sql}
               ) AS score,
               a.best_claims, a.best_body, a.best_heading,
               CASE WHEN a.best_body IS NOT NULL
                    THEN ts_headline('turkish', a.best_body, q.qt, 'MaxWords=28, MinWords=12, StartSel=«, StopSel=»')
                    ELSE ts_headline('simple', d.content, q.qs, 'MaxWords=28, MinWords=12, StartSel=«, StopSel=»') END AS snippet
        FROM search_documents d CROSS JOIN q LEFT JOIN agg a ON a.page_id = d.page_id
        WHERE d.project_id = :project_id
          AND (a.page_id IS NOT NULL OR d.symbols && CAST(:symbols AS text[])
               OR d.tsv_simple @@ q.qsr OR d.tsv_turkish @@ q.qt
               OR d.title ILIKE ANY(CAST(:likes AS text[]))
               OR EXISTS (SELECT 1 FROM unnest(d.aliases) a2 WHERE lower(a2) = ANY(CAST(:words AS text[])))
               {"OR EXISTS (SELECT 1 FROM unnest(d.symbols) s, unnest(CAST(:symbols AS text[])) sym WHERE similarity(s, sym) > 0.45)" if fuzzy and parsed.symbols else ""})
          {"AND d.kind = :kind" if kind else ""}
        ORDER BY score DESC, d.title
        LIMIT 200
        """
    ).bindparams(bindparam("symbols"), bindparam("likes"), bindparam("words"))
    params = {
        "oq": or_query,
        "oqs": fold(or_query),
        "symbols": parsed.symbols,
        "likes": like_terms,
        "words": parsed.expanded,
        "project_id": project_id,
    }
    if kind:
        params["kind"] = kind
    rows = [dict(r) for r in db.execute(sql, params).mappings().all()]
    dense_res = dense_search(db, project_id, q) if dense else DenseResult("unavailable", [])
    rows = _fuse(db, project_id, rows, dense_res, kind)
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
                best_claims=list(r["best_claims"] or []),
                heading_path=r["best_heading"] or "",
                passage_text=r["best_body"],
            )
        )
        if len(hits) >= limit:
            break
    return SearchOut(hits=hits, fuzzy_available=fuzzy, query_terms=parsed.expanded + parsed.symbols, dense=dense_res.state)
