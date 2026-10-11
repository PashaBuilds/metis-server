"""Worker çalışma zamanı: talep (SKIP LOCKED), lease + fence + attempt, yetki yeniden kontrolü, bütçe.

- Tek `metis-worker` kimliği; yetki her zaman `requester_id` üzerinden türetilir (iş başına yeni kimlik yok).
- Her yazma öncesi `guard()`: iş satırı kilitlenir, fence/lease/durum doğrulanır, istekte bulunanın yetkisi
  yeniden kontrol edilir. İptal/yeniden dene/yanıt fence'i artırdığı için eski worker yazamaz.
- Bütçe: adım ≤ 20, kaynak ≤ 10, kaynak başına ≤ 30 000 karakter, muhafazakâr token rezervi.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from metis.core.access import can_read_source, require_member
from metis.core.db import transaction, utcnow
from metis.core.errors import AppError
from metis.core.models import Job, JobMessage, ModelCall, Source, SourceRevision, User
from metis.modules.jobs.service import add_event

MAX_STEPS = 20
MAX_SOURCES = 10
MAX_SOURCE_CHARS = 30_000
MAX_TOKENS = 256_000
MAX_ATTEMPTS = 3


def lease_seconds() -> int:
    return int(os.getenv("METIS_WORKER_LEASE_S", "90"))


class LeaseLost(Exception):
    """İş başka bir worker'a geçti, iptal edildi veya fence değişti: yazma yapılmaz."""


class BudgetExceeded(Exception):
    pass


class JobFailed(Exception):
    def __init__(self, code: str, summary: str) -> None:
        super().__init__(code)
        self.code = code
        self.summary = summary


class AwaitInput(Exception):
    def __init__(self, questions: list[dict]) -> None:
        super().__init__("awaiting_input")
        self.questions = questions


def worker_identity(db: Session) -> User:
    from metis.modules.auth.service import ensure_worker_identity

    return ensure_worker_identity(db)


