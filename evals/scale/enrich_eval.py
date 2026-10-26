"""Model zenginleştirmesinin arama kalitesine katkısı, gerçek modelle (kurgusal derlem; gerçek şirket içeriği değildir).

    set DEEPSEEK_API_KEY=...   (anahtar ortamdan okunur; yazdırılmaz, dosyaya yazılmaz)
    python -m evals.scale.enrich_eval --base-url https://api.deepseek.com/v1 --model deepseek-flash \
        --distractors 300 --embed MODEL_DIR --out evals/reports/enrich-deepseek-flash.json

Ayrı veritabanına (`--db`, varsayılan metisenrich) ölçüm derlemini ve aynı alandan kurgusal rakip sayfaları yayımlar;
modeli Lab akışıyla (probe + ortak benchmark) yeterli kılar; zenginleştirmeden önce ve sonra ölçüm sorularını (kelime ve
hibrit; kartsız ve kart süzgeçli) koşar. Zenginleştirme kanıt değildir; yalnız aramaya etkisi ölçülür.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path


def _quality(pid: str, pages: dict[str, str], dense_ready: bool) -> dict:
    from sqlalchemy import text
    from tests.retrieval_kit import corpus_questions

    from evals.retrieval.corpus import NEGATIVE
    from metis.core.db import transaction
    from metis.core.models import User
    from metis.modules.search import vectors
    from metis.modules.search.evaluate import evaluate
    from metis.modules.search.service import search

    out = {}
    modes = [("lexical", False, None), ("lexical_kart", False, {"kart": ["VPK120"]})]
    if dense_ready:
        modes += [("hybrid", True, None), ("hybrid_kart", True, {"kart": ["VPK120"]})]
    with transaction() as db:
        user = db.get(User, db.scalar(text("SELECT id FROM users WHERE username = 'ayse'")))
        for mode, dense, flt in modes:
            vectors.reset_cache()

            def run(db, user, project_id, q, scope=None, kind=None, limit=20, _d=dense, _f=flt):  # noqa: ANN001, ANN202
                return search(db, user, project_id, q, _f, kind, limit, dense=_d)

            res = evaluate(db, user, uuid.UUID(pid), corpus_questions(pages), search_fn=run)
            neg = {q: len(r.hits) for q in NEGATIVE if (r := search(db, user, uuid.UUID(pid), q, flt, dense=dense)).hits}
            out[mode] = {
                "metrics": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in res.metrics.items() if k != "by_kind"},
                "by_kind": res.metrics.get("by_kind"),
                "negative_with_hits": neg,
                "per_question_rank": {r["question"]: r["rank"] for r in res.per_question},
            }
    return out


def main() -> None:
    from evals.scale import run as base

    p = argparse.ArgumentParser()
    p.add_argument("--admin-dsn", default=os.environ.get("METIS_TEST_ADMIN_DSN", "postgresql://metisdev:metis-dev@127.0.0.1:5432/postgres"))
    p.add_argument("--db", default="metisenrich")
    p.add_argument("--base-url", default="https://api.deepseek.com/v1")
    p.add_argument("--model", default="deepseek-flash")
    p.add_argument("--key-env", default="DEEPSEEK_API_KEY")
    p.add_argument("--distractors", type=int, default=300)
    p.add_argument("--embed", default="")
    p.add_argument("--reset", action="store_true")
    p.add_argument("--out", default="evals/reports/enrich-deepseek-flash.json")
    a = p.parse_args()
    key = os.environ.get(a.key_env, "")
    if not key:
        sys.exit(f"{a.key_env} ortam değişkeni yok.")
    if a.db.startswith("metis_") or a.db == "metis":
        sys.exit("Kurulu METIS'in adlarına dokunulmaz.")
    os.environ["METIS_ENDPOINT_ALLOWLIST"] = a.base_url
    # Bu deneme internetteki sağlayıcıya gider (sunucuda şirket ağı); yalnız bu süreçte genel adreslere izin verilir.
    os.environ["METIS_ENDPOINT_NETWORKS"] = "0.0.0.0/0,::/0"
    data_dir = Path(tempfile.gettempdir()) / f"metis-scale-{a.db}"
    data_dir.mkdir(parents=True, exist_ok=True)
    fresh = base._ensure_db(a.admin_dsn, a.db, a.reset)
    url = base._env(a.admin_dsn, a.db, data_dir)
    from alembic import command

    from metis.cli import _alembic_config

    command.upgrade(_alembic_config(url), "head")
    from metis.core import security

    security.SCRYPT_N = 2**10
    api = base.Api()
    pid = base._setup(api, fresh)
    needles = base._needles(api, pid)
    api.ok("PATCH", f"/api/v1/projects/{pid}", json={"enrichment_enabled": False})  # önce zenginleştirmesiz ölçüm
    if fresh:
        base._load(api, pid, len(needles) + a.distractors, 0)
    report: dict = {"model": a.model, "base_url": a.base_url, "distractors": a.distractors, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if a.embed:
        report["embed_before"] = base._embed(a.embed)
    report["before"] = _quality(pid, needles, bool(a.embed))

    # Model: Lab akışı (sağlayıcı → probe → ortak benchmark), sonra zenginleştirme
    from tests.llm_helpers import model_id, qualify

    prov = api.ok("POST", "/api/v1/providers", expect=201, json={"name": "Deneme sağlayıcı", "base_url": a.base_url, "api_key": key, "model_ids": [a.model], "timeout_s": 120, "max_concurrency": 2})
    mid = model_id(a.model, prov["id"])
    shim = base.api_client_shim_full(api)
    t = time.perf_counter()
    report["qualification"] = qualify(shim, mid)
    report["qualification_s"] = round(time.perf_counter() - t, 1)
    from metis.core.db import transaction
    from metis.core.models import Project
    from metis.modules.lab.service import route

    with transaction() as db:
        model, reasons = route(db, db.get(Project, uuid.UUID(pid)))
        report["route"] = {"model": model.display_name if model else None, "reasons": reasons}
    if model is None:
        Path(a.out).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        sys.exit("Model yönlendirmeye uygun değil; zenginleştirme ölçülemedi (rapora bakın).")
    api.ok("PATCH", f"/api/v1/projects/{pid}", json={"enrichment_enabled": True})
    from metis.modules.search.enrichment import enrich_next, enrichment_status

    t = time.perf_counter()
    calls, blocks, waits = 0, 0, 0
    while True:
        n = enrich_next()
        if n == 0:
            break
        if n < 0:
            waits += 1
            if waits > 30:
                break
            time.sleep(10)
            continue
        calls += 1
        blocks += n
        if calls % 20 == 0:
            print(f"  … {calls} çağrı, {blocks} blok, {time.perf_counter() - t:.0f} sn", flush=True)
    report["enrichment"] = {**enrichment_status(), "calls": calls, "wall_s": round(time.perf_counter() - t, 1), "transient_waits": waits}
    with transaction() as db:
        from sqlalchemy import text

        report["model_calls"] = [dict(r._mapping) for r in db.execute(text(
            """SELECT purpose, state, count(*) AS n,
                      percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) AS p50_ms,
                      percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_ms,
                      sum((usage->>'prompt_tokens')::int) AS prompt_tokens,
                      sum((usage->>'completion_tokens')::int) AS completion_tokens
               FROM model_calls GROUP BY purpose, state"""))]
        report["samples"] = [dict(r._mapping) for r in db.execute(text(
            """SELECT sp.heading_path, left(sp.body, 160) AS body, pe.context, pe.questions, pe.status
               FROM passage_enrichments pe JOIN search_passages sp ON sp.base_sha256 = pe.base_sha256
               JOIN search_documents d ON d.page_id = sp.page_id WHERE d.title NOT LIKE '%#%' ORDER BY sp.id LIMIT 12"""))]
    if a.embed:
        report["embed_after"] = base._embed(a.embed)
    report["after"] = _quality(pid, needles, bool(a.embed))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    for mode in report["after"]:
        b, c = report["before"][mode]["metrics"], report["after"][mode]["metrics"]
        print(mode, {k: (b[k], c[k]) for k in ("recall_at_5", "mrr", "ndcg_at_10", "quote_at_5")}, flush=True)


if __name__ == "__main__":
    main()
