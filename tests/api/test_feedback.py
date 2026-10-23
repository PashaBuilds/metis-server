"""Geri bildirim (2026-10-23, ürün sahibinin isteği): kullanıcılar hata ya da istek yazar, ekran görüntüsü ekleyebilir.

Herkes (okur dahil) yazar ve giriş yapmış herkes hepsini görür; durumu ve cevabı yalnız yönetici verir. Yazan kendi
bildirimini, yönetici her bildirimi silebilir. Görseller tek tek yüklenir (vekilin istek boyutu sınırı dosya başına).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from metis.core.db import transaction
from tests.factories import create_user, setup_admin

PNG = b"\x89PNG\r\n\x1a\n" + b"\x03" * 64  # kurgusal: yalnız imza denetlenir
JPG = b"\xff\xd8\xff" + b"\x04" * 64


@pytest.fixture
def fb(client, make_client):  # noqa: ANN001, ANN201
    me = setup_admin(client)
    pid = me["memberships"][0]["project_id"]
    return {
        "admin": client,
        "reader": create_user(client, "okur", ["reader"], pid, make_client),
        "other": create_user(client, "katki", ["contributor"], pid, make_client),
        "anon": make_client(),
    }


def upload(c, files: list[tuple[str, bytes]]):  # noqa: ANN001, ANN201
    return c.post("/api/v1/feedback/images", files=[("files", f) for f in files])


def send(c, kind: str = "bug", body: str = "Katkı eklerken kaydet düğmesi hata verdi.", image_ids: list[str] | None = None):  # noqa: ANN001, ANN201
    return c.post("/api/v1/feedback", json={"kind": kind, "text": body, "image_ids": image_ids or []})


def test_reader_writes_bug_with_screenshots_everyone_sees(fb):  # noqa: ANN001
    imgs = upload(fb["reader"], [("ekran.png", PNG), ("ikinci.jpg", JPG)])
    assert imgs.status_code == 201, imgs.text
    ids = [i["id"] for i in imgs.json()]
    r = send(fb["reader"], image_ids=ids)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["kind"] == "bug" and out["status"] == "new" and out["reply"] == ""
    assert out["author_name"] == "Okur" and [i["filename"] for i in out["images"]] == ["ekran.png", "ikinci.jpg"]

    listed = fb["other"].get("/api/v1/feedback")
    assert listed.status_code == 200
    assert [f["id"] for f in listed.json()] == [out["id"]]
    assert listed.json()[0]["can_delete"] is False
    img = fb["other"].get(f"/api/v1/feedback/images/{ids[0]}")
    assert img.status_code == 200 and img.content == PNG and img.headers["content-type"] == "image/png"


def test_request_kind_and_newest_first(fb):  # noqa: ANN001
    first = send(fb["reader"], "request", "Menüde arama düğmesi solda olsun.").json()
    second = send(fb["other"], "bug").json()
    assert first["kind"] == "request"
    assert [f["id"] for f in fb["reader"].get("/api/v1/feedback").json()] == [second["id"], first["id"]]


def test_newest_first_even_with_equal_timestamps(fb):  # noqa: ANN001
    # Windows saatinin çözünürlüğünde art arda gelen bildirimlerin zamanı eşit olabilir (CI'da görüldü).
    ids = [send(fb["reader"], body=f"Kurgusal bildirim {n}").json()["id"] for n in range(6)]
    with transaction() as db:
        db.execute(text("UPDATE feedback SET created_at = '2026-10-23T12:00:00+00'"))
    assert [f["id"] for f in fb["reader"].get("/api/v1/feedback").json()] == ids[::-1]


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"kind": "question", "text": "x"}, "kind"),
        ({"kind": "bug", "text": "   "}, "text"),
        ({"kind": "bug", "text": "a" * 5001}, "text"),
    ],
)
def test_validation(fb, payload, field):  # noqa: ANN001
    r = fb["reader"].post("/api/v1/feedback", json=payload)
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert field in r.text


def test_only_images_up_to_five(fb):  # noqa: ANN001
    bad = upload(fb["reader"], [("rapor.pdf", b"%PDF-1.4 kurgusal")])
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "UNSUPPORTED_FILE"
    assert upload(fb["reader"], [(f"{n}.png", PNG) for n in range(6)]).status_code == 422
    ids = [i["id"] for n in range(6) for i in upload(fb["reader"], [(f"{n}.png", PNG)]).json()]
    r = send(fb["reader"], image_ids=ids)
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_cannot_use_someone_elses_or_used_image(fb):  # noqa: ANN001
    mine = upload(fb["reader"], [("a.png", PNG)]).json()[0]["id"]
    assert send(fb["other"], image_ids=[mine]).status_code == 404
    # Bağlanmamış görsel yalnız yükleyene görünür.
    assert fb["other"].get(f"/api/v1/feedback/images/{mine}").status_code == 404
    assert fb["reader"].get(f"/api/v1/feedback/images/{mine}").status_code == 200
    assert send(fb["reader"], image_ids=[mine]).status_code == 201
    assert send(fb["reader"], image_ids=[mine]).status_code == 404


def test_only_admin_sets_status_and_reply(fb):  # noqa: ANN001
    fid = send(fb["reader"]).json()["id"]
    r = fb["reader"].patch(f"/api/v1/feedback/{fid}", json={"status": "done"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "ADMIN_REQUIRED"
    r = fb["admin"].patch(f"/api/v1/feedback/{fid}", json={"status": "done", "reply": "2.0.17'de düzeltildi."})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done" and r.json()["reply"] == "2.0.17'de düzeltildi." and r.json()["reply_by_name"] == "Ayşe Yönetici"
    seen = fb["other"].get("/api/v1/feedback").json()[0]
    assert seen["status"] == "done" and seen["reply"] == "2.0.17'de düzeltildi."
    bad = fb["admin"].patch(f"/api/v1/feedback/{fid}", json={"status": "kapandi"})
    assert bad.status_code == 422


def test_author_or_admin_deletes(fb):  # noqa: ANN001
    img = upload(fb["reader"], [("a.png", PNG)]).json()[0]["id"]
    mine = send(fb["reader"], image_ids=[img]).json()
    assert mine["can_delete"] is True
    assert fb["other"].delete(f"/api/v1/feedback/{mine['id']}").status_code == 403
    assert fb["reader"].delete(f"/api/v1/feedback/{mine['id']}").status_code == 204
    assert fb["other"].get("/api/v1/feedback").json() == []
    assert fb["other"].get(f"/api/v1/feedback/images/{img}").status_code == 404
    assert fb["admin"].patch(f"/api/v1/feedback/{mine['id']}", json={"status": "done"}).status_code == 404
    theirs = send(fb["other"]).json()["id"]
    assert fb["admin"].delete(f"/api/v1/feedback/{theirs}").status_code == 204


def test_requires_login(fb):  # noqa: ANN001
    assert fb["anon"].get("/api/v1/feedback").status_code == 401
    assert fb["anon"].post("/api/v1/feedback", json={"kind": "bug", "text": "x"}).status_code in (401, 403)
