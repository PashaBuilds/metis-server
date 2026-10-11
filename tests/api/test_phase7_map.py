"""Faz 7 kabul (backend): erişilemeyen düğüm görünmüyor; odak + komşuluk; ilişki önerisi incelemeden geçer."""

from __future__ import annotations

from tests.kb import add_note, approve, draft, evidence, publish, publish_note, submit


def _rel(client, pid, a, b, predicate="depends_on"):  # noqa: ANN001, ANN202
    r = client.post(f"/api/v1/projects/{pid}/changes", json={"summary": "ilişki", "relations": [{"subject_page_id": a, "predicate": predicate, "object_page_id": b, "rationale": "kurgusal"}], "submit": True})
    assert r.status_code == 201, r.text
    return r.json()


def test_map_hides_inaccessible_nodes_and_edges(team):
    c, rv, pid = team["contributor"], team["reviewer"], team["pid"]
    a = publish_note(c, rv, pid, "A sayfası", "A bileşeni B'ye bağlıdır.")["page_id"]
    b = publish_note(c, rv, pid, "B sayfası", "B bileşeni saat üretir.")["page_id"]
    src = add_note(c, pid, "Gizli", "Gizli bileşen C ayrıntısı.", acl=[rv.user["id"]])
    ev = evidence(c, src["revision"]["id"], "Gizli bileşen C ayrıntısı.")["id"]
    secret = publish(rv, approve(rv, submit(c, draft(c, pid, "C (gizli)", [("Gizli bileşen C ayrıntısı.", ev)])["id"]))["id"])["published_page_ids"][0]
    publish(rv, approve(rv, _rel(c, pid, a, b))["id"])
    publish(rv, approve(rv, _rel(c, pid, b, secret, "explains"))["id"])
    full = rv.get(f"/api/v1/projects/{pid}/map").json()
    assert len(full["nodes"]) == 3 and len(full["edges"]) == 2
    limited = team["reader"].get(f"/api/v1/projects/{pid}/map").json()
    assert {n["title"] for n in limited["nodes"]} == {"A sayfası", "B sayfası"}
    assert len(limited["edges"]) == 1 and limited["total_nodes"] == 2
    assert team["reader"].get(f"/api/v1/projects/{pid}/map", params={"focus": secret}).status_code == 404


def test_map_focus_depth_and_predicate_filter(team):
    c, rv, pid = team["contributor"], team["reviewer"], team["pid"]
    ids = [publish_note(c, rv, pid, f"Sayfa {i}", f"Bileşen {i} tanımı yapılır.")["page_id"] for i in range(4)]
    for x, y in zip(ids, ids[1:], strict=False):
        publish(rv, approve(rv, _rel(c, pid, x, y))["id"])
    one = rv.get(f"/api/v1/projects/{pid}/map", params={"focus": ids[0], "depth": 1}).json()
    assert {n["id"] for n in one["nodes"]} == {ids[0], ids[1]}
    two = rv.get(f"/api/v1/projects/{pid}/map", params={"focus": ids[0], "depth": 2}).json()
    assert len(two["nodes"]) == 3
    none = rv.get(f"/api/v1/projects/{pid}/map", params={"predicate": ["supersedes"]}).json()
    assert none["edges"] == []


def test_relation_proposal_not_live_until_reviewed(team):
    c, rv, pid = team["contributor"], team["reviewer"], team["pid"]
    a = publish_note(c, rv, pid, "A sayfası", "A bileşeni B'ye bağlıdır.")["page_id"]
    b = publish_note(c, rv, pid, "B sayfası", "B bileşeni saat üretir.")["page_id"]
    _rel(c, pid, a, b)
    assert rv.get(f"/api/v1/projects/{pid}/map").json()["edges"] == []
