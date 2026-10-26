"""Hibrit arama (İş 3): kelime + vektör RRF; sembol isabeti üstte; erişim ve yayın sınırları vektörde de geçerli."""

from __future__ import annotations

import uuid

import pytest

from metis.core.db import transaction
from metis.modules.search import embedding
from metis.modules.search.vectors import embed_missing, reset_cache
from tests.api.test_search_blocks import _publish
from tests.retrieval_kit import publish_corpus
from tests.vector_kit import FakeEmbedder

# Sahte gömme diller arası eşleşmeyi taklit eder: İngilizce sözcükler Türkçe karşılıklarıyla aynı kovaya düşer.
SYN = {"busy": "mesgul", "wait": "bekleme", "loops": "dongusu", "loop": "dongusu"}


def _embed_all() -> None:
    while True:
        with transaction() as db:
            if not embed_missing(db, limit=100):
                return


@pytest.fixture
def hybrid(team):  # noqa: ANN001, ANN201
    embedding.use_for_tests(FakeEmbedder(SYN))
    reset_cache()
    pid = team["pid"]
    assert team["admin"].patch(f"/api/v1/projects/{pid}", json={"review_policy": "self_publish"}).status_code == 200
    pages = publish_corpus(team["contributor"], pid)
    _embed_all()
    yield {**team, "pages": pages}
    embedding.reset()
    reset_cache()


def _search(c, pid: str, q: str) -> dict:  # noqa: ANN001
    r = c.get(f"/api/v1/projects/{pid}/search", params={"q": q})
    assert r.status_code == 200, r.text
    return r.json()


def test_dense_finds_cross_language(hybrid):  # noqa: ANN001
    out = _search(hybrid["reader"], hybrid["pid"], "meşgul bekleme döngüsü kuralı")
    assert out["dense"] == "available"
    assert hybrid["pages"]["coding-std"] in [h["page_id"] for h in out["hits"][:5]]


def test_symbol_still_first(hybrid):  # noqa: ANN001
    out = _search(hybrid["reader"], hybrid["pid"], "wdt_pause")
    assert out["hits"][0]["matched_symbols"] == ["wdt_pause"]


def test_unreadable_not_leaked_by_dense(hybrid):  # noqa: ANN001
    from metis.core.models import Page, SourceAcl

    with transaction() as db:
        page = db.get(Page, uuid.UUID(hybrid["pages"]["coding-std"]))
        db.add(SourceAcl(source_id=page.note_source_id, user_id=uuid.UUID(hybrid["admin"].user["id"])))
    out = _search(hybrid["reader"], hybrid["pid"], "meşgul bekleme döngüsü kuralı")
    assert hybrid["pages"]["coding-std"] not in [h["page_id"] for h in out["hits"]]


def test_withdrawn_page_not_in_dense(hybrid):  # noqa: ANN001
    c, pid, page_id = hybrid["contributor"], hybrid["pid"], hybrid["pages"]["coding-std"]
    detail = c.get(f"/api/v1/pages/{page_id}").json()
    item = {"page_id": page_id, "base_revision_id": detail["published_revision_id"], "action": "withdraw", "note": True, "title": "x"}
    ch = c.post(f"/api/v1/projects/{pid}/changes", json={"summary": "geri çek", "items": [item]}).json()
    assert c.post(f"/api/v1/changes/{ch['id']}/check").status_code == 200
    ch = c.get(f"/api/v1/changes/{ch['id']}").json()
    assert c.post(f"/api/v1/changes/{ch['id']}/publish-direct", json={"hash": ch["hash"], "acknowledge_issues": True}).status_code == 200
    out = _search(hybrid["reader"], pid, "meşgul bekleme döngüsü kuralı")
    assert page_id not in [h["page_id"] for h in out["hits"]]


def test_new_page_without_vectors_is_partial(hybrid):  # noqa: ANN001
    _publish(hybrid["contributor"], hybrid["pid"], "Kurgusal yeni not", "Yeni kurgusal bilgi.")
    assert _search(hybrid["reader"], hybrid["pid"], "kurgusal yeni")["dense"] == "partial"


def test_no_model_is_unavailable(team):  # noqa: ANN001
    embedding.reset()
    reset_cache()
    r = team["reader"].get(f"/api/v1/projects/{team['pid']}/search", params={"q": "PCIe"})
    assert r.status_code == 200 and r.json()["dense"] == "unavailable"


