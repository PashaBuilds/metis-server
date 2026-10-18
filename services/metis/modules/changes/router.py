from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session

from metis.core.deps import current_user, get_db
from metis.core.models import User
from metis.modules.changes import schemas, service

router = APIRouter(tags=["changes"])


@router.get("/projects/{project_id}/changes", response_model=schemas.ChangeListOut)
def list_changes(
    project_id: uuid.UUID,
    tab: str = Query(default="drafts", pattern="^(review|drafts|published)$"),
    origin: str | None = Query(default=None, pattern="^(human|metis)$"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
) -> schemas.ChangeListOut:
    return service.list_changes(db, user, project_id, tab, origin)


@router.post("/projects/{project_id}/changes", response_model=schemas.ChangeDetailOut, status_code=201)
def create_change(
    project_id: uuid.UUID,
    data: schemas.ChangeCreateIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
) -> schemas.ChangeDetailOut:
    from metis.core.access import require_human

    require_human(user)
    change = service.create_change(db, user, project_id, data, idempotency_key=idempotency_key)
    db.flush()
    return service.change_detail(db, user, change.id)


@router.get("/changes/{change_id}", response_model=schemas.ChangeDetailOut)
def get_change(
    change_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> schemas.ChangeDetailOut:
    return service.change_detail(db, user, change_id)


@router.put("/changes/{change_id}", response_model=schemas.ChangeDetailOut)
def update_change(
    change_id: uuid.UUID,
    data: schemas.ChangeUpdateIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
) -> schemas.ChangeDetailOut:
    service.update_change(db, user, change_id, data)
    return service.change_detail(db, user, change_id)


@router.post("/changes/{change_id}/submit", response_model=schemas.ChangeDetailOut)
def submit(
    change_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> schemas.ChangeDetailOut:
    service.submit(db, user, change_id)
    return service.change_detail(db, user, change_id)


@router.post("/changes/{change_id}/reviews", response_model=schemas.ChangeDetailOut)
def review(
    change_id: uuid.UUID, data: schemas.ReviewIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> schemas.ChangeDetailOut:
    service.review(db, user, change_id, data)
    return service.change_detail(db, user, change_id)


@router.post("/changes/{change_id}/publish", response_model=schemas.ChangeDetailOut)
def publish(
    change_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> schemas.ChangeDetailOut:
    service.publish_change(db, user, change_id)
    return service.change_detail(db, user, change_id)


@router.post("/changes/{change_id}/check", response_model=schemas.PrepublishCheckOut)
def prepublish_check(change_id: uuid.UUID, user: User = Depends(current_user)) -> schemas.PrepublishCheckOut:
    """Yayın öncesi kontrol (kural + varsa model). Model çağrıları istek oturumu dışında yapılır."""
    from metis.modules.changes.prepublish import run_check

    return run_check(user.id, change_id)


@router.post("/changes/{change_id}/publish-direct", response_model=schemas.ChangeDetailOut)
def publish_direct(
    change_id: uuid.UUID, data: schemas.PublishDirectIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> schemas.ChangeDetailOut:
    service.publish_direct(db, user, change_id, data)
    return service.change_detail(db, user, change_id)


@router.post("/changes/{change_id}/rebase", response_model=schemas.ChangeDetailOut, status_code=201)
def rebase(
    change_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> schemas.ChangeDetailOut:
    new = service.rebase(db, user, change_id)
    db.flush()
    return service.change_detail(db, user, new.id)


@router.delete("/changes/{change_id}", status_code=200)
def delete_change(change_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> dict:
    return service.delete_change(db, user, change_id)


@router.post("/changes/{change_id}/restore", status_code=204)
def restore_change(change_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> Response:
    service.restore_change(db, user, change_id)
    return Response(status_code=204)


@router.post("/pages/{page_id}/withdraw", response_model=schemas.ChangeOut)
def withdraw_page(
    page_id: uuid.UUID, data: schemas.WithdrawIn, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> schemas.ChangeOut:
    return service.change_out(db, service.withdraw_page(db, user, page_id, data.reason))


@router.delete("/pages/{page_id}", status_code=200)
def delete_page(page_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> dict:
    return service.delete_page(db, user, page_id)


@router.post("/pages/{page_id}/restore", status_code=204)
def restore_page(page_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> Response:
    service.restore_page(db, user, page_id)
    return Response(status_code=204)
