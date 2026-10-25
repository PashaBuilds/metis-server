"""Vektör kanalı: blok vektörlerinin hesaplanması (worker) ve proje matrisiyle en yakın bloklar (API). Tasarım bölüm 6.

Vektör saklama: `passage_vectors` (model + gömülen metnin sha256'sı → float16). Sorguda proje matrisi süreç belleğinde
tutulur ve `search_state.version` değişince yeniden yüklenir. Okunabilirlik ve kapsam süzgeci arama katmanındadır.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import uuid
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from metis.core.models import PassageVector, SearchState
from metis.modules.search.embedding import get_embedder

log = logging.getLogger("metis.vectors")


def embed_text(title: str, heading_path: str, body: str) -> str:
    return "\n".join(p for p in (title.strip(), heading_path.strip(), body.strip()) if p)


def embed_hash(title: str, heading_path: str, body: str) -> str:
    return hashlib.sha256(embed_text(title, heading_path, body).encode("utf-8")).hexdigest()


def bump(db: Session, project_ids: set[uuid.UUID]) -> None:
    for pid in project_ids:
        db.execute(
            insert(SearchState)
            .values(project_id=pid, version=1)
            .on_conflict_do_update(index_elements=["project_id"], set_={"version": SearchState.version + 1})
        )


def embed_missing(db: Session, limit: int = 64) -> int:
    """Vektörü olmayan blokların en çok `limit` tanesini hesaplar. Model yoksa 0. Dönen: hesaplanan vektör sayısı."""
    emb = get_embedder()
    if emb is None:
        return 0
    rows = db.execute(
        text(
            """
            SELECT DISTINCT ON (sp.embed_sha256) sp.embed_sha256 AS h, d.title, sp.heading_path, sp.body
            FROM search_passages sp
            JOIN search_documents d ON d.page_id = sp.page_id
            WHERE sp.embed_sha256 IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM passage_vectors pv WHERE pv.model_id = :m AND pv.text_sha256 = sp.embed_sha256)
            ORDER BY sp.embed_sha256
            LIMIT :limit
            """
        ),
        {"m": emb.model_id, "limit": limit},
    ).all()
    if not rows:
        return 0
    vecs = emb.embed([embed_text(r.title, r.heading_path, r.body) for r in rows], "passage")
    db.execute(
        insert(PassageVector)
        .values([{"model_id": emb.model_id, "text_sha256": r.h, "vector": v.astype(np.float16).tobytes()} for r, v in zip(rows, vecs, strict=True)])
        .on_conflict_do_nothing()
    )
    projects = set(
        db.scalars(text("SELECT DISTINCT project_id FROM search_passages WHERE embed_sha256 = ANY(:hs)"), {"hs": [r.h for r in rows]})
    )
    bump(db, projects)
    return len(rows)


# ---------------------------------------------------------------- sorgu: proje matrisi ve en yakın bloklar

RRF_K = 60
DENSE_TOP = 50
_cache: dict[tuple[uuid.UUID, str], dict] = {}
_cache_lock = threading.Lock()


@dataclass
class DensePage:
    page_id: uuid.UUID
    claim_id: uuid.UUID
    heading_path: str
    body: str
    score: float


@dataclass
class DenseResult:
    state: str  # available | partial | unavailable
    pages: list[DensePage]


def reset_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _matrix(db: Session, project_id: uuid.UUID, model_id: str) -> dict:
    version = db.scalar(select(SearchState.version).where(SearchState.project_id == project_id)) or 0
    key = (project_id, model_id)
    with _cache_lock:
        hit = _cache.get(key)
    if hit and hit["version"] == version:
        return hit
    rows = db.execute(
        text(
            """
            SELECT sp.page_id, sp.claim_id, sp.heading_path, sp.body, sp.is_heading, pv.vector
            FROM search_passages sp
            JOIN passage_vectors pv ON pv.model_id = :m AND pv.text_sha256 = sp.embed_sha256
            WHERE sp.project_id = :p
            """
        ),
        {"m": model_id, "p": project_id},
    ).all()
    total = db.scalar(text("SELECT count(*) FROM search_passages WHERE project_id = :p"), {"p": project_id}) or 0
    entry = {
        "version": version,
        "rows": [(r.page_id, r.claim_id, r.heading_path, r.body, r.is_heading) for r in rows],
        # float16 saklanır (bellek yarıya iner); skor hesabı parça parça float32.
        "matrix": np.vstack([np.frombuffer(r.vector, dtype=np.float16) for r in rows]) if rows else None,
        "partial": len(rows) < total,
    }
    with _cache_lock:
        _cache[key] = entry
    return entry


def dense_search(db: Session, project_id: uuid.UUID, query: str) -> DenseResult:
    """Sorguya en yakın bloklar → sayfa başına en iyi blok (başlık satırı yerine altındaki blok tercih edilir)."""
    emb = get_embedder()
    if emb is None:
        return DenseResult("unavailable", [])
    try:
        m = _matrix(db, project_id, emb.model_id)
        state = "partial" if m["partial"] else "available"
        if m["matrix"] is None:
            return DenseResult(state, [])
        q = emb.embed([query], "query")[0]
        scores = np.concatenate([m["matrix"][i : i + 20000].astype(np.float32) @ q for i in range(0, len(m["matrix"]), 20000)])
    except Exception:  # noqa: BLE001 — vektör kanalı arızası aramayı düşürmez
        log.exception("dense search failed")
        return DenseResult("unavailable", [])
    top = np.argsort(-scores)[:DENSE_TOP]
    best: dict[uuid.UUID, DensePage] = {}
    for i in top:
        page_id, claim_id, heading, body, is_heading = m["rows"][int(i)]
        cur = best.get(page_id)
        if cur is None or (cur.body.lstrip().startswith("#") and not is_heading):
            best[page_id] = DensePage(page_id, claim_id, heading, body, float(scores[int(i)]) if cur is None else cur.score)
    return DenseResult(state, sorted(best.values(), key=lambda p: -p.score))
