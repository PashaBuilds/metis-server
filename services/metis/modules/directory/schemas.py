from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DirectorySettingsIn(BaseModel):
    enabled: bool = False
    server_url: str = Field(default="", max_length=500)
    domain: str = Field(default="", max_length=200)
    base_dn: str = Field(default="", max_length=1000)
    group_dn: str = Field(default="", max_length=1000)
    new_user_role: Literal["none", "reader"] = "reader"  # ürün sahibinin kararı: yeni gelen Okur başlar


class DirectorySettingsOut(DirectorySettingsIn):
    https_ok: bool  # METIS_PUBLIC_URL https mi (şirket hesabıyla giriş için şart)
    updated_at: datetime | None = None


class DirectoryTestIn(BaseModel):
    settings: DirectorySettingsIn
    username: str = Field(min_length=1, max_length=200)
    password: str = Field(default="", max_length=500)


class DirectoryTestOut(BaseModel):
    ok: bool
    username: str | None = None
    display_name: str | None = None
    email: str | None = None
    in_group: bool | None = None
    error: str | None = None


class AuthMethodsOut(BaseModel):
    directory: bool
    passwordless: bool = False
