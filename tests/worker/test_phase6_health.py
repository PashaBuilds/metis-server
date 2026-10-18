"""Faz 6 kabul: kaynak değişimi işaretleme (mentor kullanmaz), bakım taraması, tek zamanlayıcı,
çelişki çözümü normal inceleme akışından geçmeden yayımlanamaz."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

from sqlalchemy import select, update

from metis.core.db import transaction, utcnow
from metis.core.models import Finding, Job, Page, Schedule
from metis.modules.health.maintenance import schedule_due_jobs
from metis.worker.loop import slot_loop
from tests.kb import approve, publish, publish_note

SCOPE = {"domain": ["Gömülü yazılım"], "kart": ["VPK120"], "yatt": [], "proje": []}


def drain():  # noqa: ANN201
    return slot_loop("w", benchmark=False, once=True)


def test_source_revision_marks_dependents_and_creates_finding(team):
    c, rv, pid = team["contributor"], team["reviewer"], team["pid"]
    out = publish_note(c, rv, pid, "UART", "UART 115200 baud ile çalışır.", scope=SCOPE)
    sid = out["source"]["source"]["id"]
    r = c.post(f"/api/v1/sources/{sid}/revisions", files={"meta": (None, json.dumps({"expected_revision": 1, "text": "UART 9600 baud ile çalışır."}))})
    assert r.json()["affected_pages"] == [out["page_id"]]
    page = team["reader"].get(f"/api/v1/pages/{out['page_id']}").json()
    assert page["freshness"] == "dependency_changed"
    assert page["findings"][0]["kind"] == "source_changed"
    f = team["reader"].get(f"/api/v1/projects/{pid}/findings").json()
    assert f["counts"]["open"] == 1 and f["items"][0]["pages"][0]["title"] == "UART"


def test_republish_resolves_source_changed_and_restores_current(team):
    c, rv, pid = team["contributor"], team["reviewer"], team["pid"]
    out = publish_note(c, rv, pid, "UART", "UART 115200 baud ile çalışır.", scope=SCOPE)
    sid = out["source"]["source"]["id"]
    r = c.post(f"/api/v1/sources/{sid}/revisions", files={"meta": (None, json.dumps({"expected_revision": 1, "text": "UART 9600 baud ile çalışır."}))})
    new_rev = r.json()["revision"]["id"]
    ev = c.post(f"/api/v1/source-revisions/{new_rev}/evidence", json={"excerpt": "UART 9600 baud ile çalışır."}).json()["id"]
    page = c.get(f"/api/v1/pages/{out['page_id']}").json()
    item = {"page_id": out["page_id"], "base_revision_id": page["revision"]["id"], "title": "UART", "scope": SCOPE, "claims": [{"statement": "UART 9600 baud ile çalışır.", "evidence": [{"evidence_id": ev, "quote": "UART 9600 baud ile çalışır."}]}]}
    ch = c.post(f"/api/v1/projects/{pid}/changes", json={"items": [item], "submit": True}).json()
    publish(rv, approve(rv, ch)["id"])
    page = team["reader"].get(f"/api/v1/pages/{out['page_id']}").json()
    assert page["freshness"] == "current" and page["findings"] == []


def test_maintenance_scan_review_due_and_missing_owner(team):
    c, rv, pid = team["contributor"], team["reviewer"], team["pid"]
    out = publish_note(c, rv, pid, "UART", "UART 115200 baud ile çalışır.", scope=SCOPE)
    with transaction() as db:
        db.execute(update(Page).where(Page.id == uuid.UUID(out["page_id"])).values(reviewed_at=utcnow() - timedelta(days=200), published_at=utcnow() - timedelta(days=200)))
    team["admin"].patch(f"/api/v1/users/{c.user['id']}", json={"active": False})
    r = team["admin"].post(f"/api/v1/projects/{pid}/health/scan", json={})
    assert r.status_code == 202
    drain()
    job = team["admin"].get(f"/api/v1/jobs/{r.json()['job_id']}").json()
    assert job["state"] == "completed" and "inceleme zamanı" in job["result_summary"]
    kinds = {f["kind"] for f in team["reader"].get(f"/api/v1/projects/{pid}/findings").json()["items"]}
    assert {"review_due", "missing_owner"} <= kinds
    assert team["reader"].get(f"/api/v1/pages/{out['page_id']}").json()["freshness"] == "review_due"
    # tekrar tarama aynı bulguyu çoğaltmaz
    team["admin"].post(f"/api/v1/projects/{pid}/health/scan", json={})
    drain()
    assert len([f for f in team["reader"].get(f"/api/v1/projects/{pid}/findings").json()["items"] if f["kind"] == "review_due"]) == 1


def test_single_schedule_enqueues_maintenance(team):
    pid = team["pid"]
    r = team["admin"].put(f"/api/v1/projects/{pid}/schedule", json={"enabled": True, "interval_days": 7})
    assert r.status_code == 200 and r.json()["enabled"] is True
    with transaction() as db:
        db.execute(update(Schedule).where(Schedule.project_id == uuid.UUID(pid)).values(next_run_at=utcnow() - timedelta(minutes=1)))
    assert schedule_due_jobs() == 1
    assert schedule_due_jobs() == 0  # next_run_at ileri alındı
    with transaction() as db:
        assert db.scalar(select(Job.kind).where(Job.project_id == uuid.UUID(pid))) == "maintenance"
        assert len(list(db.scalars(select(Schedule).where(Schedule.project_id == uuid.UUID(pid))))) == 1
    assert team["contributor"].put(f"/api/v1/projects/{pid}/schedule", json={"enabled": False, "interval_days": 7}).status_code == 403


def _conflict(team):  # noqa: ANN001, ANN202
    c, rv, pid = team["contributor"], team["reviewer"], team["pid"]
    a = publish_note(c, rv, pid, "UART hızı A", "UART 115200 baud ile çalışır.", scope=SCOPE)
    b = publish_note(c, rv, pid, "UART hızı B", "UART 9600 baud ile çalışır.", scope=SCOPE)
    r = team["admin"].post(f"/api/v1/projects/{pid}/health/scan", json={})
    drain()
    items = team["reader"].get(f"/api/v1/projects/{pid}/findings", params={"kind": "conflict"}).json()["items"]
    assert len(items) == 1, r.text
    return a, b, items[0]


def test_conflict_detected_and_resolution_requires_review(team):
    a, b, finding = _conflict(team)
    assert {p["title"] for p in finding["pages"]} == {"UART hızı A", "UART hızı B"}
    assert len(finding["detail"]["sides"]) == 2
    case = team["contributor"].post(f"/api/v1/findings/{finding['id']}/case").json()
    assert len(case["options"]) == 2 and case["options"][0]["evidence"][0]["quote"]
    opt = case["options"][0]
    r = team["contributor"].post(f"/api/v1/conflict-cases/{case['id']}/choose", json={"option_id": opt["id"], "reason": "Ölçüm kaydı 115200 baud gösteriyor.", "acknowledge_whole_pages": False})
    assert r.status_code == 422 and r.json()["error"]["code"] == "REVIEW_CHECK_REQUIRED"
    case = team["contributor"].post(f"/api/v1/conflict-cases/{case['id']}/choose", json={"option_id": opt["id"], "reason": "Ölçüm kaydı 115200 baud gösteriyor.", "acknowledge_whole_pages": True}).json()
    change_id = case["resolution_change_id"]
    change = team["reviewer"].get(f"/api/v1/changes/{change_id}").json()
    assert change["kind"] == "resolution" and change["state"] == "in_review"
    # İnceleme olmadan yayımlanamaz
    r = team["reviewer"].post(f"/api/v1/changes/{change_id}/publish")
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_STATE"
    retired = opt["retire"][0]["page_id"]
    assert team["reader"].get(f"/api/v1/pages/{retired}").status_code == 200
    # Normal akış: onay + yayın → sayfa geri çekilir, bulgu kapanır
    publish(team["reviewer"], approve(team["reviewer"], change)["id"])
    assert team["reader"].get(f"/api/v1/pages/{retired}").json()["lifecycle"] == "withdrawn"  # banner ile görünür
    assert retired not in [r["page_id"] for r in team["reader"].get(f"/api/v1/projects/{team['pid']}/pages").json()["items"]]
    resolved = team["reader"].get(f"/api/v1/projects/{team['pid']}/findings", params={"state": "resolved"}).json()["items"]
    assert any(f["id"] == finding["id"] for f in resolved)


def test_resolve_with_reason_no_bulk(team):
    _, _, finding = _conflict(team)
    assert team["reader"].post(f"/api/v1/findings/{finding['id']}/resolve", json={"reason": "Farklı modlar için geçerli."}).status_code == 403
    r = team["reviewer"].post(f"/api/v1/findings/{finding['id']}/resolve", json={"reason": "kısa"})
    assert r.status_code == 422
    r = team["reviewer"].post(f"/api/v1/findings/{finding['id']}/resolve", json={"reason": "Değerler farklı çalışma modlarına ait; kayıt güncellenecek."})
    assert r.status_code == 200 and r.json()["state"] == "resolved"


def test_finding_with_inaccessible_page_hidden(team):
    c, rv, pid = team["contributor"], team["reviewer"], team["pid"]
    from tests.kb import add_note, draft, evidence, submit

    src = add_note(c, pid, "Gizli", "UART 57600 baud ile çalışır.", scope=SCOPE, acl=[rv.user["id"]])
    ev = evidence(c, src["revision"]["id"], "UART 57600 baud ile çalışır.")["id"]
    publish(rv, approve(rv, submit(c, draft(c, pid, "Gizli UART", [("UART 57600 baud ile çalışır.", ev)], scope=SCOPE)["id"]))["id"])
    publish_note(c, rv, pid, "Açık UART", "UART 115200 baud ile çalışır.", scope=SCOPE)
    team["admin"].post(f"/api/v1/projects/{pid}/health/scan", json={})
    drain()
    assert len(rv.get(f"/api/v1/projects/{pid}/findings", params={"kind": "conflict"}).json()["items"]) == 1
    assert team["reader"].get(f"/api/v1/projects/{pid}/findings", params={"kind": "conflict"}).json()["items"] == []
    with transaction() as db:
        assert db.scalar(select(Finding.kind).where(Finding.kind == "conflict")) == "conflict"


def test_demo_seed_conflict_is_not_duplicated_by_rule_scan(client):  # noqa: ANN001
    from metis.seed.demo import create_demo_workspace

    out = create_demo_workspace()
    pid = uuid.UUID(out["project_id"])
    client.login(out["users"]["admin"], "Kurgusal-Parola-2026")
    r = client.post(f"/api/v1/projects/{pid}/health/scan", json={})
    assert r.status_code == 202
    drain()
    with transaction() as db:
        conflicts = db.scalars(select(Finding).where(Finding.project_id == pid, Finding.kind == "conflict", Finding.state == "open")).all()
    assert len(conflicts) == 1  # tohum ve kural taraması aynı parmak izini kullanır


def test_demo_seed_matches_self_publish_flow(make_client):  # noqa: ANN001
    """Kurgusal çalışma alanı güncel ürünü yansıtır: yazar yayımlar, bilerek geçilen çelişki, metin içi görsel,
    sahibine "Bilgilerin güncellendi", yarım taslak; incelemede bekleyen kayıt yok."""
    from metis.core.models import ChangeSet, Project
    from metis.seed.demo import create_demo_workspace

    out = create_demo_workspace()
    pid = out["project_id"]
    deniz = make_client()
    deniz.login("deniz", "Kurgusal-Parola-2026")
    with transaction() as db:
        assert db.get(Project, uuid.UUID(pid)).review_policy == "self_publish"
        states = {c.state for c in db.scalars(select(ChangeSet).where(ChangeSet.project_id == uuid.UUID(pid)))}
    assert "in_review" not in states and "draft" in states
    pages = deniz.get(f"/api/v1/projects/{pid}/pages", params={"limit": 50}).json()["items"]
    by_title = {p["title"]: p["page_id"] for p in pages}
    uart = deniz.get(f"/api/v1/pages/{by_title['Hata ayıklama UART hızı']}").json()
    assert uart["review_policy_badge"] == "self_publish" and uart["approved_by"] == "Deniz Kaya"
    assert len(uart["revision"]["figures"]) == 1 and "{{görsel 1}}" in uart["revision"]["body_md"]
    saha = deniz.get(f"/api/v1/pages/{by_title['Konsol baud hızı (saha)']}").json()
    assert saha["approved_by"] == "Barış Demir"
    conflicts = deniz.get(f"/api/v1/projects/{pid}/findings", params={"kind": "conflict"}).json()["items"]
    assert len(conflicts) == 1 and conflicts[0]["detail"]["acknowledged_at_publish"] is True
    updates = deniz.get(f"/api/v1/projects/{pid}/inbox").json()["updated_pages"]
    assert [(u["title"], u["by_name"]) for u in updates] == [("SPI saat bölücü ayarı", "Barış Demir")]
