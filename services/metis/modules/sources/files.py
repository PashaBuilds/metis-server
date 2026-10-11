"""Yükleme doğrulaması: uzantı allowlist + magic byte + boyut; metin UTF-8 olmalı."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath

from metis.core.errors import AppError

TEXT_EXT = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".c": "text/x-c",
    ".h": "text/x-c",
    ".cpp": "text/x-c++",
    ".hpp": "text/x-c++",
    ".cc": "text/x-c++",
    ".py": "text/x-python",
    ".tcl": "text/x-tcl",
    ".vhd": "text/x-vhdl",
    ".vhdl": "text/x-vhdl",
    ".v": "text/x-verilog",
    ".sv": "text/x-systemverilog",
    ".s": "text/x-asm",
    ".asm": "text/x-asm",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".json": "application/json",
    ".yaml": "text/yaml",
    ".yml": "text/yaml",
    ".xml": "application/xml",
    ".log": "text/plain",
    ".ini": "text/plain",
    ".cfg": "text/plain",
    ".xdc": "text/plain",
}
BINARY = {
    ".pdf": ("application/pdf", [b"%PDF-"]),
    ".png": ("image/png", [b"\x89PNG\r\n\x1a\n"]),
    ".jpg": ("image/jpeg", [b"\xff\xd8\xff"]),
    ".jpeg": ("image/jpeg", [b"\xff\xd8\xff"]),
}


@dataclass
class CheckedFile:
    filename: str
    media_type: str
    category: str  # text | pdf | image
    text: str


def safe_filename(name: str) -> str:
    base = PurePath(name.replace("\\", "/")).name.strip()
    base = "".join(ch for ch in base if ch >= " " and ch not in '<>:"|?*')
    return base[:200] or "dosya"


def check_upload(filename: str, data: bytes, max_bytes: int) -> CheckedFile:
    if len(data) > max_bytes:
        raise AppError("FILE_TOO_LARGE", "file exceeds size limit", limit=max_bytes)
    if not data:
        raise AppError("UNSUPPORTED_FILE", "empty file")
    name = safe_filename(filename)
    ext = PurePath(name).suffix.lower()
    if ext in BINARY:
        media, magics = BINARY[ext]
        if not any(data.startswith(m) for m in magics):
            raise AppError("UNSUPPORTED_FILE", "file content does not match its extension", extension=ext)
        return CheckedFile(name, media, "pdf" if ext == ".pdf" else "image", "")
    if ext in TEXT_EXT:
        if b"\x00" in data[:8192]:
            raise AppError("UNSUPPORTED_FILE", "binary content in text file")
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise AppError("UNSUPPORTED_FILE", "text files must be UTF-8") from exc
        return CheckedFile(name, TEXT_EXT[ext], "text", text.replace("\r\n", "\n"))
    raise AppError("UNSUPPORTED_FILE", "file type not allowed", extension=ext)
