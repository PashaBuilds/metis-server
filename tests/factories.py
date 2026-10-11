"""Test yardımcıları — yalnız kurgusal veri."""

from __future__ import annotations

from metis.core.db import transaction
from metis.modules.auth.service import issue_setup_code

ADMIN_PASSWORD = "Yonetici-Parola-2026"
USER_PASSWORD = "Kullanici-Parola-2026"


def setup_admin(client, project_name: str = "Kurgusal Proje") -> dict:  # noqa: ANN001
    with transaction() as db:
        code = issue_setup_code(db)
    r = client.post(
        "/api/v1/setup",
        json={
            "code": code,
            "display_name": "Ayşe Yönetici",
            "username": "ayse",
            "password": ADMIN_PASSWORD,
            "mode": "empty",
            "project_name": project_name,
        },
    )
    assert r.status_code == 200, r.text
    client.csrf = r.json()["csrf_token"]
    client.user = r.json()["user"]
    return r.json()


def create_user(admin, username: str, roles: list[str], project_id: str, make_client) -> object:  # noqa: ANN001
    r = admin.post(
        "/api/v1/users",
        json={"username": username, "display_name": username.title(), "temporary_password": "Gecici-Parola-2026"},
    )
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    if roles:
        r = admin.put(f"/api/v1/projects/{project_id}/members", json={"user_id": uid, "roles": roles})
        assert r.status_code == 204, r.text
    c = make_client()
    c.login(username, "Gecici-Parola-2026")
    r = c.post("/api/v1/auth/password", json={"current_password": "Gecici-Parola-2026", "new_password": USER_PASSWORD})
    assert r.status_code == 200, r.text
    c.csrf = r.json()["csrf_token"]
    c.user = r.json()["user"]
    return c


def add_scope_values(client, project_id: str, values: dict[str, list[str]]) -> None:  # noqa: ANN001
    for dim, vals in values.items():
        for v in vals:
            r = client.post(f"/api/v1/projects/{project_id}/scopes", json={"dimension": dim, "value": v})
            assert r.status_code == 201, r.text
