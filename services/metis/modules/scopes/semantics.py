"""Dört boyutlu kapsam semantiği (saf fonksiyonlar, property testli).

- Boyutlar: domain, yatt, kart, proje.
- Bir boyutta `[]` = Belirlenmemiş, `["*"]` = Bağımsız. İkisi aynı değildir.
- Seçici (filtre) tarafında boş boyut kısıt koymaz; dolu boyut daraltır.
- Belirlenmemiş kayıt, dolu bir seçiciye otomatik uymaz.
- Bir boyutta birden çok değer VEYA, farklı boyutlar VE anlamındadır.
- Kapsam metadata'dan okunur; alıntı metninden asla çıkarılmaz.
"""

from __future__ import annotations

from typing import Any

DIMENSIONS: tuple[str, ...] = ("domain", "yatt", "kart", "proje")
WILDCARD = "*"
LABELS = {"domain": "Domain", "yatt": "YATT", "kart": "Kart", "proje": "Proje"}

Scope = dict[str, list[str]]

_LEGACY_DIM = {"domain": "domain", "yatt": "yatt", "card": "kart", "kart": "kart", "project": "proje", "proje": "proje"}


def _clean_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    seen: dict[str, str] = {}
    for raw in values:
        value = str(raw).strip()
        if not value:
            continue
        if value.casefold() in ("all", "tüm kartlar", "tüm platformlar"):
            value = WILDCARD
        seen.setdefault(value.casefold(), value)
    result = sorted(seen.values(), key=str.casefold)
    return [WILDCARD] if WILDCARD in result else result


def normalize_scope(value: Any) -> Scope:
    """Herhangi bir (v2 veya v0.5.5) kapsam gösterimini kanonik dört boyuta çevirir."""
    value = value or {}
    if not isinstance(value, dict):
        return {d: [] for d in DIMENSIONS}
    if isinstance(value.get("dimensions"), dict):
        dims = value["dimensions"]
        out = {d: [] for d in DIMENSIONS}
        for key, vals in dims.items():
            if key in _LEGACY_DIM:
                out[_LEGACY_DIM[key]] = _clean_list(vals)
        return out
    if any(k in value for k in DIMENSIONS):
        return {d: _clean_list(value.get(d)) for d in DIMENSIONS}
    # v0.5.x iki alanlı biçim: platform -> proje, hardware -> kart
    return {
        "domain": [],
        "yatt": [],
        "kart": _clean_list(value.get("hardware")),
        "proje": _clean_list(value.get("platform")),
    }


def _fold(values: list[str]) -> set[str]:
    return {v.casefold() for v in values}


def canonical(value: Any) -> dict[str, list[str]]:
    scope = normalize_scope(value)
    return {d: sorted(_fold(scope[d])) for d in DIMENSIONS}


def same_scope(left: Any, right: Any) -> bool:
    return canonical(left) == canonical(right)


def is_empty_selector(selector: Any) -> bool:
    return all(not v for v in normalize_scope(selector).values())


def matches_scope(item: Any, selector: Any) -> bool:
    """Kayıt kapsamı `item`, filtre `selector`'a uyuyor mu?"""
    item_dims, sel_dims = canonical(item), canonical(selector)
    for dim in DIMENSIONS:
        wanted = sel_dims[dim]
        if not wanted or WILDCARD in wanted:
            continue
        actual = item_dims[dim]
        if WILDCARD in actual:
            continue
        if not set(actual) & set(wanted):
            return False
    return True


def mismatched_dimensions(item: Any, selector: Any) -> list[str]:
    item_dims, sel_dims = canonical(item), canonical(selector)
    result = []
    for dim in DIMENSIONS:
        wanted = sel_dims[dim]
        if not wanted or WILDCARD in wanted:
            continue
        actual = item_dims[dim]
        if WILDCARD not in actual and not set(actual) & set(wanted):
            result.append(dim)
    return result


def overlaps(left: Any, right: Any) -> bool:
    """Çelişki adayı için: iki kapsam aynı duruma uygulanabilir mi?

    Bilinmeyen (boş) kapsam eleme gerekçesi değildir — belirsizlik olarak örtüşür.
    """
    a, b = canonical(left), canonical(right)
    for dim in DIMENSIONS:
        x, y = a[dim], b[dim]
        if not x or not y or WILDCARD in x or WILDCARD in y:
            continue
        if not set(x) & set(y):
            return False
    return True


def disjoint(left: Any, right: Any) -> bool:
    return not overlaps(left, right)


def unspecified_dimensions(value: Any) -> list[str]:
    scope = normalize_scope(value)
    return [d for d in DIMENSIONS if not scope[d]]


def scope_label(value: Any) -> str:
    scope = normalize_scope(value)
    parts = []
    for dim in DIMENSIONS:
        vals = scope[dim]
        text = "Bağımsız" if vals == [WILDCARD] else ", ".join(vals) if vals else "Belirlenmemiş"
        parts.append(f"{LABELS[dim]}: {text}")
    return " / ".join(parts)
