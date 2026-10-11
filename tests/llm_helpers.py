"""Kurgusal model yardımcıları (testler 127.0.0.1:9101 üzerinde mock sunucu kullanır)."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update

from metis.core.db import transaction
from metis.core.models import BenchmarkRun, Model, Project

MOCK_URL = "http://127.0.0.1:9101/v1"


def make_demo(project_id: str) -> None:
    with transaction() as db:
        db.execute(update(Project).where(Project.id == uuid.UUID(project_id)).values(is_demo=True))


def add_provider(admin, models: list[str], url: str = MOCK_URL, key: str = "kurgusal-anahtar-123") -> dict:  # noqa: ANN001
    r = admin.post("/api/v1/providers", json={"name": "Kurgusal sağlayıcı", "base_url": url, "api_key": key, "model_ids": models, "timeout_s": 20})
    assert r.status_code == 201, r.text
    return r.json()


def model_id(remote_id: str, provider_id: str | None = None) -> str:
    with transaction() as db:
        q = select(Model.id).where(Model.remote_id == remote_id, Model.deleted_at.is_(None))
        if provider_id:
            q = q.where(Model.provider_id == uuid.UUID(provider_id))
        return str(db.scalars(q).first())


def qualify(admin, mid: str) -> dict:  # noqa: ANN001
    """probe + ortak benchmark (senkron çalıştırılır)."""
    from metis.modules.lab.service import execute_benchmark, start_benchmark

    r = admin.post(f"/api/v1/models/{mid}/probe")
    assert r.status_code == 200, r.text
    from metis.core.models import User

    with transaction() as db:
        actor = db.scalar(select(User).where(User.is_admin.is_(True)))
        run = start_benchmark(db, actor, uuid.UUID(mid))
        run_id = run.id
    metrics = execute_benchmark(run_id)
    with transaction() as db:
        assert db.get(BenchmarkRun, run_id).state == "completed"
    return metrics
