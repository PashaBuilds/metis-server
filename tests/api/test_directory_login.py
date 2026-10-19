"""Şirket hesabıyla giriş (Active Directory / LDAPS) — ürün sahibinin isteği 2026-10-19.

Kullanıcı Windows'a girdiği kullanıcı adı ve parolayla girer; ilk girişte METIS hesabı kendiliğinden oluşur, rol
bekler. Hiçbir parola saklanmaz. Dizin, kurgusal kayıtlarla sahte bir bağlantı nesnesiyle taklit edilir
(`metis.modules.directory.ldap._connect`); gerçek ldap3 yolu ulaşılamayan sunucu testiyle sınanır.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator

import pytest
from sqlalchemy import select, text

from metis.core.db import transaction
from metis.core.models import ProjectMember, User
from tests.factories import ADMIN_PASSWORD, setup_admin

HTTPS = "https://localhost:8000"
DOMAIN = "kurgu.test"
GROUP = "CN=METIS Kullanicilari,OU=Gruplar,DC=kurgu,DC=test"
PW = "Kurgusal-Dizin-Parolasi-1"


class FakeDirectory:
    """Kurgusal dizin: UPN (ad@kurgu.test) ya da NetBIOS (KURGU\\ad) ile bağlanma, kişinin kendi kaydını okuma."""

    def __init__(self) -> None:
        self.people: dict[str, dict] = {}
        self.binds: list[str] = []
        self.down = False

    def add(self, sam: str, password: str, name: str, groups: list[str] | None = None, guid: str | None = None) -> None:
        self.people[sam.lower()] = {
            "dn": f"CN={name},OU=Kisiler,DC=kurgu,DC=test",
            "password": password,
            "attributes": {
                "sAMAccountName": sam,
                "displayName": name,
                "mail": f"{sam}@{DOMAIN}",
                "objectGUID": guid or "{" + f"{abs(hash(sam)):032x}"[:32] + "}",
                "memberOf": groups or [],
            },
        }

    def connect(self, cfg, bind_name: str, password: str):  # noqa: ANN001, ANN201
        directory = self

        class Conn:
            result: dict = {}
            response: list = []

            def bind(self) -> bool:
                if directory.down:
                    from metis.modules.directory.ldap import DirectoryUnavailable

                    raise DirectoryUnavailable("kurgusal: sunucu kapalı")
                directory.binds.append(bind_name)
                sam = bind_name.split("\\")[-1].split("@")[0].lower()
                person = directory.people.get(sam)
                good_name = bind_name.lower() in (f"{sam}@{DOMAIN}", f"kurgu\\{sam}")
                ok = bool(person and good_name and password and person["password"] == password)
                self.result = {"result": 0 if ok else 49, "description": "success" if ok else "invalidCredentials"}
                return ok

            def search(self, base: str, flt: str, attributes=None) -> bool:  # noqa: ANN001
                m = re.search(r"sAMAccountName=([^)]+)\)", flt)
                person = directory.people.get(m.group(1).lower()) if m else None
                found = bool(person and person["dn"].lower().endswith(base.lower()))
                self.response = [{"type": "searchResEntry", "dn": person["dn"], "attributes": person["attributes"]}] if found else []
                return found

            def unbind(self) -> None:
                pass

        return Conn()


@pytest.fixture
def directory(monkeypatch) -> FakeDirectory:  # noqa: ANN001
    fake = FakeDirectory()
    from metis.modules.directory import ldap

    monkeypatch.setattr(ldap, "_connect", fake.connect)
    return fake


@pytest.fixture
def https_app() -> Iterator[object]:
    from metis.app import create_app
    from metis.core.config import reset_settings_cache

    old = os.environ["METIS_PUBLIC_URL"]
    os.environ["METIS_PUBLIC_URL"] = HTTPS
    reset_settings_cache()
    try:
        yield create_app()
    finally:
        os.environ["METIS_PUBLIC_URL"] = old
        reset_settings_cache()


class Client:
    def __init__(self, app, base: str = HTTPS) -> None:  # noqa: ANN001
        from fastapi.testclient import TestClient

        self.http = TestClient(app, base_url=base, headers={"Origin": base}, raise_server_exceptions=False)
        self.csrf = ""

    def _h(self) -> dict:
        return {"X-CSRF-Token": self.csrf} if self.csrf else {}

    def get(self, url: str):  # noqa: ANN201
        return self.http.get(url)

    def post(self, url: str, json=None):  # noqa: ANN001, ANN201
        return self.http.post(url, json=json, headers=self._h())

    def put(self, url: str, json=None):  # noqa: ANN001, ANN201
        return self.http.put(url, json=json, headers=self._h())

    def patch(self, url: str, json=None):  # noqa: ANN001, ANN201
        return self.http.patch(url, json=json, headers=self._h())

    def login(self, username: str, password: str):  # noqa: ANN201
        r = self.http.post("/api/v1/auth/login", json={"username": username, "password": password})
        if r.status_code == 200:
            self.csrf = r.json()["csrf_token"]
        return r


SETTINGS = {
    "enabled": True,
    "server_url": "ldaps://dc1.kurgu.test",
    "domain": DOMAIN,
    "base_dn": "",
    "group_dn": "",
    "new_user_role": "none",
}


@pytest.fixture
def admin(https_app) -> Client:  # noqa: ANN001
    c = Client(https_app)
    setup_admin(c)
    return c


def enable(admin: Client, **over) -> dict:  # noqa: ANN003
    r = admin.put("/api/v1/directory", json={**SETTINGS, **over})
    assert r.status_code == 200, r.text
    return r.json()


def test_first_login_creates_pending_user_and_stores_no_password(https_app, admin, directory):  # noqa: ANN001
    directory.add("ayse.k", PW, "Ayşe Kurgu")
    enable(admin)
    assert Client(https_app).get("/api/v1/auth/methods").json() == {"directory": True}
    u = Client(https_app)
    r = u.login("ayse.k", PW)
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["user"]["username"] == "ayse.k" and me["user"]["display_name"] == "Ayşe Kurgu"
    assert me["user"]["auth_source"] == "directory" and me["user"]["must_change_password"] is False
    assert me["memberships"] == []  # rol bekler
    assert directory.binds == [f"ayse.k@{DOMAIN}"]
    with transaction() as db:
        user = db.scalar(select(User).where(User.username == "ayse.k"))
        assert user is not None and user.password_hash == "" and user.external_id
        dump = " ".join(str(v) for row in db.execute(text("SELECT * FROM users")).all() for v in row)
        dump += " ".join(str(v) for row in db.execute(text("SELECT * FROM audit_events")).all() for v in row)
        dump += " ".join(str(v) for row in db.execute(text("SELECT * FROM login_attempts")).all() for v in row)
        assert PW not in dump
    # Yönetici yeni geleni kullanıcı listesinde görür, rol verir.
    users = {x["username"]: x for x in admin.get("/api/v1/users").json()}
    assert users["ayse.k"]["auth_source"] == "directory" and users["ayse.k"]["pending_role"] is True
    assert users["ayse"]["pending_role"] is False  # yerel yönetici
    # İkinci giriş aynı hesap; dizindeki ad değişikliği yansır.
    directory.people["ayse.k"]["attributes"]["displayName"] = "Ayşe K. Kurgu"
    again = Client(https_app).login("KURGU\\ayse.k", PW)
    assert again.status_code == 200 and again.json()["user"]["id"] == me["user"]["id"]
    assert again.json()["user"]["display_name"] == "Ayşe K. Kurgu"
    assert Client(https_app).login(f"ayse.k@{DOMAIN}", PW).json()["user"]["id"] == me["user"]["id"]


def test_wrong_or_empty_password_rejected_and_empty_never_reaches_directory(https_app, admin, directory):  # noqa: ANN001
    directory.add("ayse.k", PW, "Ayşe Kurgu")
    enable(admin)
    assert Client(https_app).login("ayse.k", "yanlis-parola").json()["error"]["code"] == "INVALID_CREDENTIALS"
    binds = len(directory.binds)
    r = Client(https_app).login("ayse.k", "")
    assert r.status_code in (401, 422)
    assert len(directory.binds) == binds  # boş parola = anonim bağlanma; dizine hiç gönderilmez
    with transaction() as db:
        assert db.scalar(select(User).where(User.username == "ayse.k")) is None


def test_group_restriction_and_reader_role_for_newcomers(https_app, admin, directory):  # noqa: ANN001
    directory.add("ayse.k", PW, "Ayşe Kurgu", groups=[GROUP])
    directory.add("bora.k", PW, "Bora Kurgu", groups=["CN=Baska,DC=kurgu,DC=test"])
    enable(admin, group_dn=GROUP.lower(), new_user_role="reader")
    assert Client(https_app).login("bora.k", PW).json()["error"]["code"] == "INVALID_CREDENTIALS"
    r = Client(https_app).login("ayse.k", PW)
    assert r.status_code == 200, r.text
    assert [m["roles"] for m in r.json()["memberships"]] == [["reader"]]
    assert {x["username"]: x for x in admin.get("/api/v1/users").json()}["ayse.k"]["pending_role"] is False
    with transaction() as db:
        uid = db.scalar(select(User.id).where(User.username == "ayse.k"))
        assert db.scalars(select(ProjectMember.role).where(ProjectMember.user_id == uid)).all() == ["reader"]


def test_local_account_cannot_be_taken_over_by_directory_account(https_app, admin, directory):  # noqa: ANN001
    directory.add("ayse", "Dizin-Parolasi-2026", "Başka Ayşe")  # kurulumdaki yerel yönetici de 'ayse'
    enable(admin)
    assert Client(https_app).login("ayse", "Dizin-Parolasi-2026").json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert Client(https_app).login("ayse", ADMIN_PASSWORD).status_code == 200


def test_directory_unavailable_is_reported_not_wrong_password(https_app, admin, directory):  # noqa: ANN001
    directory.add("ayse.k", PW, "Ayşe Kurgu")
    enable(admin)
    directory.down = True
    r = Client(https_app).login("ayse.k", PW)
    assert r.status_code == 503 and r.json()["error"]["code"] == "DIRECTORY_UNAVAILABLE"


def test_directory_user_password_cannot_be_changed_or_reset_in_metis(https_app, admin, directory):  # noqa: ANN001
    directory.add("ayse.k", PW, "Ayşe Kurgu")
    enable(admin)
    u = Client(https_app)
    uid = u.login("ayse.k", PW).json()["user"]["id"]
    r = u.post("/api/v1/auth/password", json={"current_password": PW, "new_password": "Yeni-Parola-2026-xx"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "PASSWORD_MANAGED_BY_DIRECTORY"
    r = admin.patch(f"/api/v1/users/{uid}", json={"temporary_password": "Gecici-Parola-2026"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "PASSWORD_MANAGED_BY_DIRECTORY"
    # Pasifleştirilen dizin kullanıcısı doğru parolayla da giremez.
    assert admin.patch(f"/api/v1/users/{uid}", json={"active": False}).status_code == 200
    assert Client(https_app).login("ayse.k", PW).json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_settings_admin_only_ldaps_only_and_test_does_not_save(https_app, admin, directory):  # noqa: ANN001
    directory.add("ayse.k", PW, "Ayşe Kurgu", groups=[GROUP])
    r = admin.put("/api/v1/directory", json={**SETTINGS, "server_url": "ldap://dc1.kurgu.test"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    test = admin.post("/api/v1/directory/test", json={"settings": {**SETTINGS, "group_dn": GROUP}, "username": "ayse.k", "password": PW})
    assert test.status_code == 200, test.text
    assert test.json() == {"ok": True, "username": "ayse.k", "display_name": "Ayşe Kurgu", "email": f"ayse.k@{DOMAIN}", "in_group": True, "error": None}
    assert admin.get("/api/v1/directory").json()["enabled"] is False  # deneme kaydetmez
    bad = admin.post("/api/v1/directory/test", json={"settings": SETTINGS, "username": "ayse.k", "password": "yanlis"})
    assert bad.json()["ok"] is False and bad.json()["error"] == "INVALID_CREDENTIALS"
    with transaction() as db:
        assert db.scalar(select(User).where(User.username == "ayse.k")) is None  # deneme hesap açmaz
    enable(admin)
    u = Client(https_app)
    u.login("ayse.k", PW)
    assert u.get("/api/v1/directory").status_code == 403
    assert u.put("/api/v1/directory", json=SETTINGS).status_code == 403


def test_http_installation_refuses_directory_login(client, directory):  # noqa: ANN001
    """Şirket parolası tarayıcıdan METIS'e gelir: http'de ağda açık giderdi. Yerel giriş etkilenmez."""
    setup_admin(client)
    r = client.put("/api/v1/directory", json=SETTINGS)
    assert r.status_code == 409 and r.json()["error"]["code"] == "HTTPS_REQUIRED"
    assert client.put("/api/v1/directory", json={**SETTINGS, "enabled": False}).status_code == 200  # ayar kaydedilebilir
    assert client.post("/api/v1/directory/test", json={"settings": SETTINGS, "username": "x", "password": "y"}).json()["error"] == "HTTPS_REQUIRED"
    assert client.get("/api/v1/auth/methods").json() == {"directory": False}
    assert directory.binds == []


def test_real_ldap3_unreachable_server_reports_unavailable():
    from metis.modules.directory.ldap import DirectoryConfig, DirectoryUnavailable, verify

    cfg = DirectoryConfig(server_url="ldaps://127.0.0.1:1", domain=DOMAIN, base_dn="", group_dn="")
    with pytest.raises(DirectoryUnavailable):
        verify(cfg, "ayse.k", PW)

def test_newcomers_start_as_reader_by_default(https_app, admin, directory):  # noqa: ANN001
    """Ürün sahibinin kararı (2026-10-19): her yeni şirket kullanıcısı varsayılan olarak Okur başlar."""
    assert admin.get("/api/v1/directory").json()["new_user_role"] == "reader"
    directory.add("ayse.k", PW, "Ayşe Kurgu")
    defaults = {k: v for k, v in SETTINGS.items() if k != "new_user_role"}
    r = admin.put("/api/v1/directory", json=defaults)
    assert r.status_code == 200 and r.json()["new_user_role"] == "reader"
    me = Client(https_app).login("ayse.k", PW).json()
    assert [m["roles"] for m in me["memberships"]] == [["reader"]]
