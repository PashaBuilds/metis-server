"""Ölçek denemesi: kurgusal büyük derlemi ayrı bir veritabanına aşamalı yükler ve her aşamada süreleri/kaliteyi ölçer.

    python -m evals.scale.run --admin-dsn postgresql://metisdev:metis-dev@127.0.0.1:5432/postgres \
        --db metisscale --stages 1000,5000,20000 [--reset] [--embed MODEL_DIR] [--out evals/reports/scale.json]

Ayrı veritabanı (`--db`) aşamalar arasında korunur; `--reset` siler. Kurulu METIS'in veritabanına dokunmaz.
Yükleme gerçek akıştan geçer (taslak → yayın öncesi kontrol → yazar yayımlar). Her aşamada kontrolün süresi örnek
partilerde ölçülür; diğer partilerde kontrol sonucu doğrudan yazılır (yükleme hızı için; ölçüm değil).
Ölçülen: yükleme ve yayın süresi, arama gecikmesi (kelime / hibrit), ölçüm sorularında kalite (büyük derlem içinde
"iğneler"), konu dışı isabet, bağlantılı bilgiler, bilgi listesi, Mentor (modelsiz: ilgili bölümler), yayın öncesi
kontrol, bakım taraması, tablo boyutları.
"""

from __future__ import annotations

import argparse
import base64
import json
import multiprocessing as mp
import os
import statistics
import sys
import tempfile
import time
import uuid
from pathlib import Path

BATCH = 5  # bir değişiklik en çok 5 sayfa (ChangeCreateIn)
CHECK_SAMPLE_EVERY = 20


def _env(admin_dsn: str, db: str, data_dir: Path) -> str:
    base = admin_dsn.rsplit("/", 1)[0].replace("postgresql://", "postgresql+psycopg://", 1)
    url = f"{base}/{db}"
    os.environ.update(
        {
            "METIS_ENV": "test",
            "METIS_DATABASE_URL": url,
            "METIS_OWNER_DATABASE_URL": url,
            "METIS_DATA_DIR": str(data_dir),
            "METIS_PUBLIC_URL": "http://localhost:8000",
            "METIS_MASTER_KEY": base64.b64encode(b"s" * 32).decode(),  # kurgusal; yalnız bu deneme veritabanı
            "METIS_STATIC_DIR": str(data_dir / "static"),
            "METIS_ENDPOINT_ALLOWLIST": os.environ.get("METIS_ENDPOINT_ALLOWLIST", "https://api.deepseek.com/v1"),
        }
    )
    from metis.core.config import reset_settings_cache

    reset_settings_cache()
    return url


def _ensure_db(admin_dsn: str, db: str, reset: bool) -> bool:
    import psycopg

    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db,)).fetchone() is not None
        if exists and reset:
            conn.execute(f'DROP DATABASE "{db}" WITH (FORCE)')
            exists = False
        if not exists:
            conn.execute(f'CREATE DATABASE "{db}"')
    return not exists


def _stats(ms: list[float]) -> dict:
    if not ms:
        return {"n": 0}
    s = sorted(ms)
    return {
        "n": len(s),
        "p50_ms": round(statistics.median(s), 1),
        "p95_ms": round(s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))], 1),
        "max_ms": round(s[-1], 1),
    }


class Api:
    def __init__(self) -> None:
        from fastapi.testclient import TestClient

        from metis.app import create_app

        self.http = TestClient(create_app(), base_url="http://localhost:8000", headers={"Origin": "http://localhost:8000"}, raise_server_exceptions=False)
        self.csrf = ""

    def call(self, method: str, url: str, **kw):  # noqa: ANN003, ANN201
        headers = {"X-CSRF-Token": self.csrf} if self.csrf and method != "GET" else {}
        r = self.http.request(method, url, headers=headers, **kw)
        return r

    def ok(self, method: str, url: str, expect: int = 200, **kw) -> dict:  # noqa: ANN003
        r = self.call(method, url, **kw)
        if r.status_code != expect:
            raise RuntimeError(f"{method} {url} → {r.status_code}: {r.text[:500]}")
        return r.json() if r.content else {}


