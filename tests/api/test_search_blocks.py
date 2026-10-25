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


def _publish(c, pid: str, title: str, body: str, **kw) -> str:  # noqa: ANN001, ANN003
    from tests.kb import DEFAULT_SCOPE

    item = {"note": True, "title": title, "summary": "", "body_md": body, "scope": DEFAULT_SCOPE, **kw}
    ch = c.post(f"/api/v1/projects/{pid}/changes", json={"summary": title, "items": [item]}).json()
    assert c.post(f"/api/v1/changes/{ch['id']}/check").status_code == 200
    ch = c.get(f"/api/v1/changes/{ch['id']}").json()
    r = c.post(f"/api/v1/changes/{ch['id']}/publish-direct", json={"hash": ch["hash"], "acknowledge_issues": True})
    assert r.status_code == 200, r.text
    return r.json()["published_page_ids"][0]


def test_dotted_capital_query(corpus):  # noqa: ANN001
    page = _publish(corpus["contributor"], corpus["pid"], "Kurgusal kuyruk", "Gelen istekler kuyrukta bekler.")
    for q in ("İstek", "İSTEKLER", "istek"):
        assert page in [h["page_id"] for h in _search(corpus["reader"], corpus["pid"], q)[:3]], q


def test_best_block_is_not_a_heading(corpus):  # noqa: ANN001
    hits = _search(corpus["reader"], corpus["pid"], "Saat ve sıfırlama")
    hit = next(h for h in hits if h["page_id"] == corpus["pages"]["pcie-bringup"])
    assert not hit["passage_text"].startswith("#") and "PERST#" in hit["passage_text"]


def test_summary_and_multiword_alias_still_found(corpus):  # noqa: ANN001
    page = _publish(
        corpus["contributor"], corpus["pid"], "Kurgusal ölçüm kaydı", "Ölçüm düzeneği hazırlandı.",
        summary="Zebrafis ölçeğiyle yapılan deneme.", aliases=["kurgu tezgahı"],
    )  # fmt: skip
    assert page in [h["page_id"] for h in _search(corpus["reader"], corpus["pid"], "zebrafis")]
    assert page in [h["page_id"] for h in _search(corpus["reader"], corpus["pid"], "kurgu tezgahı")]


def test_long_question_keeps_symbol_hit_and_drops_single_common_word(corpus):  # noqa: ANN001
    """Doğal dil sorusunda (4+ içerik sözcüğü) tek sık sözcükle eşleşen sayfa düşer; tanımlayıcı isabeti kalır."""
    page = _publish(corpus["contributor"], corpus["pid"], "Kurgusal saat seçimi", "Saat kaynağı `KURGU_SAAT_SEL` yazmacıyla seçilir.")
    hits = [h["page_id"] for h in _search(corpus["reader"], corpus["pid"], "kart açılırken KURGU_SAAT_SEL hangi değeri alır acaba")]
    assert page in hits
    assert _search(corpus["reader"], corpus["pid"], "uzay aracı yakıtı nasıl seçilir bilmiyorum") == []
