"""Eski yöntemden kalan bağımsız kaynaklar (hiçbir bilgiye bağlanmamış) yükseltmede taslağa dönüşür (2026-10-19).

Kullanıcının girdiği hiçbir şey kaybolmaz: metin → not, dosya (görsel/PDF) → ek; kaynak silinmez; ikinci çalıştırma
hiçbir şey yapmaz. Bir bilgiye dayanak olmuş kaynaklar dönüştürülmez.
"""

from __future__ import annotations

from sqlalchemy import select

from metis.core.db import transaction
from metis.core.models import Attachment, ChangeSet, Page, PageRevisionAttachment, Source
from tests.kb import add_note, publish_note, upload

PNG = b"\x89PNG\r\n\x1a\n" + b"\x03" * 64
TEXT = "Kurgusal kartta ön seçici geçiş bölgesine göre eşik 3 dB düzeltilir; 1. görselde ölçüm var."


def convert() -> int:
    from metis.modules.notes.service import convert_standalone_sources

    with transaction() as db:
        return convert_standalone_sources(db)


def test_standalone_note_with_image_becomes_draft(team):
    c, pid = team["contributor"], team["pid"]
    r = upload(c, pid, "olcum.png", PNG, title="Eşik düzeltmesi", kind="note", text=TEXT)
    assert r.status_code == 201, r.text
    src_id = r.json()["source"]["id"]
    assert convert() == 1
    with transaction() as db:
        page = db.scalar(select(Page).where(Page.note_source_id.is_not(None)))
        assert page is not None and page.published_revision_id is None and page.owner_id is not None
        change = db.scalar(select(ChangeSet).where(ChangeSet.state == "draft"))
        assert change is not None and change.author_id == page.owner_id
        assert change.detail.get("converted_from_source") == src_id
        atts = db.execute(select(Attachment).join(PageRevisionAttachment)).scalars().all()
        assert [(a.filename, a.media_type) for a in atts] == [("olcum.png", "image/png")]
        assert db.get(Source, src_id).deleted_at is None  # kaynak silinmez
    detail = c.get(f"/api/v1/changes/{change.id}").json()
    proposed = detail["items"][0]["proposed"]
    assert proposed["title"] == "Eşik düzeltmesi" and proposed["body_md"] == TEXT
    assert [cl["statement"] for cl in proposed["claims"]] == [TEXT]
    assert convert() == 0  # tekrar çalıştırma bir şey yapmaz


def test_text_only_and_pdf_sources_convert_used_sources_do_not(team):
    from tests.pdfgen import make_pdf

    c, r_, pid = team["contributor"], team["reviewer"], team["pid"]
    add_note(c, pid, "Yalnız metin notu", "Kurgusal çekirdek beslemesi 1,0 V.")
    assert upload(c, pid, "rapor.pdf", make_pdf(["Kurgusal rapor."]), title="Rapor").status_code == 201
    publish_note(c, r_, pid, "Yayımlanmış bilgi", "UART hızı 115200 baud.")  # kaynağı bir bilgiye dayanak
    assert convert() == 2
    with transaction() as db:
        drafts = db.scalars(select(ChangeSet).where(ChangeSet.state == "draft")).all()
        assert sorted(d.detail["converted_from_source"] is not None for d in drafts) == [True, True]
