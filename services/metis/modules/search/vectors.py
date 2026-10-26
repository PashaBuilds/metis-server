"""Vektör kanalı: blok vektörlerinin hesaplanması (worker) ve proje matrisiyle en yakın bloklar (API). Tasarım bölüm 6.

Vektör saklama: `passage_vectors` (model + gömülen metnin sha256'sı → float16; hesaplanamayan blok boş işaretle).
Sorguda proje matrisi süreç belleğinde float32 tutulur (en çok 8 proje). `search_state.version` (yayın) değişince hemen,
`vectors_version` (yeni vektörler) değişince en çok dakikada bir tazelenir; tazelemede yalnız yeni blokların vektörü okunur. Benzerlik eşikleri modelin
`MODEL.json`'undadır: `min_score` altı yok sayılır; yalnız vektörle bulunan sayfa `admit_score`'u geçmelidir (konu dışı
soruda "kanıt yok" korunur). Okunabilirlik, kapsam ve tür süzgeci arama katmanındadır.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from metis.core.models import PassageVector, SearchState
from metis.llm.prompts import ENRICH
from metis.modules.search.embedding import get_embedder

log = logging.getLogger("metis.vectors")

FAILED = b""  # hesaplanamayan blok işareti: yeniden denenmez, matrise girmez, durumda "hesaplanamadı" sayılır


def embed_text(title: str, heading_path: str, body: str, context: str = "", questions: list[str] | None = None) -> str:
    """Gömülen metin: başlık, başlık yolu, gövde; varsa zenginleştirme (bağlam + sorular, kanıt değildir)."""
    parts = (title, heading_path, body, context, *(questions or []))
    return "\n".join(p.strip() for p in parts if p and p.strip())


def embed_hash(title: str, heading_path: str, body: str, context: str = "", questions: list[str] | None = None) -> str:
    return hashlib.sha256(embed_text(title, heading_path, body, context, questions).encode("utf-8")).hexdigest()


def bump(db: Session, project_ids: set[uuid.UUID], vectors: bool = False) -> None:
    """Yayın değişince `version`, yalnız yeni vektör gelince `vectors_version` artar."""
    col = "vectors_version" if vectors else "version"
    for pid in project_ids:
        db.execute(
            insert(SearchState)
            .values(project_id=pid, **{col: 1})
            .on_conflict_do_update(index_elements=["project_id"], set_={col: getattr(SearchState, col) + 1})
        )


def embed_missing(db: Session, limit: int = 16) -> int:
    """Vektörü olmayan en çok `limit` bloğu hesaplar (kısa metinler önce: dolgu belleği küçük kalır). Toplu hesap
    başarısız olursa bloklar tek tek denenir; yine olmayan blok `FAILED` işaretlenir ve tekrar denenmez. Model yoksa 0."""
    emb = get_embedder()
    if emb is None:
        return 0
    rows = db.execute(
        text(
            """
            SELECT h, title, heading_path, body, context, questions FROM (
              SELECT DISTINCT ON (sp.embed_sha256) sp.embed_sha256 AS h, d.title, sp.heading_path, sp.body,
                     coalesce(pe.context, '') AS context, coalesce(pe.questions, '{}') AS questions
              FROM search_passages sp
              JOIN search_documents d ON d.page_id = sp.page_id
              LEFT JOIN passage_enrichments pe
                ON pe.base_sha256 = sp.base_sha256 AND pe.prompt_version = :pv AND pe.status = 'ok'
              WHERE sp.embed_sha256 IS NOT NULL
                AND NOT EXISTS (SELECT 1 FROM passage_vectors pv WHERE pv.model_id = :m AND pv.text_sha256 = sp.embed_sha256)
              ORDER BY sp.embed_sha256
              LIMIT :limit
            ) x ORDER BY length(body)
            """
        ),
        {"m": emb.model_id, "limit": limit, "pv": ENRICH},
    ).all()
    if not rows:
        return 0
    texts = [embed_text(r.title, r.heading_path, r.body, r.context, list(r.questions)) for r in rows]
    try:
        vecs: list[bytes] = [v.astype(np.float16).tobytes() for v in emb.embed(texts, "passage")]
    except Exception:  # noqa: BLE001 — bir blok tüm partiyi sonsuza dek kilitlemesin
        vecs = []
        for r, t in zip(rows, texts, strict=True):
            try:
                vecs.append(emb.embed([t], "passage")[0].astype(np.float16).tobytes())
            except Exception:  # noqa: BLE001
                log.warning("passage could not be embedded", extra={"event": r.h[:16]})
                vecs.append(FAILED)
    db.execute(
        insert(PassageVector)
        .values([{"model_id": emb.model_id, "text_sha256": r.h, "vector": v} for r, v in zip(rows, vecs, strict=True)])
        .on_conflict_do_nothing()
    )
    projects = set(db.scalars(text("SELECT DISTINCT project_id FROM search_passages WHERE embed_sha256 = ANY(:hs)"), {"hs": [r.h for r in rows]}))
    bump(db, projects, vectors=True)
    return len(rows)


# ---------------------------------------------------------------- sorgu: proje matrisi ve en yakın bloklar

RRF_K = 60
DENSE_TOP = 50
CACHE_PROJECTS = 8
VECTOR_RELOAD_S = 60.0
_cache: OrderedDict[tuple[uuid.UUID, str], dict] = OrderedDict()
_cache_lock = threading.Lock()
_load_locks: dict[tuple[uuid.UUID, str], threading.Lock] = {}


@dataclass
class DensePage:
    page_id: uuid.UUID
    claim_id: uuid.UUID
    score: float
    admit: bool  # yalnız vektörle bulunduysa sonuca girebilir mi (admit_score)
    heading_path: str = ""
    body: str = ""


@dataclass
class DenseResult:
    state: str  # available | partial | unavailable
    pages: list[DensePage]


def reset_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _fresh(entry: dict | None, version: int, vectors_version: int) -> bool:
    if entry is None or entry["version"] != version:
        return False
    return entry["vectors_version"] == vectors_version or time.monotonic() - entry["loaded_at"] < VECTOR_RELOAD_S


last_refresh: dict = {}  # son tazelemede okunan vektör sayısı (ölçek testi ve tanı için)


def _refresh(db: Session, project_id: uuid.UUID, model_id: str, old: dict | None) -> dict:
    """Projenin güncel bloklarına göre matrisi kurar. Önceki matristeki vektörler (aynı metin özeti) yeniden okunmaz;
    veritabanından yalnız yeni blokların vektörü gelir — her yayında tüm proje vektörlerini taşımak büyük derlemde
    (230 bin blok ≈ 350 MB) yayından sonraki ilk aramayı saniyelerce bekletiyordu."""
    rows = db.execute(
        text("SELECT page_id, claim_id, is_heading, embed_sha256 FROM search_passages WHERE project_id = :p AND embed_sha256 IS NOT NULL"),
        {"p": project_id},
    ).all()
    old_row: dict[str, int] = old["hash_row"] if old else {}
    need = sorted({r.embed_sha256 for r in rows if r.embed_sha256 not in old_row})
    fresh: dict[str, np.ndarray] = {}
    for i in range(0, len(need), 5000):
        for h, v in db.execute(
            text("SELECT text_sha256, vector FROM passage_vectors WHERE model_id = :m AND text_sha256 = ANY(:hs) AND length(vector) > 0"),
            {"m": model_id, "hs": need[i : i + 5000]},
        ):
            fresh[h] = np.frombuffer(v, dtype=np.float16)
    keep = [r for r in rows if r.embed_sha256 in old_row or r.embed_sha256 in fresh]
    matrix = None
    if keep:
        dim = old["matrix"].shape[1] if old and old["matrix"] is not None else next(iter(fresh.values())).shape[0]
        # float32: sorguda dönüştürme yok (500 bin × 768 ≈ 1,5 GB'a kadar; KURULUM.md bellek notu)
        matrix = np.empty((len(keep), dim), dtype=np.float32)
        from_old = np.array([r.embed_sha256 in old_row for r in keep], dtype=bool)
        if from_old.any():
            matrix[from_old] = old["matrix"][np.array([old_row[r.embed_sha256] for r in keep if r.embed_sha256 in old_row])]  # type: ignore[index]
        if not from_old.all():
            matrix[~from_old] = np.vstack([fresh[r.embed_sha256] for r in keep if r.embed_sha256 not in old_row]).astype(np.float32)
    last_refresh.update(fetched=len(fresh), rows=len(keep))
    return {
        "page_ids": [r.page_id for r in keep],
        "claim_ids": [r.claim_id for r in keep],
        "is_heading": np.array([bool(r.is_heading) for r in keep], dtype=bool),
        "hash_row": {r.embed_sha256: i for i, r in enumerate(keep)},
        "matrix": matrix,
        "partial": len(keep) < len(rows) or _unhashed(db, project_id),
    }


def _unhashed(db: Session, project_id: uuid.UUID) -> bool:
    return db.scalar(text("SELECT 1 FROM search_passages WHERE project_id = :p AND embed_sha256 IS NULL LIMIT 1"), {"p": project_id}) is not None


def _matrix(db: Session, project_id: uuid.UUID, model_id: str) -> dict:
    st = db.execute(select(SearchState.version, SearchState.vectors_version).where(SearchState.project_id == project_id)).first()
    version, vversion = (st.version, st.vectors_version) if st else (0, 0)
    key = (project_id, model_id)
    with _cache_lock:
        entry = _cache.get(key)
        if _fresh(entry, version, vversion):
            _cache.move_to_end(key)
            return entry  # type: ignore[return-value]
        load_lock = _load_locks.setdefault(key, threading.Lock())
    with load_lock:  # aynı süreçte eşzamanlı istekler matrisi bir kez yükler
        with _cache_lock:
            entry = _cache.get(key)
            if _fresh(entry, version, vversion):
                return entry  # type: ignore[return-value]
        entry = _refresh(db, project_id, model_id, entry)
        entry.update(version=version, vectors_version=vversion, loaded_at=time.monotonic())
        with _cache_lock:
            _cache[key] = entry
            _cache.move_to_end(key)
            while len(_cache) > CACHE_PROJECTS:
                _cache.popitem(last=False)
        return entry


def dense_search(db: Session, project_id: uuid.UUID, query: str) -> DenseResult:
    """Eşik üstündeki en yakın bloklar → sayfa başına en iyi blok (başlık satırı yerine altındaki blok tercih edilir)."""
    emb = get_embedder()
    if emb is None:
        return DenseResult("unavailable", [])
    try:
        m = _matrix(db, project_id, emb.model_id)
        state = "partial" if m["partial"] else "available"
        if m["matrix"] is None:
            return DenseResult(state, [])
        scores = m["matrix"] @ emb.embed([query], "query")[0]
    except Exception:  # noqa: BLE001 — vektör kanalı arızası aramayı düşürmez
        log.exception("dense search failed")
        return DenseResult("unavailable", [])
    cand = np.flatnonzero(scores >= emb.min_score)
    if cand.size > DENSE_TOP:
        cand = cand[np.argpartition(-scores[cand], DENSE_TOP)[:DENSE_TOP]]
    cand = cand[np.argsort(-scores[cand])]
    best: dict[uuid.UUID, int] = {}
    for i in cand:
        pid = m["page_ids"][i]
        if pid not in best or (m["is_heading"][best[pid]] and not m["is_heading"][i]):
            best[pid] = int(i)
    pages = [
        DensePage(m["page_ids"][i], m["claim_ids"][i], float(scores[i]), float(scores[i]) >= emb.admit_score)
        for i in sorted(best.values(), key=lambda i: -scores[i])
    ]
    if pages:
        texts = {
            r.claim_id: (r.heading_path, r.body)
            for r in db.execute(
                text("SELECT claim_id, heading_path, body FROM search_passages WHERE claim_id = ANY(:c)"), {"c": [p.claim_id for p in pages]}
            )
        }
        for p in pages:
            p.heading_path, p.body = texts.get(p.claim_id, ("", ""))
    return DenseResult(state, pages)
