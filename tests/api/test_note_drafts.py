"""Tek adımda taslak (ürün sahibinin kararı 2026-10-19): not, bilginin dayanağıdır.

Not tabanlı öğe (`note: true`) kaydedilince sunucu notu sayfaya bağlı bir uzman notu kaynağına yazar ve her
bloğu kendiliğinden bir iddia yapar (iddia == alıntı == notun birebir aralığı). Yazar alıntı seçmez.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from metis.core.db import transaction
from metis.core.models import Finding, Page, Source
from tests.kb import DEFAULT_SCOPE

B1 = "UART hızı 115200 baud olarak ayarlanır."
B2 = "Akış denetimi kurgusal kartta kapalıdır."
BODY = f"{B1}\n\n{B2}\n"


@pytest.fixture
def sp(team):  # noqa: ANN001, ANN201
    r = team["admin"].patch(f"/api/v1/projects/{team['pid']}", json={"review_policy": "self_publish"})
    assert r.status_code == 200, r.text
    return team


def note_item(title: str, body: str, **kw) -> dict:  # noqa: ANN003
    return {"note": True, "title": title, "summary": "", "body_md": body, "scope": DEFAULT_SCOPE, **kw}


def create(client, pid: str, item: dict) -> dict:  # noqa: ANN001
    r = client.post(f"/api/v1/projects/{pid}/changes", json={"summary": item["title"], "items": [item]})
    assert r.status_code == 201, r.text
    return r.json()


def update(client, change: dict, item: dict) -> dict:  # noqa: ANN001
    r = client.put(f"/api/v1/changes/{change['id']}", json={"expected_hash": change["hash"], "items": [item]})
    assert r.status_code == 200, r.text
    return r.json()


def publish_direct(client, change: dict) -> dict:  # noqa: ANN001
    assert client.post(f"/api/v1/changes/{change['id']}/check").status_code == 200
    change = client.get(f"/api/v1/changes/{change['id']}").json()
    r = client.post(f"/api/v1/changes/{change['id']}/publish-direct", json={"hash": change["hash"], "acknowledge_issues": True})
    assert r.status_code == 200, r.text
    return r.json()


def proposed(change: dict) -> dict:
    return change["items"][0]["proposed"]


def note_source(page_id: str) -> Source:
    with transaction() as db:
        page = db.get(Page, page_id)
        assert page is not None and page.note_source_id is not None
        src = db.get(Source, page.note_source_id)
        assert src is not None
        db.expunge(src)
        return src


def test_note_draft_creates_claims_from_blocks(sp):
    ch = create(sp["contributor"], sp["pid"], note_item("UART ayarları", BODY))
    claims = proposed(ch)["claims"]
    assert [c["statement"] for c in claims] == [B1, B2]
    for c in claims:
        assert c["kind"] == "expert_statement" and c["verbatim"]
        assert [e["quote"] for e in c["evidence"]] == [c["statement"]]
    src = note_source(ch["items"][0]["page_id"])
    assert src.kind == "note" and src.title == "UART ayarları" and src.current_revision_no == 1
    assert {e["source_id"] for c in claims for e in c["evidence"]} == {str(src.id)}


def test_note_resave_same_text_reuses_source_revision(sp):
    ch = create(sp["contributor"], sp["pid"], note_item("UART ayarları", BODY))
    page_id = ch["items"][0]["page_id"]  # taslak düzenlenirken aynı sayfa (editör bunu gönderir)
    ch = update(sp["contributor"], ch, note_item("UART ayarları (gözden geçirildi)", BODY, page_id=page_id))
    assert ch["items"][0]["page_id"] == page_id
    assert note_source(page_id).current_revision_no == 1
    ch = update(sp["contributor"], ch, note_item("UART ayarları", BODY + "\nYeni satır 3,3 V.\n", page_id=page_id))
    assert note_source(page_id).current_revision_no == 2


def test_note_text_change_new_source_revision_without_findings(sp):
    from metis.modules.health.maintenance import deterministic_scan

    c, pid = sp["contributor"], sp["pid"]
    out = publish_direct(c, create(c, pid, note_item("UART ayarları", BODY)))
    page_id = out["published_page_ids"][0]
    page = c.get(f"/api/v1/pages/{page_id}").json()
    edit = note_item("UART ayarları", f"{B1}\n\nAkış denetimi açıktır.\n", page_id=page_id, base_revision_id=page["revision"]["id"])
    publish_direct(c, create(c, pid, edit))
    assert note_source(page_id).current_revision_no == 2
    with transaction() as db:
        assert db.get(Page, page_id).freshness == "current"
        assert deterministic_scan(db, db.get(Page, page_id).project_id, None)["source_changed"] == 0
        assert not db.scalars(select(Finding).where(Finding.kind == "source_changed")).all()


def test_note_with_claims_rejected(sp):
    item = note_item("UART", BODY, claims=[{"statement": B1, "evidence": []}])
    r = sp["contributor"].post(f"/api/v1/projects/{sp['pid']}/changes", json={"items": [item]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_empty_note_saves_but_cannot_publish(sp):
    c = sp["contributor"]
    ch = create(c, sp["pid"], note_item("Boş taslak", "  \n\n "))
    assert proposed(ch)["claims"] == []
    assert "no_claims" in ch["approve_blockers"]
    assert c.post(f"/api/v1/changes/{ch['id']}/check").status_code == 200
    ch = c.get(f"/api/v1/changes/{ch['id']}").json()
    r = c.post(f"/api/v1/changes/{ch['id']}/publish-direct", json={"hash": ch["hash"], "acknowledge_issues": True})
    assert r.status_code == 422 and r.json()["error"]["code"] == "EVIDENCE_REQUIRED"


def test_unpublished_note_source_hidden_from_other_members(sp):
    c, reader, pid = sp["contributor"], sp["reader"], sp["pid"]
    ch = create(c, pid, note_item("UART ayarları", BODY))
    sid = note_source(ch["items"][0]["page_id"]).id
    assert c.get(f"/api/v1/sources/{sid}").status_code == 200
    assert reader.get(f"/api/v1/sources/{sid}").status_code == 404
    assert sp["reviewer"].get(f"/api/v1/sources/{sid}").status_code == 200  # bağımsız incelemede taslağı açabilmeli
    assert str(sid) not in c.get(f"/api/v1/projects/{pid}/sources").text  # not kaynakları listelerde görünmez
    publish_direct(c, ch)
    assert reader.get(f"/api/v1/sources/{sid}").status_code == 200


def test_note_page_readable_with_paragraph_claims(sp):
    c, pid = sp["contributor"], sp["pid"]
    out = publish_direct(c, create(c, pid, note_item("UART ayarları", BODY)))
    page = sp["reader"].get(f"/api/v1/pages/{out['published_page_ids'][0]}").json()
    assert [c_["statement"] for c_ in page["revision"]["claims"]] == [B1, B2]
    assert all(p["claim_ords"] for p in page["paragraphs"])


def test_page_detail_marks_note_based(sp):
    from tests.api.test_attachments import PNG_A, uploaded

    c, pid = sp["contributor"], sp["pid"]
    aid = uploaded(c, pid, [("a.png", PNG_A)])[0]["id"]
    out = publish_direct(c, create(c, pid, note_item("UART ayarları", BODY, attachments=[aid])))
    page = sp["reader"].get(f"/api/v1/pages/{out['published_page_ids'][0]}").json()
    assert page["note_based"] is True
    assert [a["id"] for a in page["revision"]["attachments"]] == [aid]


def test_evidence_view_note_source_has_page_and_attachments(sp):
    from tests.api.test_attachments import PDF, uploaded

    c, pid = sp["contributor"], sp["pid"]
    aid = uploaded(c, pid, [("rapor.pdf", PDF)])[0]["id"]
    out = publish_direct(c, create(c, pid, note_item("UART ayarları", BODY, attachments=[aid])))
    page_id = out["published_page_ids"][0]
    claim = sp["reader"].get(f"/api/v1/pages/{page_id}").json()["revision"]["claims"][0]
    ev = sp["reader"].get(f"/api/v1/evidence/{claim['evidence'][0]['evidence_id']}", params={"claim_id": claim["id"]}).json()
    assert ev["note_page_id"] == page_id
    assert [a["id"] for a in ev["attachments"]] == [aid]
