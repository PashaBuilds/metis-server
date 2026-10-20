from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SetupStatus(BaseModel):
    needs_setup: bool


class SetupInput(BaseModel):
    code: str = Field(min_length=4, max_length=40)
    display_name: str = Field(min_length=1, max_length=150)
    username: str = Field(min_length=2, max_length=150, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=1, max_length=200)
    mode: Literal["empty"] = "empty"  # v0.5.5 aktarımı 2026-10-19'da kaldırıldı
    project_name: str = Field(default="", max_length=180)


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(default="", max_length=200)  # parolasız giriş açıkken boş olabilir


class LoginSettingsIO(BaseModel):
    passwordless: bool  # yönetici olmayanlar yalnız kullanıcı adıyla girer (yönetici hesapları parolalı kalır)


class PasswordChangeInput(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


class MembershipOut(BaseModel):
    project_id: uuid.UUID
    project_name: str
    is_demo: bool
    roles: list[str]


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    is_admin: bool
    active: bool
    must_change_password: bool
    auth_source: str = "local"  # 'local' | 'directory' (şirket hesabı)
    pending_role: bool = False  # şirket hesabıyla girmiş, hiçbir projede rolü yok (yalnız kullanıcı listesinde)
    created_at: datetime


class MeOut(BaseModel):
    user: UserOut
    csrf_token: str
    memberships: list[MembershipOut]
    preferences: dict[str, object]
    profile: Literal["development", "test", "production"]


class UserCreateInput(BaseModel):
    username: str = Field(min_length=2, max_length=150, pattern=r"^[A-Za-z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=150)
    temporary_password: str = Field(min_length=1, max_length=200)
    is_admin: bool = False


class UserUpdateInput(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=150)
    active: bool | None = None
    is_admin: bool | None = None
    temporary_password: str | None = Field(default=None, min_length=1, max_length=200)


class PreferenceInput(BaseModel):
    value: object
