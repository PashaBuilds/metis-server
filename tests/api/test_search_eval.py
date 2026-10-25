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
    pid = team["pid"]
    body = {"question": "PCIe neden Gen1'de?", "expected_page_ids": [], "expected_quote": "", "kind": "issue"}
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
    with capsys.disabled():
        print("\nARAMA ÖLÇÜMÜ", json.dumps({k: v for k, v in m.items() if k != "by_kind"}, ensure_ascii=False))
        print("TÜR", json.dumps(m["by_kind"], ensure_ascii=False))
        print("KAÇAN", [r["question"] for r in res.per_question if not r["rank"] or r["rank"] > 5])
