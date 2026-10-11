"""Faz 2 kabul: hash'e bağlı onay, eşzamanlı düzenleme 409, yayın fault-injection, politika, silme/geri al."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from metis.core.db import transaction
from metis.core.models import ChangeSet, ChangeSetItem, Page, PageRevision, Project
from tests.kb import add_note, approve, draft, evidence, publish, publish_note, submit

TEXT = "UART modulu 115200 baud ile calisir. Tampon boyutu 512 bayttir."
S1 = "UART modulu 115200 baud ile calisir."
S2 = "Tampon boyutu 512 bayttir."


def _setup_draft(team):  # noqa: ANN001, ANN202
    c, pid = team["contributor"], team["pid"]
    src = add_note(c, pid, "UART notu", TEXT)
    ev1 = evidence(c, src["revision"]["id"], S1)["id"]
    return src, draft(c, pid, "UART ayarları", [(S1, ev1)])


def test_full_flow_publish_and_read(team):
    out = publish_note(team["contributor"], team["reviewer"], team["pid"], "UART ayarları", TEXT, [S1, S2])
    page = team["reader"].get(f"/api/v1/pages/{out['page_id']}").json()
    assert page["revision"]["title"] == "UART ayarları"
    assert [c["statement"] for c in page["revision"]["claims"]] == [S1, S2]
    assert page["approved_by"] == "Rana" and page["freshness"] == "current"
    assert all(p["claim_ords"] for p in page["paragraphs"])
    rows = team["reader"].get(f"/api/v1/projects/{team['pid']}/pages").json()["items"]
    assert rows[0]["evidence_count"] == 2 and rows[0]["claim_count"] == 2


def test_draft_not_visible_in_library_until_published(team):
    _, ch = _setup_draft(team)
    assert team["reader"].get(f"/api/v1/projects/{team['pid']}/pages").json()["total"] == 0
    assert team["reader"].get(f"/api/v1/pages/{ch['items'][0]['page_id']}").status_code == 404


def test_claim_requires_evidence_and_verbatim_quote(team):
    c, pid = team["contributor"], team["pid"]
    src = add_note(c, pid, "Not", TEXT)
    ev = evidence(c, src["revision"]["id"], S1)["id"]
    item = {
        "title": "X",
        "scope": {"domain": ["Gömülü yazılım"], "kart": ["VPK120"]},
        "claims": [{"statement": "a", "evidence": []}],
    }
    r = c.post(f"/api/v1/projects/{pid}/changes", json={"items": [item]})
    assert r.json()["error"]["code"] == "CLAIM_EVIDENCE"
    item["claims"] = [{"statement": "a", "evidence": [{"evidence_id": ev, "quote": "uydurma"}]}]
    r = c.post(f"/api/v1/projects/{pid}/changes", json={"items": [item]})
    assert r.json()["error"]["code"] == "QUOTE_NOT_IN_EVIDENCE"


def test_page_scope_cannot_exceed_source_scope(team):
    c, pid = team["contributor"], team["pid"]
    src = add_note(c, pid, "Not", TEXT, scope={"kart": ["VPK120"]})
    ev = evidence(c, src["revision"]["id"], S1)["id"]
    item = {
        "title": "X",
        "scope": {"kart": ["K2"]},
        "claims": [{"statement": S1, "evidence": [{"evidence_id": ev, "quote": S1}]}],
    }
    r = c.post(f"/api/v1/projects/{pid}/changes", json={"items": [item]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "SCOPE_MISMATCH"


def test_review_with_stale_hash_is_rejected(team):
    _, ch = _setup_draft(team)
    ch = submit(team["contributor"], ch["id"])
    r = team["reviewer"].post(
        f"/api/v1/changes/{ch['id']}/reviews", json={"decision": "approve", "evidence_checked": True, "hash": "0" * 64}
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "HASH_MISMATCH"


def test_content_change_after_approval_blocks_publish(team):
    """Onaydan sonra tek karakter değişirse (yeni revizyon) yayın reddedilir; yeniden onay gerekir."""
    c, pid = team["contributor"], team["pid"]
    src, ch = _setup_draft(team)
    ch = submit(c, ch["id"])
    ch = approve(team["reviewer"], ch)
    # Aynı sayfa için tek karakteri farklı yeni bir revizyon üret ve kaydın öğesini ona yönelt (kurcalama simülasyonu).
    ev = evidence(c, src["revision"]["id"], S1)["id"]
    other = draft(c, pid, "UART ayarları!", [(S1, ev)])
    with transaction() as db:
        item = db.scalar(select(ChangeSetItem).where(ChangeSetItem.change_set_id == uuid.UUID(ch["id"])))
        other_item = db.scalar(select(ChangeSetItem).where(ChangeSetItem.change_set_id == uuid.UUID(other["id"])))
        item.proposed_revision_id = other_item.proposed_revision_id
    r = team["reviewer"].post(f"/api/v1/changes/{ch['id']}/publish")
    assert r.status_code == 409 and r.json()["error"]["code"] == "HASH_MISMATCH"
    assert team["reader"].get(f"/api/v1/projects/{pid}/pages").json()["total"] == 0


def test_concurrent_edit_yields_409(team):
    c, rv, pid = team["contributor"], team["reviewer"], team["pid"]
    out = publish_note(c, rv, pid, "UART", TEXT, [S1])
    page = c.get(f"/api/v1/pages/{out['page_id']}").json()
    base = page["revision"]["id"]
    ev = page["revision"]["claims"][0]["evidence"][0]["evidence_id"]
    a = draft(c, pid, "UART v2-a", [(S1, ev)], page_id=out["page_id"], base=base)
    b = draft(team["admin"], pid, "UART v2-b", [(S1, ev)], page_id=out["page_id"], base=base)
    a = approve(rv, submit(c, a["id"]))
    publish(rv, a["id"])
    b = submit(team["admin"], b["id"])
    r = rv.post(
        f"/api/v1/changes/{b['id']}/reviews", json={"decision": "approve", "evidence_checked": True, "hash": b["hash"]}
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "REVISION_CONFLICT"
    # eski taban ile yeni taslak da 409
    item = {
        "page_id": out["page_id"],
        "base_revision_id": base,
        "title": "Eski",
        "scope": {"domain": ["Gömülü yazılım"], "kart": ["VPK120"]},
        "claims": [{"statement": S1, "evidence": [{"evidence_id": ev, "quote": S1}]}],
    }
    r = c.post(f"/api/v1/projects/{pid}/changes", json={"items": [item]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "REVISION_CONFLICT"
    # yeniden temellendir → yeni kayıt, eskisi superseded
    r = team["admin"].post(f"/api/v1/changes/{b['id']}/rebase")
    assert r.status_code == 201, r.text
    assert r.json()["items"][0]["base_is_current"] is True
    assert team["admin"].get(f"/api/v1/changes/{b['id']}").json()["state"] == "superseded"


def test_publish_fault_injection_keeps_old_publication(team, monkeypatch):
    c, rv, pid = team["contributor"], team["reviewer"], team["pid"]
    out = publish_note(c, rv, pid, "UART", TEXT, [S1])
    with transaction() as db:
        old_pub = db.get(Project, uuid.UUID(pid)).active_publication_id
        old_rev = db.get(Page, uuid.UUID(out["page_id"])).published_revision_id
    page = c.get(f"/api/v1/pages/{out['page_id']}").json()
    ev = page["revision"]["claims"][0]["evidence"][0]["evidence_id"]
    ch = approve(
        rv, submit(c, draft(c, pid, "UART v2", [(S1, ev)], page_id=out["page_id"], base=page["revision"]["id"])["id"])
    )

    def boom(*_a, **_k):  # noqa: ANN002, ANN003
        raise RuntimeError("index failure injected")

    monkeypatch.setattr("metis.modules.search.index.index_pages", boom)
    r = rv.post(f"/api/v1/changes/{ch['id']}/publish")
    assert r.status_code == 500
    with transaction() as db:
        assert db.get(Project, uuid.UUID(pid)).active_publication_id == old_pub
        assert db.get(Page, uuid.UUID(out["page_id"])).published_revision_id == old_rev
        assert db.get(ChangeSet, uuid.UUID(ch["id"])).state == "approved"
    assert team["reader"].get(f"/api/v1/pages/{out['page_id']}").json()["revision"]["title"] == "UART"
    monkeypatch.undo()
    publish(rv, ch["id"])
    assert team["reader"].get(f"/api/v1/pages/{out['page_id']}").json()["revision"]["title"] == "UART v2"


def test_independent_policy_blocks_self_approval(team):
    c = team["contributor"]
    _, ch = _setup_draft(team)
    ch = submit(c, ch["id"])
    # yazar inceleyici rolüne sahip olsa da kendi kaydını onaylayamaz
    team["admin"].put(
        f"/api/v1/projects/{team['pid']}/members", json={"user_id": c.user["id"], "roles": ["contributor", "reviewer"]}
    )
    r = c.post(
        f"/api/v1/changes/{ch['id']}/reviews",
        json={"decision": "approve", "evidence_checked": True, "hash": ch["hash"]},
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "SELF_REVIEW_FORBIDDEN"
    detail = c.get(f"/api/v1/changes/{ch['id']}").json()
    assert "self_review" in detail["approve_blockers"]


def test_owner_review_policy_allows_self_with_badge(team):
    pid, admin = team["pid"], team["admin"]
    assert admin.patch(f"/api/v1/projects/{pid}", json={"review_policy": "owner_review"}).status_code == 200
    src = add_note(admin, pid, "Not", TEXT)
    ev = evidence(admin, src["revision"]["id"], S1)["id"]
    ch = approve(admin, submit(admin, draft(admin, pid, "Pilot", [(S1, ev)])["id"]))
    assert ch["reviews"][-1]["policy"] == "owner_review"
    ch = publish(admin, ch["id"])
    page = admin.get(f"/api/v1/pages/{ch['published_page_ids'][0]}").json()
    assert page["review_policy_badge"] == "owner_review"


def test_steward_only_admin_can_switch_policy(team):
    r = team["reviewer"].patch(f"/api/v1/projects/{team['pid']}", json={"review_policy": "owner_review"})
    assert r.status_code == 403


def test_approval_requires_evidence_checkbox_and_reason_for_reject(team):
    _, ch = _setup_draft(team)
    ch = submit(team["contributor"], ch["id"])
    r = team["reviewer"].post(
        f"/api/v1/changes/{ch['id']}/reviews",
        json={"decision": "approve", "evidence_checked": False, "hash": ch["hash"]},
    )
    assert r.json()["error"]["code"] == "REVIEW_CHECK_REQUIRED"
    r = team["reviewer"].post(f"/api/v1/changes/{ch['id']}/reviews", json={"decision": "reject", "hash": ch["hash"]})
    assert r.json()["error"]["code"] == "REASON_REQUIRED"
    r = team["reviewer"].post(
        f"/api/v1/changes/{ch['id']}/reviews",
        json={"decision": "request_changes", "reason": "Kapsamı daralt", "hash": ch["hash"]},
    )
    assert r.status_code == 200 and r.json()["state"] == "draft"


def test_reader_cannot_review_or_publish(team):
    _, ch = _setup_draft(team)
    ch = submit(team["contributor"], ch["id"])
    r = team["reader"].post(
        f"/api/v1/changes/{ch['id']}/reviews",
        json={"decision": "approve", "evidence_checked": True, "hash": ch["hash"]},
    )
    assert r.status_code == 403
    assert team["reader"].post(f"/api/v1/changes/{ch['id']}/publish").status_code == 403


def test_idempotency_key(team):
    c, pid = team["contributor"], team["pid"]
    src = add_note(c, pid, "Not", TEXT)
    ev = evidence(c, src["revision"]["id"], S1)["id"]
    a = draft(c, pid, "Aynı", [(S1, ev)], key="k-1")
    b = draft(c, pid, "Aynı", [(S1, ev)], key="k-1")
    assert a["id"] == b["id"]
    item = {"title": "Farklı", "scope": {}, "claims": []}
    r = c.post(
        f"/api/v1/projects/{pid}/changes", json={"summary": "x", "items": [item]}, headers={"Idempotency-Key": "k-1"}
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_withdraw_removes_from_active_and_search(team):
    out = publish_note(team["contributor"], team["reviewer"], team["pid"], "UART", TEXT, [S1])
    r = team["reviewer"].post(f"/api/v1/pages/{out['page_id']}/withdraw", json={"reason": "Kaynak geçersiz"})
    assert r.status_code == 200 and r.json()["kind"] == "withdrawal"
    assert team["reader"].get(f"/api/v1/projects/{team['pid']}/pages").json()["total"] == 0
    assert team["reader"].get(f"/api/v1/projects/{team['pid']}/search", params={"q": "UART"}).json()["hits"] == []


def test_delete_published_record_and_undo(team):
    out = publish_note(team["contributor"], team["reviewer"], team["pid"], "UART", TEXT, [S1])
    cid = out["change"]["id"]
    r = team["reviewer"].delete(f"/api/v1/changes/{cid}")
    assert r.status_code == 200 and r.json()["pruned_pages"] == [out["page_id"]]
    assert team["reader"].get(f"/api/v1/projects/{team['pid']}/pages").json()["total"] == 0
    assert team["reviewer"].get(f"/api/v1/changes/{cid}").status_code == 404
    assert team["reviewer"].post(f"/api/v1/changes/{cid}/restore").status_code == 204
    assert team["reader"].get(f"/api/v1/projects/{team['pid']}/pages").json()["total"] == 1


def test_contributor_can_delete_own_draft_only(team):
    _, ch = _setup_draft(team)
    assert team["reader"].delete(f"/api/v1/changes/{ch['id']}").status_code == 403
    assert team["contributor"].delete(f"/api/v1/changes/{ch['id']}").status_code == 200


def test_delete_page_from_library_and_restore(team):
    out = publish_note(team["contributor"], team["reviewer"], team["pid"], "UART", TEXT, [S1])
    assert team["contributor"].delete(f"/api/v1/pages/{out['page_id']}").status_code == 403
    assert team["reviewer"].delete(f"/api/v1/pages/{out['page_id']}").json() == {"was_active": True}
    assert team["reader"].get(f"/api/v1/pages/{out['page_id']}").status_code == 404
    assert team["reviewer"].post(f"/api/v1/pages/{out['page_id']}/restore").status_code == 204
    assert team["reader"].get(f"/api/v1/pages/{out['page_id']}").status_code == 200


def test_claim_diff_and_history_compare(team):
    c, rv, pid = team["contributor"], team["reviewer"], team["pid"]
    out = publish_note(c, rv, pid, "UART", TEXT, [S1])
    page = c.get(f"/api/v1/pages/{out['page_id']}").json()
    src_rev = out["source"]["revision"]["id"]
    ev2 = evidence(c, src_rev, S2)["id"]
    ev1 = page["revision"]["claims"][0]["evidence"][0]["evidence_id"]
    ch = draft(c, pid, "UART", [(S1, ev1), (S2, ev2)], page_id=out["page_id"], base=page["revision"]["id"])
    item = ch["items"][0]
    assert item["summary_counts"]["added"] == 1 and item["summary_counts"]["unchanged"] == 1
    publish(rv, approve(rv, submit(c, ch["id"]))["id"])
    hist = c.get(f"/api/v1/pages/{out['page_id']}/history").json()
    assert [h["number"] for h in hist] == [2, 1]
    cmp = c.get(
        f"/api/v1/pages/{out['page_id']}/compare", params={"a": hist[1]["revision_id"], "b": hist[0]["revision_id"]}
    ).json()
    assert [d["status"] for d in cmp["claim_diff"]] == ["unchanged", "added"]


@pytest.mark.parametrize(
    "table", ["page_revisions", "claims", "claim_evidence", "reviews", "publications", "publication_pages"]
)
def test_immutability_triggers_on_knowledge_tables(team, table):
    publish_note(team["contributor"], team["reviewer"], team["pid"], "UART", TEXT, [S1])
    col = {
        "page_revisions": "title",
        "claims": "statement",
        "claim_evidence": "quote",
        "reviews": "reason",
        "publications": "kind",
        "publication_pages": "page_id",
    }[table]
    value = "page_id" if col == "page_id" else "'x'"
    with pytest.raises(DBAPIError) as exc, transaction() as db:
        db.execute(text(f"UPDATE {table} SET {col} = {value}"))
    assert "METIS_IMMUTABLE" in str(exc.value)


def test_worker_identity_cannot_publish_or_review(team):
    """LLM/worker hiçbir zaman onaylamaz/yayımlamaz — sunucu tarafı yetki ile."""
    from metis.core.errors import AppError
    from metis.core.models import User
    from metis.modules.auth.service import ensure_worker_identity
    from metis.modules.changes import schemas as cs
    from metis.modules.changes import service as svc

    _, ch = _setup_draft(team)
    ch = submit(team["contributor"], ch["id"])
    with transaction() as db:
        worker = ensure_worker_identity(db)
        db.flush()
        with pytest.raises(AppError) as exc:
            svc.review(
                db, worker, uuid.UUID(ch["id"]), cs.ReviewIn(decision="approve", evidence_checked=True, hash=ch["hash"])
            )
        assert exc.value.code in ("HUMAN_REQUIRED", "NOT_FOUND")
        with pytest.raises(AppError):
            svc.publish_change(db, worker, uuid.UUID(ch["id"]))
        with pytest.raises(AppError):
            svc.withdraw_page(db, worker, uuid.UUID(ch["items"][0]["page_id"]), "x")
        assert db.scalar(select(User).where(User.kind == "worker")).is_admin is False
    with transaction() as db:
        assert db.get(PageRevision, uuid.UUID(ch["items"][0]["proposed"]["id"])) is not None


def test_review_tab_and_inbox_show_waiting_records(team):
    """Bağımsız politikada inceleyici, başkasının incelemedeki kaydını görür; yazar kendi kaydını görmez."""
    _, ch = _setup_draft(team)
    submit(team["contributor"], ch["id"])
    pid = team["pid"]
    lst = team["reviewer"].get(f"/api/v1/projects/{pid}/changes", params={"tab": "review"}).json()
    assert [c["id"] for c in lst["items"]] == [ch["id"]] and lst["counts"]["review"] == 1
    assert team["reviewer"].get(f"/api/v1/projects/{pid}/inbox").json()["reviews_waiting"] == 1
    team["admin"].put(f"/api/v1/projects/{pid}/members", json={"user_id": team["contributor"].user["id"], "roles": ["contributor", "reviewer"]})
    assert team["contributor"].get(f"/api/v1/projects/{pid}/changes", params={"tab": "review"}).json()["items"] == []
    assert team["contributor"].get(f"/api/v1/projects/{pid}/inbox").json()["reviews_waiting"] == 0
