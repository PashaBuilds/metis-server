"""Arama ölçümü: soru seti üzerinde deterministik metrikler (modelsiz). Tasarım bölüm 5.3.

Sayfa düzeyi: recall@5, recall@10, MRR, nDCG@10 (ikili ilgi, birden çok beklenen sayfa olabilir).
Alıntı düzeyi: `quote_at_5` — ilk 5 sonucun en iyi bloğunda beklenen alıntı birebir geçiyor mu. Arama blok bilgisi
vermiyorsa ya da hiçbir soruda beklenen alıntı yoksa `None` ("ölçülmedi").
"""

from __future__ import annotations

import math
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from metis.modules.search.service import search

MAX_QUESTIONS = 500


@dataclass
class EvalQuestion:
    id: str
    question: str
    expected_page_ids: list[uuid.UUID]
    expected_quote: str = ""
    kind: str = "kavram"


@dataclass
class EvalResult:
    metrics: dict
    per_question: list[dict] = field(default_factory=list)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _summary(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0, "recall_at_5": None, "recall_at_10": None, "mrr": None, "ndcg_at_10": None, "quote_at_5": None}
    quotes = [r["quote_hit"] for r in rows if r["quote_hit"] is not None]
    return {
        "n": n,
        "recall_at_5": sum(1 for r in rows if r["rank"] and r["rank"] <= 5) / n,
        "recall_at_10": sum(1 for r in rows if r["rank"] and r["rank"] <= 10) / n,
        "mrr": sum(1 / r["rank"] for r in rows if r["rank"]) / n,
        "ndcg_at_10": sum(r["ndcg"] for r in rows) / n,
        "quote_at_5": (sum(quotes) / len(quotes)) if quotes else None,
    }


def evaluate(db, user, project_id, questions: list[EvalQuestion], search_fn: Callable = search) -> EvalResult:  # noqa: ANN001
    rows = []
    for q in questions[:MAX_QUESTIONS]:
        hits = search_fn(db, user, project_id, q.question, None, None, 10).hits
        expected = set(q.expected_page_ids)
        ranks = [i + 1 for i, h in enumerate(hits) if h.page_id in expected]
        dcg = sum(1 / math.log2(r + 1) for r in ranks)
        idcg = sum(1 / math.log2(i + 2) for i in range(min(len(expected), 10)))
        quote_hit: int | None = None
        if q.expected_quote:
            if hits and not hasattr(hits[0], "passage_text"):
                quote_hit = None  # arama blok bilgisi vermiyor: ölçülmedi
            else:  # blok bilgisi var: ilk 5'te yoksa (ya da yalnız başlıkla bulunduysa) ıska sayılır
                passages = [getattr(h, "passage_text", None) for h in hits[:5]]
                quote_hit = int(any(p and _norm(q.expected_quote) in _norm(p) for p in passages))
        rows.append(
            {
                "id": q.id,
                "question": q.question,
                "kind": q.kind,
                "rank": ranks[0] if ranks else None,
                "ndcg": dcg / idcg if idcg else 0.0,
                "quote_hit": quote_hit,
                "top": [str(h.page_id) for h in hits[:5]],
            }
        )
    metrics = _summary(rows)
    metrics["by_kind"] = {k: _summary([r for r in rows if r["kind"] == k]) for k in sorted({r["kind"] for r in rows})}
    return EvalResult(metrics=metrics, per_question=rows)
