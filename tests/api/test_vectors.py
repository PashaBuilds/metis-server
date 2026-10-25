"""Vektör saklama ve worker hesaplaması (İş 3): eksik bloklar hesaplanır, aynı metin yeniden hesaplanmaz."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from metis.core.db import transaction
from metis.core.models import PassageVector, SearchPassage, SearchState
from metis.modules.search import embedding
from metis.modules.search.vectors import embed_missing
from tests.retrieval_kit import publish_corpus
from tests.vector_kit import FakeEmbedder


@pytest.fixture
def fake():  # noqa: ANN201
    e = FakeEmbedder()
    embedding.use_for_tests(e)
    yield e
    embedding.reset()


def test_embed_missing_once(team, fake):  # noqa: ANN001
    pid = team["pid"]
    assert team["admin"].patch(f"/api/v1/projects/{pid}", json={"review_policy": "self_publish"}).status_code == 200
    publish_corpus(team["contributor"], pid)
    with transaction() as db:
        hashes = db.scalar(select(func.count(func.distinct(SearchPassage.embed_sha256))))
        assert db.scalar(select(func.count()).select_from(SearchPassage).where(SearchPassage.embed_sha256.is_(None))) == 0
        before = db.scalar(select(SearchState.vectors_version))
    done = 0
    while True:
        with transaction() as db:
            n = embed_missing(db, limit=40)
        if not n:
            break
        done += n
    assert done == hashes
    with transaction() as db:
        assert db.scalar(select(func.count()).select_from(PassageVector).where(PassageVector.model_id == fake.model_id)) == hashes
        assert db.scalar(select(SearchState.vectors_version)) > (before or 0)
        assert embed_missing(db) == 0


def test_no_model_no_work(team):  # noqa: ANN001
    embedding.reset()
    with transaction() as db:
        assert embed_missing(db) == 0


def test_system_status_reports_vector_search(team, fake):  # noqa: ANN001
    pid = team["pid"]
    assert team["admin"].patch(f"/api/v1/projects/{pid}", json={"review_policy": "self_publish"}).status_code == 200
    publish_corpus(team["contributor"], pid)
    st = team["admin"].get("/api/v1/system/status").json()["vector_search"]
    assert st["state"] == "ready" and st["model_id"] == fake.model_id and st["blocks_embedded"] == 0 and st["blocks_total"] > 0
    with transaction() as db:
        while embed_missing(db, limit=100):
            pass
    st = team["admin"].get("/api/v1/system/status").json()["vector_search"]
    assert st["blocks_embedded"] == st["blocks_total"]
    embedding.reset()
    assert team["admin"].get("/api/v1/system/status").json()["vector_search"]["state"] == "absent"


def test_failing_block_is_marked_not_retried(team, fake):  # noqa: ANN001
    from tests.api.test_search_blocks import _publish

    pid = team["pid"]
    assert team["admin"].patch(f"/api/v1/projects/{pid}", json={"review_policy": "self_publish"}).status_code == 200
    _publish(team["contributor"], pid, "Kurgusal hatalı", "Normal paragraf.\n\nZEHIRLI paragraf.")
    with transaction() as db:
        while embed_missing(db):
            pass
        assert embed_missing(db) == 0  # takılıp kalmaz
    st = team["admin"].get("/api/v1/system/status").json()["vector_search"]
    assert st["blocks_failed"] == 1 and st["blocks_embedded"] == st["blocks_total"] - 1
