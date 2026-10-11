"""Parola, oturum belirteci, sağlayıcı anahtarı şifreleme ve SSRF koruması."""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import os
import secrets
import socket
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from metis.core.config import get_settings
from metis.core.errors import AppError

# ---------------------------------------------------------------- parola

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**15, 8, 1
MIN_PASSWORD = 12


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, maxmem=128 * 1024 * 1024)
    b64 = base64.b64encode
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${b64(salt).decode()}${b64(digest).decode()}"


def verify_password(password: str, stored: str) -> tuple[bool, bool]:
    """(doğru mu, yeniden hash gerekiyor mu). v0.5.5 `salt:hex` (N=16384) biçimini de doğrular."""
    if not stored:
        return False, False
    try:
        if stored.startswith("scrypt$"):
            _, n, r, p, salt, expected = stored.split("$")
            digest = hashlib.scrypt(
                password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), maxmem=128 * 1024 * 1024
            )
            ok = hmac.compare_digest(digest, base64.b64decode(expected))
            return ok, ok and (int(n), int(r), int(p)) != (SCRYPT_N, SCRYPT_R, SCRYPT_P)
        salt_hex, expected_hex = stored.split(":")
        digest = hashlib.scrypt(password.encode(), salt=salt_hex.encode(), n=16384, r=8, p=1)
        ok = hmac.compare_digest(digest.hex(), expected_hex)
        return ok, ok
    except (ValueError, TypeError):
        return False, False


def check_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise AppError("WEAK_PASSWORD", "password must be at least 12 characters", field="password")
    if password.strip() != password or len(set(password)) < 4:
        raise AppError("WEAK_PASSWORD", "password too simple", field="password")


# ---------------------------------------------------------------- belirteçler


def token() -> str:
    return secrets.token_urlsafe(40)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def setup_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    raw = "".join(secrets.choice(alphabet) for _ in range(16))
    return "-".join(raw[i : i + 4] for i in range(0, 16, 4))


# ---------------------------------------------------------------- master key ve AES-GCM


def load_master_key() -> bytes:
    settings = get_settings()
    raw = settings.master_key_inline
    if settings.master_key_file:
        path = Path(settings.master_key_file)
        if not path.is_file():
            raise AppError("SECRET_STORE_UNAVAILABLE", "master key file missing")
        raw = path.read_text(encoding="ascii").strip()
    if not raw:
        raise AppError("SECRET_STORE_UNAVAILABLE", "master key not configured")
    try:
        key = base64.b64decode(raw, validate=True)
    except ValueError as exc:
        raise AppError("SECRET_STORE_UNAVAILABLE", "master key is not base64") from exc
    if len(key) != 32:
        raise AppError("SECRET_STORE_UNAVAILABLE", "master key must be 32 bytes")
    return key


def master_key_fingerprint(key: bytes | None = None) -> str:
    return hashlib.sha256(key or load_master_key()).hexdigest()


def generate_master_key() -> str:
    return base64.b64encode(os.urandom(32)).decode()


AAD = b"metis-v2-provider-secret"


def encrypt_secret(secret: str, key: bytes | None = None) -> str:
    """v2 biçimi: 'v2:' + b64(nonce12 ‖ ciphertext+tag), AAD sabit."""
    if not secret:
        return ""
    nonce = os.urandom(12)
    ct = AESGCM(key or load_master_key()).encrypt(nonce, secret.encode(), AAD)
    return "v2:" + base64.b64encode(nonce + ct).decode()


def decrypt_secret(value: str, key: bytes | None = None) -> str:
    if not value:
        return ""
    if not value.startswith("v2:"):
        raise AppError("SECRET_STORE_UNAVAILABLE", "unknown secret format")
    raw = base64.b64decode(value[3:])
    return AESGCM(key or load_master_key()).decrypt(raw[:12], raw[12:], AAD).decode()


def decrypt_legacy_v1_secret(value: str, legacy_key: bytes) -> str:
    """v0.5.5 biçimi: b64(nonce16 ‖ tag16 ‖ ct), AAD yok."""
    raw = base64.b64decode(value)
    nonce, tag, ct = raw[:16], raw[16:32], raw[32:]
    return AESGCM(legacy_key).decrypt(nonce, ct + tag, None).decode()


# ---------------------------------------------------------------- SSRF


def validate_endpoint(url: str, *, resolve: bool = True) -> str:
    settings = get_settings()
    url = url.strip().rstrip("/")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise AppError("INVALID_ENDPOINT", "base URL must be http(s) without credentials")
    if parts.query or parts.fragment:
        raise AppError("INVALID_ENDPOINT", "base URL must not include query or fragment")
    if url.endswith("/chat/completions"):
        raise AppError("INVALID_ENDPOINT", "give the base URL, not the completions path")
    allowed = [a.rstrip("/") for a in settings.endpoint_allowlist]
    if url not in allowed:
        raise AppError("ENDPOINT_NOT_ALLOWED", "endpoint is not in METIS_ENDPOINT_ALLOWLIST", url=url)
    if settings.is_production and parts.scheme != "https":
        raise AppError("TLS_REQUIRED", "production requires https endpoints")
    if resolve:
        networks = [ipaddress.ip_network(n) for n in settings.endpoint_networks]
        port = parts.port or (443 if parts.scheme == "https" else 80)
        try:
            addresses = {info[4][0] for info in socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)}
        except OSError as exc:
            raise AppError("DNS_UNAVAILABLE", "endpoint host could not be resolved") from exc
        if not addresses or not all(any(ipaddress.ip_address(a) in n for n in networks) for a in addresses):
            raise AppError("ADDRESS_NOT_ALLOWED", "endpoint resolves outside METIS_ENDPOINT_NETWORKS")
    return url
