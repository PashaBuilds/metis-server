"""Yazar yayımlar: yayın öncesi kontrol (kural + model), uyarıyı bilerek geçme, sahibine bildirim, politika."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from metis.llm.client import CallResult
from tests.kb import add_note, draft, evidence, submit
from tests.llm_helpers import add_provider, make_demo, model_id, qualify

SCOPE = {"domain": ["Gömülü yazılım"], "kart": ["VPK120"], "yatt": [], "proje": []}
FAST = "UART modülü 115200 baud ile çalışır."
SLOW = "UART modülü 57600 baud ile çalışır."
OTHER = "SPI saati 12 MHz değerindedir."


@pytest.fixture
def sp(team):  # noqa: ANN001, ANN201
    r = team["admin"].patch(f"/api/v1/projects/{team['pid']}", json={"review_policy": "self_publish"})
    assert r.status_code == 200, r.text
    return team


def _draft(client, pid: str, title: str, statement: str, **kw) -> dict:  # noqa: ANN001
    src = add_note(client, pid, f"{title} notu", statement, scope=SCOPE)
    ev = evidence(client, src["revision"]["id"], statement)["id"]
    return draft(client, pid, title, [(statement, ev)], scope=SCOPE, **kw)


def _check(client, change_id: str) -> dict:  # noqa: ANN001
    r = client.post(f"/api/v1/changes/{change_id}/check")
    assert r.status_code == 200, r.text
    return r.json()


def _publish(client, change: dict, ack: bool = False):  # noqa: ANN001, ANN202
    return client.post(f"/api/v1/changes/{change['id']}/publish-direct", json={"hash": change["hash"], "acknowledge_issues": ack})


def _self_publish(client, pid: str, title: str, statement: str, **kw) -> dict:  # noqa: ANN001
    ch = _draft(client, pid, title, statement, **kw)
    _check(client, ch["id"])
    r = _publish(client, ch)
    assert r.status_code == 200, r.text
    return r.json()


def test_new_project_default_is_self_publish(client):  # noqa: ANN001
    from tests.factories import setup_admin

    me = setup_admin(client)
    pid = me["memberships"][0]["project_id"]
    assert client.get(f"/api/v1/projects/{pid}").json()["review_policy"] == "self_publish"


def test_author_publishes_own_draft_after_check(sp):
    c, pid = sp["contributor"], sp["pid"]
    ch = _draft(c, pid, "UART hızı", FAST)
    detail = c.get(f"/api/v1/changes/{ch['id']}").json()
    assert detail["can_publish_direct"] is True and detail["prepublish"] is None
    # Kontrol olmadan yayın yok
    r = _publish(c, ch)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CHECK_REQUIRED"
    check = _check(c, ch["id"])
    assert check["issues"] == [] and check["model_status"] == "not_configured" and check["hash"] == ch["hash"]
    assert c.get(f"/api/v1/changes/{ch['id']}").json()["prepublish"]["hash"] == ch["hash"]
    out = _publish(c, ch).json()
    assert out["state"] == "published"
    assert out["reviews"][-1]["policy"] == "self_publish" and out["reviews"][-1]["reviewer_id"] == c.user["id"]
    page = sp["reader"].get(f"/api/v1/pages/{out['published_page_ids'][0]}").json()
    assert page["revision"]["title"] == "UART hızı" and page["review_policy_badge"] == "self_publish"


def test_check_is_bound_to_content_hash(sp):
    c, pid = sp["contributor"], sp["pid"]
    ch = _draft(c, pid, "UART hızı", FAST)
    _check(c, ch["id"])
    item = c.get(f"/api/v1/changes/{ch['id']}").json()["items"][0]["proposed"]
    upd = c.put(
        f"/api/v1/changes/{ch['id']}",
        json={
            "expected_hash": ch["hash"],
            "summary": "Güncel",
            "items": [{"page_id": ch["items"][0]["page_id"], "title": "UART hızı (güncel)", "summary": item["summary"], "body_md": item["body_md"], "scope": SCOPE, "claims": [{"statement": cl["statement"], "evidence": [{"evidence_id": cl["evidence"][0]["evidence_id"], "quote": cl["statement"]}]} for cl in item["claims"]]}],
        },
    )
    assert upd.status_code == 200, upd.text
    ch2 = upd.json()
    assert ch2["hash"] != ch["hash"] and ch2["prepublish"] is None
    r = _publish(c, ch2)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CHECK_REQUIRED"
    assert _publish(c, ch).json()["error"]["code"] == "HASH_MISMATCH"


def test_rule_conflict_warns_and_acknowledged_publish_opens_finding(sp):
    c, a, pid = sp["contributor"], sp["admin"], sp["pid"]
    first = _self_publish(c, pid, "UART hızı A", FAST)
    ch = _draft(a, pid, "UART hızı B", SLOW)
    check = _check(a, ch["id"])
    assert check["model_status"] == "not_configured"
    assert [(i["kind"], i["detected_by"], i["ours"], i["theirs"]) for i in check["issues"]] == [("conflict", "rule", SLOW, FAST)]
    assert check["issues"][0]["page_id"] == first["published_page_ids"][0]
    r = _publish(a, ch)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CHECK_WARNINGS"
    out = _publish(a, ch, ack=True).json()
    assert out["state"] == "published"
    findings = sp["reviewer"].get(f"/api/v1/projects/{pid}/findings", params={"kind": "conflict"}).json()["items"]
    assert len(findings) == 1 and findings[0]["detail"]["acknowledged_at_publish"] is True
    # Bulgu bildiğimiz çözüm akışıyla açılabilir (iki taraf da kanıtlı)
    case = c.post(f"/api/v1/findings/{findings[0]['id']}/case").json()
    assert len(case["options"]) == 2 and all(o["evidence"][0]["quote"] for o in case["options"])
    # Bakım taraması aynı çifti ikinci kez açmaz
    from metis.worker.loop import slot_loop

    a.post(f"/api/v1/projects/{pid}/health/scan", json={})
    slot_loop("w", benchmark=False, once=True)
    assert len(sp["reviewer"].get(f"/api/v1/projects/{pid}/findings", params={"kind": "conflict"}).json()["items"]) == 1


def test_different_scope_is_not_a_conflict(sp):
    c, pid = sp["contributor"], sp["pid"]
    _self_publish(c, pid, "UART hızı A", FAST)
    src = add_note(c, pid, "K2 notu", SLOW, scope={**SCOPE, "kart": ["K2"]})
    ev = evidence(c, src["revision"]["id"], SLOW)["id"]
    ch = draft(c, pid, "UART hızı K2", [(SLOW, ev)], scope={**SCOPE, "kart": ["K2"]})
    assert _check(c, ch["id"])["issues"] == []


def test_unreadable_page_is_not_revealed(sp):
    c, a, pid = sp["contributor"], sp["admin"], sp["pid"]
    src = add_note(a, pid, "Gizli not", FAST, scope=SCOPE, acl=[a.user["id"]])
    ev = evidence(a, src["revision"]["id"], FAST)["id"]
    hidden = draft(a, pid, "Gizli UART", [(FAST, ev)], scope=SCOPE)
    _check(a, hidden["id"])
    assert _publish(a, hidden).status_code == 200
    # Katkı sahibi gizli kaynağı okuyamaz: uyarıda o bilgi (başlığı dahil) görünmez
    ch = _draft(c, pid, "UART hızı", SLOW)
    assert _check(c, ch["id"])["issues"] == []


def test_only_contributors_publish_directly(sp):
    c, rv, pid = sp["contributor"], sp["reviewer"], sp["pid"]
    ch = submit(c, _draft(c, pid, "UART hızı", FAST)["id"])
    _check(c, ch["id"])
    detail = rv.get(f"/api/v1/changes/{ch['id']}").json()
    assert detail["can_publish_direct"] is False
    r = _publish(rv, ch)
    assert r.status_code == 403 and r.json()["error"]["code"] == "ROLE_REQUIRED"
    assert sp["reader"].post(f"/api/v1/changes/{ch['id']}/publish-direct", json={"hash": ch["hash"]}).status_code in (403, 404)
    # Gönderilmiş (incelemede) kayıt da yazarınca doğrudan yayımlanabilir
    assert _publish(c, ch).json()["state"] == "published"


def test_independent_policy_still_requires_review(team):
    c, pid = team["contributor"], team["pid"]
    ch = _draft(c, pid, "UART hızı", FAST)
    assert c.get(f"/api/v1/changes/{ch['id']}").json()["can_publish_direct"] is False
    _check(c, ch["id"])
    r = _publish(c, ch)
    assert r.status_code == 409 and r.json()["error"]["code"] == "REVIEW_REQUIRED"


def test_editing_someone_elses_page_notifies_owner(sp):
    c, a, pid = sp["contributor"], sp["admin"], sp["pid"]
    first = _self_publish(c, pid, "UART hızı", FAST)
    page_id = first["published_page_ids"][0]
    assert c.get(f"/api/v1/projects/{pid}/inbox").json()["updated_pages"] == []
    base = c.get(f"/api/v1/pages/{page_id}").json()["revision"]["id"]
    src = add_note(a, pid, "Ek not", OTHER, scope=SCOPE)
    ev = evidence(a, src["revision"]["id"], OTHER)["id"]
    old = c.get(f"/api/v1/pages/{page_id}").json()["revision"]["claims"][0]
    ch = a.post(
        f"/api/v1/projects/{pid}/changes",
        json={
            "summary": "SPI eklendi",
            "items": [{"page_id": page_id, "base_revision_id": base, "title": "UART hızı", "summary": "Hız ve saat", "body_md": f"{FAST}\n\n{OTHER}", "scope": SCOPE, "claims": [{"statement": FAST, "evidence": [{"evidence_id": old["evidence"][0]["evidence_id"], "quote": FAST}]}, {"statement": OTHER, "evidence": [{"evidence_id": ev, "quote": OTHER}]}]}],
        },
    ).json()
    _check(a, ch["id"])
    assert _publish(a, ch).json()["state"] == "published"
    updates = c.get(f"/api/v1/projects/{pid}/inbox").json()["updated_pages"]
    assert [(u["page_id"], u["by_name"]) for u in updates] == [(page_id, "Ayşe Yönetici")]
    # Yayımlayan kendi bildirimini görmez; "gördüm" listeyi temizler
    assert a.get(f"/api/v1/projects/{pid}/inbox").json()["updated_pages"] == []
    assert c.put("/api/v1/preferences/updates_seen_at", json={"value": datetime.now(UTC).isoformat()}).status_code == 204
    assert c.get(f"/api/v1/projects/{pid}/inbox").json()["updated_pages"] == []


@pytest.fixture
def sp_model(sp, mock_llm):  # noqa: ANN001, ANN201
    make_demo(sp["pid"])
    prov = add_provider(sp["admin"], ["fixture-reference"])
    qualify(sp["admin"], model_id("fixture-reference", prov["id"]))
    return sp


def test_model_judges_rule_candidates_and_finds_duplicates(sp_model):
    c, a, pid = sp_model["contributor"], sp_model["admin"], sp_model["pid"]
    _self_publish(c, pid, "UART hızı A", FAST)
    ch = _draft(a, pid, "UART hızı B", SLOW)
    check = _check(a, ch["id"])
    assert check["model_status"] == "ok" and check["model_name"]
    assert ("conflict", "model") in {(i["kind"], i["detected_by"]) for i in check["issues"]}
    # Aynı bilgiyi tekrar etmek: kural adayı yok, model "zaten var" der
    dup = _draft(a, pid, "UART hızı A", FAST)
    kinds = {i["kind"] for i in _check(a, dup["id"])["issues"]}
    assert "duplicate" in kinds


def test_model_failure_is_reported_and_rule_result_kept(sp_model, monkeypatch):
    c, a, pid = sp_model["contributor"], sp_model["admin"], sp_model["pid"]
    _self_publish(c, pid, "UART hızı A", FAST)
    from metis.modules.changes import prepublish

    monkeypatch.setattr(prepublish.ModelClient, "call", lambda *_a, **_k: CallResult(ok=False, error="TIMEOUT"))
    ch = _draft(a, pid, "UART hızı B", SLOW)
    check = _check(a, ch["id"])
    assert check["model_status"] == "failed"
    assert [(i["kind"], i["detected_by"]) for i in check["issues"]] == [("conflict", "rule")]
    assert _publish(a, ch, ack=True).json()["state"] == "published"