def _setup(api: Api, fresh: bool) -> str:
    from tests.factories import ADMIN_PASSWORD, add_scope_values, setup_admin

    if fresh:
        me = setup_admin(api_client_shim(api))
        pid = me["memberships"][0]["project_id"]
        api.ok("PATCH", f"/api/v1/projects/{pid}", json={"review_policy": "self_publish"})
        from evals.scale.generate import BOARDS

        add_scope_values(api_client_shim(api), pid, {"domain": ["Gömülü yazılım"], "kart": ["VPK120", *BOARDS]})
        return pid
    r = api.ok("POST", "/api/v1/auth/login", json={"username": "ayse", "password": ADMIN_PASSWORD})
    api.csrf = r["csrf_token"]
    from sqlalchemy import text

    from metis.core.db import transaction

    with transaction() as db:
        return str(db.scalar(text("SELECT id FROM projects ORDER BY created_at LIMIT 1")))


def api_client_shim(api: Api):  # noqa: ANN201
    """tests.factories yardımcıları ApiClient bekler (post + csrf)."""

    class Shim:
        def post(self, url, json=None, **kw):  # noqa: ANN001, ANN003, ANN202
            r = api.call("POST", url, json=json, **kw)
            if r.status_code == 200 and "csrf_token" in (r.json() if r.content else {}):
                api.csrf = r.json()["csrf_token"]
            return r

        @property
        def csrf(self):  # noqa: ANN202
            return api.csrf

        @csrf.setter
        def csrf(self, v):  # noqa: ANN001, ANN202
            api.csrf = v

        user: dict = {}

    return Shim()


