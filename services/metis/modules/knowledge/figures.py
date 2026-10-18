"""Açıklayıcı görsellerin gövdedeki yeri: kendi satırında `{{görsel N}}` (N = 1'den başlayan sıra)."""

from __future__ import annotations

import re

FIGURE_LINE = re.compile(r"^[ \t]*\{\{\s*görsel\s+(\d+)\s*\}\}[ \t]*$", re.MULTILINE | re.IGNORECASE)


def figure_refs(body: str) -> list[int]:
    return [int(m.group(1)) for m in FIGURE_LINE.finditer(body)]


def isolate_figures(body: str) -> str:
    """Yer tutucu satırları ayrı paragraf yapar (paragraf eşleme ve görüntüleme için)."""
    return FIGURE_LINE.sub(lambda m: f"\n\n{{{{görsel {m.group(1)}}}}}\n\n", body)


def strip_figures(body: str, captions: list[str] | None = None) -> str:
    """Arama, mentor ve dışa aktarma için: yer tutucuyu açıklamayla değiştirir (yoksa siler)."""

    def repl(m: re.Match[str]) -> str:
        n = int(m.group(1))
        cap = captions[n - 1].strip() if captions and 0 < n <= len(captions) else ""
        return f"[Görsel: {cap}]" if cap else ""

    return FIGURE_LINE.sub(repl, body)
