"""Faz 1 kabul: yetki matrisi, değişmezlik trigger'ı, dosya doğrulama, PDF zaman/bellek limiti, revizyon 409, ACL."""

from __future__ import annotations

import json
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from metis.core.db import transaction
from metis.modules.sources.pdf_extract import extract_isolated
from tests.kb import add_note, evidence, upload
from tests.pdfgen import make_pdf

NOTE = "SPI saat bolucusu 8 olarak ayarlanir. INIT_BUS cagrisi saat ayarindan once yapilir."


# ------------------------------------------------------------------ yetki matrisi (rol × uç)

ENDPOINTS = [
    # (ad, metod, yol şablonu, gövde fabrikası, izinli roller)
    ("kaynak listele", "get", "/api/v1/projects/{pid}/sources", None, {"admin", "contributor", "reviewer", "reader"}),
    ("kaynak ekle", "post_source", "/api/v1/projects/{pid}/sources", None, {"admin", "contributor"}),
    ("kapsam kataloğu", "get", "/api/v1/projects/{pid}/scopes", None, {"admin", "contributor", "reviewer", "reader"}),
    (
        "kapsam ekle",
        "post",
        "/api/v1/projects/{pid}/scopes",
        lambda: {"dimension": "kart", "value": f"K-{uuid.uuid4().hex[:4]}"},
        {"admin", "contributor"},
    ),
    ("üyeler", "get", "/api/v1/projects/{pid}/members", None, {"admin", "contributor", "reviewer", "reader"}),
    ("üye ata", "put_member", "/api/v1/projects/{pid}/members", None, {"admin"}),
    ("proje güncelle", "patch", "/api/v1/projects/{pid}", lambda: {"description": "x"}, {"admin"}),
    ("kullanıcı listesi", "get_global", "/api/v1/users", None, {"admin"}),
    ("sistem durumu", "get_global", "/api/v1/system/status", None, {"admin"}),
    ("kayıt listesi", "get", "/api/v1/projects/{pid}/changes", None, {"admin", "contributor", "reviewer", "reader"}),
    ("bilgi listesi", "get", "/api/v1/projects/{pid}/pages", None, {"admin", "contributor", "reviewer", "reader"}),
]
ROLES = ["admin", "contributor", "reviewer", "reader", "outsider"]


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=[e[0] for e in ENDPOINTS])
def test_authorization_matrix(team, role, endpoint):
    name, method, path, body, allowed = endpoint
    c = team[role]
    url = path.format(pid=team["pid"])
    if method in ("get", "get_global"):
        r = c.get(url)
    elif method == "post":
        r = c.post(url, json=body())
    elif method == "patch":
        r = c.patch(url, json=body())
    elif method == "post_source":
        meta = {"title": "Not", "kind": "note", "text": NOTE, "scope": {}}
        r = c.post(url, files={"meta": (None, json.dumps(meta))})
    elif method == "put_member":
        r = c.put(url, json={"user_id": team["reader"].user["id"], "roles": ["reader"]})
    else:  # pragma: no cover
        raise AssertionError(method)
    if role in allowed:
        assert r.status_code < 300, (name, role, r.text)
    elif role == "outsider" and method not in ("get_global",):
        assert r.status_code == 404, (name, role, r.status_code)  # varlık sızdırılmaz
    else:
        assert r.status_code == 403, (name, role, r.status_code, r.text)


def test_anonymous_gets_401(client):
    assert client.get(f"/api/v1/projects/{uuid.uuid4()}/sources").status_code == 401


# ------------------------------------------------------------------ kaynak + revizyon


def test_source_create_and_revision_conflict(team):
    c, pid = team["contributor"], team["pid"]
    src = add_note(c, pid, "SPI notu", NOTE)
    assert src["revision"]["number"] == 1 and src["revision"]["extraction"] == "complete"
    sid = src["source"]["id"]
    meta = {"expected_revision": 1, "text": NOTE + " Yeni satir."}
    r = c.post(f"/api/v1/sources/{sid}/revisions", files={"meta": (None, json.dumps(meta))})
    assert r.status_code == 201 and r.json()["revision"]["number"] == 2
    r = c.post(f"/api/v1/sources/{sid}/revisions", files={"meta": (None, json.dumps(meta))})
    assert r.status_code == 409 and r.json()["error"]["code"] == "REVISION_CONFLICT"
    assert r.json()["error"]["details"]["current_revision"] == 2
    detail = c.get(f"/api/v1/sources/{sid}").json()
    assert [rv["number"] for rv in detail["revisions"]] == [2, 1]