def _publish_batch(api: Api, pid: str, items: list[dict], real_check: bool) -> dict:
    t0 = time.perf_counter()
    change = api.ok("POST", f"/api/v1/projects/{pid}/changes", expect=201, json={"summary": items[0]["title"], "items": items})
    t1 = time.perf_counter()
    if real_check:
        api.ok("POST", f"/api/v1/changes/{change['id']}/check")
    else:  # yükleme hızı için: kontrol sonucu (sorun yok, model yok) doğrudan yazılır — ölçülmez
        from metis.core.db import transaction
        from metis.core.models import ChangeSet

        with transaction() as db:
            ch = db.get(ChangeSet, uuid.UUID(change["id"]))
            ch.detail = {**ch.detail, "prepublish": {"hash": ch.hash, "model_status": "not_configured", "model_name": None, "issues": [], "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}}
    t2 = time.perf_counter()
    h = api.ok("GET", f"/api/v1/changes/{change['id']}")["hash"]
    api.ok("POST", f"/api/v1/changes/{change['id']}/publish-direct", json={"hash": h, "acknowledge_issues": True})
    t3 = time.perf_counter()
    return {"create_ms": (t1 - t0) * 1000, "check_ms": (t2 - t1) * 1000 if real_check else None, "publish_ms": (t3 - t2) * 1000}


def _page_count(pid: str) -> int:
    from sqlalchemy import text

    from metis.core.db import transaction

    with transaction() as db:
        return db.scalar(text("SELECT count(*) FROM pages WHERE project_id = :p AND published_revision_id IS NOT NULL"), {"p": pid}) or 0


def _load(api: Api, pid: str, target: int, generated: int) -> tuple[int, dict]:
    from tests.kb import DEFAULT_SCOPE

    from evals.scale.generate import page

    timings: dict[str, list[float]] = {"create_ms": [], "check_ms": [], "publish_ms": []}
    t0 = time.perf_counter()
    n_batch = 0
    while _page_count(pid) < target:
        items = []
        for i in range(generated, generated + BATCH):
            board, title, body = page(i)
            items.append({"note": True, "title": title, "summary": "", "body_md": body, "scope": {**DEFAULT_SCOPE, "kart": [board]}})
        generated += BATCH
        t = _publish_batch(api, pid, items, real_check=n_batch % CHECK_SAMPLE_EVERY == 0)
        for k, v in t.items():
            if v is not None:
                timings[k].append(v)
        n_batch += 1
        if n_batch % 20 == 0:
            print(f"  … {generated} sayfa üretildi, son parti yayın {t['publish_ms']:.0f} ms", flush=True)
    return generated, {"wall_s": round(time.perf_counter() - t0, 1), "batch_pages": BATCH, **{k: _stats(v) for k, v in timings.items()}}


def _needles(api: Api, pid: str) -> dict[str, str]:
    from sqlalchemy import text
    from tests.retrieval_kit import publish_corpus

    from evals.retrieval.corpus import PAGES
    from metis.core.db import transaction

    with transaction() as db:
        rows = db.execute(text("SELECT title, id FROM search_documents d JOIN pages p ON p.id = d.page_id WHERE d.project_id = :p"), {"p": pid}).all()
    by_title = {t: str(i) for t, i in rows}
    if all(title in by_title for _, title, _ in PAGES):
        return {slug: by_title[title] for slug, title, _ in PAGES}
    return publish_corpus(api_client_shim_full(api), pid)


def api_client_shim_full(api: Api):  # noqa: ANN201
    class Shim:
        def post(self, url, json=None, **kw):  # noqa: ANN001, ANN003, ANN202
            return api.call("POST", url, json=json, **kw)

        def get(self, url, **kw):  # noqa: ANN001, ANN003, ANN202
            return api.call("GET", url, **kw)

    return Shim()


def _timed(fn) -> tuple[float, object]:  # noqa: ANN001
    t = time.perf_counter()
    out = fn()
    return (time.perf_counter() - t) * 1000, out


def _scan_child(url: str, pid: str, q) -> None:  # noqa: ANN001
    os.environ["METIS_DATABASE_URL"] = url
    from metis.core.config import reset_settings_cache

    reset_settings_cache()
    from metis.core.db import transaction
    from metis.modules.health.maintenance import conflict_pairs

    t = time.perf_counter()
    with transaction() as db:
        n = len(conflict_pairs(db, uuid.UUID(pid)))
    q.put({"conflict_pairs_ms": round((time.perf_counter() - t) * 1000), "pairs": n})


def _conflict_scan(url: str, pid: str, timeout_s: int) -> dict:
    q: mp.Queue = mp.Queue()
    p = mp.Process(target=_scan_child, args=(url, pid, q))
    p.start()
    p.join(timeout_s)
    if p.is_alive():
        p.terminate()
        return {"conflict_pairs_ms": None, "timed_out_after_s": timeout_s}
    return q.get() if not q.empty() else {"error": f"exit {p.exitcode}"}


def _measure(api: Api, pid: str, pages: dict[str, str], url: str, scan_timeout: int) -> dict:
    from sqlalchemy import text
    from tests.retrieval_kit import corpus_questions

    from evals.retrieval.corpus import NEGATIVE
    from metis.core.db import transaction
    from metis.core.models import User
    from metis.modules.search import vectors
    from metis.modules.search.evaluate import evaluate
    from metis.modules.search.service import search

    out: dict = {}
    with transaction() as db:
        out["counts"] = dict(
            db.execute(
                text(
                    """SELECT (SELECT count(*) FROM pages WHERE published_revision_id IS NOT NULL) AS pages,
                              (SELECT count(*) FROM search_passages) AS passages,
                              (SELECT count(*) FROM claims) AS claims,
                              (SELECT count(*) FROM publications) AS publications,
                              (SELECT count(*) FROM publication_pages) AS publication_pages,
                              (SELECT count(*) FROM passage_vectors) AS vectors,
                              pg_database_size(current_database()) AS db_bytes"""
                )
            )
            .one()
            ._mapping
        )
        out["counts"] = {k: int(v) for k, v in out["counts"].items()}
        out["tables_mb"] = {
            r[0]: round(r[1] / 2**20, 1)
            for r in db.execute(
                text(
                    """SELECT relname, pg_total_relation_size(relid) FROM pg_stat_user_tables
                       ORDER BY pg_total_relation_size(relid) DESC LIMIT 8"""
                )
            )
        }
        user = db.scalar(text("SELECT id FROM users WHERE username = 'ayse'"))
        user = db.get(User, user)
        qs = corpus_questions(pages)
        dense_ready = (out["counts"]["vectors"] or 0) > 0
        modes = [("lexical", False, None), ("lexical_kart", False, {"kart": ["VPK120"]})]
        if dense_ready:
            modes += [("hybrid", True, None), ("hybrid_kart", True, {"kart": ["VPK120"]})]
        for mode, dense, flt in modes:
            vectors.reset_cache()
            if dense and "matrix_load_ms" not in out:  # ilk sorgu matrisi yükler: ayrı ölçülür
                out["matrix_load_ms"], _ = _timed(lambda: search(db, user, uuid.UUID(pid), "ısınma sorgusu", dense=True))
            lat = []

            def run(db, user, project_id, q, scope=None, kind=None, limit=20, _dense=dense, _flt=flt, _lat=lat):  # noqa: ANN001, ANN202
                ms, res = _timed(lambda: search(db, user, project_id, q, _flt, kind, limit, dense=_dense))
                _lat.append(ms)
                return res

            res = evaluate(db, user, uuid.UUID(pid), qs, search_fn=run)
            neg = {}
            for q in NEGATIVE:
                ms, r = _timed(lambda q=q, f=flt, d=dense: search(db, user, uuid.UUID(pid), q, f, dense=d))
                lat.append(ms)
                if r.hits:
                    neg[q] = len(r.hits)
            m = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in res.metrics.items() if k != "by_kind"}
            out[mode] = {
                "latency": _stats(lat),
                "metrics": m,
                "by_kind": res.metrics.get("by_kind"),
                "negative_with_hits": neg,
                "missed": [r["question"] for r in res.per_question if not r["rank"] or r["rank"] > 5],
            }
        sample = [r[0] for r in db.execute(text("SELECT id FROM pages WHERE published_revision_id IS NOT NULL ORDER BY id LIMIT 30"))]
    rel, detail = [], []
    for page_id in [*pages.values(), *map(str, sample)]:
        ms, _ = _timed(lambda p=page_id: api.ok("GET", f"/api/v1/pages/{p}/related"))
        rel.append(ms)
        ms, _ = _timed(lambda p=page_id: api.ok("GET", f"/api/v1/pages/{p}"))
        detail.append(ms)
    out["related"] = _stats(rel)
    out["page_detail"] = _stats(detail)
    lst = []
    for params in ({}, {"q": "kesme"}, {"kart": "R3"}, {"q": "watchdog zaman aşımı"}):
        ms, _ = _timed(lambda p=params: api.ok("GET", f"/api/v1/projects/{pid}/pages", params=p))
        lst.append(ms)
    out["page_list"] = _stats(lst)
    mentor = []
    for q in ["PERST# ne kadar süre aktif tutulmalı?", "UART baud hızı nasıl ayarlanır?", "Watchdog sıfırlama nedeni nereden okunur?"]:
        ms, _ = _timed(lambda q=q: api.call("POST", f"/api/v1/projects/{pid}/mentor/answers", json={"question": q}))
        mentor.append(ms)
    out["mentor_no_model"] = _stats(mentor)
    # Tek sayfalık yeni taslak: gerçek kontrol + yayın
    from tests.kb import DEFAULT_SCOPE

    from evals.scale.generate import page

    one = []
    for k in range(3):
        board, title, body = page(10_000_000 + int(time.time()) % 100_000 + k)
        one.append(_publish_batch(api, pid, [{"note": True, "title": title, "summary": "", "body_md": body, "scope": {**DEFAULT_SCOPE, "kart": [board]}}], real_check=True))
    out["single_page"] = {k: _stats([t[k] for t in one]) for k in ("create_ms", "check_ms", "publish_ms")}
    if out["counts"]["vectors"]:  # yayından sonraki ilk hibrit arama: matris tazelenir
        with transaction() as db:
            user = db.get(User, db.scalar(text("SELECT id FROM users WHERE username = 'ayse'")))
            out["first_hybrid_after_publish_ms"], _ = _timed(lambda: search(db, user, uuid.UUID(pid), "watchdog besleme aralığı", dense=True))
            out["refresh"] = dict(vectors.last_refresh) if hasattr(vectors, "last_refresh") else None
    out["maintenance"] = _conflict_scan(url, pid, scan_timeout)
    return out


def _embed(model_dir: str) -> dict:
    os.environ["METIS_EMBEDDING_MODEL_DIR"] = model_dir
    from metis.core.db import transaction
    from metis.modules.search import embedding
    from metis.modules.search.vectors import embed_missing

    embedding.reset()
    t0 = time.perf_counter()
    total = 0
    while True:
        with transaction() as db:
            n = embed_missing(db, limit=64)
        if not n:
            break
        total += n
        if total % 6400 < 64:
            el = time.perf_counter() - t0
            print(f"  … {total} blok gömüldü ({total / el:.0f}/sn)", flush=True)
    el = time.perf_counter() - t0
    return {"blocks": total, "wall_s": round(el, 1), "blocks_per_s": round(total / el, 1) if el else None}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--admin-dsn", default=os.environ.get("METIS_TEST_ADMIN_DSN", "postgresql://metisdev:metis-dev@127.0.0.1:5432/postgres"))
    p.add_argument("--db", default="metisscale")
    p.add_argument("--stages", default="1000,5000,20000")
    p.add_argument("--reset", action="store_true")
    p.add_argument("--embed", default="", help="gömme modeli dizini; verilirse son aşamadan sonra tüm bloklar gömülür ve hibrit ölçülür")
    p.add_argument("--embed-each-stage", action="store_true")
    p.add_argument("--scan-timeout", type=int, default=300)
    p.add_argument("--out", default="evals/reports/scale.json")
    p.add_argument("--no-migrate", action="store_true", help="şemayı yükseltme (eski kodu aynı veritabanında ölçmek için)")
    p.add_argument("--label", default="", help="rapordaki aşama adına ek (ör. önce/sonra)")
    a = p.parse_args()
    if a.db.startswith("metis_") or a.db == "metis":
        sys.exit("Kurulu METIS'in adlarına dokunulmaz: --db başka bir ad olmalı.")
    data_dir = Path(tempfile.gettempdir()) / f"metis-scale-{a.db}"
    data_dir.mkdir(parents=True, exist_ok=True)
    fresh = _ensure_db(a.admin_dsn, a.db, a.reset)
    url = _env(a.admin_dsn, a.db, data_dir)
    from alembic import command

    from metis.cli import _alembic_config

    if not a.no_migrate:
        command.upgrade(_alembic_config(url), "head")
    from metis.core import security

    security.SCRYPT_N = 2**10  # yalnız bu deneme: giriş hızı (ölçülen değil)
    api = Api()
    pid = _setup(api, fresh)
    needles = _needles(api, pid)
    report_path = Path(a.out)
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() and not a.reset else {"stages": {}}
    report["machine"] = {"cpu_count": os.cpu_count(), "platform": sys.platform}
    generated = int(report.get("generated", 0))
    for target in [int(s) for s in a.stages.split(",")]:
        print(f"==> aşama {target} sayfa", flush=True)
        generated, load = _load(api, pid, target, generated)
        report["generated"] = generated
        stage: dict = {"load": load}
        if a.embed and (a.embed_each_stage or target == int(a.stages.split(",")[-1])):
            stage["embed"] = _embed(a.embed)
        stage.update(_measure(api, pid, needles, url, a.scan_timeout))
        report["stages"][f"{target}{a.label}"] = stage
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(json.dumps({k: v for k, v in stage.items() if k not in ("tables_mb",)}, ensure_ascii=False, default=str)[:3000], flush=True)


if __name__ == "__main__":
    main()
