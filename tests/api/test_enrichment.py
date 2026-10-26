"""İçe aktarmada model zenginleştirmesi (İş 4): model açıkken yayımlanmış bloklara bağlam + soru; saklanır, aramada kullanılır.

Zenginleştirme kanıt değildir: bilgi sayfasında, alıntıda ve Mentor paketinde yer almaz. Kurgusal model (mock) çıktısı
deterministiktir; arama kalitesine katkısı burada ölçülmez (gerçek şirket modeliyle ölçülmedi).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select, text

from metis.core.db import transaction
from metis.core.models import PassageEnrichment, SearchPassage
from metis.modules.search.enrichment import accept, enrich_next
from tests.api.test_search_blocks import _publish
from tests.llm_helpers import add_provider, make_demo, model_id, qualify

BODY = "## Saat\n\nPERST# sinyali en az 100 ms aktif tutulur.\n\n## Kesme\n\nMSI-X kesmeleri XPcie_EnableMsix ile açılır."


def test_accept_filters_invented_identifiers():
    block = "PERST# sinyali en az 100 ms aktif tutulur."
    ctx, qs = accept(block, "PCIe", "", "Bölüm PCIe sıfırlama süresini anlatır.", ["PERST# ne kadar tutulur?", "LTSSM_STATE nedir?", "", "x" * 400])
    assert ctx == "Bölüm PCIe sıfırlama süresini anlatır."
    assert qs == ["PERST# ne kadar tutulur?"]  # blokta geçmeyen tanımlayıcı, boş ve aşırı uzun soru atılır
    ctx, _ = accept(block, "PCIe", "", "LTSSM_STATE değerini anlatır.", [])
    assert ctx == ""  # bağlam da blokta olmayan tanımlayıcı uyduramaz


def test_enrichment_off_by_default(team):  # noqa: ANN001
    """Ürün sahibinin kararı (2026-10-26): kurgusal ölçümde kazanç görülmedi, model token'ı harcar → proje açarsa çalışır."""
    r = team["admin"].get(f"/api/v1/projects/{team['pid']}")
    assert r.status_code == 200 and r.json()["enrichment_enabled"] is False
    with transaction() as db:
        default = db.scalar(
            text("SELECT column_default FROM information_schema.columns WHERE table_name = 'projects' AND column_name = 'enrichment_enabled'")
        )
    assert default == "false"  # SQL ile açılan proje de kapalı başlar


