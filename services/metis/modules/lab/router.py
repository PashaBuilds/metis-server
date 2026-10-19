from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from metis.core.access import require_admin
from metis.core.deps import current_user, get_db
from metis.core.errors import AppError
from metis.core.models import BenchmarkCase, BenchmarkResult, BenchmarkRun, Job, Model, ProjectMember, Provider, User
from metis.modules.lab import service

router = APIRouter(tags=["lab"])


def _require_member(db: Session, user: User) -> None:
    """Model listesi ve benchmark sonuçları (salt okunur) her proje üyesine açık (ürün sahibinin isteği 2026-10-19);
    sağlayıcılar, adresler, anahtarlar ve tüm işlemler yalnız yöneticide."""
    if user.is_admin and user.kind == "human":
        return
    if db.scalar(select(ProjectMember.user_id).where(ProjectMember.user_id == user.id).limit(1)) is None:
        raise AppError("ROLE_REQUIRED", "project membership required")


class ProviderIn(BaseModel):
    name: str = Field(default="", max_length=180)
    base_url: str = Field(min_length=8, max_length=500)
    api_key: str = Field(default="", max_length=2000)
    model_ids: list[str] = Field(min_length=1, max_length=50)
    max_concurrency: int = Field(default=4, ge=1, le=32)  # 14 kişilik yük testinde 2 → en kötü 15 sn, 4 → 10 sn (2026-10-18)
    timeout_s: int = Field(default=60, ge=5, le=600)


class KeyIn(BaseModel):
    api_key: str = Field(default="", max_length=2000)


class ModelIdsIn(BaseModel):
    model_ids: list[str] = Field(min_length=1, max_length=50)


class ModelPatch(BaseModel):
    enabled: bool | None = None
    display_name: str | None = Field(default=None, max_length=200)


class BenchmarkIn(BaseModel):
    model_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)


class ClearIn(BaseModel):
    model_id: uuid.UUID | None = None


class AvailableModel(BaseModel):
    id: str
    display_name: str
    eligible: bool
    reason: str
    is_fixture: bool


class ModelRow(BaseModel):
    id: str
    provider_id: str
    provider_name: str
    remote_id: str
    display_name: str
    enabled: bool
    is_fixture: bool
    transport_profile: dict
    probes: dict[str, dict]
    benchmark: dict | None
    latency: dict
    eligible: bool
    eligibility_reason: str
    task_label: str | None


class RunRow(BaseModel):
    id: str
    model_id: str
    model_name: str
    state: str
    metrics: dict
    created_at: datetime
    finished_at: datetime | None
    current_fingerprint: bool


