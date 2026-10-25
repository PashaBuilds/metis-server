"""Blok puanlamalı arama (İş 2): uzun sayfada doğru bölüm, ASCII yazımla Türkçe eşleşme, en iyi bloklar."""

from __future__ import annotations

import pytest

from tests.retrieval_kit import publish_corpus


@pytest.fixture
def corpus(team):  # noqa: ANN001, ANN201
    pid = team["pid"]
    assert team["admin"].patch(f"/api/v1/projects/{pid}", json={"review_policy": "self_publish"}).status_code == 200
    return {**team, "pages": publish_corpus(team["contributor"], pid)}


def _search(c, pid: str, q: str) -> list[dict]:  # noqa: ANN001
    r = c.get(f"/api/v1/projects/{pid}/search", params={"q": q})
    assert r.status_code == 200, r.text
    return r.json()["hits"]


def test_long_page_section_found(corpus):  # noqa: ANN001
    hits = _search(corpus["reader"], corpus["pid"], "PERST# ne kadar süre tutulur")
    top = [h["page_id"] for h in hits[:3]]
    assert corpus["pages"]["pcie-bringup"] in top
    hit = next(h for h in hits if h["page_id"] == corpus["pages"]["pcie-bringup"])
    assert "PERST#" in hit["passage_text"] and hit["heading_path"] == "Saat ve sıfırlama"
    assert len(hit["best_claims"]) >= 1


def test_ascii_query_matches_turkish(corpus):  # noqa: ANN001
    hits = _search(corpus["reader"], corpus["pid"], "kaynagi secilir")
    assert corpus["pages"]["clock-tree"] in [h["page_id"] for h in hits[:3]]


def test_symbol_block_ranks_first(corpus):  # noqa: ANN001
    hits = _search(corpus["reader"], corpus["pid"], "wdt_pause")
    assert hits[0]["page_id"] in (corpus["pages"]["power-mgmt"], corpus["pages"]["issue-wdt-reset"])
    assert "wdt_pause" in hits[0]["passage_text"]