def test_scope_value_must_be_in_catalog(team):
    c, pid = team["contributor"], team["pid"]
    meta = {"title": "Not", "kind": "note", "text": NOTE, "scope": {"kart": ["TANIMSIZ"]}}
    r = c.post(f"/api/v1/projects/{pid}/sources", files={"meta": (None, json.dumps(meta))})
    assert r.status_code == 422 and r.json()["error"]["code"] == "SCOPE_INVALID"


def test_blob_sha256_and_download(team):
    c, pid = team["contributor"], team["pid"]
    src = add_note(c, pid, "Ç ş ğ İ başlık", "Türkçe içerik: ğüşıöç İĞÜŞÖÇ")
    import hashlib

    rev = src["revision"]
    assert rev["sha256"] == hashlib.sha256("Türkçe içerik: ğüşıöç İĞÜŞÖÇ".encode()).hexdigest()
    r = c.get(f"/api/v1/source-revisions/{rev['id']}/download")
    assert r.status_code == 200 and r.content.decode() == "Türkçe içerik: ğüşıöç İĞÜŞÖÇ"
    assert "attachment" in r.headers["content-disposition"]


def test_upload_allowlist_magic_bytes_and_size(team):
    c, pid = team["contributor"], team["pid"]
    r = upload(c, pid, "sahte.pdf", b"MZ\x90\x00 not a pdf")
    assert r.status_code == 422 and r.json()["error"]["code"] == "UNSUPPORTED_FILE"
    r = upload(c, pid, "program.exe", b"MZ\x90\x00")
    assert r.status_code == 422 and r.json()["error"]["code"] == "UNSUPPORTED_FILE"
    r = upload(c, pid, "buyuk.txt", b"a" * (10 * 1024 * 1024 + 1))
    assert r.status_code == 413 and r.json()["error"]["code"] == "FILE_TOO_LARGE"
    r = upload(c, pid, "latin1.txt", "çalışma".encode("cp1254"))
    assert r.status_code == 422
    r = upload(c, pid, "surucu.c", b"void INIT_BUS(void) { /* saat */ }\n", kind="code")
    assert r.status_code == 201 and r.json()["revision"]["media_type"] == "text/x-c"


def test_pdf_extraction_pages_become_evidence(team):
    c, pid = team["contributor"], team["pid"]
    pdf = make_pdf(["Page one: DMA buffer is 512 bytes.", "Page two: UART runs at 115200 baud."])
    r = upload(c, pid, "veri-sayfasi.pdf", pdf)
    assert r.status_code == 201, r.text
    rev = r.json()["revision"]
    assert rev["extraction"] == "complete"
    assert [e["locator"]["page"] for e in rev["page_evidence"]] == [1, 2]
    ev = evidence(c, rev["id"], "UART runs at 115200 baud.")
    assert ev["locator"]["page"] == 2 and ev["locator_label"] == "Sayfa 2"


def test_pdf_sandbox_time_limit():
    pdf = make_pdf(["slow"] * 3)
    result = extract_isolated(pdf, timeout=0.001)
    assert result == {"status": "annotation_only", "pages": [], "reason": "timeout"}


def test_pdf_sandbox_memory_limit():
    pdf = make_pdf(["memory bound"])
    # 4 MB, Python'un zaten kullandığı belleğin altında: sınır uygulandıktan sonra her yeni ayırma reddedilir
    # (POSIX RLIMIT_AS ve Windows Job Object için aynı). Sonuç dosya hatası (parse_error) değil bellek/çökme olmalı.
    result = extract_isolated(pdf, memory_limit=4 * 1024 * 1024)
    assert result["status"] == "annotation_only" and result["reason"] in ("crashed", "memory", "bad_output"), result


