"""METIS-Baslat.exe / baslat.ps1 ileti kutuları en üstte açılmalı.

2.0.7'de başlatıcı gizli pencerede çalıştığı için WinForms ileti kutusu açık pencerelerin ARKASINDA ve görev çubuğu
düğmesi olmadan açılıyordu: çift tıklayınca "hiçbir şey olmuyor" sanıldı, kullanıcı tekrar tıkladı (3 kopya birikti).
Statik denetim her yerde koşar; gerçek pencere ölçümü yalnız Windows masaüstünde (METIS_DESKTOP_TEST=1) koşar.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASLAT = ROOT / "deploy" / "windows" / "baslat.ps1"
LAUNCHER = ROOT / "deploy" / "windows" / "launcher" / "MetisBaslat.cs"


def _show_message_source() -> str:
    m = re.search(r"(?s)function Show-Message.*?\n}\r?\n", BASLAT.read_text(encoding="utf-8"))
    assert m, "Show-Message işlevi bulunamadı"
    return m.group(0)


def test_launcher_message_boxes_are_topmost_and_unowned():
    fn = _show_message_source()
    assert "System.Windows.Forms.MessageBox" not in fn, "gizli sahipli WinForms ileti kutusu arkada kalır"
    assert "MessageBoxW([IntPtr]::Zero" in fn
    assert "0x1000" in fn, "MB_SYSTEMMODAL olmadan Windows 10'da en üstte açılmıyor"
    cs = LAUNCHER.read_text(encoding="utf-8")
    assert "MB_SYSTEMMODAL" in cs and "AllowSetForegroundWindow(p.Id)" in cs
    assert 'new Mutex(true, "Local\\\\METIS-Baslat"' in cs, "tek kopya koruması"
    assert "System.Windows.Forms" not in cs


def _probe_dialog(pid: int) -> tuple[bool, int] | None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindow.restype = wintypes.HWND
    found: list[tuple[bool, int]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):  # noqa: ANN001
        owner_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if owner_pid.value == pid and cls.value == "#32770" and user32.IsWindowVisible(hwnd):
            ex = user32.GetWindowLongW(hwnd, -20)
            found.append((bool(ex & 0x8), user32.GetWindow(hwnd, 4) or 0))
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


@pytest.mark.skipif(sys.platform != "win32" or os.getenv("METIS_DESKTOP_TEST") != "1", reason="Windows masaüstü gerekir (METIS_DESKTOP_TEST=1)")
def test_show_message_window_is_topmost_on_desktop():
    script = "$Onayla = $false\r\n" + _show_message_source() + '\r\nShow-Message "METIS deneme iletisi" "Information" "OK" | Out-Null\r\n'
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ileti.ps1"
        path.write_bytes(b"\xef\xbb\xbf" + script.encode("utf-8"))
        # Başlatıcı gibi: gizli pencereli Windows PowerShell 5.1.
        p = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)],
            creationflags=subprocess.CREATE_NO_WINDOW,  # type: ignore[attr-defined]
        )
        try:
            result = None
            deadline = time.monotonic() + 30
            while result is None and time.monotonic() < deadline:
                time.sleep(0.3)
                result = _probe_dialog(p.pid)
            assert result is not None, "ileti kutusu açılmadı"
            topmost, owner = result
            assert topmost, "ileti kutusu en üstte değil (açık pencerelerin arkasında kalır)"
            assert owner == 0, "sahipli ileti kutusunun görev çubuğu düğmesi olmaz"
        finally:
            p.kill()
            p.wait(timeout=10)
