"""Faz 4 kabul: model gateway (şifreli anahtar, probe→profil, log, cache) ve kaynaklı mentor."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select, text

from metis.core.db import transaction
from metis.core.models import Answer, Finding, FindingPage, Model, ModelCall, Provider
from tests.kb import publish_note
from tests.llm_helpers import add_provider, make_demo, model_id, qualify

SPI = "SPI denetleyicisi 100 MHz referans saatini 8 bölücü ile 12.5 MHz SCLK'ye indirir."
ISR = "ISR içinde printf kullanılmaz."


@pytest.fixture
def mentor_env(team, mock_llm):  # noqa: ANN001, ANN201
    make_demo(team["pid"])
    out = publish_note(team["contributor"], team["reviewer"], team["pid"], "SPI saat bölücü", f"{SPI} {ISR}", [SPI, ISR])
    prov = add_provider(team["admin"], ["fixture-reference"])
    mid = model_id("fixture-reference", prov["id"])
    metrics = qualify(team["admin"], mid)
    return {**team, "page": out, "model_id": mid, "provider": prov, "metrics": metrics}


def ask(client, pid, q, **kw):  # noqa: ANN001, ANN201
    r = client.post(f"/api/v1/projects/{pid}/mentor/answers", json={"question": q, **kw})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- gateway


def test_provider_key_encrypted_and_never_returned(team, mock_llm):
    prov = add_provider(team["admin"], ["fixture-reference"], key="cok-gizli-anahtar-XYZ")
    assert prov["secret_configured"] is True and "api_key" not in prov
    with transaction() as db:
        row = db.get(Provider, uuid.UUID(prov["id"]))
        assert row.secret_enc.startswith("v2:") and "cok-gizli" not in row.secret_enc
        dump = db.execute(text("SELECT string_agg(detail::text, ' ') FROM audit_events")).scalar() or ""
        assert "cok-gizli" not in dump
    listing = team["admin"].get("/api/v1/providers").text
    assert "cok-gizli" not in listing


def test_endpoint_allowlist_and_ssrf(team):
    r = team["admin"].post("/api/v1/providers", json={"base_url": "http://169.254.169.254/v1", "model_ids": ["x"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "ENDPOINT_NOT_ALLOWED"
    r = team["admin"].post("/api/v1/providers", json={"base_url": "http://127.0.0.1:9101/v1/chat/completions", "model_ids": ["x"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_ENDPOINT"
    assert team["reviewer"].post("/api/v1/providers", json={"base_url": "http://127.0.0.1:9101/v1", "model_ids": ["x"]}).status_code == 403


def test_probe_selects_transport_profile(team, mock_llm):
    prov = add_provider(team["admin"], ["fixture-reference", "fixture-no-schema", "fixture-no-thinking"])
    ref = team["admin"].post(f"/api/v1/models/{model_id('fixture-reference', prov['id'])}/probe").json()
    assert ref["profile"]["json_mode"] == "json_schema" and ref["profile"]["thinking"] == "disabled" and ref["evidence_contract"]
    ns = team["admin"].post(f"/api/v1/models/{model_id('fixture-no-schema', prov['id'])}/probe").json()
    assert ns["profile"]["json_mode"] == "json_object" and ns["results"]["json_schema"]["error"] == "HTTP_400"
    nt = team["admin"].post(f"/api/v1/models/{model_id('fixture-no-thinking', prov['id'])}/probe").json()
    assert nt["profile"]["thinking"] == "not_supported"


def test_probe_reports_auth_failure(team, mock_llm):
    prov = add_provider(team["admin"], ["fixture-reference"], key="wrong-key")
    res = team["admin"].post(f"/api/v1/models/{model_id('fixture-reference', prov['id'])}/probe").json()
    assert res["results"]["connection"]["error"] == "HTTP_401" and res["evidence_contract"] is False


def test_model_calls_are_logged(mentor_env):
    with transaction() as db:
        purposes = {r[0] for r in db.execute(select(ModelCall.purpose))}
        assert {"probe", "benchmark"} <= purposes


def test_key_rotation_invalidates_qualification(mentor_env):
    env = mentor_env
    avail = env["reader"].get("/api/v1/models/available", params={"project_id": env["pid"]}).json()
    assert avail[0]["eligible"] is True
    env["admin"].post(f"/api/v1/providers/{env['provider']['id']}/key", json={"api_key": "yeni-anahtar-456"})
    avail = env["reader"].get("/api/v1/models/available", params={"project_id": env["pid"]}).json()
    assert avail[0]["eligible"] is False and avail[0]["reason"] == "config_changed"


def test_fixture_model_not_for_company_projects(team, mock_llm):
    prov = add_provider(team["admin"], ["fixture-reference"])
    mid = model_id("fixture-reference", prov["id"])
    qualify(team["admin"], mid)
    avail = team["reader"].get("/api/v1/models/available", params={"project_id": team["pid"]}).json()
    assert avail[0]["reason"] == "fixture_not_for_company_data"


# ---------------------------------------------------------------- mentor


def test_supported_answer_with_verified_explanation(mentor_env):
    env = mentor_env
    a = ask(env["reader"], env["pid"], "SPI saat bölücü kaç olarak ayarlanır?")
    assert a["decision"] == "SUPPORTED"
    assert a["citations"] and a["citations"][0]["quote"] == SPI
    assert a["explanation"] and all(s["refs"] for s in a["explanation"])
    assert a["model"]["display_name"] == "fixture-reference" and a["prompt_version"] == "evidence-explain-v1"
    assert a["publication_id"] and a["timings"]["total_ms"] is not None
    detail = env["reader"].get(f"/api/v1/answers/{a['id']}").json()
    assert detail["decision"] == "SUPPORTED"
    assert env["reader"].get(f"/api/v1/projects/{env['pid']}/answers").json()[0]["id"] == a["id"]


def test_level_changes_explanation_length(mentor_env):
    env = mentor_env
    short = ask(env["reader"], env["pid"], "SPI ve ISR hakkında ne biliniyor? Açıkla.", level="short")
    steps = ask(env["reader"], env["pid"], "SPI ve ISR hakkında ne biliniyor? Açıkla.", level="steps")
    assert len(short["explanation"]) <= 2 and len(steps["explanation"]) >= len(short["explanation"])


def test_no_evidence_vs_retrieval_unavailable(mentor_env, monkeypatch):
    env = mentor_env
    a = ask(env["reader"], env["pid"], "Yemekhane menüsü ne zaman açıklanır?")
    assert a["decision"] == "NO_EVIDENCE" and a["citations"] == []

    def broken(*_a, **_k):  # noqa: ANN002, ANN003
        raise RuntimeError("search index down")

    monkeypatch.setattr("metis.modules.search.service.search", broken)
    b = ask(env["reader"], env["pid"], "SPI saat bölücü kaç?")
    assert b["decision"] == "RETRIEVAL_UNAVAILABLE"
    assert b["decision"] != "NO_EVIDENCE"


def test_needs_scope_names_dimension(mentor_env):
    env = mentor_env
    a = ask(env["reader"], env["pid"], "SPI saat bölücü kaç?", scope={"kart": ["K2"]})
    assert a["decision"] == "NEEDS_SCOPE" and a["needs_scope_dimensions"] == ["kart"]


def test_open_conflict_forces_conflicting(mentor_env):
    env = mentor_env
    with transaction() as db:
        f = Finding(project_id=uuid.UUID(env["pid"]), kind="conflict", severity="high", detail={"sides": []})
        db.add(f)
        db.flush()
        db.add(FindingPage(finding_id=f.id, page_id=uuid.UUID(env["page"]["page_id"])))
    a = ask(env["reader"], env["pid"], "SPI saat bölücü kaç?")
    assert a["decision"] == "CONFLICTING" and a["citations"] == [] and a["explanation"] == []


def test_open_conflict_flags_only_conflicting_pages(mentor_env):
    env = mentor_env
    other = publish_note(env["contributor"], env["reviewer"], env["pid"], "SPI bölücü notu", "SPI saat bölücü notları ayrı sayfadadır.")
    with transaction() as db:
        f = Finding(project_id=uuid.UUID(env["pid"]), kind="conflict", severity="high", detail={"sides": []})
        db.add(f)
        db.flush()
        db.add(FindingPage(finding_id=f.id, page_id=uuid.UUID(env["page"]["page_id"])))
    a = ask(env["reader"], env["pid"], "SPI saat bölücü kaç?")
    flags = {r["page_id"]: r["open_conflict"] for r in a["related"]}
    assert a["decision"] == "CONFLICTING"
    assert flags[env["page"]["page_id"]] is True
    assert flags.get(other["page_id"]) is False  # çelişkiye dahil olmayan ilgili sayfa işaretlenmez

def test_unrelated_conflict_page_does_not_block_answer(mentor_env, monkeypatch):
    """Brief 5.6: çelişkili sayfa *seçilirse* CONFLICTING. Aramada yalnız yan sonuç olarak çıkan, kaynak seçiminde
    ilgisiz bulunan çelişkili sayfa cevabı engellemez (canlı modelle bulundu, 2026-10-18)."""
    from metis.llm import prompts
    from metis.llm.client import CallResult, ModelClient

    env = mentor_env
    other = publish_note(env["contributor"], env["reviewer"], env["pid"], "SPI bölücü notu", "SPI saat bölücü notları ayrı sayfadadır.")
    with transaction() as db:
        f = Finding(project_id=uuid.UUID(env["pid"]), kind="conflict", severity="high", detail={"sides": []})
        db.add(f)
        db.flush()
        db.add(FindingPage(finding_id=f.id, page_id=uuid.UUID(other["page_id"])))
    original = ModelClient.call
    selected: list[list[str]] = []

    def fake(self, model, provider, *, prompt_id, payload, **kw):  # noqa: ANN001, ANN202
        if prompt_id == prompts.SOURCE_SELECTION:
            selected.append([p["page_id"] for p in payload["pages"]])
            return CallResult(ok=True, output={"reviews": [{"page_id": p["page_id"], "relevance": "irrelevant" if p["page_id"] == other["page_id"] else "relevant", "reason": "kurgusal"} for p in payload["pages"]]})
        return original(self, model, provider, prompt_id=prompt_id, payload=payload, **kw)

    monkeypatch.setattr(ModelClient, "call", fake)
    a = ask(env["reader"], env["pid"], "SPI saat bölücü kaç?")
    assert selected, "çelişkili sayfa yanında başka sayfa varken kaynak seçimi yapılmalı"
    assert a["decision"] == "SUPPORTED" and a["citations"]
    assert all(c["page_id"] != other["page_id"] for c in a["citations"])
    assert {r["page_id"]: r["open_conflict"] for r in a["related"]}[other["page_id"]] is True


def test_permission_revoked_during_model_call_returns_403_and_saves_nothing(mentor_env, monkeypatch):
    env = mentor_env
    from metis.core.models import SourceAcl
    from metis.llm.client import ModelClient

    original = ModelClient.call
    source_id = uuid.UUID(env["page"]["source"]["source"]["id"])
    reviewer_id = uuid.UUID(env["reviewer"].user["id"])

    def revoking(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        result = original(self, *args, **kwargs)
        with transaction() as db:  # model çağrısı sürerken kaynak yalnız inceleyiciye kısıtlanır
            db.add(SourceAcl(source_id=source_id, user_id=reviewer_id))
        return result

    monkeypatch.setattr(ModelClient, "call", revoking)
    with transaction() as db:
        before = db.scalar(select(func.count()).select_from(Answer))
    r = env["reader"].post(f"/api/v1/projects/{env['pid']}/mentor/answers", json={"question": "SPI saat bölücü kaç?"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "SOURCE_ACCESS_CHANGED"
    with transaction() as db:
        assert db.scalar(select(func.count()).select_from(Answer)) == before


def test_no_silent_fallback(mentor_env, monkeypatch):
    env = mentor_env
    # İkinci uygun model (başka sağlayıcı) — seçilen model bozulursa ona düşülmemeli.
    prov2 = add_provider(env["admin"], ["fixture-reference"])
    second = model_id("fixture-reference", prov2["id"])
    qualify(env["admin"], second)
    from metis.llm import transport

    original = transport.post_completion

    def failing(url, headers, payload, seconds, ca=None):  # noqa: ANN001, ANN202
        raise transport.TransportError("CONNECTION_FAILED")

    monkeypatch.setattr("metis.llm.client.post_completion", failing)
    with transaction() as db:
        before_second = db.scalar(select(func.count()).select_from(ModelCall).where(ModelCall.model_id == uuid.UUID(second), ModelCall.purpose == "mentor"))
    a = ask(env["reader"], env["pid"], "SPI saat bölücü kaç?", model_id=env["model_id"])
    assert a["decision"] == "MODEL_UNAVAILABLE"
    assert a["model_unavailable_reason"] == "call_failed"
    assert {alt["id"] for alt in a["alternatives"]} == {second}  # alternatif önerilir, kullanılmaz
    assert a["citations"] == []
    with transaction() as db:
        after_second = db.scalar(select(func.count()).select_from(ModelCall).where(ModelCall.model_id == uuid.UUID(second), ModelCall.purpose == "mentor"))
    assert after_second == before_second
    monkeypatch.setattr("metis.llm.client.post_completion", original)


def test_selected_ineligible_model_is_reported_not_replaced(mentor_env):
    env = mentor_env
    prov = add_provider(env["admin"], ["fixture-500"])
    bad = model_id("fixture-500", prov["id"])
    a = ask(env["reader"], env["pid"], "SPI saat bölücü kaç?", model_id=bad)
    assert a["decision"] == "MODEL_UNAVAILABLE" and a["model_unavailable_reason"] == "probe_missing"
    assert a["model"] is None and env["model_id"] in {x["id"] for x in a["alternatives"]}


def test_no_eligible_model_states_reason(team, mock_llm):
    make_demo(team["pid"])
    publish_note(team["contributor"], team["reviewer"], team["pid"], "SPI saat bölücü", SPI, [SPI])
    a = ask(team["reader"], team["pid"], "SPI saat bölücü kaç?")
    assert a["decision"] == "MODEL_UNAVAILABLE" and a["model_unavailable_reason"] == "no_models"


def test_cache_reused_and_revalidated(mentor_env):
    env = mentor_env
    ask(env["reader"], env["pid"], "SPI saat bölücü kaç?")
    ask(env["reader"], env["pid"], "SPI saat bölücü kaç?")
    with transaction() as db:
        cached = db.scalar(select(func.count()).select_from(ModelCall).where(ModelCall.state == "cached", ModelCall.purpose == "mentor"))
    assert cached >= 1


def test_dependency_changed_page_not_used(mentor_env):
    env = mentor_env
    import json as _json

    sid = env["page"]["source"]["source"]["id"]
    meta = {"expected_revision": 1, "text": f"{SPI} {ISR} Ek bilgi."}
    r = env["contributor"].post(f"/api/v1/sources/{sid}/revisions", files={"meta": (None, _json.dumps(meta))})
    assert r.status_code == 201 and r.json()["affected_pages"] == [env["page"]["page_id"]]
    a = ask(env["reader"], env["pid"], "SPI saat bölücü kaç?")
    assert a["decision"] == "NO_EVIDENCE"
    assert a["related"][0]["excluded"] == "dependency_changed"


def test_stream_emits_progress_and_result(mentor_env):
    env = mentor_env
    with env["reader"].http.stream(
        "POST", f"/api/v1/projects/{env['pid']}/mentor/stream", json={"question": "SPI saat bölücü kaç?"}, headers={"X-CSRF-Token": env["reader"].csrf}
    ) as r:
        body = "".join(r.iter_text())
    events = [line.split(": ", 1)[1] for line in body.splitlines() if line.startswith("event: ")]
    assert events[0] == "progress" and "sources" in events and events[-1] == "result"
    assert "kullanılmaz" not in body.split("event: result")[0]  # doğrulanmamış içerik sonuçtan önce akmaz
    # Sıralayıcı yokken adımlar (2.0.26): aranıyor → kaynaklar → model yazıyor → cevap denetleniyor; "ranking" yok.
    steps = [line.split('"step": "', 1)[1].split('"', 1)[0] for line in body.splitlines() if line.startswith("data: ") and '"step": "' in line]
    assert steps == ["searching", "generating", "verifying"]
    assert events.index("sources") < len(events) - 1 and body.index('"generating"') > body.index("event: sources")
def test_answer_delete_is_private(mentor_env):
    env = mentor_env
    a = ask(env["reader"], env["pid"], "SPI saat bölücü kaç?")
    assert env["contributor"].get(f"/api/v1/answers/{a['id']}").status_code == 404
    assert env["reader"].delete(f"/api/v1/answers/{a['id']}").status_code == 204
    assert env["reader"].get(f"/api/v1/projects/{env['pid']}/answers").json() == []


def test_evals_mock_mode_is_100_percent(mock_llm):
    """evals/ vakaları mock modelde %100 (hat doğrulaması; model kalitesi değil)."""
    import argparse
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "evals"))
    import run as evals_run  # type: ignore[import-not-found]

    args = argparse.Namespace(base_url=mock_llm, model="fixture-reference", ca_bundle=None, mode="mock")
    profile = {"json_mode": "json_schema", "thinking": "disabled"}
    ev = evals_run.run_evidence(args, profile, "")
    wk = evals_run.run_worker(args, profile, "")
    ex = evals_run.run_explanation()
    assert (ev["passed"], ev["critical"]) == (ev["n"], 0), [r for r in ev["rows"] if not r["passed"]]
    assert wk["passed"] == wk["n"], [r for r in wk["rows"] if not r["passed"]]
    assert ex["passed"] == ex["n"]
    assert ev["n"] == 26 and wk["n"] == 35 and ex["n"] == 15  # +9 canlı model vakası (1i yalnız canlı modda)


def test_models_table_reports_insufficient_p95(mentor_env):
    rows = mentor_env["admin"].get("/api/v1/models").json()
    ref = next(r for r in rows if r["id"] == mentor_env["model_id"])
    assert ref["latency"]["n"] == 26 and ref["latency"]["p95_ms"] is None and ref["latency"]["p95_notice"] == "yetersiz örnek"
    assert ref["task_label"] == "Kaynaklı kısa cevap için uygun"
    with transaction() as db:
        assert db.get(Model, uuid.UUID(mentor_env["model_id"])).transport_profile["json_mode"] == "json_schema"


def test_long_model_endpoints_do_not_hold_db_connection(mentor_env, monkeypatch):
    """Uzun model çağrısı sırasında istek, kimlik doğrulamadan kalan bir DB bağlantısı tutmaz
    (yük testinde 42 eşzamanlı Mentor isteğinde havuz tükeniyordu, 2026-10-18)."""
    from metis.core.db import engine
    from metis.core.errors import AppError
    from metis.modules.mentor import service as mentor

    seen: list[int] = []

    def fake_ask(*_a, **_k):  # noqa: ANN002, ANN003, ANN202
        seen.append(engine().pool.checkedout())
        raise AppError("NOT_FOUND", "kurgusal")

    monkeypatch.setattr(mentor, "ask", fake_ask)
    r = mentor_env["reader"].post(f"/api/v1/projects/{mentor_env['pid']}/mentor/answers", json={"question": "SPI saat bölücü kaç?"})
    assert r.status_code == 404 and seen == [0]


def test_unrelated_conflict_without_model_reports_model_unavailable(mentor_env):
    """Model yokken, yanında başka sayfalar da bulunan çelişkili sayfa kararı 'Çelişkili' yapmaz: soru cevaplanamaz,
    neden dürüstçe 'model kullanılamıyor'dur."""
    env = mentor_env
    other = publish_note(env["contributor"], env["reviewer"], env["pid"], "SPI bölücü notu", "SPI saat bölücü notları ayrı sayfadadır.")
    with transaction() as db:
        f = Finding(project_id=uuid.UUID(env["pid"]), kind="conflict", severity="high", detail={"sides": []})
        db.add(f)
        db.flush()
        db.add(FindingPage(finding_id=f.id, page_id=uuid.UUID(other["page_id"])))
    assert env["admin"].patch(f"/api/v1/models/{env['model_id']}", json={"enabled": False}).status_code == 200
    a = ask(env["reader"], env["pid"], "SPI saat bölücü kaç?")
    assert a["decision"] == "MODEL_UNAVAILABLE"
    assert {r["page_id"]: r["open_conflict"] for r in a["related"]}[other["page_id"]] is True
