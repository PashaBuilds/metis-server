"""Geliştirme bilgisayarında aday ZIP'in ajan tarafından denenmesi (scripts/deneme-yukseltme).

Yönetici bir kez `kur.ps1` ile zamanlanmış görev kurar; görev `calistir.ps1`'i yükseltilmiş çalıştırır. Bu yüzden
çalıştırıcı, istekteki ZIP'i yalnız adı ve SHA-256'sı tutarsa ve METIS zaten kuruluysa (yalnız yükseltme) açar. Burada
reddetme yolları yönetici olmadan denenir (hiçbir şey açılmadan/kurulmadan sonuç yazılmalı).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "scripts" / "deneme-yukseltme"
SCRIPTS = sorted(DIR.glob("*.ps1"))

windows = pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"), reason="Windows PowerShell 5.1 gerekir")


def test_scripts_exist():
    assert {p.name for p in SCRIPTS} == {"kur.ps1", "calistir.ps1", "kaldir.ps1"}


@windows
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_script_parses(script: Path):
    cmd = (
        "$e=$null; [System.Management.Automation.Language.Parser]::ParseFile("
        f"'{script}', [ref]$null, [ref]$e) | Out-Null; $e | ForEach-Object {{ $_.Message }}; exit $e.Count"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


def _run(base: Path, request: dict) -> dict:
    (base / "istek").mkdir(parents=True, exist_ok=True)
    (base / "istek" / "istek.json").write_text(json.dumps(request), encoding="utf-8")
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(DIR / "calistir.ps1"), "-Base", str(base)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert not (base / "istek" / "istek.json").exists(), "istek tek kullanımlık"
    assert not (base / "paket").exists() or not any((base / "paket").glob("*/*")), "reddedilen istekte paket açılmaz"
    return json.loads((base / "istek" / "sonuc.json").read_text(encoding="utf-8-sig"))


@windows
def test_runner_rejects_wrong_hash(tmp_path: Path):
    zip_path = tmp_path / "METIS-9.9.9-server-win64.zip"
    zip_path.write_bytes(b"kurgusal")
    out = _run(tmp_path / "taban", {"zip": str(zip_path), "sha256": "0" * 64})
    assert out["basarili"] is False and "SHA-256" in out["hata"]


@windows
def test_runner_rejects_unexpected_file_name(tmp_path: Path):
    zip_path = tmp_path / "baska.zip"
    zip_path.write_bytes(b"kurgusal")
    out = _run(tmp_path / "taban", {"zip": str(zip_path), "sha256": "0" * 64})
    assert out["basarili"] is False and "METIS-" in out["hata"]


def test_release_script_has_trial_step():
    text = (ROOT / "scripts" / "release.ps1").read_text(encoding="utf-8-sig")
    assert "[switch]$Dene" in text and "METIS-Deneme-Yukseltme" in text
