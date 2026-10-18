"""Sürüm tek kaynaktan: metis.__version__ (büyük.küçük.ilerleme). Yayın adı, web paketi ve kurulu sürüm aynı olmalı."""

from __future__ import annotations

import json
import re
from pathlib import Path

from metis import __version__

ROOT = Path(__file__).resolve().parents[2]


def test_version_is_major_minor_progress():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_release_name_and_web_packages_match_app_version():
    assert (ROOT / "deploy" / "RELEASE").read_text(encoding="utf-8").strip() == f"v{__version__}"
    for pkg in ("package.json", "apps/web/package.json"):
        assert json.loads((ROOT / pkg).read_text(encoding="utf-8"))["version"] == __version__, pkg
    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    assert lock["version"] == __version__
    assert lock["packages"][""]["version"] == __version__
    assert lock["packages"]["apps/web"]["version"] == __version__
    openapi = json.loads((ROOT / "apps" / "web" / "openapi.json").read_text(encoding="utf-8"))
    assert openapi["info"]["version"] == __version__


def test_public_health_reports_version(client):
    assert client.get("/api/v1/health/live").json()["version"] == __version__
