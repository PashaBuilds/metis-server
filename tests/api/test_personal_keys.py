"""Kişisel API anahtarı (2.0.28, ürün sahibinin kararı 2026-10-27): herkes modelleri kendi anahtarıyla çağırır.

Anahtarsız kişi Mentor'da cevap üretemez (ilgili bölümler görünür); yönetici kişisel anahtar eklemediyse ortak anahtarla
(kendi anahtarı). Önbellek anahtar sahibine özel; kişisel anahtarın reddi modelin devre kesicisini açmaz. Kullanım:
kişi kendi dökümünü, yönetici kişi başına toplamları görür.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from metis.core.db import transaction
from metis.core.models import Model, ModelCall, UserProviderKey
from metis.llm import mock_server
from tests.kb import publish_note
from tests.llm_helpers import add_provider, make_demo, model_id, personal_key_value, qualify

SPI = "SPI denetleyicisi 100 MHz referans saatini 8 bölücü ile 12.5 MHz SCLK'ye indirir."
QUESTION = "SPI saat bölücü kaç?"


@pytest.fixture
def env(team, mock_llm):  # noqa: ANN001, ANN201
    make_demo(team["pid"])
    publish_note(team["contributor"], team["reviewer"], team["pid"], "SPI saat bölücü", SPI, [SPI])
    prov = add_provider(team["admin"], ["fixture-reference"])
    mid = model_id("fixture-reference", prov["id"])
    qualify(team["admin"], mid)
    ids = {name: team[name].get("/api/v1/auth/me").json()["user"]["id"] for name in ("admin", "contributor", "reviewer", "reader")}
    return {**team, "provider_id": prov["id"], "model_id": mid, "ids": ids}


def ask(client, pid, **kw):  # noqa: ANN001, ANN201
    r = client.post(f"/api/v1/projects/{pid}/mentor/answers", json={"question": QUESTION, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def drop_key(user_id: str, provider_id: str) -> None:
    with transaction() as db:
        db.execute(UserProviderKey.__table__.delete().where(UserProviderKey.user_id == uuid.UUID(user_id), UserProviderKey.provider_id == uuid.UUID(provider_id)))


def mentor_calls(user_id: str | None = None) -> list[ModelCall]:
    with transaction() as db:
        q = select(ModelCall).where(ModelCall.purpose == "mentor").order_by(ModelCall.created_at)
        if user_id:
            q = q.where(ModelCall.user_id == uuid.UUID(user_id))
        rows = list(db.scalars(q))
        for r in rows:
            db.expunge(r)
        return rows


# ---------------------------------------------------------------- anahtar yönetimi


def test_set_key_encrypted_never_returned_and_bound_to_owner(env):
    c, pid = env["reader"], env["provider_id"]
    assert c.put(f"/api/v1/me/keys/{pid}", json={"api_key": "okurun-gizli-anahtari-77"}).status_code == 204
    listing = c.get("/api/v1/me/keys")
    assert listing.status_code == 200 and "okurun-gizli" not in listing.text
    row = next(k for k in listing.json() if k["provider_id"] == pid)
    assert row["has_key"] is True and row["uses_shared"] is False and row["models"]
    with transaction() as db:
        dump = db.execute(text("SELECT string_agg(secret_enc, ' ') FROM user_provider_keys")).scalar() or ""
        audit = db.execute(text("SELECT string_agg(detail::text, ' ') FROM audit_events")).scalar() or ""
    assert "okurun-gizli" not in dump and "okurun-gizli" not in audit
    # Şifreli değer başka kişinin satırına kopyalanırsa çözülmez (AAD kişi + sağlayıcı).
    with transaction() as db:
        mine = db.get(UserProviderKey, (uuid.UUID(env["ids"]["reader"]), uuid.UUID(pid)))
        other = db.get(UserProviderKey, (uuid.UUID(env["ids"]["reviewer"]), uuid.UUID(pid)))
        other.secret_enc = mine.secret_enc
    out = ask(env["reviewer"], env["pid"], model_id=env["model_id"])
    assert out["decision"] == "MODEL_UNAVAILABLE" and out["model_unavailable_reason"] == "personal_key_rejected"


def test_short_key_rejected_and_delete(env):
    c, pid = env["reader"], env["provider_id"]
    r = c.put(f"/api/v1/me/keys/{pid}", json={"api_key": "kisa"})
    assert r.status_code == 422
    assert c.delete(f"/api/v1/me/keys/{pid}").status_code == 204
    assert c.delete(f"/api/v1/me/keys/{pid}").status_code == 404
    assert next(k for k in c.get("/api/v1/me/keys").json() if k["provider_id"] == pid)["has_key"] is False


def test_key_check_reports_ok_and_rejection(env):
    c, pid = env["reader"], env["provider_id"]
    ok = c.post(f"/api/v1/me/keys/{pid}/check").json()
    assert ok["ok"] is True and ok["error"] is None
    c.put(f"/api/v1/me/keys/{pid}", json={"api_key": "wrong-key"})
    bad = c.post(f"/api/v1/me/keys/{pid}/check").json()
    assert bad["ok"] is False and bad["error"] == "HTTP_401"
    row = next(k for k in c.get("/api/v1/me/keys").json() if k["provider_id"] == pid)
    assert row["check_ok"] is False and row["check_error"] == "HTTP_401"


# ---------------------------------------------------------------- Mentor


def test_mentor_uses_personal_key_and_logs_owner(env):
    mock_server.SEEN_AUTH.clear()
    out = ask(env["reader"], env["pid"])
    assert out["decision"] == "SUPPORTED", out
    assert f"Bearer {personal_key_value(env['ids']['reader'])}" in mock_server.SEEN_AUTH
    assert "Bearer kurgusal-anahtar-123" not in mock_server.SEEN_AUTH  # ortak (yönetici) anahtarı kullanılmadı
    calls = mentor_calls(env["ids"]["reader"])
    assert calls and all(c.key_source == "personal" for c in calls)


def test_mentor_without_key_shows_passages_only(env):
    drop_key(env["ids"]["reader"], env["provider_id"])
    mock_server.SEEN_AUTH.clear()
    out = ask(env["reader"], env["pid"])
    assert out["decision"] == "MODEL_UNAVAILABLE" and out["model_unavailable_reason"] == "personal_key_missing"
    assert out["related_passages"] and out["alternatives"] == []
    assert mock_server.SEEN_AUTH == [] and mentor_calls(env["ids"]["reader"]) == []
    models = env["reader"].get(f"/api/v1/models/available?project_id={env['pid']}").json()
    assert next(m for m in models if m["id"] == env["model_id"])["reason"] == "personal_key_missing"


def test_admin_without_personal_key_uses_shared_key(env):
    drop_key(env["ids"]["admin"], env["provider_id"])
    mock_server.SEEN_AUTH.clear()
    out = ask(env["admin"], env["pid"])
    assert out["decision"] == "SUPPORTED"
    assert "Bearer kurgusal-anahtar-123" in mock_server.SEEN_AUTH
    assert {c.key_source for c in mentor_calls(env["ids"]["admin"])} == {"shared"}


def test_rejected_personal_key_does_not_open_circuit(env):
    env["reader"].put(f"/api/v1/me/keys/{env['provider_id']}", json={"api_key": "wrong-key"})
    for _ in range(4):
        out = ask(env["reader"], env["pid"], model_id=env["model_id"])
        assert out["model_unavailable_reason"] == "personal_key_rejected"
    with transaction() as db:
        m = db.get(Model, uuid.UUID(env["model_id"]))
        assert m.failures == 0 and m.circuit_until is None
    assert ask(env["reviewer"], env["pid"])["decision"] == "SUPPORTED"  # başkası etkilenmez


def test_cache_is_per_key_owner(env):
    assert ask(env["reader"], env["pid"])["decision"] == "SUPPORTED"
    assert ask(env["reviewer"], env["pid"])["decision"] == "SUPPORTED"
    assert {c.state for c in mentor_calls(env["ids"]["reviewer"])} == {"completed"}  # okurun önbelleğinden gelmedi
    assert ask(env["reader"], env["pid"])["decision"] == "SUPPORTED"
    assert "cached" in {c.state for c in mentor_calls(env["ids"]["reader"])}


def test_model_off_returns_passages_without_calls(env):
    mock_server.SEEN_AUTH.clear()
    out = ask(env["reader"], env["pid"], use_model=False)
    assert out["decision"] == "MODEL_UNAVAILABLE" and out["model_unavailable_reason"] == "model_off"
    assert out["related_passages"] and out["explanation"] == []
    assert mock_server.SEEN_AUTH == []


def test_timeout_bounds_validated_and_reason_mapping(env):
    from metis.modules.mentor.service import _failure_reason

    r = env["reader"].post(f"/api/v1/projects/{env['pid']}/mentor/answers", json={"question": QUESTION, "timeout_s": 5})
    assert r.status_code == 422
    assert ask(env["reader"], env["pid"], timeout_s=120)["decision"] == "SUPPORTED"
    assert _failure_reason("BUDGET_EXCEEDED") == _failure_reason("TIMEOUT") == "timeout"
    assert _failure_reason("HTTP_401") == "personal_key_rejected" and _failure_reason("HTTP_500") == "call_failed"


def test_budget_override_can_exceed_provider_timeout(env):
    """Kullanıcının seçtiği süre sağlayıcının süresinin yerine geçer (yalnız kısaltma değil)."""
    from metis.core.models import Provider
    from metis.llm.client import KeyRef, ModelClient

    with transaction() as db:
        model = db.get(Model, uuid.UUID(env["model_id"]))
        provider = db.get(Provider, model.provider_id)
        db.expunge(model)
        db.expunge(provider)
    key = KeyRef(user_id=uuid.UUID(env["ids"]["reader"]), personal=True)
    fast = ModelClient().call(model, provider, prompt_id="probe-v1", payload={"echo": "connection"}, schema=None, purpose="key_check", cache=False, key=key, budget_s=0.0001)
    assert fast.ok is False and fast.error in ("TIMEOUT", "BUDGET_EXCEEDED")
    assert ModelClient().call(model, provider, prompt_id="probe-v1", payload={"echo": "connection"}, schema=None, purpose="key_check", cache=False, key=key, budget_s=300).ok


# ---------------------------------------------------------------- görevler ve kullanım


def test_job_requires_personal_key(env):
    drop_key(env["ids"]["contributor"], env["provider_id"])
    from tests.kb import add_note

    src = add_note(env["contributor"], env["pid"], "Kurgusal kaynak", "Kurgusal kartta UART 115200 baud çalışır.")
    r = env["contributor"].post(
        f"/api/v1/projects/{env['pid']}/jobs",
        json={"kind": "prepare_draft", "model_id": env["model_id"], "source_revision_ids": [src["revision"]["id"]]},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "PERSONAL_KEY_MISSING"


def test_usage_own_and_admin_totals(env):
    ask(env["reader"], env["pid"])
    mine = env["reader"].get("/api/v1/me/usage").json()
    assert any(r["purpose"] == "mentor" and r["key_source"] == "personal" and r["calls"] >= 1 for r in mine["rows"])
    assert env["reader"].get("/api/v1/usage/users").status_code == 403
    rows = env["admin"].get("/api/v1/usage/users").json()["rows"]
    reader_row = next(r for r in rows if r["user_id"] == env["ids"]["reader"])
    assert reader_row["calls"] >= 1 and reader_row["name"]
    assert set(reader_row) == {"user_id", "name", "key_source", "calls", "prompt_tokens", "completion_tokens"}  # içerik yok


def test_preferences_store_mentor_choices(env):
    c = env["reader"]
    assert c.put("/api/v1/preferences/mentor_timeout_s", json={"value": 180}).status_code in (200, 204)
    assert c.put("/api/v1/preferences/mentor_use_model", json={"value": False}).status_code in (200, 204)
    prefs = c.get("/api/v1/auth/me").json()["preferences"]
    assert prefs["mentor_timeout_s"] == 180 and prefs["mentor_use_model"] is False
