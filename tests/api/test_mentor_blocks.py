"""Mentor ve bloklar (İş 2): uzun sayfanın ilgili blokları pakete girer; model yokken ilgili yayımlanmış bölümler."""

from __future__ import annotations

from metis.modules.mentor.service import select_blocks
from tests.retrieval_kit import publish_corpus


def _rows(n: int, headings: dict[int, str]) -> list[dict]:
    return [{"claim_id": f"c{i}", "ord": i, "statement": headings.get(i, f"paragraf {i}")} for i in range(n)]


def test_select_blocks_keeps_neighbours_and_heading():
    rows = _rows(20, {0: "## A", 10: "## B"})
    assert [r["ord"] for r in select_blocks(rows, ["c14"])] == [10, 13, 14, 15]
    assert [r["ord"] for r in select_blocks(rows, ["c3", "c14"])] == [0, 2, 3, 4, 10, 13, 14, 15]
    assert [r["ord"] for r in select_blocks(rows, [])] == list(range(8))  # blok sıralaması yoksa ilk 8
    short = _rows(6, {})
    assert select_blocks(short, ["c5"]) == short  # kısa sayfa olduğu gibi


def test_model_unavailable_returns_related_passages(team):  # noqa: ANN001
    pid = team["pid"]
    assert team["admin"].patch(f"/api/v1/projects/{pid}", json={"review_policy": "self_publish"}).status_code == 200
    pages = publish_corpus(team["contributor"], pid)
    r = team["reader"].post(f"/api/v1/projects/{pid}/mentor/answers", json={"question": "PERST# ne kadar süre tutulur?"})
    assert r.status_code == 200, r.text
    ans = r.json()
    assert ans["decision"] == "MODEL_UNAVAILABLE" and ans["citations"] == [] and ans["explanation"] == []
    passages = ans["related_passages"]
    assert 1 <= len(passages) <= 5
    first = passages[0]
    assert first["page_id"] == pages["pcie-bringup"] and first["heading_path"] == "Saat ve sıfırlama" and "PERST#" in first["text"]
    again = team["reader"].get(f"/api/v1/answers/{ans['id']}").json()
    assert again["related_passages"] == passages
