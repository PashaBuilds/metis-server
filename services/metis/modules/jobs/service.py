"""Metis görevleri: kuyruk, durum geçişleri, idempotency, olay akışı (SSE için job_events).

Durumlar: queued → running → (awaiting_input → queued) → completed | failed | cancelled | budget_exceeded.
İptal / yeniden dene / yanıt fence'i artırır: eski worker artık yazamaz.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from metis.core.access import can_read_source, require_human, require_member
from metis.core.audit import audit
from metis.core.db import utcnow
from metis.core.errors import AppError
from metis.core.models import (
    ChangeSet,
    Job,
    JobEvent,
    JobMessage,
    JobOutput,
    Model,
    Project,
    Source,
    SourceRevision,
    User,
)
from metis.core.util import fingerprint

PRIORITY = {"prepare_draft": 80, "refine_draft": 80, "audit_pool": 50, "maintenance": 30, "benchmark": 10}
USER_KINDS = {"prepare_draft", "refine_draft", "audit_pool"}
ACTIVE = ("queued", "running", "awaiting_input")
KIND_TITLES = {
    "prepare_draft": "Kaynaktan taslak hazırla",
    "refine_draft": "Taslağı düzenle ve karşılaştır",
    "audit_pool": "Bilgi havuzunu denetle",
    "maintenance": "Bakım taraması",
    "benchmark": "Ortak benchmark",
}


class JobCreateIn(BaseModel):
    kind: str = Field(pattern="^(prepare_draft|refine_draft|audit_pool)$")
    model_id: uuid.UUID | None = None
    source_revision_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)
    draft_change_id: uuid.UUID | None = None
    instructions: str = Field(default="", max_length=2000)


class AnswerIn(BaseModel):
    text: str = Field(default="", max_length=4000)
    scope: dict | None = None


def add_event(db: Session, job_id: uuid.UUID, kind: str, **data: object) -> None:
    db.add(JobEvent(job_id=job_id, kind=kind, data={k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in data.items()}))


from metis.modules.keys.service import key_for  # noqa: E402


def _model_ok(db: Session, model_id: uuid.UUID | None, project: Project) -> Model:
    from metis.modules.lab.service import eligibility

    if not model_id:
        raise AppError("MODEL_REQUIRED", "select a model explicitly")
    model = db.get(Model, model_id)
    if model is None:
        raise AppError("MODEL_NOT_ELIGIBLE", "model not found", reason="not_found")
    ok, reason = eligibility(db, model, project)
    if not ok:
        raise AppError("MODEL_NOT_ELIGIBLE", "model not eligible", reason=reason)
    return model


def enqueue(db: Session, user: User, project_id: uuid.UUID, data: JobCreateIn) -> tuple[Job, bool]:
    """(job, yeni mi). Aynı girdiyle aktif veya tamamlanmış iş varsa onu döner (idempotent tek taslak)."""
    require_human(user)
    require_member(db, user, project_id, ["contributor"])
    project = db.get(Project, project_id)
    assert project is not None
    model = _model_ok(db, data.model_id, project)
    # Görev başlatanın kişisel anahtarıyla çalışır (2.0.28); yönetici kişisel anahtar eklemediyse ortak anahtarla.
    key = key_for(db, user, model.provider_id)
    if key is None:
        raise AppError("PERSONAL_KEY_MISSING", "add your own API key for this model's provider", provider_id=str(model.provider_id))
    inputs: dict = {"model_id": str(model.id), "instructions": data.instructions.strip(), "key_source": key.source}
    if data.kind == "prepare_draft":
        if not data.source_revision_ids:
            raise AppError("VALIDATION_ERROR", "source revisions required", fields=[{"field": "source_revision_ids", "type": "missing"}])
        for rid in data.source_revision_ids:
            rev = db.get(SourceRevision, rid)
            src = db.get(Source, rev.source_id) if rev else None
            if not rev or not src or src.project_id != project_id or not can_read_source(db, user, src):
                raise AppError("NOT_FOUND", "source revision not found")
        inputs["source_revision_ids"] = sorted(str(r) for r in data.source_revision_ids)
    elif data.kind == "refine_draft":
        if not data.draft_change_id:
            raise AppError("VALIDATION_ERROR", "draft required", fields=[{"field": "draft_change_id", "type": "missing"}])
        from metis.modules.changes.service import accessible_change

        change = accessible_change(db, user, data.draft_change_id)
        if change.state not in ("draft", "in_review"):
            raise AppError("INVALID_STATE", "only open drafts can be refined")
        inputs["draft_change_id"] = str(change.id)
        inputs["draft_hash"] = change.hash
    fp = fingerprint(data.kind, project_id, model.id, inputs.get("source_revision_ids"), inputs.get("draft_hash"), inputs["instructions"])
    if data.kind != "audit_pool":
        existing = db.scalar(
            select(Job)
            .where(Job.project_id == project_id, Job.input_fingerprint == fp, Job.deleted_at.is_(None), or_(Job.state.in_(ACTIVE), Job.state == "completed"))
            .order_by(Job.created_at.desc())
            .limit(1)
        )
        if existing is not None:
            outputs_alive = db.scalars(
                select(ChangeSet.id).join(JobOutput, JobOutput.change_set_id == ChangeSet.id).where(JobOutput.job_id == existing.id, ChangeSet.deleted_at.is_(None))
            ).all()
            if existing.state in ACTIVE or outputs_alive or (existing.checkpoint or {}).get("produced_draft") is False:
                return existing, False
    job = Job(
        project_id=project_id,
        requester_id=user.id,
        kind=data.kind,
        title=KIND_TITLES[data.kind],
        inputs=inputs,
        input_fingerprint=fp if data.kind != "audit_pool" else "",
        state="queued",
        priority=PRIORITY[data.kind],
        model_id=model.id,
    )
    db.add(job)
    db.flush()
    add_event(db, job.id, "state", state="queued")
    audit(db, user.id, "job.enqueue", "job", job.id, kind=data.kind)
    return job, True


def enqueue_system_job(db: Session, user: User | None, *, kind: str, inputs: dict, title: str, priority: int, project_id: uuid.UUID | None = None) -> Job:
    if project_id is None:
        project_id = db.scalar(select(Project.id).where(Project.deleted_at.is_(None)).order_by(Project.created_at).limit(1))
    if project_id is None:
        raise AppError("INVALID_STATE", "no project for system job")
    requester = user.id if user else db.scalar(select(User.id).where(User.is_admin.is_(True), User.kind == "human").limit(1))
    job = Job(project_id=project_id, requester_id=requester, kind=kind, title=title, inputs=inputs, state="queued", priority=priority)
    if kind == "benchmark":
        from metis.core.models import BenchmarkRun

        run = db.get(BenchmarkRun, uuid.UUID(inputs["run_id"]))
        job.model_id = run.model_id if run else None
    db.add(job)
    db.flush()
    add_event(db, job.id, "state", state="queued")
    return job


def get_job(db: Session, user: User, job_id: uuid.UUID) -> Job:
    job = db.get(Job, job_id)
    if not job or job.deleted_at is not None:
        raise AppError("NOT_FOUND", "job not found")
    require_member(db, user, job.project_id)
    if job.requester_id != user.id and not ({"steward"} & _roles(db, user, job.project_id)):
        raise AppError("NOT_FOUND", "job not found")
    return job


def _roles(db: Session, user: User, project_id: uuid.UUID) -> set[str]:
    from metis.core.access import effective_roles

    return effective_roles(db, user, project_id)


def cancel(db: Session, user: User, job_id: uuid.UUID) -> Job:
    require_human(user)
    job = get_job(db, user, job_id)
    db.refresh(job, with_for_update=True)
    if job.state not in ACTIVE:
        raise AppError("INVALID_STATE", "job is not active")
    job.state = "cancelled"
    job.fence += 1  # eski worker artık yazamaz
    job.lease_until = None
    job.finished_at = utcnow()
    job.updated_at = utcnow()
    add_event(db, job.id, "state", state="cancelled")
    audit(db, user.id, "job.cancel", "job", job.id)
    return job


def retry(db: Session, user: User, job_id: uuid.UUID) -> Job:
    require_human(user)
    job = get_job(db, user, job_id)
    db.refresh(job, with_for_update=True)
    if job.state not in ("failed", "cancelled", "budget_exceeded"):
        raise AppError("INVALID_STATE", "only failed or cancelled jobs can be retried")
    if job.input_fingerprint and db.scalar(
        select(Job.id).where(Job.project_id == job.project_id, Job.input_fingerprint == job.input_fingerprint, Job.state.in_(ACTIVE), Job.id != job.id)
    ):
        raise AppError("INVALID_STATE", "an identical job is already active")
    job.state = "queued"
    job.fence += 1
    job.attempt = 0
    job.error_code = None
    job.lease_until = None
    job.updated_at = utcnow()
    add_event(db, job.id, "state", state="queued")
    audit(db, user.id, "job.retry", "job", job.id)
    return job


def answer_question(db: Session, user: User, job_id: uuid.UUID, data: AnswerIn) -> Job:
    """'Yanıtını bekliyor' sorusuna cevap. Kapsam cevabı, kaynağın aynı içerikle yeni (insan) revizyonunu oluşturur."""
    require_human(user)
    job = get_job(db, user, job_id)
    db.refresh(job, with_for_update=True)
    if job.state != "awaiting_input":
        raise AppError("INVALID_STATE", "job is not waiting for input")
    if job.requester_id != user.id:
        raise AppError("ROLE_REQUIRED", "only the requester can answer")
    if not data.text.strip() and not data.scope:
        raise AppError("VALIDATION_ERROR", "answer required", fields=[{"field": "text", "type": "missing"}])
    if data.scope:
        from metis.core.blobs import read_blob
        from metis.modules.scopes.schemas import ScopeIn
        from metis.modules.sources import schemas as ss
        from metis.modules.sources import service as sources

        new_ids = []
        for rid in job.inputs.get("source_revision_ids", []):
            rev = db.get(SourceRevision, uuid.UUID(rid))
            src = db.get(Source, rev.source_id) if rev else None
            if not rev or not src:
                raise AppError("NOT_FOUND", "source revision not found")
            if src.current_revision_no != rev.number:
                raise AppError("REVISION_CONFLICT", "source changed meanwhile", current_revision=src.current_revision_no)
            content = sources.PreparedContent(read_blob(rev.sha256), rev.filename, rev.media_type, rev.text, rev.extraction, rev.extractor_version, [])
            meta = ss.RevisionMetaIn(expected_revision=rev.number, scope=ScopeIn(**data.scope))
            _, new_rev, _ = sources.add_revision(db, user, src.id, meta, content)
            new_ids.append(str(new_rev.id))
        job.inputs = {**job.inputs, "source_revision_ids": sorted(new_ids)}
        job.input_fingerprint = fingerprint(job.input_fingerprint, "answered", sorted(new_ids))
    for msg in db.scalars(select(JobMessage).where(JobMessage.job_id == job.id, JobMessage.role == "metis", JobMessage.answered_at.is_(None))):
        msg.answered_at = utcnow()
    db.add(JobMessage(job_id=job.id, role="user", body=data.text.strip() or "Kapsam seçildi.", detail={"scope": data.scope} if data.scope else {}, author_id=user.id))
    job.state = "queued"
    job.fence += 1
    job.lease_until = None
    job.updated_at = utcnow()
    add_event(db, job.id, "message", role="user")
    add_event(db, job.id, "state", state="queued")
    audit(db, user.id, "job.answer", "job", job.id)
    return job


def delete_job(db: Session, user: User, job_id: uuid.UUID) -> None:
    require_human(user)
    job = get_job(db, user, job_id)
    if job.state in ("running",):
        raise AppError("INVALID_STATE", "cancel the job first")
    job.deleted_at = utcnow()
    audit(db, user.id, "job.delete", "job", job.id)


# ---------------------------------------------------------------- görünümler


class JobRow(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    state: str
    created_at: object
    started_at: object
    finished_at: object
    result_summary: str
    error_code: str | None
    model_name: str | None
    requester_name: str
    output_change_ids: list[uuid.UUID]
    awaiting_question: bool
    legacy: bool


class JobDetail(JobRow):
    messages: list[dict]
    report: dict
    technical: dict
    can_cancel: bool
    can_retry: bool
    can_answer: bool


def job_row(db: Session, job: Job) -> JobRow:
    model = db.get(Model, job.model_id) if job.model_id else None
    requester = db.get(User, job.requester_id)
    outs = db.scalars(
        select(JobOutput.change_set_id).join(ChangeSet, ChangeSet.id == JobOutput.change_set_id).where(JobOutput.job_id == job.id, ChangeSet.deleted_at.is_(None))
    ).all()
    waiting = job.state == "awaiting_input"
    return JobRow(
        id=job.id,
        kind=job.kind,
        title=job.title,
        state=job.state,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        result_summary=job.result_summary,
        error_code=job.error_code,
        model_name=model.display_name if model else None,
        requester_name=requester.display_name if requester else "",
        output_change_ids=list(outs),
        awaiting_question=waiting,
        legacy=job.legacy,
    )


def job_detail(db: Session, user: User, job_id: uuid.UUID) -> JobDetail:
    job = get_job(db, user, job_id)
    msgs = db.scalars(select(JobMessage).where(JobMessage.job_id == job.id).order_by(JobMessage.created_at)).all()
    row = job_row(db, job)
    cp = job.checkpoint or {}
    return JobDetail(
        **row.model_dump(),
        messages=[{"id": str(m.id), "role": m.role, "body": m.body, "detail": m.detail, "created_at": m.created_at.isoformat(), "answered": m.answered_at is not None} for m in msgs],
        report=cp.get("report", {}),
        technical={
            "fence": job.fence,
            "attempt": job.attempt,
            "lease_until": job.lease_until.isoformat() if job.lease_until else None,
            "worker_id": job.worker_id,
            "steps": cp.get("steps", []),
            "budget": job.budget_used,
            "model_call_ids": cp.get("model_call_ids", []),
            "inputs": job.inputs,
        },
        can_cancel=job.state in ACTIVE and job.requester_id == user.id,
        can_retry=job.state in ("failed", "cancelled", "budget_exceeded") and job.requester_id == user.id,
        can_answer=job.state == "awaiting_input" and job.requester_id == user.id,
    )


def list_jobs(db: Session, user: User, project_id: uuid.UUID) -> list[JobRow]:
    roles = require_member(db, user, project_id)
    q = select(Job).where(Job.project_id == project_id, Job.deleted_at.is_(None), Job.kind.in_(list(USER_KINDS | {"maintenance"})))
    if "steward" not in roles:
        q = q.where(Job.requester_id == user.id)
    return [job_row(db, j) for j in db.scalars(q.order_by(Job.created_at.desc()).limit(100))]


def events_after(db: Session, user: User, job_id: uuid.UUID, after: int) -> list[JobEvent]:
    get_job(db, user, job_id)
    return list(db.scalars(select(JobEvent).where(JobEvent.job_id == job_id, JobEvent.id > after).order_by(JobEvent.id).limit(200)))


def stale_cutoff() -> object:
    return utcnow() - timedelta(seconds=1)
