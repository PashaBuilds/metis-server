"""Mentor yeniden sıralayıcısı (2.0.26): aramanın adayları soruyla birlikte okunup yeniden sıralanır; sıra kanıt değildir.

Gerçek model gerektirmeyen testler sahte bir sıralayıcıyla (puan = adayın arama sırasının tersi) davranışı sınar.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from metis.modules.mentor import schemas
from metis.modules.mentor.service import ask
from metis.modules.search import rerank
from tests.retrieval_kit import publish_corpus

# Kurgusal derlemde birden çok sayfanın eşleştiği genel soru (vektörsüz test ortamında da birkaç aday).
QUESTION = "saat ve sıfırlama ayarı"


class Reverse:
    model_id = "kurgu-siralayici"

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []
        self.texts: list[str] = []

    def scores(self, query: str, texts: list[str]) -> list[float]:
        self.calls.append((query, len(texts)))
        self.texts = list(texts)
        return [i / len(texts) for i in range(len(texts))]  # son aday en yüksek


@pytest.fixture(autouse=True)
def _fresh():  # noqa: ANN202
    rerank.reset()
    yield
    rerank.reset()


def _ask(team) -> tuple[schemas.AnswerOut, list[tuple[str, dict]]]:  # noqa: ANN001
    events: list[tuple[str, dict]] = []
    out = ask(uuid.UUID(team["reader"].user["id"]), uuid.UUID(team["pid"]), schemas.AskIn(question=QUESTION), emit=lambda e, d: events.append((e, d)))
    return out, events


def test_mentor_reorders_candidates_with_reranker(team, monkeypatch):  # noqa: ANN001
    pid = team["pid"]
    assert team["admin"].patch(f"/api/v1/projects/{pid}", json={"review_policy": "self_publish"}).status_code == 200
    publish_corpus(team["contributor"], pid)
    monkeypatch.setenv("METIS_RERANKER_MODEL_DIR", str(Path(team["pid"]) / "yok"))
    plain, plain_events = _ask(team)
    assert not [d for e, d in plain_events if e == "progress" and d.get("step") == "ranking"]
    assert plain.timings.get("rerank_ms") is None
    assert len(plain.related) >= 2

    fake = Reverse()
    monkeypatch.setattr(rerank, "get_reranker", lambda wait=True: fake)
    out, events = _ask(team)
    assert fake.calls and fake.calls[0][0] == QUESTION and fake.calls[0][1] <= rerank.CANDIDATES
    ranking = [d for e, d in events if e == "progress" and d.get("step") == "ranking"]
    assert ranking and ranking[0]["candidates"] == fake.calls[0][1]
    # Aday metni "başlık — bölüm başlığı — metin"; sahte puan son adayı başa alır: cevap sayfaları bu sırayı izler.
    expected = [t.split(" — ")[0] for t in reversed(fake.texts)]
    got = [r.title for r in out.related]
    idx = [expected.index(t) for t in got]
    assert idx == sorted(idx) and got != [r.title for r in plain.related]
    rel_ids = [str(r.page_id) for r in out.related]
    pos = [rel_ids.index(str(p.page_id)) for p in out.related_passages]
    assert pos and pos == sorted(pos)  # model yokken gösterilen bölümler de yeni sırada
    assert out.timings["rerank_ms"] is not None and out.decision == "MODEL_UNAVAILABLE"


def test_reranker_failure_falls_back_to_search_order(team, monkeypatch):  # noqa: ANN001
    pid = team["pid"]
    assert team["admin"].patch(f"/api/v1/projects/{pid}", json={"review_policy": "self_publish"}).status_code == 200
    publish_corpus(team["contributor"], pid)
    monkeypatch.setenv("METIS_RERANKER_MODEL_DIR", str(Path(team["pid"]) / "yok"))
    plain, _ = _ask(team)

    class Broken:
        model_id = "bozuk"

        def scores(self, query: str, texts: list[str]) -> list[float]:
            raise RuntimeError("onnx hatası")

    monkeypatch.setattr(rerank, "get_reranker", lambda wait=True: Broken())
    out, _ = _ask(team)
    assert [r.page_id for r in out.related] == [r.page_id for r in plain.related]
    assert out.timings.get("rerank_ms") is None and out.timings.get("rerank_error") == "RuntimeError"


def test_budget_stops_scoring_and_keeps_search_order_for_the_rest(monkeypatch):  # noqa: ANN001
    """Uzun bölümlerde 30 aday işlemcide 8–12 sn sürebilir: bütçe dolunca kalan adaylar arama sırasında kalır."""
    import time

    class Slow:
        model_id = "yavas"

        def __init__(self) -> None:
            self.batches: list[int] = []

        def scores(self, query: str, texts: list[str]) -> list[float]:
            self.batches.append(len(texts))
            time.sleep(0.04)
            return [i / len(texts) for i in range(len(texts))]

    monkeypatch.setattr(rerank, "BUDGET_S", 0.05)
    slow = Slow()
    order, scored = rerank.order(slow, "soru", [f"aday {i}" for i in range(30)])
    assert slow.batches == [rerank.BATCH] and scored == rerank.BATCH
    assert order == list(reversed(range(rerank.BATCH))) + list(range(rerank.BATCH, 30))
    monkeypatch.setattr(rerank, "BUDGET_S", 60.0)
    fast = Reverse()
    order, scored = rerank.order(fast, "soru", [f"aday {i}" for i in range(30)])
    assert scored == 30 and order[0] == rerank.BATCH - 1  # parti içi puanlar: her partinin son adayı en yüksek


def test_absent_and_wrong_kind_reranker(tmp_path: Path, monkeypatch):  # noqa: ANN001
    monkeypatch.setenv("METIS_RERANKER_MODEL_DIR", str(tmp_path / "yok"))
    assert rerank.reranker_status()["state"] == "absent" and rerank.get_reranker() is None
    rerank.reset()
    (tmp_path / "MODEL.json").write_text('{"id": "kurgu", "kind": "embedding"}', encoding="utf-8")
    monkeypatch.setenv("METIS_RERANKER_MODEL_DIR", str(tmp_path))
    st = rerank.reranker_status()
    assert st["state"] == "error" and "reranker" in st["reason"]


def test_model_loads_in_background_without_blocking_mentor_or_status(tmp_path: Path, monkeypatch):  # noqa: ANN001
    """İlk soru ve Sistem durumu modeli (≈ 0,6 GB, birkaç sn) beklemez: yükleme arka planda; o sırada Mentor arama sırasıyla."""
    (tmp_path / "onnx").mkdir()
    (tmp_path / "onnx" / "model_quantized.onnx").write_bytes(b"bozuk")
    (tmp_path / "tokenizer.json").write_text("{}", encoding="utf-8")
    (tmp_path / "MODEL.json").write_text('{"id": "kurgu", "kind": "reranker"}', encoding="utf-8")
    monkeypatch.setenv("METIS_RERANKER_MODEL_DIR", str(tmp_path))
    assert rerank.get_reranker(wait=False) is None  # yüklenmemiş: beklemeden None, yükleme arka planda başlar
    assert rerank.reranker_status(load=False)["state"] in ("loading", "error")
    rerank.join_loader(30)
    st = rerank.reranker_status(load=False)
    assert st["state"] == "error" and st["reason"]
    assert rerank.get_reranker(wait=False) is None


def test_status_without_model_does_not_start_loading(tmp_path: Path, monkeypatch):  # noqa: ANN001
    monkeypatch.setenv("METIS_RERANKER_MODEL_DIR", str(tmp_path / "yok"))
    assert rerank.reranker_status(load=False)["state"] == "absent"
    assert rerank.get_reranker(wait=False) is None


@pytest.mark.skipif(not os.getenv("METIS_TEST_RERANKER_MODEL_DIR"), reason="gerçek sıralayıcı dizini verilmedi")
def test_real_reranker_prefers_the_answering_passage(monkeypatch):  # noqa: ANN001
    monkeypatch.setenv("METIS_RERANKER_MODEL_DIR", os.environ["METIS_TEST_RERANKER_MODEL_DIR"])
    rr = rerank.get_reranker()
    assert rr is not None and rerank.reranker_status()["state"] == "ready"
    texts = ["DDR test prosedürü (VPK120) — Genel", "DDR eğitimi başarısız olursa iki kez daha denenir, sonra hata kaydı yazılır.", "Kahve makinesi haftada bir temizlenir."]
    assert rerank.order(rr, "DDR eğitimi kaç kez denenir?", texts) == ([1, 0, 2], 3)
