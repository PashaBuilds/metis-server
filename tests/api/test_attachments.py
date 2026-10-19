"""Ekler (2026-10-19): bir nota birden çok görsel/PDF; yalnız ulaşılabilir dosyalar — okunmaz, aranmaz, modele gitmez.
Ekler bilgi revizyonuyla sürümlenir, revizyon hash'ine girer ve değişmezdir; erişilemeyene 404."""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from metis.core.db import transaction
from tests.api.test_note_drafts import create, note_item, publish_direct, sp  # noqa: F401 — fixture
from tests.pdfgen import make_pdf

PNG_A = b"\x89PNG\r\n\x1a\n" + b"\x01" * 64  # kurgusal: yalnız imza denetlenir
PNG_B = b"\x89PNG\r\n\x1a\n" + b"\x02" * 64
PDF = make_pdf(["Kurgusal olcum raporu ZEBRAKELIME sayfasi."])
BODY = "UART hızı 115200 baud olarak ayarlanır; 1. görsel osiloskop çıktısıdır."


def upload(client, pid: str, files: list[tuple[str, bytes]]):  # noqa: ANN001, ANN201
    return client.post(f"/api/v1/projects/{pid}/attachments", files=[("files", f) for f in files])


def uploaded(client, pid: str, files: list[tuple[str, bytes]]) -> list[dict]:  # noqa: ANN001
    r = upload(client, pid, files)
    assert r.status_code == 201, r.text
    return r.json()


def test_upload_multiple_png_pdf(sp):  # noqa: F811
    out = uploaded(sp["contributor"], sp["pid"], [("a.png", PNG_A), ("b.png", PNG_B), ("rapor.pdf", PDF)])
    assert [(a["filename"], a["media_type"], a["is_image"]) for a in out] == [
        ("a.png", "image/png", True),
        ("b.png", "image/png", True),
        ("rapor.pdf", "application/pdf", False),
    ]
    assert out[2]["size_bytes"] == len(PDF)


@pytest.mark.parametrize(("name", "data"), [("not.docx", b"PK\x03\x04xx"), ("sahte.png", b"not a png at all"), ("a.txt", b"metin")])
def test_upload_rejects_other_types(sp, name, data):  # noqa: ANN001, F811
    r = upload(sp["contributor"], sp["pid"], [(name, data)])
    assert r.status_code == 422 and r.json()["error"]["code"] == "UNSUPPORTED_FILE"


def test_upload_limit_30(sp):  # noqa: F811
    r = upload(sp["contributor"], sp["pid"], [(f"{i}.png", PNG_A) for i in range(31)])
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_reader_cannot_upload(sp):  # noqa: F811
    assert upload(sp["reader"], sp["pid"], [("a.png", PNG_A)]).status_code == 403


def test_note_draft_with_attachments_published_and_downloadable(sp):  # noqa: F811
    c, pid = sp["contributor"], sp["pid"]
    ids = [a["id"] for a in uploaded(c, pid, [("osiloskop.png", PNG_A), ("rapor.pdf", PDF)])]
    out = publish_direct(c, create(c, pid, note_item("UART ayarları", BODY, attachments=ids)))
    page = sp["reader"].get(f"/api/v1/pages/{out['published_page_ids'][0]}").json()
    atts = page["revision"]["attachments"]
    assert [a["filename"] for a in atts] == ["osiloskop.png", "rapor.pdf"] and [a["id"] for a in atts] == ids
    dl = sp["reader"].get(f"/api/v1/attachments/{ids[1]}/download")
    assert dl.status_code == 200 and dl.content == PDF and dl.headers["content-type"] == "application/pdf"
    assert "attachment" in dl.headers["content-disposition"]
    assert dl.headers["x-content-type-options"] == "nosniff" and "default-src" in dl.headers["content-security-policy"]


def test_attachment_order_is_part_of_revision_hash(sp):  # noqa: F811
    c, pid = sp["contributor"], sp["pid"]
    ids = [a["id"] for a in uploaded(c, pid, [("a.png", PNG_A), ("b.png", PNG_B)])]
    h1 = create(c, pid, note_item("Sıra", BODY, attachments=ids))["items"][0]["proposed"]["hash"]
    h2 = create(c, pid, note_item("Sıra", BODY, attachments=list(reversed(ids))))["items"][0]["proposed"]["hash"]
    h0 = create(c, pid, note_item("Sıra", BODY))["items"][0]["proposed"]["hash"]
    assert len({h0, h1, h2}) == 3


def test_attachmentless_revision_hash_unchanged_by_feature():
    """Eksiz revizyonun hash içeriğinde `attachments` anahtarı yok: eski onaylar geçerli kalır."""
    from metis.modules.changes import schemas, service

    item = schemas.ItemIn(title="Eksiz", body_md="Bir bilgi.")
    assert "attachments" not in service.revision_content(item, {}, [])
    with_att = item.model_copy(update={"attachments": [__import__("uuid").uuid4()]})
    assert "attachments" in service.revision_content(with_att, {}, [])


