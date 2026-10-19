"""Paketteki PowerShell betikleri Windows PowerShell 5.1'de hatasız ayrıştırılmalı; ağ erişimi betiğinin sözleşmesi.

Betikler pakete BOM'la girer (build-bundle.py); burada da aynı biçimde (BOM'lu kopya) ayrıştırılır. Ayrıştırma yalnız
Windows'ta koşar (powershell.exe); statik denetimler her yerde.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = sorted((ROOT / "deploy" / "windows").glob("*.ps1"))
AG = ROOT / "deploy" / "windows" / "ag-erisimi.ps1"


@pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"), reason="Windows PowerShell 5.1 gerekir")
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_script_parses_in_windows_powershell(script: Path):
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / script.name
        copy.write_bytes(b"\xef\xbb\xbf" + script.read_bytes().removeprefix(b"\xef\xbb\xbf"))
        cmd = (
            "$e=$null; [System.Management.Automation.Language.Parser]::ParseFile("
            f"'{copy}', [ref]$null, [ref]$e) | Out-Null; $e | ForEach-Object {{ $_.Message }}; exit $e.Count"
        )
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    assert r.returncode == 0, r.stdout + r.stderr


def test_network_access_script_keeps_metis_local_and_refuses_production():
    text = AG.read_text(encoding="utf-8")
    assert "Assert-Admin" in text
    assert "http://127.0.0.1:$ApiPort/{R:1}" in text, "IIS yalnız yerel METIS'e iletir"
    assert '"METIS_ENV") -eq "production"' in text, "https kurulumunu http'ye çevirmez"
    assert "responseBufferLimit:0" in text, "Mentor akışı (SSE) tamponlanmamalı"
    assert "Write-PublicUrlFile" in text, "başlatıcı yeni adresi açmalı"
    assert "-Profile Domain, Private" in text, "güvenlik duvarı genel (Public) ağa açılmaz"
