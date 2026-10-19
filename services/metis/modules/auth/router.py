from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from metis.core.config import get_settings
from metis.core.deps import SESSION_COOKIE, current_session, current_user, current_user_any, get_db
from metis.core.models import User, UserSession
from metis.modules.auth import schemas, service

router = APIRouter(tags=["auth"])


def _cookie_path(request: Request) -> str:
    # METIS bir alt yolda yayınlanıyorsa (ör. /metis) oturum çerezi yalnız o yola gönderilir; makinedeki diğer
    # uygulamalar onu görmez.
    return request.scope.get("root_path", "") or "/"


def _set_cookie(response: Response, raw: str, path: str) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        raw,
        max_age=settings.session_hours * 3600,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
        path=path,
    )


def _me(db: Session, user: User, sess: UserSession) -> schemas.MeOut:
    return schemas.MeOut(
        user=service.to_out(user),
        csrf_token=sess.csrf,
        memberships=service.memberships(db, user),
        preferences=service.preferences(db, user),
        profile=get_settings().env,  # type: ignore[arg-type]
    )


@router.get("/setup/status", response_model=schemas.SetupStatus)
def setup_status(db: Session = Depends(get_db, scope="function")) -> schemas.SetupStatus:
    return schemas.SetupStatus(needs_setup=service.needs_setup(db))


@router.post("/setup", response_model=schemas.MeOut)
def setup(
    data: schemas.SetupInput, request: Request, response: Response, db: Session = Depends(get_db, scope="function")
) -> schemas.MeOut:
    user = service.complete_setup(db, data)
    raw, sess = service.create_session(db, user, request.state.client_ip)
    _set_cookie(response, raw, _cookie_path(request))
    return _me(db, user, sess)


@router.post("/auth/login", response_model=schemas.MeOut)
def login(
    data: schemas.LoginInput, request: Request, response: Response, db: Session = Depends(get_db, scope="function")
) -> schemas.MeOut:
    raw, sess, user = service.login(db, data, request.state.client_ip)
    _set_cookie(response, raw, _cookie_path(request))
    return _me(db, user, sess)


@router.post("/auth/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    pair: tuple[UserSession, User] = Depends(current_session),
    db: Session = Depends(get_db, scope="function"),
) -> Response:
    service.logout(db, db.merge(pair[0]))
    response.delete_cookie(SESSION_COOKIE, path=_cookie_path(request))
    response.status_code = 204
    return response


@router.get("/auth/me", response_model=schemas.MeOut)
def me(pair: tuple[UserSession, User] = Depends(current_session), db: Session = Depends(get_db, scope="function")) -> schemas.MeOut:
    sess, user = pair
    return _me(db, user, sess)


@router.post("/auth/password", response_model=schemas.MeOut)
def change_password(
    data: schemas.PasswordChangeInput,
    pair: tuple[UserSession, User] = Depends(current_session),
    db: Session = Depends(get_db, scope="function"),
) -> schemas.MeOut:
    sess, user = pair
    service.change_password(db, user, data, sess.id)
    return _me(db, user, sess)


@router.put("/preferences/{key}", status_code=204)
def set_preference(
    key: str, data: schemas.PreferenceInput, user: User = Depends(current_user_any), db: Session = Depends(get_db, scope="function")
) -> Response:
    service.set_preference(db, user, key, data.value)
    return Response(status_code=204)


@router.get("/users", response_model=list[schemas.UserOut])
def list_users(user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")) -> list[schemas.UserOut]:
    return service.list_users(db, user)


@router.post("/users", response_model=schemas.UserOut, status_code=201)
def create_user(
    data: schemas.UserCreateInput, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> schemas.UserOut:
    return service.to_out(service.create_user(db, user, data))


@router.patch("/users/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: uuid.UUID, data: schemas.UserUpdateInput, user: User = Depends(current_user), db: Session = Depends(get_db, scope="function")
) -> schemas.UserOut:
    return service.to_out(service.update_user(db, user, user_id, data))