def test_other_users_upload_cannot_be_referenced(sp):  # noqa: F811
    c, pid = sp["contributor"], sp["pid"]
    other = uploaded(sp["admin"], pid, [("a.png", PNG_A)])[0]["id"]
    r = c.post(f"/api/v1/projects/{pid}/changes", json={"items": [note_item("Ek", BODY, attachments=[other])]})
    assert r.status_code == 404


def test_edit_keeps_previous_revision_attachments(sp):  # noqa: F811
    c, pid = sp["contributor"], sp["pid"]
    ids = [a["id"] for a in uploaded(c, pid, [("a.png", PNG_A)])]
    out = publish_direct(c, create(c, pid, note_item("Ekli", BODY, attachments=ids)))
    page_id = out["published_page_ids"][0]
    page = sp["admin"].get(f"/api/v1/pages/{page_id}").json()
    edit = note_item("Ekli", BODY + "\n\nEk bilgi 3,3 V.", page_id=page_id, base_revision_id=page["revision"]["id"], attachments=ids)
    ch = create(sp["admin"], pid, edit)  # başka kullanıcı, yayımlanmış sayfanın ekini korur
    assert [a["id"] for a in ch["items"][0]["proposed"]["attachments"]] == ids


def test_unpublished_attachment_hidden(sp):  # noqa: F811
    c, pid = sp["contributor"], sp["pid"]
    aid = uploaded(c, pid, [("a.png", PNG_A)])[0]["id"]
    create(c, pid, note_item("Taslak", BODY, attachments=[aid]))
    assert c.get(f"/api/v1/attachments/{aid}/download").status_code == 200
    assert sp["reader"].get(f"/api/v1/attachments/{aid}/download").status_code == 404


def test_attachments_immutable(sp):  # noqa: F811
    c, pid = sp["contributor"], sp["pid"]
    aid = uploaded(c, pid, [("a.png", PNG_A)])[0]["id"]
    create(c, pid, note_item("Değişmez", BODY, attachments=[aid]))
    for sql in ("UPDATE attachments SET filename = 'x'", "DELETE FROM page_revision_attachments"):
        with pytest.raises(DBAPIError) as exc, transaction() as db:
            db.execute(text(sql))
        assert "METIS_IMMUTABLE" in str(exc.value)


def test_attachments_never_searched(sp):  # noqa: F811
    c, pid = sp["contributor"], sp["pid"]
    aid = uploaded(c, pid, [("rapor.pdf", PDF)])[0]["id"]
    publish_direct(c, create(c, pid, note_item("Rapor ekli", BODY, attachments=[aid])))
    r = sp["reader"].get(f"/api/v1/projects/{pid}/search", params={"q": "ZEBRAKELIME"}).json()
    assert r["hits"] == []
    with transaction() as db:  # blob içerik adresli
        assert db.execute(text("SELECT sha256 FROM attachments")).scalar_one() == hashlib.sha256(PDF).hexdigest()


def test_rebase_keeps_note_and_attachments(sp):  # noqa: F811
    c, pid = sp["contributor"], sp["pid"]
    ids = [a["id"] for a in uploaded(c, pid, [("a.png", PNG_A), ("rapor.pdf", PDF)])]
    out = publish_direct(c, create(c, pid, note_item("Yeniden temel", BODY, attachments=ids)))
    page_id = out["published_page_ids"][0]
    base = c.get(f"/api/v1/pages/{page_id}").json()["revision"]["id"]
    draft = create(c, pid, note_item("Yeniden temel", BODY + "\n\nTaslak satırı 5 V.", page_id=page_id, base_revision_id=base, attachments=ids))
    publish_direct(c, create(c, pid, note_item("Yeniden temel", BODY + "\n\nAra yayın 12 V.", page_id=page_id, base_revision_id=base, attachments=ids)))
    r = c.post(f"/api/v1/changes/{draft['id']}/rebase")
    assert r.status_code in (200, 201), r.text
    proposed_rev = r.json()["items"][0]["proposed"]
    assert [a["id"] for a in proposed_rev["attachments"]] == ids
    assert "Taslak satırı 5 V." in [cl["statement"] for cl in proposed_rev["claims"]]

def test_export_includes_attachments(sp):  # noqa: F811
    import io
    import zipfile

    c, pid = sp["contributor"], sp["pid"]
    ids = [a["id"] for a in uploaded(c, pid, [("osiloskop.png", PNG_A), ("rapor.pdf", PDF)])]
    publish_direct(c, create(c, pid, note_item("UART ayarları", BODY, attachments=ids)))
    r = sp["reader"].get(f"/api/v1/projects/{pid}/export.zip")
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert z.read("ekler/uart-ayarlari/1-osiloskop.png") == PNG_A
    assert z.read("ekler/uart-ayarlari/2-rapor.pdf") == PDF
    md = z.read("sayfalar/uart-ayarlari.md").decode()
    assert "## Ekler" in md and "(../ekler/uart-ayarlari/2-rapor.pdf)" in md