@router.get("/models/available", response_model=list[AvailableModel])
def available(project_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> list[AvailableModel]:
    return [AvailableModel(**m) for m in service.available_models(db, user, project_id)]


@router.get("/providers")
def providers(user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> list[dict]:
    require_admin(user)
    return [service.provider_out(db, p) for p in db.scalars(select(Provider).where(Provider.deleted_at.is_(None)).order_by(Provider.created_at))]


@router.post("/providers", status_code=201)
def create_provider(data: ProviderIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> dict:
    p = service.create_provider(db, user, data.name, data.base_url, data.api_key, data.model_ids, data.max_concurrency, data.timeout_s)
    return service.provider_out(db, p)


@router.post("/providers/{provider_id}/key")
def rotate_key(provider_id: uuid.UUID, data: KeyIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> dict:
    return service.provider_out(db, service.rotate_key(db, user, provider_id, data.api_key))


@router.post("/providers/{provider_id}/models", status_code=201)
def add_models(provider_id: uuid.UUID, data: ModelIdsIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> dict:
    return {"added": [m.remote_id for m in service.add_models(db, user, provider_id, data.model_ids)]}


@router.delete("/providers/{provider_id}", status_code=204)
def delete_provider(provider_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> Response:
    service.delete_provider(db, user, provider_id)
    return Response(status_code=204)


class AllowedEndpointIn(BaseModel):
    url: str = Field(min_length=8, max_length=500)


class AllowedEndpointRow(BaseModel):
    id: str | None  # sunucu ayarındakiler için None (yalnız metis.env'den kaldırılır)
    url: str
    source: str  # "config" | "ui"
    created_at: datetime | None
    created_by: str | None
    providers: int


@router.get("/allowed-endpoints", response_model=list[AllowedEndpointRow])
def allowed_endpoints(user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> list[AllowedEndpointRow]:
    return [AllowedEndpointRow(**row) for row in service.list_allowed_endpoints(db, user)]


@router.post("/allowed-endpoints", status_code=201, response_model=AllowedEndpointRow)
def allow_endpoint(data: AllowedEndpointIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> AllowedEndpointRow:
    row = service.allow_endpoint(db, user, data.url)
    return AllowedEndpointRow(id=str(row.id), url=row.url, source="ui", created_at=row.created_at, created_by=user.display_name, providers=0)


@router.delete("/allowed-endpoints/{endpoint_id}", status_code=204)
def disallow_endpoint(endpoint_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> Response:
    service.disallow_endpoint(db, user, endpoint_id)
    return Response(status_code=204)


def _model_row(db: Session, m: Model) -> ModelRow:
    p = db.get(Provider, m.provider_id)
    assert p is not None
    probes = {}
    for cap in ("connection", "auth", "json_schema", "thinking_disabled", "evidence_contract"):
        pr = service.latest_probe(db, m.id, cap)
        probes[cap] = {"status": pr.status, "at": pr.at.isoformat(), "error": pr.detail.get("error")} if pr else {"status": "unknown", "at": None, "error": None}
    fp = service.fingerprint(m, p)
    run = db.scalar(
        select(BenchmarkRun)
        .where(BenchmarkRun.model_id == m.id, BenchmarkRun.hidden_at.is_(None), BenchmarkRun.state == "completed")
        .order_by(BenchmarkRun.created_at.desc())
        .limit(1)
    )
    ok, reason = service.eligibility(db, m, None)
    return ModelRow(
        id=str(m.id),
        provider_id=str(p.id),
        provider_name=p.name,
        remote_id=m.remote_id,
        display_name=m.display_name,
        enabled=m.enabled,
        is_fixture=m.is_fixture,
        transport_profile=m.transport_profile,
        probes=probes,
        benchmark={**run.metrics, "run_id": str(run.id), "current_fingerprint": run.fingerprint == fp, "at": run.created_at.isoformat()} if run else None,
        latency=service.latency_summary(db, m, p),
        eligible=ok,
        eligibility_reason=reason,
        task_label="Kaynaklı kısa cevap için uygun" if ok else None,
    )


def _member_view(row: ModelRow) -> ModelRow:
    """Yönetici olmayan üyeye bağlantı ayrıntısı gönderilmez: sağlayıcı adı (ad verilmezse model sunucusunun iç
    adresidir), istek profili ve test hata metinleri. Model adı, uygunluk, benchmark ve gecikme görünür."""
    probes = {k: {**v, "error": None} for k, v in row.probes.items()}
    return row.model_copy(update={"provider_id": "", "provider_name": "", "transport_profile": {}, "probes": probes})


@router.get("/models", response_model=list[ModelRow])
def models(user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> list[ModelRow]:
    _require_member(db, user)
    rows = [_model_row(db, m) for m in db.scalars(select(Model).where(Model.deleted_at.is_(None)).order_by(Model.display_name))]
    return rows if user.is_admin else [_member_view(r) for r in rows]


@router.patch("/models/{model_id}", response_model=ModelRow)
def patch_model(model_id: uuid.UUID, data: ModelPatch, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> ModelRow:
    return _model_row(db, service.update_model(db, user, model_id, data.enabled, data.display_name))


@router.delete("/models/{model_id}", status_code=204)
def delete_model(model_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> Response:
    service.delete_model(db, user, model_id)
    return Response(status_code=204)


@router.post("/models/{model_id}/probe")
def probe(model_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> dict:
    require_admin(user)
    db.commit()
    return service.probe(model_id, user.id)


@router.post("/models/benchmark", status_code=202)
def benchmark(data: BenchmarkIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> dict:
    require_admin(user)
    from metis.modules.jobs.service import enqueue_system_job

    runs = []
    for mid in data.model_ids:
        run = service.start_benchmark(db, user, mid)
        enqueue_system_job(db, user, kind="benchmark", inputs={"run_id": str(run.id)}, title="Ortak benchmark", priority=10)
        runs.append(str(run.id))
    return {"run_ids": runs}


@router.get("/benchmark-runs", response_model=list[RunRow])
def runs(model_id: uuid.UUID | None = None, limit: int = Query(default=50, le=200), user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> list[RunRow]:
    _require_member(db, user)
    q = select(BenchmarkRun).where(BenchmarkRun.hidden_at.is_(None))
    if model_id:
        q = q.where(BenchmarkRun.model_id == model_id)
    out = []
    for r in db.scalars(q.order_by(BenchmarkRun.created_at.desc()).limit(limit)):
        m = db.get(Model, r.model_id)
        p = db.get(Provider, m.provider_id) if m else None
        out.append(RunRow(id=str(r.id), model_id=str(r.model_id), model_name=m.display_name if m else "", state=r.state, metrics=r.metrics, created_at=r.created_at, finished_at=r.finished_at, current_fingerprint=bool(m and p and service.fingerprint(m, p) == r.fingerprint)))
    return out


@router.get("/benchmark-runs/{run_id}")
def run_detail(run_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> dict:
    _require_member(db, user)
    run = db.get(BenchmarkRun, run_id)
    if not run or run.hidden_at is not None:
        raise AppError("NOT_FOUND", "run not found")
    rows = db.execute(select(BenchmarkResult, BenchmarkCase).join(BenchmarkCase, BenchmarkCase.id == BenchmarkResult.case_id).where(BenchmarkResult.run_id == run.id).order_by(BenchmarkCase.case_key)).all()
    return {
        "id": str(run.id),
        "state": run.state,
        "metrics": run.metrics,
        "results": [
            {"case": c.case_key, "task": c.task, "expected": c.expected.get("decision"), "decision": r.decision, "passed": r.passed, "critical": r.critical, "critical_kind": r.critical_kind, "latency_ms": r.latency_ms, "error": r.error}
            for r, c in rows
        ],
    }


@router.post("/models/clear-results")
def clear(data: ClearIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> dict:
    return {"cleared_runs": service.clear_results(db, user, data.model_id)}


@router.get("/models/{model_id}/jobs")
def model_jobs(model_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> list[dict]:
    require_admin(user)
    return [{"id": str(j.id), "state": j.state} for j in db.scalars(select(Job).where(Job.kind == "benchmark", Job.model_id == model_id).limit(20))]
