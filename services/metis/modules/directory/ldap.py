"""Şirket dizini (Active Directory) ile LDAPS doğrulaması.

Hiçbir parola saklanmaz ve hizmet hesabı kullanılmaz: kullanıcı kendi kullanıcı adı ve parolasıyla dizine bağlanır
(LDAP simple bind, yalnız LDAPS) ve kendi kaydını okur. Parola yalnız bu çağrı süresince bellekte durur.
"""

from __future__ import annotations

import re
import ssl
import uuid
from dataclasses import dataclass
from urllib.parse import urlsplit

from metis.core.errors import AppError

# Ön Windows 2000 oturum adı (sAMAccountName) için güvenli küme; filtre yine de kaçışlanır.
_ACCOUNT = re.compile(r"^[A-Za-z0-9._-]{1,104}$")
INVALID_CREDENTIALS = 49
ATTRIBUTES = ["sAMAccountName", "displayName", "mail", "objectGUID", "memberOf"]


class DirectoryUnavailable(Exception):
    """Dizine ulaşılamadı ya da beklenmedik yanıt (yanlış parola değil)."""


@dataclass(frozen=True)
class DirectoryConfig:
    server_url: str
    domain: str
    base_dn: str = ""
    group_dn: str = ""


@dataclass(frozen=True)
class DirectoryEntry:
    username: str
    display_name: str
    email: str
    external_id: str
    groups: tuple[str, ...]


def validate_server_url(url: str) -> str:
    """Yalnız ldaps:// (şifresiz ldap:// ile parola ağda açık giderdi)."""
    parts = urlsplit(url.strip())
    try:
        port = parts.port
    except ValueError:
        port = -1
    if parts.scheme.lower() != "ldaps" or not parts.hostname or port == -1 or parts.path not in ("", "/"):
        raise AppError(
            "VALIDATION_ERROR", "server_url must be ldaps://host[:port]", fields=[{"field": "server_url", "type": "ldaps_required"}]
        )
    return f"ldaps://{parts.hostname}" + (f":{port}" if port else "")


def account_name(typed: str) -> str:
    """'ALAN\\ad', 'ad@alan.com' ya da 'ad' → 'ad'."""
    name = typed.strip()
    if "\\" in name:
        name = name.split("\\", 1)[1]
    if "@" in name:
        name = name.split("@", 1)[0]
    return name


def bind_name(cfg: DirectoryConfig, account: str) -> str:
    domain = cfg.domain.strip()
    return f"{account}@{domain}" if "." in domain else f"{domain}\\{account}"


def search_base(cfg: DirectoryConfig) -> str:
    if cfg.base_dn.strip():
        return cfg.base_dn.strip()
    domain = cfg.domain.strip()
    return ",".join(f"DC={part}" for part in domain.split(".")) if "." in domain else ""


def _escape(value: str) -> str:
    out = []
    for ch in value:
        out.append(f"\\{ord(ch):02x}" if ch in "\\*()\x00" else ch)
    return "".join(out)


def _one(value: object) -> object:
    if isinstance(value, (list, tuple)):
        return value[0] if value else ""
    return value


def _guid(value: object) -> str:
    value = _one(value)
    if isinstance(value, (bytes, bytearray)) and len(value) == 16:
        return str(uuid.UUID(bytes_le=bytes(value)))
    return str(value or "").strip("{}").lower()


class _Ldap3Connection:
    """ldap3 bağlantısını tek bir hata türüne (DirectoryUnavailable) indirger."""

    def __init__(self, conn: object) -> None:
        self._conn = conn

    @property
    def result(self) -> dict:
        return getattr(self._conn, "result", None) or {}

    @property
    def response(self) -> list:
        return getattr(self._conn, "response", None) or []

    def _call(self, fn, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        from ldap3.core.exceptions import LDAPException

        try:
            return fn(*args, **kwargs)
        except (LDAPException, OSError) as exc:
            raise DirectoryUnavailable(type(exc).__name__) from exc

    def bind(self) -> bool:
        return bool(self._call(self._conn.bind))  # type: ignore[attr-defined]

    def search(self, base: str, flt: str, attributes: list[str] | None = None) -> bool:
        return bool(self._call(self._conn.search, base, flt, attributes=attributes))  # type: ignore[attr-defined]

    def unbind(self) -> None:
        from contextlib import suppress

        with suppress(Exception):  # kapanıştaki hata önemsiz
            self._conn.unbind()  # type: ignore[attr-defined]


def _connect(cfg: DirectoryConfig, user: str, password: str):  # noqa: ANN202 — testlerde sahte dizinle değiştirilir
    import ldap3

    from metis.core.config import get_settings

    parts = urlsplit(cfg.server_url)
    # Sunucu sertifikası doğrulanır: şirket kök sertifikası METIS_CA_BUNDLE'da ya da Windows sertifika deposunda olmalı.
    tls = ldap3.Tls(validate=ssl.CERT_REQUIRED, ca_certs_file=get_settings().ca_bundle or None)
    server = ldap3.Server(parts.hostname, port=parts.port or 636, use_ssl=True, tls=tls, get_info=ldap3.NONE, connect_timeout=5)
    conn = ldap3.Connection(
        server,
        user=user,
        password=password,
        authentication=ldap3.SIMPLE,
        read_only=True,
        auto_referrals=False,
        raise_exceptions=False,
        receive_timeout=10,
    )
    return _Ldap3Connection(conn)


def verify(cfg: DirectoryConfig, typed_username: str, password: str, *, check_group: bool = True) -> DirectoryEntry | None:
    """Kullanıcı adı/parola dizinde doğruysa (ve izinli gruptaysa) kişinin kaydı; değilse None.
    Dizine ulaşılamazsa DirectoryUnavailable."""
    if not password:
        return None  # LDAP'ta boş parola anonim bağlanmadır: dizine hiç gönderilmez
    account = account_name(typed_username)
    if not _ACCOUNT.match(account):
        return None
    conn = _connect(cfg, bind_name(cfg, account), password)
    try:
        if not conn.bind():
            if conn.result.get("result") == INVALID_CREDENTIALS:
                return None
            raise DirectoryUnavailable(str(conn.result.get("description") or "bind failed"))
        flt = f"(&(objectClass=user)(sAMAccountName={_escape(account)}))"
        if not conn.search(search_base(cfg), flt, attributes=ATTRIBUTES):
            return None
        found = [r for r in conn.response if r.get("type") == "searchResEntry"]
        if len(found) != 1:
            return None
        attrs = found[0].get("attributes") or {}
        raw = found[0].get("raw_attributes") or {}
        groups = tuple(str(g) for g in (attrs.get("memberOf") or []))
        if check_group and cfg.group_dn.strip() and cfg.group_dn.strip().lower() not in {g.lower() for g in groups}:
            return None
        external_id = _guid(raw.get("objectGUID") or attrs.get("objectGUID"))
        if not external_id:
            return None
        username = str(_one(attrs.get("sAMAccountName")) or account).lower()
        return DirectoryEntry(
            username=username,
            display_name=str(_one(attrs.get("displayName")) or username),
            email=str(_one(attrs.get("mail")) or ""),
            external_id=external_id,
            groups=groups,
        )
    finally:
        conn.unbind()
