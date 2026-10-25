from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from metis.modules.attachments.schemas import AttachmentOut

Kind = Literal["confluence", "gitlab"]


class ConnectionIn(BaseModel):
    kind: Kind
    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=1, max_length=500)
    # Boş: kayıtlı token korunur (güncellemede). Yanıtta asla dönmez.
    token: str = Field(default="", max_length=4000)
    allowed_scopes: list[str] = Field(min_length=1, max_length=50)
    enabled: bool = True


class ConnectionOut(BaseModel):
    """Yönetici tüm alanları görür; katkı sahibine yalnız kimlik, tür, ad ve izinli kapsamlar (diğerleri boş, yanıtta yok)."""

    id: uuid.UUID
    kind: Kind
    name: str
    allowed_scopes: list[str]
    base_url: str | None = None
    enabled: bool | None = None
    secret_configured: bool | None = None
    updated_at: datetime | None = None


class ConnectionTestIn(BaseModel):
    kind: Kind
    base_url: str = Field(min_length=1, max_length=500)
    token: str = Field(default="", max_length=4000)
    connection_id: uuid.UUID | None = None


class ConnectionTestOut(BaseModel):
    ok: bool
    error: str | None = None
    user: str | None = None


class SearchItemOut(BaseModel):
    key: str
    title: str
    url: str
    container: str


class PreviewIn(BaseModel):
    connection_id: uuid.UUID
    url: str = Field(min_length=1, max_length=2000)


class SkippedOut(BaseModel):
    name: str
    # type: desteklenmeyen dosya türü · size: boyut sınırı · limit: taslak başına ek sınırı · fetch: indirilemedi ·
    # macro: desteklenmeyen Confluence makrosu
    reason: Literal["type", "size", "limit", "fetch", "macro"]
    url: str = ""


class OriginOut(BaseModel):
    kind: Kind
    url: str
    version: str
    connection_name: str
    imported_at: datetime | None = None


class PreviewOut(BaseModel):
    import_id: uuid.UUID
    kind: Kind
    title: str
    body_md: str
    attachments: list[AttachmentOut]
    skipped: list[SkippedOut]
    origin: OriginOut
    existing_page_id: uuid.UUID | None = None
    existing_title: str | None = None
    # Kaynak bu projede yayımlanmamış (ya da bu kullanıcının okuyamadığı) bir taslağa bağlı: kimliği/başlığı gösterilmez.
    existing_unavailable: bool = False
    # Var olan bilgi içe aktarıldıktan sonra METIS'te elle değiştirilmiş mi (güncelleme taslağı o değişiklikleri içermez).
    edited_since_import: bool = False
