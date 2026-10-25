"""Vektör kanalı: blok vektörlerinin hesaplanması (worker) ve proje matrisiyle en yakın bloklar (API). Tasarım bölüm 6.

Vektör saklama: `passage_vectors` (model + gömülen metnin sha256'sı → float16). Sorguda proje matrisi süreç belleğinde
tutulur ve `search_state.version` değişince yeniden yüklenir. Okunabilirlik ve kapsam süzgeci arama katmanındadır.
"""

from __future__ import annotations

import hashlib
import logging
import uuid

import numpy as np
from sqlalchemy import text
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