def test_pdf_sandbox_memory_limit_is_enforced_on_this_platform():
    """Sınırın gerçekten uygulandığının platformdan bağımsız kanıtı: 256 MB sınırdan sonra 1 GB ayırma başarısız olur."""
    import subprocess
    import sys

    code = (
        "from metis.modules.sources.pdf_extract import _apply_memory_limit\n"
        "_apply_memory_limit(256 * 1024 * 1024)\n"
        "try:\n"
        "    block = bytearray(1024 * 1024 * 1024)\n"
        "    print('ALLOCATED')\n"
        "except MemoryError:\n"
        "    print('DENIED')\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    # Ayırma reddi MemoryError ya da sürecin sonlandırılması olarak görülebilir; asla başarılı olmamalı.
    assert "ALLOCATED" not in out.stdout, (out.stdout, out.stderr)
    assert "DENIED" in out.stdout or out.returncode != 0, (out.stdout, out.stderr)


def test_broken_pdf_never_reported_as_complete(team):
    c, pid = team["contributor"], team["pid"]
    r = upload(c, pid, "bozuk.pdf", b"%PDF-1.4\n garbage without objects", text="Kullanıcı açıklaması")
    assert r.status_code == 201
    assert r.json()["revision"]["extraction"] == "annotation_only"


def test_source_acl_hides_source_and_evidence(team):
    c, pid = team["contributor"], team["pid"]
    src = add_note(c, pid, "Gizli not", NOTE, acl=[team["reviewer"].user["id"]])
    sid = src["source"]["id"]
    ev = evidence(c, src["revision"]["id"], "INIT_BUS")
    assert team["reviewer"].get(f"/api/v1/sources/{sid}").status_code == 200
    assert team["reader"].get(f"/api/v1/sources/{sid}").status_code == 404
    assert team["reader"].get(f"/api/v1/evidence/{ev['id']}").status_code == 404
    assert sid not in [s["id"] for s in team["reader"].get(f"/api/v1/projects/{pid}/sources").json()["items"]]


def test_evidence_must_be_verbatim(team):
    c, pid = team["contributor"], team["pid"]
    src = add_note(c, pid, "Not", NOTE)
    r = c.post(f"/api/v1/source-revisions/{src['revision']['id']}/evidence", json={"excerpt": "uydurma alinti"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "QUOTE_NOT_IN_EVIDENCE"


def test_evidence_view_for_iz_panel(team):
    c, pid = team["contributor"], team["pid"]
    src = add_note(c, pid, "Not", NOTE)
    ev = evidence(c, src["revision"]["id"], "INIT_BUS cagrisi")
    view = c.get(f"/api/v1/evidence/{ev['id']}").json()
    assert view["text"][view["highlight"]["start"] : view["highlight"]["end"]] == "INIT_BUS cagrisi"
    assert view["revision"]["number"] == 1 and view["revision"]["is_current"] is True
    assert view["locator_label"].startswith("Satır")


@pytest.mark.parametrize(
    "table",
    ["source_revisions", "evidence"],
)
def test_immutability_triggers_on_source_tables(team, table):
    c, pid = team["contributor"], team["pid"]
    src = add_note(c, pid, "Not", NOTE)
    evidence(c, src["revision"]["id"], "INIT_BUS")
    column = {"source_revisions": "filename", "evidence": "excerpt"}[table]
    with pytest.raises(DBAPIError) as exc, transaction() as db:
        db.execute(text(f"UPDATE {table} SET {column} = 'x'"))
    assert "METIS_IMMUTABLE" in str(exc.value)
    with pytest.raises(DBAPIError), transaction() as db:
        db.execute(text(f"DELETE FROM {table}"))



def test_pdf_sandbox_fails_closed_when_memory_limit_cannot_be_applied(monkeypatch, tmp_path):
    """Bellek sınırı uygulanamazsa (setrlimit / Job Object reddi) dosya hiç açılmaz: kapalı başarısızlık."""
    from metis.modules.sources import pdf_extract

    if os.name == "nt":
        monkeypatch.setattr(pdf_extract, "_limit_memory_windows", lambda _limit: (_ for _ in ()).throw(OSError("job")))
    else:
        import resource

        monkeypatch.setattr(resource, "setrlimit", lambda *_a: (_ for _ in ()).throw(OSError("setrlimit")))
    with pytest.raises(pdf_extract._SandboxUnavailable):
        pdf_extract._extract(str(tmp_path / "yok.pdf"))