def test_unrelated_query_gets_no_dense_only_hits(hybrid):  # noqa: ANN001
    out = _search(hybrid["reader"], hybrid["pid"], "zürafa kahvaltı tatili")
    assert out["dense"] == "available" and out["hits"] == []
    r = hybrid["reader"].post(f"/api/v1/projects/{hybrid['pid']}/mentor/answers", json={"question": "zürafa kahvaltı tatili"})
    assert r.status_code == 200 and r.json()["decision"] == "NO_EVIDENCE"


def test_dense_only_page_respects_scope(hybrid):  # noqa: ANN001
    r = hybrid["reader"].get(f"/api/v1/projects/{hybrid['pid']}/search", params={"q": "meşgul bekleme döngüsü kuralı", "kart": ["K2"]})
    assert r.status_code == 200 and hybrid["pages"]["coding-std"] not in [h["page_id"] for h in r.json()["hits"]]


def test_republished_page_uses_new_blocks(hybrid):  # noqa: ANN001
    from tests.kb import DEFAULT_SCOPE

    c, pid, page_id = hybrid["contributor"], hybrid["pid"], hybrid["pages"]["coding-std"]
    detail = c.get(f"/api/v1/pages/{page_id}").json()
    item = {
        "note": True, "page_id": page_id, "base_revision_id": detail["published_revision_id"], "title": "Driver coding guidelines",
        "summary": "", "body_md": "Busy-wait loops are forbidden in drivers.", "scope": DEFAULT_SCOPE,
    }  # fmt: skip
    ch = c.post(f"/api/v1/projects/{pid}/changes", json={"summary": "yeni", "items": [item]}).json()
    assert c.post(f"/api/v1/changes/{ch['id']}/check").status_code == 200
    ch = c.get(f"/api/v1/changes/{ch['id']}").json()
    assert c.post(f"/api/v1/changes/{ch['id']}/publish-direct", json={"hash": ch["hash"], "acknowledge_issues": True}).status_code == 200
    _embed_all()
    hit = next(h for h in _search(hybrid["reader"], pid, "meşgul bekleme döngüsü kuralı")["hits"] if h["page_id"] == page_id)
    assert "forbidden" in hit["passage_text"]


def test_mentor_says_when_vectors_partial(hybrid):  # noqa: ANN001
    _publish(hybrid["contributor"], hybrid["pid"], "Kurgusal yeni not", "Yeni kurgusal bilgi.")
    r = hybrid["reader"].post(f"/api/v1/projects/{hybrid['pid']}/mentor/answers", json={"question": "PERST# ne kadar süre tutulur?"})
    assert r.status_code == 200 and r.json()["dense_note"] == "partial"


def test_eval_can_compare_channels(hybrid):  # noqa: ANN001
    a, pid = hybrid["admin"], hybrid["pid"]
    q = {"question": "meşgul bekleme döngüsü kuralı", "expected_page_ids": [hybrid["pages"]["coding-std"]], "expected_quote": "", "kind": "karisik"}
    assert a.post(f"/api/v1/projects/{pid}/search-eval/questions", json=q).status_code == 201
    on = a.post(f"/api/v1/projects/{pid}/search-eval/runs", json={"note": "açık"}).json()["metrics"]
    off = a.post(f"/api/v1/projects/{pid}/search-eval/runs", json={"note": "kapalı", "dense": False}).json()["metrics"]
    assert on["dense"] is True and off["dense"] is False
    assert on["recall_at_5"] == 1.0 and off["recall_at_5"] == 0.0


def test_publish_refreshes_matrix_incrementally(hybrid):  # noqa: ANN001
    """Ölçek: her yayından sonra tüm proje vektörleri yeniden okunmaz (20 bin sayfada ~230 bin blok); yalnız yeni bloklar."""
    from metis.modules.search import vectors

    _search(hybrid["reader"], hybrid["pid"], "meşgul bekleme döngüsü kuralı")
    assert vectors.last_refresh["fetched"] > 20  # ilk yükleme: tüm bloklar
    _publish(hybrid["contributor"], hybrid["pid"], "Kurgusal yeni not", "Yeni kurgusal bilgi.")
    _embed_all()
    out = _search(hybrid["reader"], hybrid["pid"], "kurgusal yeni bilgi")
    assert vectors.last_refresh["fetched"] == 1 and out["dense"] == "available"
