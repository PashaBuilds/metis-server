"""Arama metni normalizasyonu. `simple` kanalı Türkçe harfleri ASCII'ye katlar: "saat kaynagi" ile "Saat kaynağı"
eşleşir. İndekste ve sorguda aynı işlev kullanılır; `turkish` kanalı (kök bulma) Türkçe harflerle kalır."""

from __future__ import annotations

_FOLD = str.maketrans({"İ": "i", "I": "i", "ı": "i", "Ğ": "g", "ğ": "g", "Ş": "s", "ş": "s", "Ç": "c", "ç": "c", "Ö": "o", "ö": "o", "Ü": "u", "ü": "u"})


def fold(text: str) -> str:
    return (text or "").translate(_FOLD).casefold()
