"""Açıklayıcı görseller: revizyona bağlı, değişmez, hash'e dahil, erişim kontrollü; kanıt değildir."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from metis.core.db import transaction
from tests.kb import DEFAULT_SCOPE, add_note, approve, evidence, publish, submit, upload

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64  # kurgusal: yalnız imza denetlenir
NOTE = "Konnektör J3 kartın sol kenarındadır."


def _image(client, pid, title="Kart üstten görünüm", acl=None):  # noqa: ANN001, ANN202
    meta = {"title": title, "kind": "image", "text": "", "scope": DEFAULT_SCOPE, "acl": acl or []}
    r = client.post(
        f"/api/v1/projects/{pid}/sources", files={"meta": (None, json.dumps(meta)), "file": ("kart.png", PNG)}
    )
    assert r.status_code == 201, r.text
    return r.json()


def _item(ev_id, figures, body=None, caption_title="Konnektör yeri"):  # noqa: ANN001, ANN202
    return {
        "title": caption_title,
        "summary": "Konnektör yeri özeti",
        "body_md": body if body is not None else f"{NOTE}\n\n{{{{görsel 1}}}}",
        "scope": DEFAULT_SCOPE,
        "claims": [{"statement": NOTE, "evidence": [{"evidence_id": ev_id, "quote": NOTE}]}],
        "figures": figures,
    }


def _note_ev(team):  # noqa: ANN001, ANN202
    c, pid = team["contributor"], team["pid"]
    src = add_note(c, pid, "Kart notu", NOTE)
    return evidence(c, src["revision"]["id"], NOTE)["id"]


def test_figure_is_published_inline_and_downloadable(team):
    c, pid = team["contributor"], team["pid"]
    img = _image(c, pid)
    ev = _note_ev(team)
    figs = [{"source_revision_id": img["revision"]["id"], "caption": "Kartın üstten görünümü"}]
    r = c.post(f"/api/v1/projects/{pid}/changes", json={"items": [_item(ev, figs)]})
    assert r.status_code == 201, r.text
    ch = publish(team["reviewer"], approve(team["reviewer"], submit(c, r.json()["id"]))["id"])
    page = team["reader"].get(f"/api/v1/pages/{ch['published_page_ids'][0]}").json()
    figs_out = page["revision"]["figures"]
    assert [(f["ord"], f["caption"], f["media_type"]) for f in figs_out] == [(1, "Kartın üstten görünümü", "image/png")]
    # Yer tutucu kendi paragrafıdır ve kanıt şeridi almaz.
    assert {"text": "{{görsel 1}}", "claim_ords": []} in page["paragraphs"]
    dl = team["reader"].get(f"/api/v1/source-revisions/{figs_out[0]['source_revision_id']}/download")
    assert dl.status_code == 200 and dl.headers["content-type"] == "image/png"


def test_figure_must_be_image_and_placeholder_must_exist(team):
    c, pid = team["contributor"], team["pid"]
    ev = _note_ev(team)
    doc = add_note(c, pid, "Metin", "Bu bir görsel değil.")
    r = c.post(
        f"/api/v1/projects/{pid}/changes",
        json={"items": [_item(ev, [{"source_revision_id": doc["revision"]["id"], "caption": ""}])]},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "FIGURE_NOT_IMAGE"
    img = _image(c, pid)
    figs = [{"source_revision_id": img["revision"]["id"], "caption": ""}]
    r = c.post(f"/api/v1/projects/{pid}/changes", json={"items": [_item(ev, figs, body=f"{NOTE}\n\n{{{{görsel 2}}}}")]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "FIGURE_MISSING"


def test_figure_caption_is_part_of_revision_hash(team):
    c, pid = team["contributor"], team["pid"]
    img = _image(c, pid)
    ev = _note_ev(team)
    hashes = []
    for cap in ("Üstten görünüm", "Alttan görünüm"):
        r = c.post(
            f"/api/v1/projects/{pid}/changes",
            json={"items": [_item(ev, [{"source_revision_id": img["revision"]["id"], "caption": cap}])]},
        )
        assert r.status_code == 201, r.text
        hashes.append(r.json()["items"][0]["proposed"]["hash"])
    assert hashes[0] != hashes[1]


def test_unreadable_figure_source_hides_page(team):
    """Görselin kaynağına erişimi olmayan, sayfayı da göremez (iddia kanıtlarıyla aynı kural)."""
    c, pid = team["contributor"], team["pid"]
    img = _image(c, pid, acl=[team["reviewer"].user["id"]])
    ev = _note_ev(team)
    r = c.post(
        f"/api/v1/projects/{pid}/changes",
        json={"items": [_item(ev, [{"source_revision_id": img["revision"]["id"], "caption": "Gizli"}])]},
    )
    assert r.status_code == 201, r.text
    ch = publish(team["reviewer"], approve(team["reviewer"], submit(c, r.json()["id"]))["id"])
    page_id = ch["published_page_ids"][0]
    assert team["reviewer"].get(f"/api/v1/pages/{page_id}").status_code == 200
    assert team["reader"].get(f"/api/v1/pages/{page_id}").status_code == 404
    assert team["reader"].get(f"/api/v1/projects/{pid}/pages").json()["total"] == 0


def test_new_image_revision_marks_page_dependency_changed(team):
    c, pid = team["contributor"], team["pid"]
    img = _image(c, pid)
    ev = _note_ev(team)
    r = c.post(
        f"/api/v1/projects/{pid}/changes",
        json={"items": [_item(ev, [{"source_revision_id": img["revision"]["id"], "caption": "Rev A"}])]},
    )
    ch = publish(team["reviewer"], approve(team["reviewer"], submit(c, r.json()["id"]))["id"])
    meta = {"expected_revision": 1, "text": ""}
    r = c.post(
        f"/api/v1/sources/{img['source']['id']}/revisions",
        files={"meta": (None, json.dumps(meta)), "file": ("kart-b.png", PNG + b"\x01")},
    )
    assert r.status_code == 201, r.text
    page = team["reader"].get(f"/api/v1/pages/{ch['published_page_ids'][0]}").json()
    assert page["freshness"] == "dependency_changed"


def test_figures_are_immutable(team):
    c, pid = team["contributor"], team["pid"]
    img = _image(c, pid)
    ev = _note_ev(team)
    r = c.post(
        f"/api/v1/projects/{pid}/changes",
        json={"items": [_item(ev, [{"source_revision_id": img["revision"]["id"], "caption": "İlk"}])]},
    )
    assert r.status_code == 201
    with pytest.raises(DBAPIError) as exc, transaction() as db:
        db.execute(text("UPDATE page_revision_figures SET caption = 'kurcalandı'"))
    assert "METIS_IMMUTABLE" in str(exc.value)


def test_upload_helper_still_rejects_fake_image(team):
    r = upload(team["contributor"], team["pid"], "sahte.png", b"not a png", kind="image")
    assert r.status_code == 422
