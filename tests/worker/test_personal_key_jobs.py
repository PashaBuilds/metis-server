"""Görevler kimin anahtarıyla (2.0.28): başlatanın kişisel anahtarı; yeniden başlatanın anahtarı; zamanlanmış bakım ortak
anahtarla. Anahtarsız kişi görevle ortak anahtara kaçamaz."""

from __future__ import annotations

import uuid

import pytest

from metis.core.db import transaction
from metis.core.models import Job, UserProviderKey
from metis.llm import mock_server
from metis.worker.loop import slot_loop
from tests.kb import add_note
from tests.llm_helpers import add_provider, make_demo, model_id, personal_key_value, qualify

NOTE = "Kurgusal kartta DMA kanalı 4 önceliklidir."
SCOPE = {"domain": ["Gömülü yazılım"], "kart": ["VPK120"], "yatt": [], "proje": []}


@pytest.fixture
def kenv(team, mock_llm):  # noqa: ANN001, ANN201
    make_demo(team["pid"])
    prov = add_provider(team["admin"], ["fixture-reference"])
    mid = model_id("fixture-reference", prov["id"])
    qualify(team["admin"], mid)
    ids = {n: team[n].get("/api/v1/auth/me").json()["user"]["id"] for n in ("admin", "contributor")}
    return {**team, "model_id": mid, "provider_id": prov["id"], "ids": ids}


def drain():  # noqa: ANN201
    return slot_loop("test-worker", benchmark=False, once=True)


def enqueue(kenv) -> dict:  # noqa: ANN001
    c, pid = kenv["contributor"], kenv["pid"]
    src = add_note(c, pid, "DMA notu", NOTE, scope=SCOPE)
    r = c.post(f"/api/v1/projects/{pid}/jobs", json={"kind": "prepare_draft", "source_revision_ids": [src["revision"]["id"]], "model_id": kenv["model_id"]})
    assert r.status_code == 201, r.text
    return r.json()


def drop_key(user_id: str, provider_id: str) -> None:
    with transaction() as db:
        db.execute(UserProviderKey.__table__.delete().where(UserProviderKey.user_id == uuid.UUID(user_id), UserProviderKey.provider_id == uuid.UUID(provider_id)))


def test_job_sends_requester_personal_key(kenv):
    job = enqueue(kenv)
    mock_server.SEEN_AUTH.clear()
    assert drain() >= 1
    assert kenv["contributor"].get(f"/api/v1/jobs/{job['id']}").json()["state"] == "completed"
    seen = set(mock_server.SEEN_AUTH)
    assert seen == {f"Bearer {personal_key_value(kenv['ids']['contributor'])}"}


def test_key_removed_after_enqueue_fails_job(kenv):
    job = enqueue(kenv)
    drop_key(kenv["ids"]["contributor"], kenv["provider_id"])
    mock_server.SEEN_AUTH.clear()
    drain()
    d = kenv["contributor"].get(f"/api/v1/jobs/{job['id']}").json()
    assert d["state"] == "failed" and d["error_code"] == "PERSONAL_KEY_MISSING"
    assert mock_server.SEEN_AUTH == []


def test_legacy_job_without_key_source_uses_requester_not_shared(kenv):
    """Yükseltme öncesinden kalan görev ortak anahtara düşmez: başlatanın anahtarı yoksa başarısız olur."""
    job = enqueue(kenv)
    with transaction() as db:
        row = db.get(Job, uuid.UUID(job["id"]))
        row.inputs = {k: v for k, v in row.inputs.items() if k != "key_source"}
    drop_key(kenv["ids"]["contributor"], kenv["provider_id"])
    mock_server.SEEN_AUTH.clear()
    drain()
    assert kenv["contributor"].get(f"/api/v1/jobs/{job['id']}").json()["error_code"] == "PERSONAL_KEY_MISSING"
    assert "Bearer kurgusal-anahtar-123" not in mock_server.SEEN_AUTH


def test_retry_by_someone_else_uses_their_key(kenv):
    job = enqueue(kenv)
    assert kenv["contributor"].post(f"/api/v1/jobs/{job['id']}/cancel").status_code == 200
    r = kenv["admin"].post(f"/api/v1/jobs/{job['id']}/retry")
    assert r.status_code == 200, r.text
    mock_server.SEEN_AUTH.clear()
    drain()
    assert set(mock_server.SEEN_AUTH) == {f"Bearer {personal_key_value(kenv['ids']['admin'])}"}


def test_scheduled_maintenance_uses_shared_key(kenv):
    from metis.core.db import utcnow
    from metis.core.models import Schedule
    from metis.modules.health.maintenance import schedule_due_jobs

    with transaction() as db:
        sched = db.query(Schedule).filter(Schedule.project_id == uuid.UUID(kenv["pid"])).one_or_none()
        if sched is None:
            sched = Schedule(project_id=uuid.UUID(kenv["pid"]))
            db.add(sched)
        sched.enabled, sched.interval_days, sched.next_run_at, sched.model_id = True, 7, utcnow(), uuid.UUID(kenv["model_id"])
    from metis.llm.client import SHARED
    from metis.worker.prepare import job_key

    assert schedule_due_jobs() == 1
    with transaction() as db:
        job = db.query(Job).filter(Job.kind == "maintenance").one()
        assert job.inputs.get("scheduled") is True
        assert job_key(db, job, uuid.UUID(kenv["provider_id"])) == SHARED
    mock_server.SEEN_AUTH.clear()
    drain()
    assert set(mock_server.SEEN_AUTH) <= {"Bearer kurgusal-anahtar-123"}
