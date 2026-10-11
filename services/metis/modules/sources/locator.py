"""Kanıt konumu: yapılandırılmış locator ve insan okunur etiket."""

from __future__ import annotations

from typing import Any


def line_range(text: str, start: int | None, end: int | None) -> tuple[int, int] | None:
    if start is None or end is None or start < 0 or end > len(text) or start >= end:
        return None
    first = text.count("\n", 0, start) + 1
    last = text.count("\n", 0, max(start, end - 1)) + 1
    return first, last


def build_locator(
    text: str, start: int | None, end: int | None, meta: dict, page: int | None = None, section: str = ""
) -> dict:
    loc: dict[str, Any] = {}
    if page is not None:
        loc["page"] = page
    if section:
        loc["section"] = section
    lines = line_range(text, start, end)
    if lines and page is None:
        loc["line_from"], loc["line_to"] = lines
    for key in ("commit", "path", "symbol"):
        if meta.get(key):
            loc[key] = meta[key]
    return loc


def locator_label(loc: dict) -> str:
    if not loc:
        return "Tüm kaynak"
    if loc.get("raw"):
        return str(loc["raw"])  # v0.5.5'ten gelen özgün konum metni (yapılandırılmış alanlar ondan türetildi)
    parts = []
    if loc.get("page") is not None:
        parts.append(f"Sayfa {loc['page']}")
    if loc.get("section"):
        parts.append(f"Bölüm: {loc['section']}")
    if loc.get("path"):
        parts.append(str(loc["path"]))
    if loc.get("symbol"):
        parts.append(f"Sembol: {loc['symbol']}")
    if loc.get("line_from"):
        a, b = loc.get("line_from"), loc.get("line_to")
        parts.append(f"Satır {a}" if a == b or not b else f"Satır {a}–{b}")
    if loc.get("commit"):
        parts.append(f"Commit {str(loc['commit'])[:10]}")
    if loc.get("raw") and not parts:
        parts.append(str(loc["raw"]))
    return ", ".join(parts) or "Tüm kaynak"
