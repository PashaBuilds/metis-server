"""Faz 0/1 temel: sağlık, güvenlik başlıkları, kurulum, giriş, CSRF, değişmezlik trigger'ı."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from metis.core.db import ImmutableRecordError, transaction
from metis.core.models import AuditEvent
from tests.factories import ADMIN_PASSWORD, setup_admin


def test_health_live_and_ready(client):
    assert client.get("/api/v1/health/live").json()["status"] == "live"
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 200 and r.json()["status"] == "ready"


def test_security_headers(client):
    r = client.get("/api/v1/health/live")
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-request-id"]


def test_host_header_rejected(client):
    r = client.http.get("/api/v1/health/live", headers={"Host": "evil.example"})
    assert r.status_code == 400


def test_error_envelope_shape(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401
    err = r.json()["error"]
    assert set(err) == {"code", "message", "retryable", "correlation_id", "details"}
    assert err["code"] == "UNAUTHENTICATED"


def test_setup_once_then_login(client, make_client):
    assert client.get("/api/v1/setup/status").json() == {"needs_setup": True}
    me = setup_admin(client)
    assert me["user"]["is_admin"] is True
    assert len(me["memberships"]) == 1
    assert client.get("/api/v1/setup/status").json() == {"needs_setup": False}
    other = make_client()
    r = other.post(
        "/api/v1/setup",
        json={
            "code": "AAAA-BBBB-CCCC-DDDD",
            "display_name": "x",
            "username": "xx",
            "password": ADMIN_PASSWORD,
            "project_name": "p",
        },
    )
    assert r.status_code == 409
    other.login("ayse", ADMIN_PASSWORD)
    assert other.get("/api/v1/auth/me").status_code == 200


def test_setup_code_single_use_and_invalid(client):
    r = client.post(
        "/api/v1/setup",
        json={
            "code": "WRONG-CODE-0000-0000",
            "display_name": "x",
            "username": "xx",
            "password": ADMIN_PASSWORD,
            "project_name": "p",
        },
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "SETUP_CODE_INVALID"


def test_csrf_required_for_mutations(client):
    setup_admin(client)
    r = client.http.post("/api/v1/projects", json={"name": "x"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF_REJECTED"
    assert client.post("/api/v1/projects", json={"name": "x"}).status_code == 201


def test_origin_allowlist(client):
    setup_admin(client)
    r = client.http.post(
        "/api/v1/projects", json={"name": "x"}, headers={"Origin": "http://evil.example", "X-CSRF-Token": client.csrf}
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "ORIGIN_REJECTED"


def test_session_cookie_flags(client):
    setup_admin(client)
    r = client.http.post("/api/v1/auth/login", json={"username": "ayse", "password": ADMIN_PASSWORD})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_login_rate_limit_in_db(client, make_client):
    setup_admin(client)
    attacker = make_client()
    for _ in range(5):
        assert (
            attacker.http.post(
                "/api/v1/auth/login", json={"username": "ayse", "password": "yanlis-parola-xx"}
            ).status_code
            == 401
        )
    r = attacker.http.post("/api/v1/auth/login", json={"username": "ayse", "password": ADMIN_PASSWORD})
    assert r.status_code == 429 and r.json()["error"]["retryable"] is True


def test_must_change_password(client, make_client):
    setup_admin(client)
    r = client.post(
        "/api/v1/users",
        json={"username": "mehmet", "display_name": "Mehmet", "temporary_password": "Gecici-Parola-2026"},
    )
    assert r.status_code == 201
    u = make_client()
    u.login("mehmet", "Gecici-Parola-2026")
    assert u.get("/api/v1/projects").json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"
    assert u.get("/api/v1/auth/me").status_code == 200
    r = u.post(
        "/api/v1/auth/password", json={"current_password": "Gecici-Parola-2026", "new_password": "Yeni-Parola-2026!"}
    )
    assert r.status_code == 200
    assert u.get("/api/v1/projects").status_code == 200


def test_audit_events_immutable_trigger_and_orm_hook():
    with transaction() as db:
        db.add(AuditEvent(op="test.op", target_type="x", target_id="1"))
    with pytest.raises(DBAPIError) as exc, transaction() as db:
        db.execute(text("UPDATE audit_events SET op = 'tampered'"))
    assert "METIS_IMMUTABLE" in str(exc.value)
    with pytest.raises(DBAPIError), transaction() as db:
        db.execute(text("DELETE FROM audit_events"))
    with pytest.raises(ImmutableRecordError), transaction() as db:
        row = db.query(AuditEvent).first()
        row.op = "tampered"


def test_unknown_api_route_is_json_404(client):
    r = client.get(f"/api/v1/nope/{uuid.uuid4()}")
    assert r.status_code == 404


def test_commit_happens_before_response_is_sent(client, monkeypatch):
    """İstek oturumunun commit'i yanıt gönderilmeden önce yapılır: commit başarısızsa istemci başarı görmez
    (aksi hâlde 200 dönüp veri kaybolur, hemen ardından gelen okuma da eski veriyi görür)."""
    from sqlalchemy.orm import Session

    from tests.factories import setup_admin

    setup_admin(client)

    def failing_commit(self):  # noqa: ANN001, ANN202
        raise RuntimeError("commit failed")

    monkeypatch.setattr(Session, "commit", failing_commit)
    r = client.put("/api/v1/preferences/theme", json={"value": "dark"})
    monkeypatch.undo()
    assert r.status_code == 500, r.text
    assert r.json()["error"]["code"]
    assert client.get("/api/v1/auth/me").json()["preferences"].get("theme") != "dark"
