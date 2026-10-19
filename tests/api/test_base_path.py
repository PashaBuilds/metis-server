"""METIS bir alt yolda yayınlanabilir (ürün sahibinin isteği 2026-10-19): http://<makine>/metis.

Makine birden çok iş için kullanılıyor; kök ve diğer yollar başka uygulamalara kalır. METIS_PUBLIC_URL'ün yolu
(ör. /metis) ön ektir: API, arayüz ve oturum çerezi o yolun altındadır. Aynı süreç kökten de yanıt verir (yalnız
127.0.0.1'de dinler; başlatıcı ve kurulum betiklerinin sağlık denetimleri köke gider).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from metis.core.db import transaction
from metis.modules.auth.service import issue_setup_code
from tests.factories import ADMIN_PASSWORD

INDEX = '<!doctype html><html lang="tr"><head><meta charset="UTF-8" /><script src="./theme-init.js"></script></head><body></body></html>'


@pytest.fixture
def prefixed() -> Iterator[object]:
    from fastapi.testclient import TestClient

    from metis.app import create_app
    from metis.core.config import get_settings, reset_settings_cache

    old = os.environ["METIS_PUBLIC_URL"]
    os.environ["METIS_PUBLIC_URL"] = "http://localhost:8000/metis"
    reset_settings_cache()
    static = Path(get_settings().static_dir)
    static.mkdir(parents=True, exist_ok=True)
    (static / "index.html").write_text(INDEX, encoding="utf-8")
    (static / "theme-init.js").write_text("// kurgusal", encoding="utf-8")
    try:
        yield TestClient(
            create_app(), base_url="http://localhost:8000", headers={"Origin": "http://localhost:8000"}, raise_server_exceptions=False
        )
    finally:
        os.environ["METIS_PUBLIC_URL"] = old
        reset_settings_cache()


def _setup(c, prefix: str) -> dict:  # noqa: ANN001
    with transaction() as db:
        code = issue_setup_code(db)
    body = {"code": code, "display_name": "Ayşe Yönetici", "username": "ayse", "password": ADMIN_PASSWORD, "mode": "empty", "project_name": "Kurgusal"}
    r = c.post(f"{prefix}/api/v1/setup", json=body)
    assert r.status_code == 200, r.text
    return r


def test_api_and_spa_served_under_prefix(prefixed):  # noqa: ANN001
    c = prefixed
    assert c.get("/metis/api/v1/health/live").status_code == 200
    page = c.get("/metis/bilgi/123")
    assert page.status_code == 200
    assert '<base href="/metis/">' in page.text and page.text.index("<base") < page.text.index("theme-init.js")
    asset = c.get("/metis/theme-init.js")
    assert asset.status_code == 200 and "kurgusal" in asset.text
    assert c.get("/metis").status_code == 200  # sondaki eğik çizgi olmadan da açılır


def test_root_still_answers_for_local_health_checks(prefixed):  # noqa: ANN001
    c = prefixed
    assert c.get("/api/v1/health/live").status_code == 200
    assert '<base href="/">' in c.get("/").text


def test_session_cookie_scoped_to_prefix_and_login_works(prefixed):  # noqa: ANN001
    c = prefixed
    r = _setup(c, "/metis")
    cookie = r.headers["set-cookie"]
    assert "Path=/metis" in cookie
    me = c.get("/metis/api/v1/auth/me")
    assert me.status_code == 200, me.text
    out = c.post("/metis/api/v1/auth/logout", headers={"X-CSRF-Token": me.json()["csrf_token"]})
    assert out.status_code == 204
    assert "Path=/metis" in out.headers["set-cookie"]
    assert c.get("/metis/api/v1/auth/me").status_code == 401


def test_without_prefix_base_is_root(client):  # noqa: ANN001
    from metis.core.config import get_settings

    static = Path(get_settings().static_dir)
    static.mkdir(parents=True, exist_ok=True)
    (static / "index.html").write_text(INDEX, encoding="utf-8")
    page = client.get("/bilgi")
    assert '<base href="/">' in page.text
    r = _setup(client.http, "")
    assert "Path=/;" in r.headers["set-cookie"] or r.headers["set-cookie"].rstrip().endswith("Path=/")
