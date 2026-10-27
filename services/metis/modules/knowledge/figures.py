"""Açıklayıcı görsellerin gövdedeki yeri: kendi satırında `{{görsel N}}` (N = 1'den başlayan sıra)."""

from __future__ import annotations

import re
import uuid

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


# Satır içi görsel (2.0.27): taslağın kendi görsel ekine Markdown bağlantısı, `![açıklama](ek:<ek kimliği>)`.
# Editör kendi satırına koyar; nerede durursa dursun iddia olmaz, blokları ayırır (notes.blocks) ve sayfada ayrı paragraftır.
INLINE_IMAGE = re.compile(r"!\[([^\]\n]*)\]\(ek:([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\)")
_INLINE_LINE = re.compile(rf"^[ \t]*{INLINE_IMAGE.pattern}[ \t]*$", re.MULTILINE)
# `ek:` hedefli her bağlantı biçimi (başlıklı, <...>, boşluklu, başvuru tanımı): kurallı satır dışında kalırsa reddedilir.
_ANY_EK_LINK = re.compile(r"\]\(\s*<?ek:|^[ \t]*\[[^\]\n]+\]:[ \t]*<?ek:", re.MULTILINE | re.IGNORECASE)


def inline_images_well_formed(body: str) -> bool:
    """Her görsel bağlantısı kendi satırında ve `![açıklama](ek:<kimlik>)` biçiminde mi (tablo hücresi, cümle içi değil)."""
    rest = _INLINE_LINE.sub("", body)
    return not INLINE_IMAGE.search(rest) and not _ANY_EK_LINK.search(rest)


def inline_image_ids(body: str) -> list[uuid.UUID]:
    return [uuid.UUID(m.group(2)) for m in INLINE_IMAGE.finditer(body)]


def isolate_inline_images(body: str) -> str:
    """Görsel bağlantısını ayrı paragraf yapar (paragraf eşleme ve görüntüleme için)."""
    return INLINE_IMAGE.sub(lambda m: f"\n\n{m.group(0)}\n\n", body)


def strip_inline_images(body: str) -> str:
    """Arama ve model için: bağlantıyı açıklamayla değiştirir (yoksa siler); ek kimliği metne girmez."""
    return INLINE_IMAGE.sub(lambda m: f"[Görsel: {m.group(1).strip()}]" if m.group(1).strip() else "", body)
