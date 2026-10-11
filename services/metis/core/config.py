"""Tek yapılandırma kaynağı: ortam değişkenleri (+ isteğe bağlı METIS_CONFIG .env dosyası)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]


def _load_env_file() -> None:
    path = os.getenv("METIS_CONFIG")
    if not path:
        return
    file = Path(path)
    if not file.is_file():
        raise RuntimeError(f"METIS_CONFIG dosyası bulunamadı: {file}")
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"'))


def _csv(name: str, default: str = "") -> list[str]:
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    env: str
    database_url: str
    owner_database_url: str
    data_dir: Path
    public_url: str
    master_key_file: str
    master_key_inline: str
    endpoint_allowlist: list[str]
    endpoint_networks: list[str]
    trusted_proxies: list[str]
    ca_bundle: str
    log_dir: Path
    session_hours: int
    max_upload_bytes: int
    retrieval_disabled: bool
    static_dir: Path
    extra_hosts: list[str] = field(default_factory=list)

    @property
    def is_dev(self) -> bool:
        return self.env in ("development", "test")

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def public_origin(self) -> str:
        parts = urlsplit(self.public_url)
        return f"{parts.scheme}://{parts.netloc}"

    @property
    def secure_cookies(self) -> bool:
        return self.public_url.startswith("https://")

    @property
    def allowed_hosts(self) -> list[str]:
        hosts = {urlsplit(self.public_url).hostname or "localhost", "localhost", "127.0.0.1", *self.extra_hosts}
        if self.env == "test":
            hosts.add("testserver")
        return sorted(hosts)

    @property
    def blob_dir(self) -> Path:
        return self.data_dir / "blobs"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_env_file()
    env = os.getenv("METIS_ENV", "development")
    if env not in ("development", "test", "production"):
        raise RuntimeError("METIS_ENV development, test veya production olmalı.")
    database_url = os.getenv("METIS_DATABASE_URL", "postgresql+psycopg://metis_owner:metis-dev@127.0.0.1:5432/metis")
    if not database_url.startswith("postgresql"):
        raise RuntimeError("METIS yalnız PostgreSQL ile çalışır (METIS_DATABASE_URL).")
    data_dir = Path(os.getenv("METIS_DATA_DIR", str(ROOT / ".data")))
    public_url = os.getenv("METIS_PUBLIC_URL", "http://localhost:8000").rstrip("/")
    if env == "production" and not public_url.startswith("https://"):
        raise RuntimeError("Production profilinde METIS_PUBLIC_URL https:// ile başlamalı.")
    return Settings(
        env=env,
        database_url=database_url,
        owner_database_url=os.getenv("METIS_OWNER_DATABASE_URL", database_url),
        data_dir=data_dir,
        public_url=public_url,
        master_key_file=os.getenv("METIS_MASTER_KEY_FILE", ""),
        master_key_inline=os.getenv("METIS_MASTER_KEY", ""),
        endpoint_allowlist=_csv("METIS_ENDPOINT_ALLOWLIST", "http://127.0.0.1:9100/v1" if env != "production" else ""),
        endpoint_networks=_csv(
            "METIS_ENDPOINT_NETWORKS", "127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
        ),
        trusted_proxies=_csv("METIS_TRUSTED_PROXIES", "127.0.0.1,::1"),
        ca_bundle=os.getenv("METIS_CA_BUNDLE", ""),
        log_dir=Path(os.getenv("METIS_LOG_DIR", str(data_dir / "logs"))),
        session_hours=int(os.getenv("METIS_SESSION_HOURS", "10")),
        max_upload_bytes=int(os.getenv("METIS_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))),
        retrieval_disabled=os.getenv("METIS_RETRIEVAL_DISABLED", "") == "true",
        static_dir=Path(os.getenv("METIS_STATIC_DIR", str(ROOT / "apps" / "web" / "dist"))),
        extra_hosts=_csv("METIS_ALLOWED_HOSTS"),
    )


def reset_settings_cache() -> None:
    get_settings.cache_clear()
