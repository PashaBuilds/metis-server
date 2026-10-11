"""Faz 3 kabul: Türkçe çekim, birebir sembol, TR↔EN alias, filtreler, erişim sızıntısı yok."""

from __future__ import annotations

from tests.kb import add_note, approve, draft, evidence, publish, publish_note, submit

KESME = "Kesme yoneticisi XAxiPcie_IntrEnable cagrisiyla MSI kesmesini etkinlestirir."
BUS = "INIT_BUS cagrisi saat ayarindan once yapilir."
SPI = "SPI denetleyicisi 8 bolucu ile 12.5 MHz uretir."


def _seed(team):  # noqa: ANN001, ANN202
    c, rv, pid = team["contributor"], team["reviewer"], team["pid"]
    a = publish_note(c, rv, pid, "Kesme yönetimi", KESME)
    b = publish_note(
        c,
        rv,
        pid,
        "Veri yolu başlatma",
        BUS,
        scope={"domain": ["Gömülü yazılım"], "kart": ["K2"], "proje": [], "yatt": []},
    )
    s = publish_note(c, rv, pid, "SPI saat ayarı", SPI)
    return a, b, s


def _q(client, pid, q, **params):  # noqa: ANN001, ANN202
    r = client.get(f"/api/v1/projects/{pid}/search", params={"q": q, **params})
    assert r.status_code == 200, r.text
    return [h["title"] for h in r.json()["hits"]]


def test_turkish_inflection(team):
    _seed(team)
    assert "Kesme yönetimi" in _q(team["reader"], team["pid"], "kesmeler")
    assert "Kesme yönetimi" in _q(team["reader"], team["pid"], "kesmesini")


def test_exact_symbol_match_ranks_first(team):
    _seed(team)
    hits = _q(team["reader"], team["pid"], "XAxiPcie_IntrEnable")
    assert hits[0] == "Kesme yönetimi"
    assert _q(team["reader"], team["pid"], "INIT_BUS")[0] == "Veri yolu başlatma"
    r = team["reader"].get(f"/api/v1/projects/{team['pid']}/search", params={"q": "INIT_BUS nasıl çağrılır"}).json()
    assert r["hits"][0]["matched_symbols"] == ["INIT_BUS"]


def test_symbol_not_normalized(team):
    _seed(team)
    # Küçük harfe çevrilmiş sembol birebir eşleşme sayılmaz (yine de FTS ile bulunabilir ama sembol eşleşmesi yok)
    r = team["reader"].get(f"/api/v1/projects/{team['pid']}/search", params={"q": "init_bus"}).json()
    assert all(h["matched_symbols"] == [] for h in r["hits"])


def test_tr_en_alias_from_domain_pack(team):
    _seed(team)
    assert "Kesme yönetimi" in _q(team["reader"], team["pid"], "interrupt")
    assert "Kesme yönetimi" in _q(team["reader"], team["pid"], "ISR")


def test_scope_filter(team):
    _seed(team)
    assert _q(team["reader"], team["pid"], "INIT_BUS", kart=["VPK120"]) == []
    assert _q(team["reader"], team["pid"], "INIT_BUS", kart=["K2"]) == ["Veri yolu başlatma"]


def test_library_filters_and_domains(team):
    _seed(team)
    pid = team["pid"]
    rows = team["reader"].get(f"/api/v1/projects/{pid}/pages", params={"kart": ["K2"]}).json()
    assert [r["title"] for r in rows["items"]] == ["Veri yolu başlatma"]
    rows = team["reader"].get(f"/api/v1/projects/{pid}/pages", params={"q": "SPI"}).json()
    assert [r["title"] for r in rows["items"]] == ["SPI saat ayarı"]
    domains = team["reader"].get(f"/api/v1/projects/{pid}/domains").json()
    assert domains[0]["label"] == "Gömülü yazılım" and domains[0]["page_count"] == 3


def test_inaccessible_page_does_not_leak_in_search_library_or_relations(team):
    c, rv, pid = team["contributor"], team["reviewer"], team["pid"]
    public = publish_note(c, rv, pid, "SPI saat ayarı", SPI)
    # Yalnız inceleyiciye açık kaynak üzerinde gizli sayfa
    secret_src = add_note(c, pid, "Gizli", "GIZLI_SEMBOL_42 yalnizca ekip icin.", acl=[rv.user["id"]])
    ev = evidence(c, secret_src["revision"]["id"], "GIZLI_SEMBOL_42 yalnizca ekip icin.")["id"]
    ch = publish(
        rv,
        approve(rv, submit(c, draft(c, pid, "Gizli bilgi", [("GIZLI_SEMBOL_42 yalnizca ekip icin.", ev)])["id"]))["id"],
    )
    secret_page = ch["published_page_ids"][0]
    # İki sayfa arasında ilişki yayımla
    rel = {
        "subject_page_id": public["page_id"],
        "predicate": "depends_on",
        "object_page_id": secret_page,
        "rationale": "kurgusal",
    }
    r = c.post(f"/api/v1/projects/{pid}/changes", json={"summary": "ilişki", "relations": [rel]})
    assert r.status_code == 201, r.text
    publish(rv, approve(rv, submit(c, r.json()["id"]))["id"])
    # inceleyici görür
    assert _q(rv, pid, "GIZLI_SEMBOL_42") == ["Gizli bilgi"]
    assert len(rv.get(f"/api/v1/pages/{public['page_id']}").json()["relations"]) == 1
    # okur görmez: arama, liste, toplam, ilişki, doğrudan erişim (404)
    reader = team["reader"]
    assert _q(reader, pid, "GIZLI_SEMBOL_42") == []
    lib = reader.get(f"/api/v1/projects/{pid}/pages").json()
    assert lib["total"] == 1 and lib["items"][0]["title"] == "SPI saat ayarı"
    assert reader.get(f"/api/v1/pages/{public['page_id']}").json()["relations"] == []
    assert reader.get(f"/api/v1/pages/{secret_page}").status_code == 404
    assert reader.get(f"/api/v1/projects/{pid}/domains").json()[0]["page_count"] == 1
    # üye olmayan için proje yok
    assert team["outsider"].get(f"/api/v1/projects/{pid}/search", params={"q": "SPI"}).status_code == 404


def test_search_index_contains_only_active_publication(team):
    c, rv, pid = team["contributor"], team["reviewer"], team["pid"]
    out = publish_note(c, rv, pid, "SPI saat ayarı", SPI)
    page = c.get(f"/api/v1/pages/{out['page_id']}").json()
    ev = page["revision"]["claims"][0]["evidence"][0]["evidence_id"]
    publish(
        rv,
        approve(
            rv,
            submit(
                c, draft(c, pid, "SPI bölücü", [(SPI, ev)], page_id=out["page_id"], base=page["revision"]["id"])["id"]
            ),
        )["id"],
    )
    from sqlalchemy import func, select

    from metis.core.db import transaction
    from metis.core.models import SearchDocument

    with transaction() as db:
        assert db.scalar(select(func.count()).select_from(SearchDocument)) == 1
        assert db.scalar(select(SearchDocument.title)) == "SPI bölücü"
