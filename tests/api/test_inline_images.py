"""Satır içi görsel ve tablo (2.0.27): görsel taslağın kendi eki olmalı; sayfada ayrı paragraf, iddia değil;
arama ve dışa aktarma ek bağlantısını kimlik olarak taşımaz."""

from __future__ import annotations

import io
import zipfile

from tests.api.test_attachments import PDF, PNG_A, uploaded
from tests.api.test_note_drafts import create, note_item, proposed, publish_direct, sp  # noqa: F401 — fixture

TEXT = "Besleme 3,3 V olarak ölçülür."
TABLE = "| Pin | Gerilim |\n| --- | --- |\n| VCC | 3,3 V |"


def _body(aid: str) -> str:
    return f"{TEXT}\n\n![osiloskop çıktısı](ek:{aid})\n\n{TABLE}"


def test_inline_image_published_as_own_paragraph(sp):  # noqa: F811
    c, pid = sp["contributor"], sp["pid"]
    aid = uploaded(c, pid, [("ekran.png", PNG_A)])[0]["id"]
    ch = create(c, pid, note_item("Besleme", _body(aid), attachments=[aid]))
    assert [cl["statement"] for cl in proposed(ch)["claims"]] == [TEXT, TABLE]
    page_id = publish_direct(c, ch)["published_page_ids"][0]
    page = sp["reader"].get(f"/api/v1/pages/{page_id}").json()
    assert [(p["text"], bool(p["claim_ords"])) for p in page["paragraphs"]] == [
        (TEXT, True),
        (f"![osiloskop çıktısı](ek:{aid})", False),
        (TABLE, True),
    ]
    assert sp["reader"].get(f"/api/v1/attachments/{aid}/download").status_code == 200


def test_inline_image_must_be_listed_attachment(sp):  # noqa: F811
    c, pid = sp["contributor"], sp["pid"]
    aid = uploaded(c, pid, [("ekran.png", PNG_A)])[0]["id"]
    r = c.post(f"/api/v1/projects/{pid}/changes", json={"summary": "x", "items": [note_item("Besleme", _body(aid))]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INLINE_IMAGE_MISSING"


def test_inline_image_must_be_image(sp):  # noqa: F811
    c, pid = sp["contributor"], sp["pid"]
    aid = uploaded(c, pid, [("rapor.pdf", PDF)])[0]["id"]
    r = c.post(f"/api/v1/projects/{pid}/changes", json={"summary": "x", "items": [note_item("Besleme", _body(aid), attachments=[aid])]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INLINE_IMAGE_NOT_IMAGE"


def test_export_links_inline_image_to_file(sp):  # noqa: F811
    c, pid = sp["contributor"], sp["pid"]
    aid = uploaded(c, pid, [("ekran.png", PNG_A)])[0]["id"]
    publish_direct(c, create(c, pid, note_item("Besleme", _body(aid), attachments=[aid])))
    z = zipfile.ZipFile(io.BytesIO(sp["reader"].get(f"/api/v1/projects/{pid}/export.zip").content))
    md = z.read("sayfalar/besleme.md").decode()
    assert "![osiloskop çıktısı](../ekler/besleme/1-ekran.png)" in md and "ek:" not in md


def test_search_content_has_no_attachment_id(sp):  # noqa: F811
    from sqlalchemy import select

    from metis.core.db import transaction
    from metis.core.models import SearchDocument

    c, pid = sp["contributor"], sp["pid"]
    aid = uploaded(c, pid, [("ekran.png", PNG_A)])[0]["id"]
    page_id = publish_direct(c, create(c, pid, note_item("Besleme", _body(aid), attachments=[aid])))["published_page_ids"][0]
    with transaction() as db:
        content = db.scalars(select(SearchDocument.content).where(SearchDocument.page_id == page_id)).one()
    assert aid not in content and "[Görsel: osiloskop çıktısı]" in content


def test_inline_image_must_stand_alone_in_canonical_form(sp):  # noqa: F811
    """Görsel bağlantısı kendi satırında ve `![açıklama](ek:<kimlik>)` biçiminde: başka biçim ek kimliğini iddiaya taşırdı."""
    c, pid = sp["contributor"], sp["pid"]
    aid = uploaded(c, pid, [("ekran.png", PNG_A)])[0]["id"]
    for body in (
        f"{TEXT} ![a](ek:{aid}) devam eder.",
        f'{TEXT}\n\n![a](ek:{aid} "başlık")',
        f"{TEXT}\n\n![a](<ek:{aid}>)",
        f"{TEXT}\n\n![a][r]\n\n[r]: ek:{aid}",
        f"| Pin | Görsel |\n| --- | --- |\n| VCC | ![a](ek:{aid}) |",
    ):
        r = c.post(f"/api/v1/projects/{pid}/changes", json={"summary": "x", "items": [note_item("Besleme", body, attachments=[aid])]})
        assert r.status_code == 422 and r.json()["error"]["code"] == "INLINE_IMAGE_FORM", body
