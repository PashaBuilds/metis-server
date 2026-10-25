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


# --- inceleme düzeltmeleri ---


def _missing_urls(c, page: str) -> set[str]:  # noqa: ANN001
    return {m["url"] for m in _related(c, page)["missing"]}


def test_url_tokens_are_not_shared_symbols(rel):  # noqa: ANN001
    a = _publish(rel["contributor"], rel["pid"], "Kurgusal not A", f"Bkz {WIKI}/pages/viewpage.action?pageId=2001")
    b = _publish(rel["contributor"], rel["pid"], "Kurgusal not B", f"Bkz {WIKI}/pages/viewpage.action?pageId=2002")
    assert b not in [x["page_id"] for x in _related(rel["reader"], a)["links"]]


def test_suggestions_are_capped(rel):  # noqa: ANN001
    body = "\n".join(f"- {GIT}/ekip/bsp/-/issues/{n}" for n in range(100, 130))
    page = _publish(rel["contributor"], rel["pid"], "Kurgusal uzun liste", body)
    assert len(_related(rel["contributor"], page)["missing"]) == 20


def test_suggestions_respect_allowed_scopes_and_pick_matching_connection(rel):  # noqa: ANN001
    other = connect(rel["admin"], "gitlab", GIT, ["ekip/diger"])["id"]
    body = f"{GIT}/baska/proje/-/issues/3 ve {WIKI}/spaces/DIGER/pages/5/Not ve {GIT}/ekip/diger/-/issues/4"
    page = _publish(rel["contributor"], rel["pid"], "Kurgusal kapsam notu", body)
    out = _related(rel["contributor"], page)["missing"]
    assert [(m["url"], m["connection_id"]) for m in out] == [(f"{GIT}/ekip/diger/-/issues/4", other)]


def test_deleted_import_is_suggested_again(rel):  # noqa: ANN001
    assert rel["admin"].delete(f"/api/v1/pages/{rel['issue']}").status_code == 200
    page = _publish(rel["contributor"], rel["pid"], "Kurgusal derleme notu", f"Bkz {GIT}/ekip/bsp/-/issues/7")
    assert _missing_urls(rel["contributor"], page) == {f"{GIT}/ekip/bsp/-/issues/7"}


def test_url_tails_in_turkish_and_markdown(rel):  # noqa: ANN001
    body = f"Sorun {GIT}/ekip/bsp/-/issues/7’de çözüldü; ayrıntı **{WIKI}/pages/viewpage.action?pageId=1001**."
    page = _publish(rel["contributor"], rel["pid"], "Kurgusal derleme notu", body)
    linked = {x["page_id"] for x in _related(rel["reader"], page)["links"]}
    assert {rel["issue"], rel["pcie"]} <= linked


def test_hash_refs_on_gitlab_page_skip_code(rel):  # noqa: ANN001
    from metis.core.models import ExternalOrigin

    body = 'Benzer sorun #7 içinde çözülmüştü. Kodda `#9` geçer:\n\n```\nprintf("#10");\n```'
    page = _publish(rel["contributor"], rel["pid"], "Kurgusal issue notu", body)
    with transaction() as db:
        db.add(
            ExternalOrigin(
                project_id=uuid.UUID(rel["pid"]),
                page_id=uuid.UUID(page),
                connection_id=uuid.UUID(rel["git"]),
                external_key="gitlab:kurgusal:20",
                url=f"{GIT}/ekip/bsp/-/issues/20",
                imported_body_sha256="0" * 64,
                imported_by=uuid.UUID(rel["contributor"].user["id"]),
            )
        )
    out = _related(rel["contributor"], page)
    assert rel["issue"] in [x["page_id"] for x in out["links"]]
    assert out["missing"] == []


def test_base_path_needs_segment_boundary(rel):  # noqa: ANN001
    page = _publish(rel["contributor"], rel["pid"], "Kurgusal not", f"Bkz {WIKI}2/pages/viewpage.action?pageId=5")
    assert _related(rel["contributor"], page)["missing"] == []


def test_symbol_slots_not_used_by_unreadable_pages(rel):  # noqa: ANN001
    from metis.core.models import Page, SourceAcl

    syms = [f"`KURGU_SYM_{i}`" for i in range(6)]
    a = _publish(rel["contributor"], rel["pid"], "Kurgusal merkez", " ".join(syms))
    others = [_publish(rel["contributor"], rel["pid"], f"Kurgusal komşu {i}", f"Yalnız {s}.") for i, s in enumerate(syms)]
    visible = max(others)
    with transaction() as db:
        for pid in others:
            if pid != visible:
                db.add(SourceAcl(source_id=db.get(Page, uuid.UUID(pid)).note_source_id, user_id=uuid.UUID(rel["admin"].user["id"])))
    assert [x["page_id"] for x in _related(rel["reader"], a)["links"]] == [visible]
