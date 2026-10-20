"""Parolasız (yalnız kullanıcı adıyla) giriş — ürün sahibinin ve ekip liderinin kararı (2026-10-19).

Ekip içi kullanım: yönetici açarsa yönetici olmayan herkes yalnız kullanıcı adıyla girer; ilk girişte hesap açılır ve
Okur başlar. Yönetici hesapları her zaman parolalıdır (yoksa biri yöneticinin adını yazıp her şeyi ele geçirirdi).
Kapalıyken (varsayılan) davranış değişmez.
"""

from __future__ import annotations

from sqlalchemy import select

from metis.core.db import transaction
from metis.core.models import ProjectMember, User
from tests.factories import ADMIN_PASSWORD, create_user, setup_admin


def _login(make_client, username: str, password: str = ""):  # noqa: ANN001, ANN202
    c = make_client()
    r = c.http.post("/api/v1/auth/login", json={"username": username, "password": password})
    if r.status_code == 200:
        c.csrf = r.json()["csrf_token"]
    return c, r


def _enable(admin, on: bool = True):  # noqa: ANN001, ANN202
    r = admin.put("/api/v1/auth/login-settings", json={"passwordless": on})
    assert r.status_code == 200, r.text
    return r.json()


def test_disabled_by_default_requires_password(client, make_client):  # noqa: ANN001
    setup_admin(client)
    assert client.get("/api/v1/auth/methods").json()["passwordless"] is False
    _, r = _login(make_client, "zeynep")
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS"
    with transaction() as db:
        assert db.scalar(select(User).where(User.username == "zeynep")) is None


def test_username_only_creates_reader_account(client, make_client):  # noqa: ANN001
    me = setup_admin(client)
    pid = me["memberships"][0]["project_id"]
    assert _enable(client) == {"passwordless": True}
    assert client.get("/api/v1/auth/methods").json() == {"directory": False, "passwordless": True}
    c, r = _login(make_client, "Zeynep.K")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["username"] == "zeynep.k" and body["user"]["must_change_password"] is False
    assert [(m["project_id"], m["roles"]) for m in body["memberships"]] == [(pid, ["reader"])]
    with transaction() as db:
        user = db.scalar(select(User).where(User.username == "zeynep.k"))
        assert user is not None and user.password_hash == "" and not user.is_admin
    # İkinci giriş aynı hesap; okur yazamaz (rolü yönetici verir).
    _, again = _login(make_client, "zeynep.k")
    assert again.json()["user"]["id"] == body["user"]["id"]
    assert c.post(f"/api/v1/projects/{pid}/changes", json={"summary": "x", "items": []}).status_code in (403, 422)


def test_existing_member_enters_without_password_and_keeps_roles(client, make_client):  # noqa: ANN001
    me = setup_admin(client)
    pid = me["memberships"][0]["project_id"]
    create_user(client, "kemal", ["contributor"], pid, make_client)
    _enable(client)
    _, r = _login(make_client, "kemal")
    assert r.status_code == 200, r.text
    assert r.json()["memberships"][0]["roles"] == ["contributor"]  # mevcut rol korunur
    # Yönetici tarafından açılmış geçici parolalı hesap: parolasız girişte parola değiştirme istenmez.
    r2 = client.post("/api/v1/users", json={"username": "aylin", "display_name": "Aylin", "temporary_password": "Gecici-Parola-2026"})
    assert r2.status_code == 201
    _, r3 = _login(make_client, "aylin")
    assert r3.status_code == 200 and r3.json()["user"]["must_change_password"] is False


def test_admin_always_needs_password(client, make_client):  # noqa: ANN001
    setup_admin(client)
    _enable(client)
    _, r = _login(make_client, "ayse")
    assert r.status_code == 401 and r.json()["error"]["code"] == "PASSWORD_REQUIRED"
    _, wrong = _login(make_client, "ayse", "yanlis-parola")
    assert wrong.json()["error"]["code"] == "INVALID_CREDENTIALS"
    _, ok = _login(make_client, "ayse", ADMIN_PASSWORD)
    assert ok.status_code == 200


def test_promoting_passwordless_user_to_admin_requires_a_password(client, make_client):  # noqa: ANN001
    setup_admin(client)
    _enable(client)
    _, r = _login(make_client, "zeynep")
    uid = r.json()["user"]["id"]
    bad = client.patch(f"/api/v1/users/{uid}", json={"is_admin": True})
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "ADMIN_NEEDS_PASSWORD"
    good = client.patch(f"/api/v1/users/{uid}", json={"is_admin": True, "temporary_password": "Gecici-Parola-2026"})
    assert good.status_code == 200, good.text
    _, now = _login(make_client, "zeynep")
    assert now.json()["error"]["code"] == "PASSWORD_REQUIRED"


def test_inactive_or_invalid_names_cannot_enter_and_only_admin_toggles(client, make_client):  # noqa: ANN001
    me = setup_admin(client)
    pid = me["memberships"][0]["project_id"]
    reader = create_user(client, "okan", ["reader"], pid, make_client)
    assert reader.put("/api/v1/auth/login-settings", json={"passwordless": True}).status_code == 403
    _enable(client)
    for bad in ("a", "ali veli", "x" * 151, "../admin", "zeynep@kurgu"):
        _, r = _login(make_client, bad)
        assert r.status_code in (401, 422), (bad, r.text)
    okan = next(u for u in client.get("/api/v1/users").json() if u["username"] == "okan")
    assert client.patch(f"/api/v1/users/{okan['id']}", json={"active": False}).status_code == 200
    _, r = _login(make_client, "okan")
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"
    # Kapatınca yeniden parola gerekir.
    _enable(client, False)
    _, r = _login(make_client, "zeynep")
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"
    with transaction() as db:
        assert db.scalar(select(ProjectMember).join(User, User.id == ProjectMember.user_id).where(User.username == "zeynep")) is None