def claim(worker_id: str, benchmark: bool) -> JobContext | None:
    with transaction() as db:
        now = utcnow()
        q = (
            select(Job)
            .where(
                Job.deleted_at.is_(None),
                or_(Job.state == "queued", (Job.state == "running") & (Job.lease_until < now)),
                (Job.kind == "benchmark") if benchmark else (Job.kind != "benchmark"),
            )
            .order_by(Job.priority.desc(), Job.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        job = db.scalar(q)
        if job is None:
            return None
        # Süresi dolan lease'ten kalan yarım model çağrıları kapatılır.
        for call in db.scalars(select(ModelCall).where(ModelCall.job_id == job.id, ModelCall.state == "running")):
            call.state = "failed"
            call.error = "WORKER_INTERRUPTED"
        if job.attempt >= MAX_ATTEMPTS:
            job.state = "failed"
            job.error_code = "RETRY_LIMIT"
            job.result_summary = "Görev üç denemede tamamlanamadı."
            job.finished_at = now
            add_event(db, job.id, "state", state="failed", error="RETRY_LIMIT")
            return None
        resumed = job.state == "running"
        job.state = "running"
        job.fence += 1
        job.attempt += 1
        job.worker_id = worker_id
        job.lease_until = now + timedelta(seconds=lease_seconds())
        job.started_at = job.started_at or now
        job.updated_at = now
        add_event(db, job.id, "state", state="running", attempt=job.attempt, resumed=resumed)
        return JobContext(job_id=job.id, fence=job.fence, worker_id=worker_id, kind=job.kind)


@dataclass
class JobContext:
    job_id: uuid.UUID
    fence: int
    worker_id: str
    kind: str

    def guard(self, db: Session, extend: bool = True, authorize: bool = True) -> Job:
        job = db.scalar(select(Job).where(Job.id == self.job_id).with_for_update())
        if job is None or job.fence != self.fence or job.state != "running" or job.worker_id != self.worker_id:
            raise LeaseLost(str(self.job_id))
        if job.lease_until is None or job.lease_until <= utcnow():
            raise LeaseLost(str(self.job_id))
        if authorize and job.kind != "benchmark":
            self._authorize(db, job)
        if extend:
            job.lease_until = utcnow() + timedelta(seconds=lease_seconds())
        return job

    def _authorize(self, db: Session, job: Job) -> User:
        requester = db.get(User, job.requester_id)
        if not requester or not requester.active or requester.kind != "human":
            raise JobFailed("REQUESTER_UNAVAILABLE", "Görevi başlatan kullanıcı artık etkin değil.")
        try:
            require_member(db, requester, job.project_id, ["contributor"] if job.kind in ("prepare_draft", "refine_draft", "audit_pool") else None)
        except AppError as exc:
            raise JobFailed("ACCESS_CHANGED", "Görevi başlatan kullanıcının yetkisi değişti.") from exc
        for rid in job.inputs.get("source_revision_ids", []):
            rev = db.get(SourceRevision, uuid.UUID(rid))
            src = db.get(Source, rev.source_id) if rev else None
            if not src or src.project_id != job.project_id or not can_read_source(db, requester, src):
                raise JobFailed("ACCESS_CHANGED", "Kaynak erişimi değişti.")
        return requester

    def requester(self, db: Session) -> User:
        job = self.guard(db)
        user = db.get(User, job.requester_id)
        assert user is not None
        return user

    def step(self, name: str, **detail: object) -> None:
        with transaction() as db:
            job = self.guard(db)
            steps = list(job.checkpoint.get("steps", []))
            if len(steps) >= MAX_STEPS:
                raise BudgetExceeded("steps")
            steps.append({"name": name, "at": utcnow().isoformat(timespec="seconds"), **{k: v for k, v in detail.items() if isinstance(v, str | int | float | bool | None)}})
            job.checkpoint = {**job.checkpoint, "steps": steps}
            job.budget_used = {**job.budget_used, "steps": len(steps)}
            add_event(db, job.id, "step", name=name, **{k: v for k, v in detail.items() if isinstance(v, str | int | float | bool | None)})

    def reserve(self, payload: object, output_tokens: int = 2000) -> None:
        """Muhafazakâr rezerv: UTF-8 bayt ≈ token üst sınırı, iki deneme (bir onarım)."""
        estimate = 2 * (len(json.dumps(payload, ensure_ascii=False, default=str).encode()) + output_tokens + 2500)
        with transaction() as db:
            job = self.guard(db)
            used = int(job.budget_used.get("reserved_tokens", 0))
            if used + estimate > MAX_TOKENS:
                raise BudgetExceeded("tokens")
            job.budget_used = {**job.budget_used, "reserved_tokens": used + estimate, "token_budget": MAX_TOKENS, "token_accounting": "conservative_utf8_reservation"}

    def save(self, **checkpoint: object) -> None:
        with transaction() as db:
            job = self.guard(db)
            job.checkpoint = {**job.checkpoint, **checkpoint}

    def checkpoint(self) -> dict:
        with transaction() as db:
            return dict(self.guard(db).checkpoint)

    def note_call(self, call_id: uuid.UUID | None) -> None:
        if not call_id:
            return
        with transaction() as db:
            job = self.guard(db)
            ids = list(job.checkpoint.get("model_call_ids", []))
            ids.append(str(call_id))
            job.checkpoint = {**job.checkpoint, "model_call_ids": ids[-60:]}

    def finish(self, state: str, summary: str, error_code: str | None = None, report: dict | None = None, produced_draft: bool | None = None) -> None:
        with transaction() as db:
            job = self.guard(db, extend=False, authorize=False)
            job.state = state
            job.result_summary = summary
            job.error_code = error_code
            job.lease_until = None
            job.finished_at = utcnow()
            job.updated_at = utcnow()
            cp = dict(job.checkpoint)
            if report is not None:
                cp["report"] = report
            if produced_draft is not None:
                cp["produced_draft"] = produced_draft
            job.checkpoint = cp
            db.add(JobMessage(job_id=job.id, role="metis", body=summary, answered_at=utcnow()))
            add_event(db, job.id, "state", state=state, summary=summary, error=error_code)

    def await_input(self, questions: list[dict]) -> None:
        with transaction() as db:
            job = self.guard(db, extend=False, authorize=False)
            job.state = "awaiting_input"
            job.lease_until = None
            job.updated_at = utcnow()
            job.result_summary = "Metis yanıtını bekliyor."
            for q in questions:
                db.add(JobMessage(job_id=job.id, role="metis", body=q["body"], detail=q.get("detail", {})))
            add_event(db, job.id, "state", state="awaiting_input")
