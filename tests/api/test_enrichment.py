"""İçe aktarmada model zenginleştirmesi (İş 4): model açıkken yayımlanmış bloklara bağlam + soru; saklanır, aramada kullanılır.

Zenginleştirme kanıt değildir: bilgi sayfasında, alıntıda ve Mentor paketinde yer almaz. Kurgusal model (mock) çıktısı
deterministiktir; arama kalitesine katkısı burada ölçülmez (gerçek şirket modeliyle ölçülmedi).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from metis.core.db import transaction
from metis.core.models import PassageEnrichment, SearchPassage
from metis.modules.search.enrichment import accept, enrich_next
from tests.api.test_search_blocks import _publish
from tests.llm_helpers import add_provider, make_demo, model_id, qualify

BODY = "## Saat\n\nPERST# sinyali en az 100 ms aktif tutulur.\n\n## Kesme\n\nMSI-X kesmeleri XPcie_EnableMsix ile açılır."


def test_accept_filters_invented_identifiers():
    block = "PERST# sinyali en az 100 ms aktif tutulur."
    ctx, qs = accept(block, "PCIe", "Bölüm PCIe sıfırlama süresini anlatır.", ["PERST# ne kadar tutulur?", "LTSSM_STATE nedir?", "", "x" * 400])
    assert ctx == "Bölüm PCIe sıfırlama süresini anlatır."
    assert qs == ["PERST# ne kadar tutulur?"]  # blokta geçmeyen tanımlayıcı, boş ve aşırı uzun soru atılır
    ctx, _ = accept(block, "PCIe", "LTSSM_STATE değerini anlatır.", [])
    assert ctx == ""  # bağlam da blokta olmayan tanımlayıcı uyduramaz


@pytest.fixture
def enrich(team, mock_llm):  # noqa: ANN001, ANN201
    pid = team["pid"]
    assert team["admin"].patch(f"/api/v1/projects/{pid}", json={"review_policy": "self_publish"}).status_code == 200
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
