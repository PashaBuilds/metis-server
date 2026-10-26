"""Gömme modeli kıyası, kurgusal ölçek veritabanında: model başına gömme, eşik ayarı, arama kalitesi; isteğe bağlı yeniden
sıralayıcı (cross-encoder) ve ayrı hız ölçümü.

    python -m evals.scale.compare_models --db metiscmp --models <dizin>,<dizin> [--reranker <dizin>] --out cmp-models.json
    python -m evals.scale.compare_models --db metiscmp --models ... --bench-only   # yalnız hız (makine boşken)

Önce `evals.scale.run` veritabanını kurmuş olmalı. Her model dizininde METIS'in okuduğu MODEL.json bulunur.

Eşikler her model için aynı kuralla bu koşuda ayarlanır (ölçüm süresince MODEL.json'a yazılır, sonra eski hâline döner):
`admit_score` = konu dışı sorulardaki en yüksek benzerlik + 0,02 (yukarı yuvarlanır); `min_score` = `admit_score` − 0,04.
Eşikler ölçümde kullanılan soru kümesiyle ayarlanır; tüm modeller aynı avantajı alır, mutlak değerler iyimserdir.

Hız: aynı 2.000 blok 64'lük partilerle (METIS worker'ı gibi kısa metin önce), sorgu süresi tek tek 30 soru; yeniden sıralayıcı
soru başına 30 aday. ONNX iş parçacığı METIS ile aynı (en çok 4).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import tempfile
import time
import uuid
from pathlib import Path

from evals.scale import run as base

CANDIDATES = 30


def _thresholds(neg_max: float) -> tuple[float, float]:
    admit = math.ceil((neg_max + 0.02) * 100) / 100
    return round(admit - 0.04, 2), admit


def _use(model_dir: Path, meta: dict | None = None) -> None:
    from metis.modules.search import embedding, vectors

    if meta is not None:
        (model_dir / "MODEL.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    os.environ["METIS_EMBEDDING_MODEL_DIR"] = str(model_dir)
    embedding.reset()
    vectors.reset_cache()


def _calibrate(pid: str, pages: dict[str, str]) -> dict:
    import numpy as np
    from tests.retrieval_kit import corpus_questions

    from evals.retrieval.corpus import NEGATIVE
    from metis.core.db import transaction
    from metis.modules.search import vectors
    from metis.modules.search.embedding import get_embedder

    emb = get_embedder()
    assert emb is not None
    with transaction() as db:
        m = vectors._matrix(db, uuid.UUID(pid), emb.model_id)
    mat, page_ids = m["matrix"], np.array([str(p) for p in m["page_ids"]])
    neg = [float((mat @ emb.embed([q], "query")[0]).max()) for q in NEGATIVE]
    pos = []
    for q in corpus_questions(pages):
        s = mat @ emb.embed([q.question], "query")[0]
        sel = np.isin(page_ids, [str(p) for p in q.expected_page_ids])
        if sel.any():
            pos.append(float(s[sel].max()))
    lo, admit = _thresholds(max(neg))
    pos.sort()
    return {
        "negative_max": round(max(neg), 3),
        "relevant_min": round(pos[0], 3),
        "relevant_p10": round(pos[len(pos) // 10], 3),
        "relevant_median": round(statistics.median(pos), 3),
        "relevant_below_admit": sum(p < admit for p in pos),
        "relevant_n": len(pos),
        "min_score": lo,
        "admit_score": admit,
    }


class Reranker:
    def __init__(self, path: Path) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, min(4, (os.cpu_count() or 2) // 2))
        self.session = ort.InferenceSession(str(path / "onnx" / "model_quantized.onnx"), opts, providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.session.get_inputs()}
        self.tok = Tokenizer.from_file(str(path / "tokenizer.json"))
        self.tok.enable_truncation(512)
        self.tok.enable_padding()

    def scores(self, query: str, texts: list[str]) -> list[float]:
        import numpy as np

        out: list[float] = []
        for i in range(0, len(texts), 16):
            enc = self.tok.encode_batch([(query, t) for t in texts[i : i + 16]])
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            feeds = {"input_ids": ids, "attention_mask": mask, "token_type_ids": np.zeros_like(ids)}
            logits = self.session.run(None, {k: v for k, v in feeds.items() if k in self.inputs})[0].reshape(-1)
            out += [1 / (1 + math.exp(-float(x))) for x in logits]
        return out


def _hit_text(h) -> str:  # noqa: ANN001
    return " — ".join(x for x in (h.title, h.heading_path, h.passage_text or h.snippet) if x)


def _quality(pid: str, pages: dict[str, str], reranker: Reranker | None) -> dict:
    from sqlalchemy import text
    from tests.retrieval_kit import corpus_questions

    from evals.retrieval.corpus import NEGATIVE
    from metis.core.db import transaction
    from metis.core.models import User
    from metis.modules.search.evaluate import evaluate
    from metis.modules.search.service import search

    out: dict = {}
    qs = corpus_questions(pages)
    modes = [("hybrid", None), ("hybrid_kart", {"kart": ["VPK120"]})]
    with transaction() as db:
        user = db.get(User, db.scalar(text("SELECT id FROM users WHERE username = 'ayse'")))
        for mode, flt in modes:
            for rr in ([False, True] if reranker else [False]):
                lat: list[float] = []
                rr_scores: dict[str, list[float]] = {"negative_top": [], "relevant_top": []}

                def fn(db, user, project_id, q, scope=None, kind=None, limit=20, _flt=flt, _rr=rr, _lat=lat):  # noqa: ANN001, ANN202
                    t = time.perf_counter()
                    res = search(db, user, project_id, q, _flt, kind, CANDIDATES if _rr else limit, dense=True)
                    if _rr and res.hits:
                        sc = reranker.scores(q, [_hit_text(h) for h in res.hits])  # type: ignore[union-attr]
                        order = sorted(range(len(res.hits)), key=lambda i: -sc[i])
                        res = res.model_copy(update={"hits": [res.hits[i] for i in order][:limit]})
                    _lat.append((time.perf_counter() - t) * 1000)
                    return res

                res = evaluate(db, user, uuid.UUID(pid), qs, search_fn=fn)
                neg = {}
                for q in NEGATIVE:
                    r = fn(db, user, uuid.UUID(pid), q)
                    if r.hits:
                        neg[q] = len(r.hits)
                        if rr:
                            rr_scores["negative_top"].append(round(max(reranker.scores(q, [_hit_text(h) for h in r.hits[:5]])), 3))  # type: ignore[union-attr]
                m = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in res.metrics.items() if k != "by_kind"}
                out[mode + ("+rerank" if rr else "")] = {
                    "latency": base._stats(lat),
                    "metrics": m,
                    "by_kind": {k: {kk: round(vv, 3) if isinstance(vv, float) else vv for kk, vv in v.items()} for k, v in res.metrics["by_kind"].items()},
                    "negative_with_hits": neg,
                    **({"rerank_negative_top": rr_scores["negative_top"]} if rr else {}),
                    "missed": [r["question"] for r in res.per_question if not r["rank"] or r["rank"] > 5],
                }
    return out


def _bench(models: list[Path], reranker_dir: Path | None) -> dict:
    from sqlalchemy import text
    from tests.retrieval_kit import QUESTIONS

    from metis.core.db import transaction
    from metis.modules.search.embedding import _load
    from metis.modules.search.vectors import embed_text

    with transaction() as db:
        rows = db.execute(
            text(
                """SELECT d.title, sp.heading_path, sp.body FROM search_passages sp JOIN search_documents d ON d.page_id = sp.page_id
                   ORDER BY sp.embed_sha256 LIMIT 2000"""
            )
        ).all()
    texts = sorted((embed_text(r.title, r.heading_path, r.body) for r in rows), key=len)
    questions = [q for q, *_ in QUESTIONS][:30]
    out: dict = {"blocks": len(texts), "threads": max(1, min(4, (os.cpu_count() or 2) // 2))}
    for d in models:
        emb = _load(d)
        emb.embed(texts[:8], "passage")  # ısınma
        t = time.perf_counter()
        for i in range(0, len(texts), 64):
            emb.embed(texts[i : i + 64], "passage")
        el = time.perf_counter() - t
        lat = []
        for q in questions:
            t = time.perf_counter()
            emb.embed([q], "query")
            lat.append((time.perf_counter() - t) * 1000)
        out[d.name] = {"model_id": emb.model_id, "dim": emb.dim, "blocks_per_s": round(len(texts) / el, 1), "query_ms": base._stats(lat)}
    if reranker_dir:
        rr = Reranker(reranker_dir)
        cand = texts[:CANDIDATES]
        rr.scores(questions[0], cand[:4])
        lat = []
        for q in questions:
            t = time.perf_counter()
            rr.scores(q, cand)
            lat.append((time.perf_counter() - t) * 1000)
        out[reranker_dir.name] = {"candidates": CANDIDATES, "query_ms": base._stats(lat)}
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--admin-dsn", default=os.environ.get("METIS_TEST_ADMIN_DSN", "postgresql://metisdev:metis-dev@127.0.0.1:5432/postgres"))
    p.add_argument("--db", default="metiscmp")
    p.add_argument("--models", required=True, help="virgülle model dizinleri (MODEL.json içeren)")
    p.add_argument("--reranker", default="")
    p.add_argument("--out", default="evals/reports/compare-models.json")
    p.add_argument("--bench-only", action="store_true")
    a = p.parse_args()
    if a.db.startswith("metis_") or a.db == "metis":
        raise SystemExit("Kurulu METIS'in adlarına dokunulmaz: --db başka bir ad olmalı.")
    base._env(a.admin_dsn, a.db, Path(tempfile.gettempdir()) / f"metis-scale-{a.db}")
    from metis.core import security

    security.SCRYPT_N = 2**10
    models = [Path(m) for m in a.models.split(",") if m]
    rr_dir = Path(a.reranker) if a.reranker else None
    out_path = Path(a.out)
    report = json.loads(out_path.read_text(encoding="utf-8")) if out_path.is_file() else {"models": {}}

    def save() -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    if not a.bench_only:
        from sqlalchemy import text

        from metis.core.db import transaction

        api = base.Api()
        pid = base._setup(api, False)
        pages = base._needles(api, pid)
        reranker = Reranker(rr_dir) if rr_dir else None
        for d in models:
            print(f"==> {d.name}", flush=True)
            meta = json.loads((d / "MODEL.json").read_text(encoding="utf-8"))
            _use(d)
            entry: dict = {"model_id": meta["id"], "dim": meta["dim"], "embed": base._embed(str(d))}
            _use(d, {**meta, "min_score": 0.0, "admit_score": 1.01})
            cal = _calibrate(pid, pages)
            _use(d, {**meta, "min_score": cal["min_score"], "admit_score": cal["admit_score"]})
            entry["calibration"] = cal
            with transaction() as db:
                n = db.scalar(text("SELECT count(*) FROM search_passages WHERE project_id = :p"), {"p": pid})
            entry["matrix_mb"] = round(n * meta["dim"] * 4 / 2**20, 1)  # API sürecindeki float32 matris
            entry.update(_quality(pid, pages, reranker))
            _use(d, meta)  # model dizini ürün eşikleriyle kalır; ayarlanan eşikler raporda
            report["models"][d.name] = entry
            save()
            print(json.dumps({k: v for k, v in entry.items() if k not in ("by_kind",)}, ensure_ascii=False, default=str)[:2500], flush=True)
    report["bench"] = _bench(models, rr_dir)
    save()
    print(json.dumps(report["bench"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
