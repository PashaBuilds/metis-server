"""Son incelemenin bulguları (2026-10-19, 2.0.10 öncesi).

- Uzun paragraf iddia sınırını (4000) aşınca 500 değil, cümle sınırından bölünür.
- İddiasız (boş notlu) taslağın ekleri ve kendisi yalnız yazara, steward ve reviewer'a görünür.
- Yayındaki not tabanlı bilginin düzenleme taslağı kaydedilince yayındaki sayfa değişmez: kaynak "güncel değil"
  olmaz, başlık sızmaz, taslak notu diğer üyelere okunmaz. Yayımlanınca yeni not görünür.
"""

from __future__ import annotations

from metis.core.db import transaction
from metis.core.models import Page
from tests.api.test_attachments import PNG_A, uploaded
from tests.api.test_note_drafts import BODY, create, note_item, publish_direct, sp, update  # noqa: F401 — fixture

SENTENCE = "Kurgusal ölçümde besleme gerilimi 3,3 V ve dalgalanma 12 mV olarak kaydedildi. "
LONG = (SENTENCE * 70).strip()  # ~5800 karakter, boş satırsız tek paragraf


def test_long_paragraph_is_split_within_claim_limit(sp):  # noqa: F811
    assert len(LONG) > 4000
    ch = create(sp["contributor"], sp["pid"], note_item("Uzun ölçüm notu", LONG))
    claims = ch["items"][0]["proposed"]["claims"]
    assert len(claims) == 2
    assert all(len(c["statement"]) <= 4000 for c in claims)
    assert claims[0]["statement"].endswith(".")
    assert " ".join(c["statement"] for c in claims) == LONG


def test_empty_note_draft_and_attachment_hidden_from_other_members(sp):  # noqa: F811
    c, pid = sp["contributor"], sp["pid"]
    aid = uploaded(c, pid, [("a.png", PNG_A)])[0]["id"]
    ch = create(c, pid, note_item("Yalnız görsel", "", attachments=[aid]))
    assert ch["items"][0]["proposed"]["claims"] == []
    assert c.get(f"/api/v1/attachments/{aid}/download").status_code == 200
    assert sp["reviewer"].get(f"/api/v1/attachments/{aid}/download").status_code == 200
    assert sp["reader"].get(f"/api/v1/attachments/{aid}/download").status_code == 404
    assert sp["reader"].get(f"/api/v1/changes/{ch['id']}").status_code == 404


def _published(page_id: str) -> str:
    with transaction() as db:
        return str(db.get(Page, page_id).published_revision_id)


def _page_evidence(client, page_id: str) -> list[dict]:  # noqa: ANN001
    r = client.get(f"/api/v1/pages/{page_id}")
    assert r.status_code == 200, r.text
    return [e for c in r.json()["revision"]["claims"] for e in c["evidence"]]


def test_edit_draft_does_not_change_published_note_page(sp):  # noqa: F811
    c, pid, reader = sp["contributor"], sp["pid"], sp["reader"]
    first = create(c, pid, note_item("UART ayarları", BODY))
    page_id = first["items"][0]["page_id"]
    publish_direct(c, first)
    with transaction() as db:
        source_id = str(db.get(Page, page_id).note_source_id)

    edit = create(c, pid, note_item("UART ayarları (taslak başlık)", BODY + "\nGİZLİTASLAK satırı.\n", page_id=page_id, base_revision_id=_published(page_id)))
    draft_evidence = [e["evidence_id"] for cl in edit["items"][0]["proposed"]["claims"] for e in cl["evidence"]]

    evs = _page_evidence(reader, page_id)
    assert evs and all(e["source_is_current"] for e in evs)
    assert {e["source_title"] for e in evs} == {"UART ayarları"}
    detail = reader.get(f"/api/v1/sources/{source_id}")
    if detail.status_code == 200:
        assert "GİZLİTASLAK" not in detail.json()["text"]
        assert detail.json()["title"] == "UART ayarları"
    for ev_id in draft_evidence:
        r = reader.get(f"/api/v1/evidence/{ev_id}")
        assert r.status_code == 404 or "GİZLİTASLAK" not in r.text

    publish_direct(c, c.get(f"/api/v1/changes/{edit['id']}").json())
    evs = _page_evidence(reader, page_id)
    assert {e["source_title"] for e in evs} == {"UART ayarları (taslak başlık)"}
    assert all(e["source_is_current"] for e in evs)
    assert any("GİZLİTASLAK" in reader.get(f"/api/v1/evidence/{e['evidence_id']}").text for e in evs)


def test_two_concurrent_edit_drafts_stay_current(sp):  # noqa: F811
    c, pid = sp["contributor"], sp["pid"]
    first = create(c, pid, note_item("SPI notu", BODY))
    page_id = first["items"][0]["page_id"]
    publish_direct(c, first)
    base = _published(page_id)
    a = create(c, pid, note_item("SPI notu", BODY + "\nA satırı.\n", page_id=page_id, base_revision_id=base))
    create(c, pid, note_item("SPI notu", BODY + "\nB satırı.\n", page_id=page_id, base_revision_id=base))
    a = c.get(f"/api/v1/changes/{a['id']}").json()
    assert all(e["source_is_current"] for cl in a["items"][0]["proposed"]["claims"] for e in cl["evidence"])
    assert update(c, a, note_item("SPI notu", BODY + "\nA satırı.\n", page_id=page_id, base_revision_id=base))
