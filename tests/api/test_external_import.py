"""Dış kaynaktan taslak (2026-10-25, ürün sahibinin isteği): Confluence sayfası ve GitLab issue'su bağlantıdan taslağa.

Gerçek sunucu yok: kurgusal Confluence + GitLab (`metis.modules.external.fake`) httpx.MockTransport ile bağlanır.
Yönetici bağlantıyı (şifreli token, izinli kapsamlar) tanımlar; katkı sahibi önizler, taslak hazırlar; insan yayımlar.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select

from metis.core.db import transaction
from metis.core.models import Attachment, AuditEvent, ExternalImport
from metis.modules.external import fake
from metis.modules.external import http as ext_http
from tests.kb import DEFAULT_SCOPE

WIKI = "http://127.0.0.1:9160/confluence"
GIT = "http://127.0.0.1:9160"


@pytest.fixture(autouse=True)
def remote(monkeypatch):  # noqa: ANN001, ANN201
    monkeypatch.setattr(ext_http, "TRANSPORT", httpx.MockTransport(fake.handle))


@pytest.fixture
def ext(team):  # noqa: ANN001, ANN201
    r = team["admin"].patch(f"/api/v1/projects/{team['pid']}", json={"review_policy": "self_publish"})
    assert r.status_code == 200, r.text
    wiki = connect(team["admin"], "confluence", WIKI, ["BSP"])
    git = connect(team["admin"], "gitlab", GIT, ["ekip/bsp"])
    return {**team, "wiki": wiki["id"], "git": git["id"]}


def connect(admin, kind: str, url: str, scopes: list[str], token: str = fake.TOKEN):  # noqa: ANN001, ANN201
    r = admin.post(
        "/api/v1/external/connections",
        json={"kind": kind, "name": f"Kurgusal {kind}", "base_url": url, "token": token, "allowed_scopes": scopes},
    )
    assert r.status_code == 201, r.text
    return r.json()


def preview(c, pid: str, connection_id: str, url: str):  # noqa: ANN001, ANN201
    return c.post(f"/api/v1/projects/{pid}/external/preview", json={"connection_id": connection_id, "url": url})


def save_draft(c, pid: str, pv: dict, **kw):  # noqa: ANN001, ANN003, ANN201
    item = {
        "note": True,
        "title": pv["title"],
        "summary": "",
        "body_md": pv["body_md"],
        "scope": DEFAULT_SCOPE,
        "attachments": [a["id"] for a in pv["attachments"]],
        "import_id": pv["import_id"],
        **kw,
    }
    return c.post(f"/api/v1/projects/{pid}/changes", json={"summary": pv["title"], "items": [item]})


def publish(c, change: dict) -> dict:  # noqa: ANN001
    assert c.post(f"/api/v1/changes/{change['id']}/check").status_code == 200
    change = c.get(f"/api/v1/changes/{change['id']}").json()
    r = c.post(f"/api/v1/changes/{change['id']}/publish-direct", json={"hash": change["hash"], "acknowledge_issues": True})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- bağlantılar


def test_admin_manages_connections_token_never_returned(team):  # noqa: ANN001
    created = connect(team["admin"], "confluence", WIKI, ["BSP"])
    assert created["secret_configured"] is True and created["allowed_scopes"] == ["BSP"]
    listed = team["admin"].get("/api/v1/external/connections")
    assert listed.status_code == 200 and fake.TOKEN not in listed.text and fake.TOKEN not in str(created)
    with transaction() as db:
        details = [str(a.detail) for a in db.scalars(select(AuditEvent).where(AuditEvent.op.like("external.%")))]
    assert details and all(fake.TOKEN not in d for d in details)

    r = team["admin"].put(f"/api/v1/external/connections/{created['id']}", json={**{k: created[k] for k in ("kind", "name", "base_url", "allowed_scopes")}, "token": "", "enabled": False})
    assert r.status_code == 200, r.text
    assert r.json()["secret_configured"] is True and r.json()["enabled"] is False

    c = team["contributor"]
    assert c.post("/api/v1/external/connections", json={"kind": "gitlab", "name": "x", "base_url": GIT, "token": "t", "allowed_scopes": ["a/b"]}).status_code == 403
    assert c.get("/api/v1/external/connections").json() == []  # kapalı bağlantı katkı sahibine görünmez
    git = connect(team["admin"], "gitlab", GIT, ["ekip/bsp"])
    seen = c.get("/api/v1/external/connections").json()
    assert [s["id"] for s in seen] == [git["id"]] and "base_url" not in seen[0]

    assert team["admin"].delete(f"/api/v1/external/connections/{git['id']}").status_code == 204
    assert c.get("/api/v1/external/connections").json() == []


def test_connection_test_ok_and_unauthorized(team):  # noqa: ANN001
    a = team["admin"]
    ok = a.post("/api/v1/external/connections/test", json={"kind": "confluence", "base_url": WIKI, "token": fake.TOKEN})
    assert ok.status_code == 200 and ok.json() == {"ok": True, "error": None, "user": "kurgusal.okur"}
    bad = a.post("/api/v1/external/connections/test", json={"kind": "gitlab", "base_url": GIT, "token": "yanlis"})
    assert bad.json()["ok"] is False and bad.json()["error"] == "EXTERNAL_UNAUTHORIZED"
    saved = connect(a, "gitlab", GIT, ["ekip/bsp"])
    again = a.post("/api/v1/external/connections/test", json={"kind": "gitlab", "base_url": GIT, "token": "", "connection_id": saved["id"]})
    assert again.json()["ok"] is True  # kayıtlı token kullanılır
    with transaction() as db:
        assert db.scalar(select(ExternalImport.id)) is None


def test_connection_validation(team):  # noqa: ANN001
    a = team["admin"]
    outside = a.post("/api/v1/external/connections", json={"kind": "gitlab", "name": "x", "base_url": "http://8.8.8.8", "token": "t", "allowed_scopes": ["a/b"]})
    assert outside.status_code == 422 and outside.json()["error"]["code"] == "ADDRESS_NOT_ALLOWED"
    for scopes in ([], ["tek"], [""]):
        r = a.post("/api/v1/external/connections", json={"kind": "gitlab", "name": "x", "base_url": GIT, "token": "t", "allowed_scopes": scopes})
        assert r.status_code == 422, scopes
    r = a.post("/api/v1/external/connections", json={"kind": "confluence", "name": "x", "base_url": WIKI, "token": "t", "allowed_scopes": ["B S P"]})
    assert r.status_code == 422


# ---------------------------------------------------------------- önizleme ve taslak


def test_confluence_page_to_draft(ext):  # noqa: ANN001
    c, pid = ext["contributor"], ext["pid"]
    r = preview(c, pid, ext["wiki"], f"{WIKI}/spaces/BSP/pages/1001/PCIe+Notu")
    assert r.status_code == 201, r.text
    pv = r.json()
    assert pv["kind"] == "confluence" and pv["title"] == "PCIe Notu"
    assert pv["body_md"].startswith("## Bağlantı eğitimi\n\n")
    assert "| PCIE_CTRL | 0x1 |" in pv["body_md"] and "```c\npcie_link_up(dev);\n```" in pv["body_md"]
    assert [a["filename"] for a in pv["attachments"]] == ["sema.png", "kilavuz.pdf"]  # gövdede geçen önce
    assert {(s["name"], s["reason"]) for s in pv["skipped"]} == {("veri.xlsx", "type"), ("toc", "macro")}
    assert pv["origin"]["version"] == "3" and pv["origin"]["url"].endswith("pageId=1001")
    assert pv["existing_page_id"] is None

    saved = save_draft(c, pid, pv)
    assert saved.status_code == 201, saved.text
    page_id = saved.json()["items"][0]["page_id"]
    publish(c, saved.json())
    detail = c.get(f"/api/v1/pages/{page_id}").json()
    assert detail["origin"]["kind"] == "confluence" and detail["origin"]["version"] == "3"
    assert [a["filename"] for a in detail["revision"]["attachments"]] == ["sema.png", "kilavuz.pdf"]

    again = save_draft(c, pid, pv)
    assert again.status_code == 409 and again.json()["error"]["code"] == "IMPORT_USED"


def test_reimport_points_to_existing_page(ext):  # noqa: ANN001
    c, pid = ext["contributor"], ext["pid"]
    url = f"{WIKI}/pages/viewpage.action?pageId=1004"
    pv = preview(c, pid, ext["wiki"], url).json()
    change = save_draft(c, pid, pv).json()
    publish(c, change)
    page_id = change["items"][0]["page_id"]

    second = preview(c, pid, ext["wiki"], url).json()
    assert second["existing_page_id"] == page_id and second["existing_title"] == "Saat Ağacı"
    assert second["edited_since_import"] is False

    detail = c.get(f"/api/v1/pages/{page_id}").json()
    edit = {
        "note": True, "page_id": page_id, "base_revision_id": detail["published_revision_id"], "title": "Saat Ağacı",
        "summary": "", "body_md": pv["body_md"] + "\n\nMETIS'te eklenen kurgusal not.", "scope": DEFAULT_SCOPE,
    }  # fmt: skip
    r = c.post(f"/api/v1/projects/{pid}/changes", json={"summary": "düzenleme", "items": [edit]})
    assert r.status_code == 201, r.text
    publish(c, r.json())
    third = preview(c, pid, ext["wiki"], url).json()
    assert third["edited_since_import"] is True

    # Güncelleme taslağı: aynı sayfaya bağlanır, yeni sayfa açılmaz; köken yeni içe aktarmaya güncellenir.
    detail = c.get(f"/api/v1/pages/{page_id}").json()
    upd = save_draft(c, pid, third, page_id=page_id, base_revision_id=detail["published_revision_id"])
    assert upd.status_code == 201, upd.text
    assert upd.json()["items"][0]["page_id"] == page_id


def test_same_source_cannot_bind_second_page(ext):  # noqa: ANN001
    c, pid = ext["contributor"], ext["pid"]
    url = f"{WIKI}/pages/viewpage.action?pageId=1004"
    first = preview(c, pid, ext["wiki"], url).json()
    second = preview(c, pid, ext["wiki"], url).json()
    assert save_draft(c, pid, first).status_code == 201
    r = save_draft(c, pid, second)  # sayfa belirtilmeden ikinci yeni sayfa
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_gitlab_issue_to_draft(ext):  # noqa: ANN001
    c, pid = ext["contributor"], ext["pid"]
    r = preview(c, pid, ext["git"], f"{GIT}/ekip/bsp/-/issues/7")
    assert r.status_code == 201, r.text
    pv = r.json()
    assert pv["kind"] == "gitlab" and pv["title"] == "PCIe bağlantısı kurulmuyor"
    body = pv["body_md"]
    assert body.startswith("**Durum:** Kapalı · **Etiketler:** pcie, sürücü")
    assert "added ~pcie label" not in body and "[Görsel: log.png]" in body and "/uploads/" not in body
    assert "### Kurgusal İkinci — 2026-01-06" in body and "### Kurgusal Kişi — 2026-01-06" in body
    assert [a["filename"] for a in pv["attachments"]] == ["log.png"]
    assert save_draft(c, pid, pv).status_code == 201


def test_restricted_and_scope_rejected(ext):  # noqa: ANN001
    c, pid = ext["contributor"], ext["pid"]
    cases = [
        (ext["wiki"], f"{WIKI}/pages/viewpage.action?pageId=1002", 403, "EXTERNAL_RESTRICTED"),
        (ext["git"], f"{GIT}/ekip/bsp/-/issues/8", 403, "EXTERNAL_RESTRICTED"),
        (ext["wiki"], f"{WIKI}/pages/viewpage.action?pageId=1003", 403, "EXTERNAL_SCOPE_NOT_ALLOWED"),
        (ext["git"], f"{GIT}/baska/proje/-/issues/1", 403, "EXTERNAL_SCOPE_NOT_ALLOWED"),
        (ext["wiki"], f"{WIKI}/pages/viewpage.action?pageId=9999", 404, "EXTERNAL_NOT_FOUND"),
        (ext["wiki"], "http://baska.example.test/confluence/pages/viewpage.action?pageId=1001", 422, "EXTERNAL_URL_UNRECOGNIZED"),
    ]
    for conn, url, status, code in cases:
        r = preview(c, pid, conn, url)
        assert (r.status_code, r.json()["error"]["code"]) == (status, code), url
    with transaction() as db:
        assert db.scalar(select(ExternalImport.id)) is None and db.scalar(select(Attachment.id)) is None


def test_import_record_private(ext):  # noqa: ANN001
    pid = ext["pid"]
    pv = preview(ext["contributor"], pid, ext["wiki"], f"{WIKI}/pages/viewpage.action?pageId=1004").json()
    other = ext["admin"]  # aynı projede başka kullanıcı (yönetici bile) başkasının önizlemesini kullanamaz
    r = save_draft(other, pid, pv, attachments=[])
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    assert preview(ext["reader"], pid, ext["wiki"], f"{WIKI}/pages/viewpage.action?pageId=1004").status_code == 403
    assert preview(ext["outsider"], pid, ext["wiki"], f"{WIKI}/pages/viewpage.action?pageId=1004").status_code in (403, 404)


def test_disabled_connection_cannot_import(ext):  # noqa: ANN001
    a = ext["admin"]
    conn = next(x for x in a.get("/api/v1/external/connections").json() if x["id"] == ext["wiki"])
    r = a.put(f"/api/v1/external/connections/{conn['id']}", json={**{k: conn[k] for k in ("kind", "name", "base_url", "allowed_scopes")}, "token": "", "enabled": False})
    assert r.status_code == 200
    r = preview(ext["contributor"], ext["pid"], ext["wiki"], f"{WIKI}/pages/viewpage.action?pageId=1004")
    assert r.status_code == 404


def test_search_lists_allowed_only(ext):  # noqa: ANN001
    c, pid = ext["contributor"], ext["pid"]
    r = c.get(f"/api/v1/projects/{pid}/external/search", params={"connection_id": ext["wiki"], "q": "sa"})
    assert r.status_code == 200, r.text
    assert {x["container"] for x in r.json()} == {"BSP"} and "Başka Alan" not in r.text
    g = c.get(f"/api/v1/projects/{pid}/external/search", params={"connection_id": ext["git"], "q": "pcie"}).json()
    assert [x["title"] for x in g] == ["PCIe bağlantısı kurulmuyor"]  # gizli issue listelenmez


def test_remote_errors_mapped(ext, monkeypatch):  # noqa: ANN001
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("kapalı", request=request)

    monkeypatch.setattr(ext_http, "TRANSPORT", httpx.MockTransport(down))
    r = preview(ext["contributor"], ext["pid"], ext["wiki"], f"{WIKI}/pages/viewpage.action?pageId=1001")
    assert r.status_code == 502 and r.json()["error"]["code"] == "EXTERNAL_UNREACHABLE"
    assert fake.TOKEN not in r.text

    def html_error(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>Bakim</html>", headers={"Content-Type": "text/html"})

    monkeypatch.setattr(ext_http, "TRANSPORT", httpx.MockTransport(html_error))
    r = preview(ext["contributor"], ext["pid"], ext["wiki"], f"{WIKI}/pages/viewpage.action?pageId=1001")
    assert r.status_code == 502 and r.json()["error"]["code"] == "EXTERNAL_BAD_RESPONSE"
    with transaction() as db:
        assert db.scalar(select(ExternalImport.id)) is None and db.scalar(select(Attachment.id)) is None
