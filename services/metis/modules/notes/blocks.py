"""Uzman notunu iddia bloklarına böler (deterministik).

Not, bilginin dayanağıdır: her blok bir iddia olur ve kanıtı notun aynı aralığıdır (statement == quote == excerpt).
Aralıklar Python karakter (code point) konumlarıdır; kanıt satırlarıyla aynı birim.
"""

from __future__ import annotations

import re

from metis.modules.knowledge.figures import INLINE_IMAGE

MAX_BLOCK = 4000  # iddia cümlesi üst sınırı (changes.schemas.ClaimIn.statement); kanıt alıntısı sınırı daha geniş
_SEPARATOR = re.compile(r"\n[ \t]*\n")
_SENTENCE_END = re.compile(r"[.!?…](?=\s)|\n")


def _trimmed(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _split_long(text: str, start: int, end: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    while end - start > MAX_BLOCK:
        limit = start + MAX_BLOCK
        cut = None
        for m in _SENTENCE_END.finditer(text, start, limit):
            cut = m.end()
        if cut is None or cut <= start:
            cut = limit
        s, e = _trimmed(text, start, cut)
        if e > s:
            out.append((s, e))
        start, _ = _trimmed(text, cut, end)
    if end > start:
        out.append((start, end))
    return out


def note_blocks(text: str) -> list[tuple[int, int]]:
    """Boş satırlarla ayrılmış, harf ya da rakam içeren bloklar; her biri en çok MAX_BLOCK karakter.
    Satır içi görsel bağlantısı da ayırıcıdır: iddiaya girmez, çevresindeki metin birebir aralık kalır."""
    spans: list[tuple[int, int]] = []
    pos = 0
    seps = sorted([*_SEPARATOR.finditer(text), *INLINE_IMAGE.finditer(text)], key=lambda m: m.start())
    for m in [*seps, None]:
        stop = m.start() if m else len(text)
        s, e = _trimmed(text, pos, stop)
        if e > s and any(ch.isalnum() for ch in text[s:e]):
            spans.extend(_split_long(text, s, e))
        if m:
            pos = m.end()
    return spans
