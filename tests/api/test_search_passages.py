"""Blok indeksi (İş 2): yayındaki her iddia bir arama bloğu; başlık yolu; yayından kaldırılınca düşer."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from metis.core.db import transaction
from metis.core.models import SearchPassage
from tests.kb import DEFAULT_SCOPE
from tests.retrieval_kit import publish_corpus

BODY = "## Saat\n\nReferans saat 100 MHz.\n\n### Sıfırlama\n\nPERST# en az 100 ms tutulur.\n\n## Kesmeler\n\nMSI-X kullanılır."


def _publish(c, pid: str, title: str, body: str) -> str:  # noqa: ANN001
    item = {"note": True, "title": title, "summary": "", "body_md": body, "scope": DEFAULT_SCOPE}
    ch = c.post(f"/api/v1/projects/{pid}/changes", json={"summary": title, "items": [item]}).json()
    assert c.post(f"/api/v1/changes/{ch['id']}/check").status_code == 200
    ch = c.get(f"/api/v1/changes/{ch['id']}").json()
    r = c.post(f"/api/v1/changes/{ch['id']}/publish-direct", json={"hash": ch["hash"], "acknowledge_issues": True})
    assert r.status_code == 200, r.text
    return r.json()["published_page_ids"][0]


def _rows(page_id: str) -> list[tuple[int, str, str]]:
    with transaction() as db:
        rows = db.scalars(select(SearchPassage).where(SearchPassage.page_id == uuid.UUID(page_id)).order_by(SearchPassage.ord))
        return [(r.ord, r.heading_path, r.body) for r in rows]


def test_passages_built_on_publish_and_dropped_on_withdraw(team):  # noqa: ANN001
    pid, c = team["pid"], team["contributor"]
    assert team["admin"].patch(f"/api/v1/projects/{pid}", json={"review_policy": "self_publish"}).status_code == 200
    page_id = _publish(c, pid, "PCIe saat ve kesme", BODY)
    rows = _rows(page_id)
    assert [(h, b) for _, h, b in rows] == [
        ("Saat", "## Saat"),
        ("Saat", "Referans saat 100 MHz."),
        ("Saat › Sıfırlama", "### Sıfırlama"),
        ("Saat › Sıfırlama", "PERST# en az 100 ms tutulur."),
        ("Kesmeler", "## Kesmeler"),
        ("Kesmeler", "MSI-X kullanılır."),
    ]
    detail = c.get(f"/api/v1/pages/{page_id}").json()
    item = {"page_id": page_id, "base_revision_id": detail["published_revision_id"], "action": "withdraw", "note": True, "title": "x"}
    ch = c.post(f"/api/v1/projects/{pid}/changes", json={"summary": "geri çek", "items": [item]})
    assert ch.status_code == 201, ch.text
    ch = ch.json()
    assert c.post(f"/api/v1/changes/{ch['id']}/check").status_code == 200
    ch = c.get(f"/api/v1/changes/{ch['id']}").json()
    r = c.post(f"/api/v1/changes/{ch['id']}/publish-direct", json={"hash": ch["hash"], "acknowledge_issues": True})
    assert r.status_code == 200, r.text
    assert _rows(page_id) == []


def test_corpus_passage_count(team):  # noqa: ANN001
    pid = team["pid"]
    assert team["admin"].patch(f"/api/v1/projects/{pid}", json={"review_policy": "self_publish"}).status_code == 200
    pages = publish_corpus(team["contributor"], pid)
    assert len(_rows(pages["pcie-bringup"])) == 16  # 8 başlık + 8 paragraf


def test_ensure_passage_index_rebuilds_missing(team):  # noqa: ANN001
    """Yükseltme (`metis migrate`): yayın var ama blok indeksi boşsa kurulur; doluysa dokunulmaz."""
    from sqlalchemy import delete

    from metis.modules.search.index import ensure_passage_index

    pid = team["pid"]
    assert team["admin"].patch(f"/api/v1/projects/{pid}", json={"review_policy": "self_publish"}).status_code == 200
    page_id = _publish(team["contributor"], pid, "PCIe saat ve kesme", BODY)
    with transaction() as db:
        assert ensure_passage_index(db) == 0
        db.execute(delete(SearchPassage))
    with transaction() as db:
        assert ensure_passage_index(db) == 1
    assert len(_rows(page_id)) == 6
