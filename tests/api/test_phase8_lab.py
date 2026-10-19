"""Faz 8 kabul: kritik hata ortalamadan bağımsız eler; n<30 → p95 'yetersiz örnek'; kalıcı temizleme; devre kesici."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import update

from metis.core.db import transaction, utcnow
from metis.core.models import Model
from tests.llm_helpers import add_provider, make_demo, model_id, qualify


def _row(admin, mid):  # noqa: ANN001, ANN202
    return next(r for r in admin.get("/api/v1/models").json() if r["id"] == mid)


def test_critical_error_eliminates_despite_high_average(team, mock_llm):
    make_demo(team["pid"])
    prov = add_provider(team["admin"], ["fixture-one-slip", "fixture-reference"])
    slip = model_id("fixture-one-slip", prov["id"])
    m = qualify(team["admin"], slip)
    assert m["n"] == 26 and m["passed"] == 25 and m["accuracy"] >= 0.9  # ortalama eşiğin üstünde
    # İki kapsam ihlalinden biri metadata ile yakalanır (deterministik koruma, ayrıca sayılır); soru metnindeki kart
    # adına dayanan diğeri modelin hatası olarak kritik kalır ve modeli eler.
    assert m["scope_guarded"] == 1
    assert m["critical_errors"] == 1 and m["critical_kinds"] == ["scope_violation"]
    row = _row(team["admin"], slip)
    assert row["eligible"] is False and row["eligibility_reason"] == "critical_error"


def test_liar_and_fake_source_are_critical(team, mock_llm):
    make_demo(team["pid"])
    prov = add_provider(team["admin"], ["fixture-liar", "fixture-fake-source"])
    liar = qualify(team["admin"], model_id("fixture-liar", prov["id"]))
    assert "fabricated_value" in liar["critical_kinds"] and "false_answer" in liar["critical_kinds"]
    fake = qualify(team["admin"], model_id("fixture-fake-source", prov["id"]))
    assert "fake_source" in fake["critical_kinds"]


def test_p95_requires_30_samples(team, mock_llm):
    make_demo(team["pid"])
    prov = add_provider(team["admin"], ["fixture-reference"])
    mid = model_id("fixture-reference", prov["id"])
    m = qualify(team["admin"], mid)
    assert m["p95_ms"] is None and m["p95_notice"] == "yetersiz örnek (n < 30)"
    assert _row(team["admin"], mid)["latency"]["p95_ms"] is None
    qualify(team["admin"], mid)  # ikinci koşu: toplam 52 örnek
    lat = _row(team["admin"], mid)["latency"]
    assert lat["n"] == 52 and lat["p95_ms"] is not None and lat["p95_notice"] is None


def test_clear_results_is_persistent_and_disqualifies(team, mock_llm):
    make_demo(team["pid"])
    prov = add_provider(team["admin"], ["fixture-reference"])
    mid = model_id("fixture-reference", prov["id"])
    qualify(team["admin"], mid)
    assert team["admin"].post("/api/v1/models/clear-results", json={"model_id": mid}).json()["cleared_runs"] == 1
    for _ in range(2):  # polling ile geri gelmez
        assert team["admin"].get("/api/v1/benchmark-runs", params={"model_id": mid}).json() == []
        assert _row(team["admin"], mid)["benchmark"] is None
    assert _row(team["admin"], mid)["eligibility_reason"] == "not_qualified"
    assert team["reviewer"].post("/api/v1/models/clear-results", json={}).status_code == 403


def test_circuit_breaker_blocks_routing(team, mock_llm):
    make_demo(team["pid"])
    prov = add_provider(team["admin"], ["fixture-reference"])
    mid = model_id("fixture-reference", prov["id"])
    qualify(team["admin"], mid)
    with transaction() as db:
        db.execute(update(Model).where(Model.id == uuid.UUID(mid)).values(circuit_until=utcnow() + timedelta(seconds=60), failures=3))
    avail = team["reader"].get("/api/v1/models/available", params={"project_id": team["pid"]}).json()
    assert avail[0]["eligible"] is False and avail[0]["reason"] == "circuit_open"


def test_routing_prefers_lower_latency_deterministically(team, mock_llm):
    from metis.core.models import Project
    from metis.modules.lab.service import route

    make_demo(team["pid"])
    p1 = add_provider(team["admin"], ["fixture-reference"])
    p2 = add_provider(team["admin"], ["fixture-slow"])
    fast = model_id("fixture-reference", p1["id"])
    qualify(team["admin"], fast)
    qualify(team["admin"], model_id("fixture-slow", p2["id"]))
    with transaction() as db:
        chosen, reasons = route(db, db.get(Project, uuid.UUID(team["pid"])))
        assert str(chosen.id) == fast


def test_members_see_models_and_benchmark_results_read_only(team, mock_llm):
    """Ürün sahibinin isteği (2026-10-19): yönetici olmayanlar Model laboratuvarında eklenen modelleri, son benchmark
    sonuçlarını ve grafiği görür; ekleme, test, benchmark, açma/kapama, silme yalnız yöneticide."""
    make_demo(team["pid"])
    prov = add_provider(team["admin"], ["fixture-reference"])
    mid = model_id("fixture-reference", prov["id"])
    qualify(team["admin"], mid)
    reader = team["reader"]
    models = reader.get("/api/v1/models")
    assert models.status_code == 200, models.text
    row = next(r for r in models.json() if r["id"] == mid)
    assert row["eligible"] is True and row["benchmark"]["n"] == 26 and row["latency"]["p50_ms"] is not None
    # Bağlantı ayrıntıları (sağlayıcı adresi — ad verilmezse adı da adrestir —, istek profili) yalnız yöneticide.
    assert "127.0.0.1" not in models.text and row["provider_name"] == "" and row["transport_profile"] == {}
    assert _row(team["admin"], mid)["provider_name"] and _row(team["admin"], mid)["transport_profile"]
    runs = reader.get("/api/v1/benchmark-runs").json()
    assert [r["model_id"] for r in runs] == [mid]
    detail = reader.get(f"/api/v1/benchmark-runs/{runs[0]['id']}")
    assert detail.status_code == 200 and len(detail.json()["results"]) == 26
    for denied in (
        reader.get("/api/v1/providers"),
        reader.get("/api/v1/allowed-endpoints"),
        reader.post(f"/api/v1/models/{mid}/probe"),
        reader.post("/api/v1/models/benchmark", json={"model_ids": [mid]}),
        reader.patch(f"/api/v1/models/{mid}", json={"enabled": False}),
        reader.delete(f"/api/v1/models/{mid}"),
        reader.post("/api/v1/models/clear-results", json={"model_id": mid}),
    ):
        assert denied.status_code == 403, denied.text
    assert _row(team["admin"], mid)["enabled"] is True
    # Hiçbir projeye üye olmayan kullanıcı görmez.
    assert team["outsider"].get("/api/v1/models").status_code == 403
    assert team["outsider"].get("/api/v1/benchmark-runs").status_code == 403
