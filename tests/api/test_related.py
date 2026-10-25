"""Deterministik bağlantılar (İş 5): açık referanslar ve ortak nadir tanımlayıcılarla "İlgili bilgiler"; METIS'te karşılığı
olmayan bağlantılı Confluence/GitLab öğesi için içe aktarma önerisi. Modelsiz; okunamayan sayfa görünmez."""

from __future__ import annotations

import uuid

import httpx
import pytest

from metis.core.db import transaction
from metis.modules.external import fake
from metis.modules.external import http as ext_http
from tests.api.test_external_import import GIT, WIKI, connect, preview, publish, save_draft
from tests.api.test_search_blocks import _publish


@pytest.fixture(autouse=True)
def remote(monkeypatch):  # noqa: ANN001, ANN201
    monkeypatch.setattr(ext_http, "TRANSPORT", httpx.MockTransport(fake.handle))


@pytest.fixture
def rel(team):  # noqa: ANN001, ANN201
    pid = team["pid"]
    assert team["admin"].patch(f"/api/v1/projects/{pid}", json={"review_policy": "self_publish"}).status_code == 200
    wiki = connect(team["admin"], "confluence", WIKI, ["BSP"])["id"]
    git = connect(team["admin"], "gitlab", GIT, ["ekip/bsp"])["id"]
    c = team["contributor"]
    pcie = publish(c, save_draft(c, pid, preview(c, pid, wiki, f"{WIKI}/pages/viewpage.action?pageId=1001").json()).json())
    issue = publish(c, save_draft(c, pid, preview(c, pid, git, f"{GIT}/ekip/bsp/-/issues/7").json()).json())
    return {**team, "wiki": wiki, "git": git, "pcie": pcie["published_page_ids"][0], "issue": issue["published_page_ids"][0]}


def _related(c, page_id: str) -> dict:  # noqa: ANN001
    r = c.get(f"/api/v1/pages/{page_id}/related")
    assert r.status_code == 200, r.text
    return r.json()


def test_reference_links_and_missing_suggestions(rel):  # noqa: ANN001
    body = (
        f"Ayrıntı: {WIKI}/spaces/BSP/pages/1001/PCIe+Notu ve sorun kaydı {GIT}/ekip/bsp/-/issues/7.\n\n"
        f"Henüz alınmamış: {WIKI}/pages/viewpage.action?pageId=1004 ve {GIT}/ekip/bsp/issues/99"
    )
    page = _publish(rel["contributor"], rel["pid"], "Kurgusal derleme notu", body)
    out = _related(rel["contributor"], page)
    refs = {(x["page_id"], x["reason"]) for x in out["links"]}
    assert (rel["pcie"], "reference") in refs and (rel["issue"], "reference") in refs
    assert {(m["url"], m["kind"]) for m in out["missing"]} == {
        (f"{WIKI}/pages/viewpage.action?pageId=1004", "confluence"),
        (f"{GIT}/ekip/bsp/issues/99", "gitlab"),
    }
    assert all(m["connection_id"] for m in out["missing"])


def test_shared_rare_symbols(rel):  # noqa: ANN001
    a = _publish(rel["contributor"], rel["pid"], "Kurgusal saat notu A", "Saat seçimi `CLK_SRC_SEL` yazmacıyla yapılır.")
    b = _publish(rel["contributor"], rel["pid"], "Kurgusal saat notu B", "Hata: `CLK_SRC_SEL` yanlış yazılınca kart açılmaz.")
    out = _related(rel["reader"], a)
    link = next(x for x in out["links"] if x["page_id"] == b)
    assert link["reason"] == "shared_symbols" and link["symbols"] == ["CLK_SRC_SEL"]


def test_unreadable_page_not_listed(rel):  # noqa: ANN001
    from metis.core.models import Page, SourceAcl

    page = _publish(rel["contributor"], rel["pid"], "Kurgusal derleme notu", f"Bkz {GIT}/ekip/bsp/-/issues/7")
    with transaction() as db:
        target = db.get(Page, uuid.UUID(rel["issue"]))
        db.add(SourceAcl(source_id=target.note_source_id, user_id=uuid.UUID(rel["admin"].user["id"])))
    assert rel["issue"] not in [x["page_id"] for x in _related(rel["reader"], page)["links"]]


def test_gitlab_hash_reference_within_same_project(rel):  # noqa: ANN001
    """GitLab issue'sundan alınmış bilgide `#7` aynı GitLab projesinin 7 numaralı issue'sudur."""
    item_page = _publish(rel["contributor"], rel["pid"], "Kurgusal issue notu", "Benzer sorun #7 içinde çözülmüştü.")
    assert all(x["page_id"] != rel["issue"] for x in _related(rel["reader"], item_page)["links"])  # GitLab kökenli değil: #7 bağlanmaz
    out = _related(rel["reader"], rel["issue"])
    assert rel["issue"] not in [x["page_id"] for x in out["links"]]  # kendine bağlanmaz


def test_draft_or_missing_page_404(rel):  # noqa: ANN001
    assert rel["reader"].get(f"/api/v1/pages/{uuid.uuid4()}/related").status_code == 404


def test_import_suggestions_only_for_contributors(rel):  # noqa: ANN001
    page = _publish(rel["contributor"], rel["pid"], "Kurgusal derleme notu", f"Alınmamış: {GIT}/ekip/bsp/-/issues/99")
    assert _related(rel["contributor"], page)["missing"]
    assert _related(rel["reader"], page)["missing"] == []
