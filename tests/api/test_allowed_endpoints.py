"""Model adresine arayüzden izin (ürün sahibinin kararı 2026-10-19): yönetici, metis.env'e dokunmadan Model
laboratuvarından bir adrese izin verir. Geçerli liste = METIS_ENDPOINT_ALLOWLIST + allowed_endpoints. Biçim, ağ aralığı
(METIS_ENDPOINT_NETWORKS) ve üretimde https şartı aynen geçerli; izin her model çağrısında da denetlenir."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from metis.core.db import transaction
from metis.core.errors import AppError
from metis.core.models import AuditEvent
from metis.core.security import validate_endpoint

NEW_URL = "http://127.0.0.1:9150/v1"  # sunucu ayarında yok (conftest: 9100–9102)
PROVIDER = {"name": "Şirket modeli (kurgusal)", "api_key": "kurgusal-anahtar-123", "model_ids": ["kurgusal-model"]}


def _provider(client, url: str):  # noqa: ANN001, ANN202
    return client.post("/api/v1/providers", json={**PROVIDER, "base_url": url})


def test_admin_allows_endpoint_then_provider_can_be_added(team):
    admin = team["admin"]
    r = _provider(admin, NEW_URL)
    assert r.status_code == 422 and r.json()["error"]["code"] == "ENDPOINT_NOT_ALLOWED"

    r = admin.post("/api/v1/allowed-endpoints", json={"url": NEW_URL + "/"})  # sondaki / temizlenir
    assert r.status_code == 201, r.text
    row = r.json()
    assert row["url"] == NEW_URL and row["source"] == "ui" and row["id"]
    # Aynı adres ikinci kez: var olan kayıt döner (çift satır yok).
    assert admin.post("/api/v1/allowed-endpoints", json={"url": NEW_URL}).json()["id"] == row["id"]

    assert _provider(admin, NEW_URL).status_code == 201
    listing = admin.get("/api/v1/allowed-endpoints").json()
    config = [e for e in listing if e["source"] == "config"]
    ui = [e for e in listing if e["source"] == "ui"]
    assert {e["url"] for e in config} == {"http://127.0.0.1:9100/v1", "http://127.0.0.1:9101/v1", "http://127.0.0.1:9102/v1"}
    assert all(e["id"] is None for e in config)
    assert [(e["url"], e["providers"]) for e in ui] == [(NEW_URL, 1)]
    assert ui[0]["created_by"]

    with transaction() as db:
        ops = [e.op for e in db.scalars(select(AuditEvent).where(AuditEvent.op.like("endpoint.%")))]
    assert ops == ["endpoint.allow"]


def test_only_admin_manages_allowlist(team):
    for who in ("reviewer", "contributor", "reader"):
        assert team[who].post("/api/v1/allowed-endpoints", json={"url": NEW_URL}).status_code == 403
        assert team[who].get("/api/v1/allowed-endpoints").status_code == 403


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("http://169.254.169.254/v1", "ADDRESS_NOT_ALLOWED"),  # bulut meta veri adresi (link-local)
        ("http://8.8.8.8/v1", "ADDRESS_NOT_ALLOWED"),  # internet: iç ağ aralıkları dışında
        ("http://127.0.0.1:9150/v1/chat/completions", "INVALID_ENDPOINT"),
        ("http://kullanici:parola@127.0.0.1:9150/v1", "INVALID_ENDPOINT"),
        ("ftp://127.0.0.1/v1", "INVALID_ENDPOINT"),
    ],
)
def test_network_and_format_rules_still_apply(team, url, code):  # noqa: ANN001
    r = team["admin"].post("/api/v1/allowed-endpoints", json={"url": url})
    assert r.status_code == 422 and r.json()["error"]["code"] == code
    assert all(e["source"] == "config" for e in team["admin"].get("/api/v1/allowed-endpoints").json())


def test_configured_endpoint_is_not_duplicated(team):
    r = team["admin"].post("/api/v1/allowed-endpoints", json={"url": "http://127.0.0.1:9101/v1"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "ENDPOINT_CONFIGURED"


def test_removal_refused_while_in_use_and_takes_effect_for_model_calls(team):
    admin = team["admin"]
    eid = admin.post("/api/v1/allowed-endpoints", json={"url": NEW_URL}).json()["id"]
    assert validate_endpoint(NEW_URL) == NEW_URL  # model çağrısındaki denetim (llm/client.py) yeni adresi görür
    pid = _provider(admin, NEW_URL).json()["id"]

    r = admin.delete(f"/api/v1/allowed-endpoints/{eid}")
    assert r.status_code == 409 and r.json()["error"]["code"] == "ENDPOINT_IN_USE"

    assert admin.delete(f"/api/v1/providers/{pid}").status_code == 204
    assert admin.delete(f"/api/v1/allowed-endpoints/{eid}").status_code == 204
    with pytest.raises(AppError) as exc:
        validate_endpoint(NEW_URL)
    assert exc.value.code == "ENDPOINT_NOT_ALLOWED"
    assert _provider(admin, NEW_URL).status_code == 422
    assert admin.delete(f"/api/v1/allowed-endpoints/{eid}").status_code == 404
