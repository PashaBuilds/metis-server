"""Arama ölçümü (İş 2): METIS içinde soru seti ve koşu; kurgusal derlemle taban çizgisi. Deterministik, modelsiz."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from metis.core.db import transaction
from metis.core.models import User
from metis.modules.search.evaluate import EvalQuestion, evaluate
from tests.retrieval_kit import corpus_questions, publish_corpus

A, B, C, D = (uuid.UUID(int=i) for i in range(1, 5))


def fake_search(ranking: dict[str, list[uuid.UUID]]):  # noqa: ANN201
    def run(db, user, project_id, q, scope=None, kind=None, limit=20):  # noqa: ANN001, ANN202
        return SimpleNamespace(hits=[SimpleNamespace(page_id=p, passage_text="") for p in ranking[q][:limit]])

    return run


def test_eval_metrics_math():
    qs = [
        EvalQuestion(id="1", question="a", expected_page_ids=[A], expected_quote="", kind="kavram"),
        EvalQuestion(id="2", question="b", expected_page_ids=[C], expected_quote="", kind="kavram"),
        EvalQuestion(id="3", question="c", expected_page_ids=[A, B], expected_quote="", kind="issue"),
        EvalQuestion(id="4", question="d", expected_page_ids=[D], expected_quote="", kind="issue"),
    ]
    ranking = {"a": [A, B], "b": [B, D, A, C], "c": [B, C, A], "d": [A, B, C]}
    res = evaluate(None, None, None, qs, search_fn=fake_search(ranking))
    m = res.metrics
    assert m["n"] == 4
    assert m["recall_at_5"] == pytest.approx(0.75) and m["recall_at_10"] == pytest.approx(0.75)
    assert m["mrr"] == pytest.approx((1 + 1 / 4 + 1 + 0) / 4)
    # c: ilgili B (1. sıra), A (3. sıra) → DCG 1 + 1/log2(4) = 1.5; IDCG 1 + 1/log2(3)
    import math

    ndcg_c = 1.5 / (1 + 1 / math.log2(3))
    assert m["ndcg_at_10"] == pytest.approx((1 + 1 / math.log2(5) + ndcg_c + 0) / 4)
    assert m["quote_at_5"] is None  # beklenen alıntı yok
    assert m["by_kind"]["issue"]["n"] == 2 and m["by_kind"]["issue"]["recall_at_5"] == pytest.approx(0.5)
    assert [r["rank"] for r in res.per_question] == [1, 4, 1, None]


def test_eval_api_roles(team):  # noqa: ANN001
    from tests.api.test_search_blocks import _publish

    pid = team["pid"]
    assert team["admin"].patch(f"/api/v1/projects/{pid}", json={"review_policy": "self_publish"}).status_code == 200
    page = _publish(team["contributor"], pid, "PCIe notu", "Bağlantı Gen1'de kalırsa SSC kapatılır.")
    body = {"question": "PCIe neden Gen1'de?", "expected_page_ids": [page], "expected_quote": "", "kind": "issue"}
    assert team["reader"].post(f"/api/v1/projects/{pid}/search-eval/questions", json=body).status_code == 403
    assert team["contributor"].post(f"/api/v1/projects/{pid}/search-eval/questions", json=body).status_code == 403
    r = team["admin"].post(f"/api/v1/projects/{pid}/search-eval/questions", json=body)
    assert r.status_code == 201, r.text
    qid = r.json()["id"]
    assert [q["id"] for q in team["admin"].get(f"/api/v1/projects/{pid}/search-eval/questions").json()] == [qid]
    run = team["admin"].post(f"/api/v1/projects/{pid}/search-eval/runs", json={"note": "ilk"})
    assert run.status_code == 201, run.text
    assert run.json()["metrics"]["n"] == 1 and run.json()["note"] == "ilk"
    assert [x["id"] for x in team["admin"].get(f"/api/v1/projects/{pid}/search-eval/runs").json()] == [run.json()["id"]]
    assert team["admin"].delete(f"/api/v1/projects/{pid}/search-eval/questions/{qid}").status_code == 204
    assert team["admin"].get(f"/api/v1/projects/{pid}/search-eval/questions").json() == []


def test_corpus_baseline(team, capsys):  # noqa: ANN001
    pid = team["pid"]
    assert team["admin"].patch(f"/api/v1/projects/{pid}", json={"review_policy": "self_publish"}).status_code == 200
    pages = publish_corpus(team["contributor"], pid)
    with transaction() as db:
        user = db.get(User, uuid.UUID(team["reader"].user["id"]))
        res = evaluate(db, user, uuid.UUID(pid), corpus_questions(pages))
    m = res.metrics
    assert m["n"] == 44 and set(m) >= {"recall_at_5", "recall_at_10", "mrr", "ndcg_at_10", "quote_at_5", "by_kind"}
    assert m["quote_at_5"] is not None and m["recall_at_5"] >= 0.95  # blok bilgisi var; taban çizgisinden düşmez
    from evals.retrieval.corpus import NEGATIVE

    from metis.modules.search.service import search

    with transaction() as db:
        user = db.get(User, uuid.UUID(team["reader"].user["id"]))
        false_hits = {q: [h.title for h in search(db, user, uuid.UUID(pid), q, dense=False).hits] for q in NEGATIVE}
    with capsys.disabled():  # CI konsolu cp1252 olabilir: yalnız ASCII yazılır
        print("\nSEARCH-EVAL", json.dumps({k: v for k, v in m.items() if k != "by_kind"}))
        print("BY-KIND", json.dumps(m["by_kind"]))
        print("MISSED", json.dumps([r["question"] for r in res.per_question if not r["rank"] or r["rank"] > 5]))
        print("NEGATIVE-LEXICAL", json.dumps({q: v for q, v in false_hits.items() if v}))
    # Konu dışı soruda sık sözcükler ("yapılır", "var", "is") tek başına isabet üretmez (Mentor'un "kanıt yok"u korunur).
    assert {q: v for q, v in false_hits.items() if v} == {}


def test_quote_miss_counts_when_blocks_supported():
    qs = [EvalQuestion(id="1", question="a", expected_page_ids=[A], expected_quote="beklenen metin", kind="kavram")]

    def run(db, user, project_id, q, scope=None, kind=None, limit=20):  # noqa: ANN001, ANN202
        return SimpleNamespace(hits=[SimpleNamespace(page_id=A, passage_text=None)])  # yalnız başlıkla bulundu

    assert evaluate(None, None, None, qs, search_fn=run).metrics["quote_at_5"] == 0


def test_question_needs_expected_page(team):  # noqa: ANN001
    body = {"question": "Boş beklenti", "expected_page_ids": [], "expected_quote": "", "kind": "kavram"}
    assert team["admin"].post(f"/api/v1/projects/{team['pid']}/search-eval/questions", json=body).status_code == 422


@pytest.mark.skipif(not __import__("os").getenv("METIS_TEST_EMBEDDING_MODEL_DIR"), reason="gerçek model dizini verilmedi")
def test_corpus_hybrid_real_model(team, capsys, monkeypatch):  # noqa: ANN001
    """Yerelde gerçek gömme modeliyle hibrit ölçüm (CI'da model yok, atlanır)."""
    import os

    from metis.modules.search import embedding
    from metis.modules.search.vectors import embed_missing, reset_cache

    monkeypatch.setenv("METIS_EMBEDDING_MODEL_DIR", os.environ["METIS_TEST_EMBEDDING_MODEL_DIR"])
    embedding.reset()
    reset_cache()
    pid = team["pid"]
    assert team["admin"].patch(f"/api/v1/projects/{pid}", json={"review_policy": "self_publish"}).status_code == 200
    pages = publish_corpus(team["contributor"], pid)
    while True:
        with transaction() as db:
            if not embed_missing(db, limit=64):
                break
    with transaction() as db:
        user = db.get(User, uuid.UUID(team["reader"].user["id"]))
        res = evaluate(db, user, uuid.UUID(pid), corpus_questions(pages))
    from evals.retrieval.corpus import NEGATIVE

    from metis.modules.search.service import search

    with transaction() as db:
        user = db.get(User, uuid.UUID(team["reader"].user["id"]))
        false_hits = {q: [h.title for h in search(db, user, uuid.UUID(pid), q).hits] for q in NEGATIVE}
        lexical_hits = {q: [h.title for h in search(db, user, uuid.UUID(pid), q, dense=False).hits] for q in NEGATIVE}
    with capsys.disabled():
        print("NEGATIVE-LEXICAL", json.dumps({q: v for q, v in lexical_hits.items() if v}))
    embedding.reset()
    reset_cache()
    m = res.metrics
    with capsys.disabled():
        print("NEGATIVE-HITS", json.dumps({q: v for q, v in false_hits.items() if v}))
        print("\nHYBRID-EVAL", json.dumps({k: v for k, v in m.items() if k != "by_kind"}))
        print("BY-KIND", json.dumps(m["by_kind"]))
        print("MISSED", json.dumps([r["question"] for r in res.per_question if not r["rank"] or r["rank"] > 5]))
    assert m["recall_at_5"] >= 0.95
    assert false_hits == lexical_hits  # vektör kanalı konu dışı soruda yanlış isabet eklemez (eşikler)
