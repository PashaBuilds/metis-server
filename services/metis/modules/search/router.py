from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from metis.core.deps import current_user, get_db
from metis.core.models import User
from metis.modules.search import eval_service, service

router = APIRouter(tags=["search"])


@router.get("/projects/{project_id}/search", response_model=service.SearchOut)
def search(
    project_id: uuid.UUID,
    q: str = Query(default="", max_length=500),
    kind: str | None = None,
    domain: list[str] = Query(default=[]),
    yatt: list[str] = Query(default=[]),
    kart: list[str] = Query(default=[]),
    proje: list[str] = Query(default=[]),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
) -> service.SearchOut:
    scope = {"domain": domain, "yatt": yatt, "kart": kart, "proje": proje}
    return service.search(db, user, project_id, q, scope, kind, limit)


@router.get("/projects/{project_id}/search-eval/questions", response_model=list[eval_service.QuestionOut])
def eval_questions(project_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> list[eval_service.QuestionOut]:
    return eval_service.list_questions(db, user, project_id)


@router.post("/projects/{project_id}/search-eval/questions", response_model=eval_service.QuestionOut, status_code=201)
def eval_add_question(
    project_id: uuid.UUID, data: eval_service.QuestionIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> eval_service.QuestionOut:
    return eval_service.add_question(db, user, project_id, data)


@router.delete("/projects/{project_id}/search-eval/questions/{question_id}", status_code=204)
def eval_delete_question(
    project_id: uuid.UUID, question_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> Response:
    eval_service.delete_question(db, user, project_id, question_id)
    return Response(status_code=204)


@router.post("/projects/{project_id}/search-eval/runs", response_model=eval_service.RunOut, status_code=201)
def eval_run(project_id: uuid.UUID, data: eval_service.RunIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> eval_service.RunOut:
    """Tüm soruları o anki aramayla çalıştırır (deterministik, modelsiz) ve sonucu saklar."""
    return eval_service.run(db, user, project_id, data)


@router.get("/projects/{project_id}/search-eval/runs", response_model=list[eval_service.RunOut])
def eval_runs(project_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> list[eval_service.RunOut]:
    return eval_service.list_runs(db, user, project_id)
