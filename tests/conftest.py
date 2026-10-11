"""Gerçek PostgreSQL test altyapısı (SQLite hiçbir yerde kullanılmaz).

Oturum başına geçici bir veritabanı oluşturulur, Alembic ile `head`'e yükseltilir;
her testten önce tüm tablolar TRUNCATE edilir (satır trigger'ları TRUNCATE'te çalışmaz).
"""

from __future__ import annotations

import base64
import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

ADMIN_DSN = os.getenv("METIS_TEST_ADMIN_DSN", "postgresql://metis_owner:metis-dev@127.0.0.1:5432/postgres")
TEST_DB = f"metis_t_{os.getpid()}_{uuid.uuid4().hex[:6]}"


def _sqlalchemy_url(dbname: str) -> str:
    base = ADMIN_DSN.rsplit("/", 1)[0].replace("postgresql://", "postgresql+psycopg://", 1)
    return f"{base}/{dbname}"


@pytest.fixture(scope="session", autouse=True)
def _database(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    data_dir = tmp_path_factory.mktemp("metis-data")
    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{TEST_DB}"')
    url = _sqlalchemy_url(TEST_DB)
    os.environ.update(
        {
            "METIS_ENV": "test",
            "METIS_DATABASE_URL": url,
            "METIS_OWNER_DATABASE_URL": url,
            "METIS_DATA_DIR": str(data_dir),
            "METIS_PUBLIC_URL": "http://localhost:8000",
            "METIS_MASTER_KEY": base64.b64encode(b"k" * 32).decode(),
            "METIS_ENDPOINT_ALLOWLIST": "http://127.0.0.1:9100/v1,http://127.0.0.1:9101/v1,http://127.0.0.1:9102/v1",
            "METIS_STATIC_DIR": str(Path(data_dir) / "static"),
        }
    )
    from metis.core.config import reset_settings_cache

    reset_settings_cache()
    from alembic import command

    from metis.cli import _alembic_config

    command.upgrade(_alembic_config(url), "head")
    yield url
    from metis.core.db import dispose_engine

    dispose_engine()
    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')


@pytest.fixture(autouse=True)
def _clean(_database: str) -> Iterator[None]:
    from sqlalchemy import text

    from metis.core.db import engine

    with engine().begin() as conn:
        tables = [
            r[0]
            for r in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'")
            )
        ]
        conn.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def db():
    from metis.core.db import session_factory

    session = session_factory()()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def app():
    from metis.app import create_app

    return create_app()


class ApiClient:
    """TestClient sarmalayıcı: CSRF başlığını oturumdan otomatik ekler."""

    def __init__(self, app):  # noqa: ANN001
        from fastapi.testclient import TestClient

        self.http = TestClient(
            app,
            base_url="http://localhost:8000",
            headers={"Origin": "http://localhost:8000"},
            raise_server_exceptions=False,
        )
        self.csrf = ""
        self.user: dict = {}

    def _headers(self, extra: dict | None = None) -> dict:
        headers = {"X-CSRF-Token": self.csrf} if self.csrf else {}
        headers.update(extra or {})
        return headers

    def get(self, url: str, **kw):  # noqa: ANN003
        return self.http.get(url, **kw)

    def post(self, url: str, json=None, headers=None, **kw):  # noqa: ANN001, ANN003
        return self.http.post(url, json=json, headers=self._headers(headers), **kw)

    def put(self, url: str, json=None, headers=None, **kw):  # noqa: ANN001, ANN003
        return self.http.put(url, json=json, headers=self._headers(headers), **kw)

    def patch(self, url: str, json=None, headers=None, **kw):  # noqa: ANN001, ANN003
        return self.http.patch(url, json=json, headers=self._headers(headers), **kw)

    def delete(self, url: str, headers=None, **kw):  # noqa: ANN001, ANN003
        return self.http.delete(url, headers=self._headers(headers), **kw)

    def login(self, username: str, password: str):  # noqa: ANN201
        r = self.http.post("/api/v1/auth/login", json={"username": username, "password": password})
        assert r.status_code == 200, r.text
        self.csrf = r.json()["csrf_token"]
        self.user = r.json()["user"]
        return r.json()


@pytest.fixture
def client(app) -> ApiClient:  # noqa: ANN001
    return ApiClient(app)


@pytest.fixture
def make_client(app):  # noqa: ANN001, ANN201
    def factory() -> ApiClient:
        return ApiClient(app)

    return factory


@pytest.fixture(scope="session")
def mock_llm():
    """Kurgusal OpenAI uyumlu model sunucusu (deterministik referans + hata modları)."""
    from metis.llm.mock_server import start_background

    server = start_background(9101)
    yield "http://127.0.0.1:9101/v1"
    server.shutdown()
