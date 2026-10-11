"""Yalıtılmış, zaman ve bellek sınırlı PDF metin çıkarımı. PDF betikleri asla çalıştırılmaz.

Ayrı alt süreçte çalışır; zaman sınırında alt süreç öldürülür. Bellek sınırı (512 MB) alt sürecin kendisine
uygulanır: POSIX'te RLIMIT_AS, Windows'ta süreç bellek sınırlı bir Job Object. Sınır uygulanamazsa çıkarım
yapılmaz (kapalı başarısızlık: "sandbox_unavailable").
"""

from __future__ import annotations

import errno
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

EXTRACTOR_VERSION = "pypdf-sandbox-v1"
TIMEOUT_S = 8
MEMORY_LIMIT = 512 * 1024 * 1024
MAX_PAGES = 200
MAX_CHARS = 400_000


def extract_isolated(data: bytes, timeout: float = TIMEOUT_S, memory_limit: int = MEMORY_LIMIT) -> dict:
    """{'status': 'complete'|'partial'|'annotation_only', 'pages': [{'page': n, 'text': str}], 'reason': str}"""
    with tempfile.TemporaryDirectory(prefix="metis-pdf-") as tmp:
        path = Path(tmp) / "input.pdf"
        path.write_bytes(data)
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT", "PYTHONPATH", "TEMP", "TMP")}
        env["METIS_PDF_MEMORY"] = str(memory_limit)
        try:
            result = subprocess.run(  # noqa: S603
                [sys.executable, "-I", "-m", "metis.modules.sources.pdf_extract", str(path)],
                capture_output=True,
                timeout=timeout,
                env=env,
                cwd=tmp,
                stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            return {"status": "annotation_only", "pages": [], "reason": "timeout"}
        if result.returncode != 0:
            return {"status": "annotation_only", "pages": [], "reason": "crashed"}
        try:
            return json.loads(result.stdout.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {"status": "annotation_only", "pages": [], "reason": "bad_output"}


def _limit_memory_windows(limit: int) -> None:
    """Bu süreci, işlenmiş (commit) belleği `limit` ile sınırlı bir Job Object'e atar (Windows 8+ iç içe job)."""
    import ctypes
    from ctypes import wintypes

    class IoCounters(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ("r_ops", "w_ops", "o_ops", "r_bytes", "w_bytes", "o_bytes")]

    class BasicLimit(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class ExtendedLimit(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimit),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    job_object_limit_process_memory = 0x00000100
    job_object_extended_limit_information = 9
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise OSError(ctypes.get_last_error(), "CreateJobObjectW")  # type: ignore[attr-defined]
    info = ExtendedLimit()
    info.BasicLimitInformation.LimitFlags = job_object_limit_process_memory
    info.ProcessMemoryLimit = limit
    if not kernel32.SetInformationJobObject(job, job_object_extended_limit_information, ctypes.byref(info), ctypes.sizeof(info)):
        raise OSError(ctypes.get_last_error(), "SetInformationJobObject")  # type: ignore[attr-defined]
    if not kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess()):
        raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject")  # type: ignore[attr-defined]


class _SandboxUnavailable(Exception):
    pass


def _apply_memory_limit(limit: int) -> None:
    try:
        if os.name == "nt":
            _limit_memory_windows(limit)
        else:
            import resource

            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except Exception as exc:  # noqa: BLE001
        raise _SandboxUnavailable from exc


def _extract(path: str) -> dict:
    _apply_memory_limit(int(os.environ.get("METIS_PDF_MEMORY", MEMORY_LIMIT)))
    try:
        from pypdf import PdfReader
    except Exception as exc:  # noqa: BLE001
        # Ayrıştırıcı (ve cryptography gibi C uzantıları) bellek sınırı altında yüklenemedi: bu bir kaynak hatasıdır,
        # dosya hatası değil. Örn. RuntimeError("An error occurred while initializing class …"), ImportError.
        raise _ResourceExhausted from exc

    reader = PdfReader(path, strict=False)
    if reader.is_encrypted:
        return {"status": "annotation_only", "pages": [], "reason": "encrypted"}
    pages = []
    total = 0
    status = "complete"
    for i, page in enumerate(reader.pages):
        if i >= MAX_PAGES:
            status = "partial"
            break
        text = (page.extract_text() or "").strip()
        total += len(text)
        if total > MAX_CHARS:
            status = "partial"
            break
        if text:
            pages.append({"page": i + 1, "text": text})
    if not pages:
        return {"status": "annotation_only", "pages": [], "reason": "no_text"}
    return {"status": status, "pages": pages, "reason": ""}


class _ResourceExhausted(Exception):
    pass


def _is_memory(exc: BaseException | None) -> bool:
    """MemoryError, ENOMEM veya zincirde bunlardan biri varsa bellek sınırı sayılır."""
    seen = 0
    while exc is not None and seen < 10:
        if isinstance(exc, MemoryError | _ResourceExhausted):
            return True
        if isinstance(exc, OSError) and exc.errno == errno.ENOMEM:
            return True
        exc = exc.__cause__ or exc.__context__
        seen += 1
    return False


if __name__ == "__main__":
    try:
        out = _extract(sys.argv[1])
    except _SandboxUnavailable:
        out = {"status": "annotation_only", "pages": [], "reason": "sandbox_unavailable"}
    except Exception as exc:  # noqa: BLE001
        out = {"status": "annotation_only", "pages": [], "reason": "memory" if _is_memory(exc) else "parse_error"}
    sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
