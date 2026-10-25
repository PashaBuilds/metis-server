"""Dış kaynak HTTP istemcisi: kimlik başlığı, süre ve boyut sınırları, aynı köken, hata kodu eşlemesi.

Sistem vekili/ortam değişkenleri kullanılmaz (`trust_env=False`), yönlendirme izlenmez, şirket CA'sı `METIS_CA_BUNDLE`.
Token hiçbir hata iletisine, loga ya da istisnaya yazılmaz.
"""

from __future__ import annotations

import json
import ssl
from typing import Any
from urllib.parse import urlsplit

import httpx

from metis.core.config import get_settings
from metis.core.errors import AppError

TIMEOUT_S = 30.0
MAX_JSON = 8 * 1024 * 1024
# Testler kurgusal sunucuyu buraya bağlar (httpx.MockTransport); üretimde None.
TRANSPORT: httpx.BaseTransport | None = None


def _origin(url: str) -> tuple[str, str, int | None]:
    p = urlsplit(url)
    return p.scheme, (p.hostname or "").lower(), p.port or (443 if p.scheme == "https" else 80)


class ExternalHttp:
    def __init__(self, kind: str, base_url: str, token: str) -> None:
        self.kind = kind
        self.base_url = base_url.rstrip("/")
        self._headers = {"Accept": "application/json"}
        if token:
            if kind == "confluence":
                self._headers["Authorization"] = f"Bearer {token}"
            else:
                self._headers["PRIVATE-TOKEN"] = token

    def url(self, path_or_url: str) -> str:
        if path_or_url.startswith(("http://", "https://")):
            if _origin(path_or_url) != _origin(self.base_url):
                raise AppError("EXTERNAL_BAD_RESPONSE", "link points outside the connection")
            return path_or_url
        return self.base_url + "/" + path_or_url.lstrip("/")

    def _client(self) -> httpx.Client:
        ca = get_settings().ca_bundle or None
        verify: ssl.SSLContext | bool = ssl.create_default_context(cafile=ca) if self.base_url.startswith("https://") else True
        return httpx.Client(
            timeout=httpx.Timeout(TIMEOUT_S, connect=10.0),
            verify=verify,
            trust_env=False,
            follow_redirects=False,
            headers=self._headers,
            transport=TRANSPORT,
        )

    def _fetch(self, path_or_url: str, params: dict | None, limit: int) -> bytes:
        url = self.url(path_or_url)
        try:
            with self._client() as client, client.stream("GET", url, params=params) as resp:
                if resp.status_code in (401, 403):
                    raise AppError("EXTERNAL_UNAUTHORIZED", "remote rejected the token", status_code=resp.status_code)
                if resp.status_code == 404:
                    raise AppError("EXTERNAL_NOT_FOUND", "remote item not found")
                if resp.status_code >= 300:
                    raise AppError("EXTERNAL_BAD_RESPONSE", "unexpected remote status", status_code=resp.status_code)
                body = bytearray()
                for chunk in resp.iter_bytes():
                    if len(body) + len(chunk) > limit:
                        raise AppError("EXTERNAL_TOO_LARGE", "remote response too large", limit=limit)
                    body.extend(chunk)
                return bytes(body)
        except AppError:
            raise
        except httpx.TimeoutException as exc:
            raise AppError("EXTERNAL_TIMEOUT", "remote did not answer in time") from exc
        except httpx.ConnectError as exc:
            if isinstance(exc.__cause__, ssl.SSLError) or "SSL" in str(exc) or "CERTIFICATE" in str(exc).upper():
                raise AppError("EXTERNAL_TLS", "TLS verification failed") from exc
            raise AppError("EXTERNAL_UNREACHABLE", "remote unreachable") from exc
        except ssl.SSLError as exc:
            raise AppError("EXTERNAL_TLS", "TLS verification failed") from exc
        except httpx.HTTPError as exc:
            raise AppError("EXTERNAL_UNREACHABLE", "remote unreachable") from exc

    def get_json(self, path_or_url: str, params: dict | None = None) -> Any:
        raw = self._fetch(path_or_url, params, MAX_JSON)
        try:
            return json.loads(raw)
        except ValueError as exc:
            raise AppError("EXTERNAL_BAD_RESPONSE", "remote did not return JSON") from exc

    def get_bytes(self, path_or_url: str, limit: int) -> bytes:
        return self._fetch(path_or_url, None, limit)
