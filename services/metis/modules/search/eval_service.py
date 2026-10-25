"""Arama ölçümü: soru seti ve koşular (yönetici ya da proje sorumlusu). Gerçek sorular yalnız veritabanında durur."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from metis.core.access import require_human, require_member
from metis.core.audit import audit
from metis.core.db import utcnow
from metis.core.errors import AppError
from metis.core.models import Page, SearchEvalQuestion, SearchEvalRun, User
from metis.modules.search.evaluate import MAX_QUESTIONS, EvalQuestion, evaluate
from metis.modules.search.service import search

Kind = Literal["tanimlayici", "kavram", "nasil", "issue", "karisik"]


class QuestionIn(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    expected_page_ids: list[uuid.UUID] = Field(min_length=1, max_length=10)
    expected_quote: str = Field(default="", max_length=1000)
    kind: Kind = "kavram"


class QuestionOut(QuestionIn):
    id: uuid.UUID
    created_at: datetime


class RunIn(BaseModel):
    note: str = Field(default="", max_length=500)
    # Vektör kanalı açık mı (kapalıyla karşılaştırmak için yalnız kelime kanalıyla da koşulabilir)
    dense: bool = True


class RunOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    note: str
    metrics: dict
    per_question: list[dict]


def _require_curator(db: Session, user: User, project_id: uuid.UUID) -> None:
    require_human(user)
    roles = require_member(db, user, project_id)
    if not (user.is_admin or "steward" in roles):
        raise AppError("ROLE_REQUIRED", "steward or administrator required")


def _out(q: SearchEvalQuestion) -> QuestionOut:
    return QuestionOut(id=q.id, question=q.question, expected_page_ids=list(q.expected_page_ids), expected_quote=q.expected_quote, kind=q.kind, created_at=q.created_at)  # type: ignore[arg-type]


def _active(db: Session, project_id: uuid.UUID) -> list[SearchEvalQuestion]:
    return list(
        db.scalars(
            select(SearchEvalQuestion)
            .where(SearchEvalQuestion.project_id == project_id, SearchEvalQuestion.deleted_at.is_(None))
            .order_by(SearchEvalQuestion.created_at)
        )
    )


def list_questions(db: Session, user: User, project_id: uuid.UUID) -> list[QuestionOut]:
    _require_curator(db, user, project_id)
    return [_out(q) for q in _active(db, project_id)]


def add_question(db: Session, user: User, project_id: uuid.UUID, data: QuestionIn) -> QuestionOut:
    _require_curator(db, user, project_id)
    if len(_active(db, project_id)) >= MAX_QUESTIONS:
        raise AppError("VALIDATION_ERROR", "question limit reached", fields=[{"field": "question", "type": "limit"}], limit=MAX_QUESTIONS)
    for pid in data.expected_page_ids:
        page = db.get(Page, pid)
        if not page or page.project_id != project_id or page.deleted_at is not None:
            raise AppError("VALIDATION_ERROR", "expected page not in project", fields=[{"field": "expected_page_ids", "type": "not_found"}])
    q = SearchEvalQuestion(
        project_id=project_id,
        question=data.question.strip(),
        expected_page_ids=list(dict.fromkeys(data.expected_page_ids)),
        expected_quote=data.expected_quote.strip(),
        kind=data.kind,
        created_by=user.id,
    )
    db.add(q)
    db.flush()
    return _out(q)


def delete_question(db: Session, user: User, project_id: uuid.UUID, question_id: uuid.UUID) -> None:
    _require_curator(db, user, project_id)
    q = db.get(SearchEvalQuestion, question_id)
    if not q or q.project_id != project_id or q.deleted_at is not None:
        raise AppError("NOT_FOUND", "question not found")
    q.deleted_at = utcnow()


def run(db: Session, user: User, project_id: uuid.UUID, data: RunIn) -> RunOut:
    """Ölçümü çalıştıran kişinin yetkisiyle arar: okuyamadığı bilgi sonuçta yoktur."""
    _require_curator(db, user, project_id)
    qs = [EvalQuestion(id=str(q.id), question=q.question, expected_page_ids=list(q.expected_page_ids), expected_quote=q.expected_quote, kind=q.kind) for q in _active(db, project_id)]
    res = evaluate(db, user, project_id, qs, search_fn=lambda *a: search(*a, dense=data.dense))
    res.metrics["dense"] = data.dense
    r = SearchEvalRun(project_id=project_id, created_by=user.id, metrics=res.metrics, per_question=res.per_question, note=data.note.strip())
    db.add(r)
    db.flush()
    audit(db, user.id, "search_eval.run", "project", project_id, questions=len(qs))
    return RunOut(id=r.id, created_at=r.created_at, note=r.note, metrics=r.metrics, per_question=r.per_question)


def list_runs(db: Session, user: User, project_id: uuid.UUID) -> list[RunOut]:
    _require_curator(db, user, project_id)
    rows = db.scalars(select(SearchEvalRun).where(SearchEvalRun.project_id == project_id).order_by(SearchEvalRun.created_at.desc()).limit(20))
    return [RunOut(id=r.id, created_at=r.created_at, note=r.note, metrics=r.metrics, per_question=r.per_question) for r in rows]
