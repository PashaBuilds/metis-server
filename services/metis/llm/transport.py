"""OpenAI uyumlu HTTP taşıma: toplam süre asyncio.timeout ile sınırlı, gövde 1 MiB cap, redirect yok,
trust_env=False (sistem vekili/ortam değişkenleri kullanılmaz), şirket CA bundle'ı ile TLS."""

from __future__ import annotations

import asyncio
import json
import ssl
from dataclasses import dataclass
from typing import Any

import httpx

MAX_BODY = 1024 * 1024


class TransportError(Exception):
    def __init__(self, code: str, status: int | None = None, body: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.body = body[:2000]


@dataclass
class Completion:
    data: dict[str, Any]
    status: int


def completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        raise TransportError("INVALID_ENDPOINT")
    return base + "/chat/completions"


def ssl_context(ca_bundle: str | None) -> ssl.SSLContext:
    return ssl.create_default_context(cafile=ca_bundle or None)


async def _post(url: str, headers: dict[str, str], payload: dict, seconds: float, ca_bundle: str | None) -> Completion:
    async with asyncio.timeout(seconds):
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(seconds, connect=min(10.0, seconds)),
            verify=ssl_context(ca_bundle) if url.startswith("https://") else True,
            trust_env=False,
            follow_redirects=False,
        ) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > MAX_BODY:
                        raise TransportError("RESPONSE_TOO_LARGE", response.status_code)
                    content.extend(chunk)
                if response.status_code >= 300:
                    raise TransportError(f"HTTP_{response.status_code}", response.status_code, content.decode("utf-8", "replace"))
                try:
                    data = json.loads(content)
                except ValueError as exc:
                    raise TransportError("INVALID_JSON_BODY", response.status_code) from exc
                if not isinstance(data, dict):
                    raise TransportError("INVALID_JSON_BODY", response.status_code)
                return Completion(data=data, status=response.status_code)


def post_completion(url: str, headers: dict[str, str], payload: dict, seconds: float, ca_bundle: str | None = None) -> Completion:
    """Senkron çağıranlar (FastAPI thread havuzu, worker) için. Hata kodları TransportError.code'da."""
    try:
        return asyncio.run(_post(url, headers, payload, max(0.001, seconds), ca_bundle))
    except TransportError:
        raise
    except (UnicodeEncodeError, httpx.LocalProtocolError):
        # Başlığa yazılamayan anahtar (satır sonu, ASCII dışı karakter). Asıl hata anahtarı içerir: zincirlenmez.
        raise TransportError("INVALID_KEY_FORMAT") from None
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise TransportError("TIMEOUT") from exc
    except httpx.ConnectError as exc:
        raise TransportError("CONNECTION_FAILED") from exc
    except ssl.SSLError as exc:
        raise TransportError("TLS_FAILED") from exc
    except httpx.HTTPError as exc:
        raise TransportError("CONNECTION_FAILED") from exc