def test_upgrade_turns_off_only_never_enriched_projects(enrich):  # noqa: ANN001
    """0016: zenginleştirmesi saklanmış proje açık kalır (bloklar zenginleştirmeyle indeksli); diğerleri kapanır."""
    import importlib.util
    from pathlib import Path

    import metis

    path = Path(metis.__file__).parent / "migrations" / "versions" / "0016_enrichment_off.py"
    spec = importlib.util.spec_from_file_location("m0016", path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    other = enrich["admin"].post("/api/v1/projects", json={"name": "Kurgusal ikinci proje"}).json()["id"]
    assert _run_all() == 2
    with transaction() as db:
        db.execute(text("UPDATE projects SET enrichment_enabled = true WHERE id IN (:a, :b)"), {"a": enrich["pid"], "b": other})
        db.execute(text(mod.FLIP))
        flags = dict(db.execute(text("SELECT id::text, enrichment_enabled FROM projects WHERE id IN (:a, :b)"), {"a": enrich["pid"], "b": other}).all())
    assert flags == {enrich["pid"]: True, other: False}


@pytest.fixture
def enrich(team, mock_llm):  # noqa: ANN001, ANN201
    pid = team["pid"]
    assert team["admin"].patch(f"/api/v1/projects/{pid}", json={"review_policy": "self_publish", "enrichment_enabled": True}).status_code == 200
    make_demo(pid)  # kurgusal model yalnız kurgusal projede kullanılabilir
    prov = add_provider(team["admin"], ["fixture-reference"])
    qualify(team["admin"], model_id("fixture-reference", prov["id"]))
    page = _publish(team["contributor"], pid, "PCIe kurgusal not", BODY)
    return {**team, "page": page}


def _run_all() -> int:
    total = 0
    while (n := enrich_next()) > 0:
        total += n
    return total


def test_enrichment_stored_and_used_by_search(enrich):  # noqa: ANN001
    with transaction() as db:
        before = dict(db.execute(select(SearchPassage.claim_id, SearchPassage.embed_sha256).where(SearchPassage.page_id == uuid.UUID(enrich["page"]))).all())
    assert _run_all() == 2  # iki gövde bloğu; başlık blokları gönderilmez
    with transaction() as db:
        assert db.scalar(select(func.count()).select_from(PassageEnrichment).where(PassageEnrichment.status == "ok")) == 2
        after = dict(db.execute(select(SearchPassage.claim_id, SearchPassage.embed_sha256).where(SearchPassage.page_id == uuid.UUID(enrich["page"]))).all())
    changed = [c for c in before if before[c] != after.get(c)]
    assert len(changed) == 2  # zenginleştirilen blokların gömme anahtarı değişti (vektör yeniden hesaplanır)
    hits = enrich["reader"].get(f"/api/v1/projects/{enrich['pid']}/search", params={"q": "anlatır"}).json()["hits"]
    assert enrich["page"] in [h["page_id"] for h in hits]  # yalnız zenginleştirmede geçen sözcükle bulunur
    detail = enrich["reader"].get(f"/api/v1/pages/{enrich['page']}").json()
    assert "anlatır" not in detail["revision"]["body_md"]  # kanıt değil: bilgi metnine girmez
    assert _run_all() == 0  # aynı metin yeniden gönderilmez


def test_disabled_project_not_enriched(enrich):  # noqa: ANN001
    r = enrich["admin"].patch(f"/api/v1/projects/{enrich['pid']}", json={"enrichment_enabled": False})
    assert r.status_code == 200 and r.json()["enrichment_enabled"] is False
    assert _run_all() == 0


def test_no_model_no_calls(team):  # noqa: ANN001
    pid = team["pid"]
    assert team["admin"].patch(f"/api/v1/projects/{pid}", json={"review_policy": "self_publish"}).status_code == 200
    _publish(team["contributor"], pid, "PCIe kurgusal not", BODY)
    assert enrich_next() == 0


def test_status_and_setting_admin_only(enrich):  # noqa: ANN001
    st = enrich["admin"].get("/api/v1/system/status").json()["enrichment"]
    assert st["blocks_eligible"] == 2 and st["blocks_enriched"] == 0
    _run_all()
    st = enrich["admin"].get("/api/v1/system/status").json()["enrichment"]
    assert st["blocks_enriched"] == 2
    r = enrich["contributor"].patch(f"/api/v1/projects/{enrich['pid']}", json={"enrichment_enabled": False})
    assert r.status_code in (403, 404)


def _search_titles(c, pid: str, q: str) -> list[str]:  # noqa: ANN001
    return [h["page_id"] for h in c.get(f"/api/v1/projects/{pid}/search", params={"q": q}).json()["hits"]]


def test_upgrade_backfills_keys_then_enriches(enrich):  # noqa: ANN001
    """2.0.20'den yükseltme: eski blokların zenginleştirme anahtarı boş; `metis migrate` doldurur, sonra iş ilerler."""
    from sqlalchemy import update

    from metis.modules.search.index import fill_embed_hashes

    with transaction() as db:
        db.execute(update(SearchPassage).values(base_sha256=None))
    assert enrich_next() == 0  # anahtarsız blok modele gönderilmez (eskiden aynı sayfada takılıyordu)
    with transaction() as db:
        assert fill_embed_hashes(db) > 0
    assert _run_all() == 2


def test_bad_output_marks_failed_and_moves_on(enrich, monkeypatch):  # noqa: ANN001
    from types import SimpleNamespace

    from metis.llm.client import ModelClient

    monkeypatch.setattr(ModelClient, "call", lambda self, *a, **k: SimpleNamespace(ok=False, error="INVALID_RESPONSE", output=None))
    assert enrich_next() == 2 and enrich_next() == 0  # takılmaz: bloklar 'failed', tekrar gönderilmez
    st = enrich["admin"].get("/api/v1/system/status").json()["enrichment"]
    assert st["blocks_failed"] == 2


def test_transient_failure_retries_later(enrich, monkeypatch):  # noqa: ANN001
    from types import SimpleNamespace

    from metis.llm.client import ModelClient

    monkeypatch.setattr(ModelClient, "call", lambda self, *a, **k: SimpleNamespace(ok=False, error="TIMEOUT", output=None))
    assert enrich_next() == -1
    with transaction() as db:
        assert db.scalar(select(func.count()).select_from(PassageEnrichment)) == 0


def test_turning_off_removes_enrichment_from_search(enrich):  # noqa: ANN001
    _run_all()
    assert enrich["page"] in _search_titles(enrich["reader"], enrich["pid"], "anlatır")
    assert enrich["admin"].patch(f"/api/v1/projects/{enrich['pid']}", json={"enrichment_enabled": False}).status_code == 200
    assert enrich["page"] not in _search_titles(enrich["reader"], enrich["pid"], "anlatır")
