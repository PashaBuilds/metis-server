"""Deterministik mentor çıktısı denetimi (saf fonksiyonlar, birim testli).

Kural: model çıktısı validator'ı geçsin diye YAMALANMAZ. Yapı geçersizse cevap VALIDATION_FAILED olur;
yapı geçerliyse açıklama cümleleri tek tek denetlenir, geçmeyen cümle ATILIR (düzeltilmez).

Cümle denetimi (brief 5.6):
 1. Her cümlenin ≥1 claim_id'si olmalı ve bu ID'ler kanıt paketinde olmalı.
 2. Cümledeki her sayı (birim dahil normalize), sembol/tanımlayıcı, hex/ikili değer ve sürüm dizgesi
    bağlı iddiaların metninde birebir geçmeli.
 3. Olumsuzlama tersine dönmemeli (basit kural; kapsamı testlerle belgelenir, mükemmel değildir).
 4. Geçmeyen cümle atılır. Hiç cümle kalmazsa yalnız alıntılar gösterilir (explanation_dropped).
 5. Alıntılar onaylı iddianın tamamı, karakteri karakterine.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from metis.llm.contracts import EvidenceAnswer

ANSWER_DECISIONS = ("SUPPORTED", "PARTIAL")
ABSTAIN_DECISIONS = ("NO_EVIDENCE", "NEEDS_SCOPE", "CONFLICTING")
LEVEL_MAX = {"short": 2, "steps": 4, "detailed": 4}

# ---------------------------------------------------------------- sayı + birim

UNITS = {
    "ghz": ("hz", 1e9),
    "mhz": ("hz", 1e6),
    "khz": ("hz", 1e3),
    "hz": ("hz", 1),
    "gib": ("byte", 1024**3),
    "mib": ("byte", 1024**2),
    "kib": ("byte", 1024),
    "gb": ("byte", 1e9),
    "mb": ("byte", 1e6),
    "kb": ("byte", 1e3),
    "bayt": ("byte", 1),
    "byte": ("byte", 1),
    "bytes": ("byte", 1),
    "b": ("byte", 1),
    "bit": ("bit", 1),
    "ns": ("s", 1e-9),
    "us": ("s", 1e-6),
    "µs": ("s", 1e-6),
    "ms": ("s", 1e-3),
    "sn": ("s", 1),
    "saniye": ("s", 1),
    "s": ("s", 1),
    "dakika": ("s", 60),
    "dk": ("s", 60),
    "mv": ("v", 1e-3),
    "v": ("v", 1),
    "ma": ("a", 1e-3),
    "a": ("a", 1),
    "baud": ("baud", 1),
    "bps": ("baud", 1),
    "derece": ("degc", 1),
    "°c": ("degc", 1),
    "%": ("pct", 1),
    "x": ("lanes", 1),
}
_UNIT_ALT = "|".join(sorted((re.escape(u) for u in UNITS), key=len, reverse=True))
# sayı: 12, 12.5, 12,5, 1.000.000 — ardından isteğe bağlı birim (+ Türkçe ek harfleri)
NUM_RE = re.compile(
    rf"(?<![\w.,])(?P<num>\d+(?:[.,]\d+)*)(?:\s?(?P<unit>{_UNIT_ALT})(?P<suffix>[a-zçğıöşü]*))?(?![\w])",
    re.IGNORECASE,
)
HEX_RE = re.compile(r"\b0[xX][0-9A-Fa-f]+\b|\b0[bB][01]+\b")
VERSION_RE = re.compile(r"\bv?\d+(?:\.\d+){2,3}\b", re.IGNORECASE)
WORD_RE = re.compile(r"[\wçğıöşüÇĞİÖŞÜ]+(?:\(\))?", re.UNICODE)
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{2,}$")

# Türkçe/İngilizce olumsuzluk işaretleri (bilinçli olarak basit)
NEG_WORDS = {"değil", "değildir", "yok", "yoktur", "hiç", "asla", "not", "no", "never", "without", "olmadan", "devre"}
NEG_SUFFIX = re.compile(r"(?:m[aeıiuü]z(?:lar|ler)?(?:d[ıi]r)?|m[ae]m[ıiuü]ş|m[ıiuü]yor|m[ae]d[ıi])$")
NEG_EXCEPT = {"maz", "mez", "kemiz", "deniz", "temiz", "semiz", "yemez"}
# Kapsam dışı genelleme: iddiada olmayan evrensel niceleyici ("tüm kartlarda", "her zaman")
UNIVERSAL = {"tüm", "bütün", "hepsi", "herhangi", "daima", "always", "every", "all", "any"}
UNIVERSAL_PHRASES = ("her zaman", "her kart", "her proje", "her durumda", "tüm kart", "bütün kart")


def _fold(text: str) -> str:
    return unicodedata.normalize("NFC", text).replace("İ", "i").replace("I", "ı").casefold()


def _to_float(raw: str) -> float | None:
    s = raw
    if s.count(".") > 1:  # 1.000.000 → binlik ayırıcı
        s = s.replace(".", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


@dataclass(frozen=True)
class Quantity:
    value: float  # temel birime çevrilmiş
    unit: str | None  # temel birim
    raw: float = 0.0  # metinde yazan sayı

    def key(self) -> tuple[float, str | None]:
        return (round(self.value, 9), self.unit)


def quantities(text: str) -> list[Quantity]:
    out = []
    cleaned = HEX_RE.sub(" ", VERSION_RE.sub(" ", text))
    for m in NUM_RE.finditer(cleaned):
        value = _to_float(m.group("num"))
        if value is None:
            continue
        unit = m.group("unit")
        if unit:
            base, factor = UNITS[unit.lower()]
            # "b" tek başına harf olarak sık kullanılır (ör. "2 b kartı") — yalnız ek almadan birim say
            if unit.lower() in ("b", "a", "s", "v", "x") and m.group("suffix"):
                out.append(Quantity(value, None, value))
                continue
            out.append(Quantity(value * factor, base, value))
        else:
            out.append(Quantity(value, None, value))
    return out


def symbols(text: str) -> set[str]:
    """Büyük harf (ilk karakter dışında), alt çizgi veya rakam içeren ASCII tanımlayıcılar."""
    found = set()
    for tok in WORD_RE.findall(text):
        core = tok.rstrip("()")
        if not IDENT_RE.match(core) or core.lower() in UNITS:
            continue
        if "_" in core or any(c.isdigit() for c in core) or any(c.isupper() for c in core[1:]):
            found.add(core)
    return found


def has_negation(text: str) -> bool:
    for word in WORD_RE.findall(_fold(text)):
        if word in NEG_WORDS:
            return True
        if len(word) > 4 and word not in NEG_EXCEPT and NEG_SUFFIX.search(word):
            return True
    return False


def has_universal(text: str) -> bool:
    folded = _fold(text)
    return any(w in UNIVERSAL for w in WORD_RE.findall(folded)) or any(p in folded for p in UNIVERSAL_PHRASES)


# ---------------------------------------------------------------- cümle denetimi


@dataclass
class SentenceResult:
    text: str
    claim_ids: list[str]
    kept: bool
    reasons: list[str] = field(default_factory=list)


def check_sentence(text: str, claim_ids: list[str], statements: dict[str, str]) -> SentenceResult:
    reasons: list[str] = []
    if not claim_ids:
        reasons.append("no_claim")
    unknown = [c for c in claim_ids if c not in statements]
    if unknown:
        reasons.append("unknown_claim")
    linked = " \n ".join(statements[c] for c in claim_ids if c in statements)
    if linked:
        claim_qs = quantities(linked)
        claim_keys = {q.key() for q in claim_qs}
        claim_raw = {round(q.raw, 9) for q in claim_qs}
        for q in quantities(text):
            # birimli sayı: değer+birim (normalize) iddialarda olmalı; birimsiz sayı: yazılan değer iddialarda geçmeli
            ok = q.key() in claim_keys if q.unit else round(q.raw, 9) in claim_raw
            if not ok:
                reasons.append("number")
                break
        claim_syms = symbols(linked)
        for sym in symbols(text):
            if sym not in claim_syms:
                reasons.append("symbol")
                break
        linked_fold = _fold(linked)
        for hx in HEX_RE.findall(text):
            if hx.lower() not in linked_fold:
                reasons.append("hex")
                break
        for ver in VERSION_RE.findall(text):
            if ver.lower() not in linked_fold:
                reasons.append("version")
                break
        if has_negation(linked) != has_negation(text):
            reasons.append("negation")
        if has_universal(text) and not has_universal(linked):
            reasons.append("generalization")
    return SentenceResult(text=text, claim_ids=list(claim_ids), kept=not reasons, reasons=reasons)


# ---------------------------------------------------------------- tam cevap denetimi


@dataclass
class AnswerValidation:
    structure_ok: bool
    decision: str | None
    claims: list[dict[str, str]]
    sentences: list[SentenceResult]
    error: str = ""

    @property
    def kept(self) -> list[SentenceResult]:
        return [s for s in self.sentences if s.kept]

    @property
    def dropped(self) -> list[SentenceResult]:
        return [s for s in self.sentences if not s.kept]


def validate_answer(output: Any, bundle: list[dict[str, Any]], level: str = "short") -> AnswerValidation:
    """bundle: [{claim_id, evidence_id, statement, ...}]"""
    try:
        parsed = EvidenceAnswer.model_validate(output)
    except (ValidationError, TypeError):
        return AnswerValidation(False, None, [], [], "schema")
    lookup = {str(b["claim_id"]): b for b in bundle}
    statements = {cid: b["statement"] for cid, b in lookup.items()}
    if parsed.decision in ABSTAIN_DECISIONS:
        if parsed.claims or parsed.explanation:
            return AnswerValidation(False, parsed.decision, [], [], "abstain_with_content")
        return AnswerValidation(True, parsed.decision, [], [])
    if not parsed.claims:
        return AnswerValidation(False, parsed.decision, [], [], "answer_without_claims")
    claims = []
    seen = set()
    for c in parsed.claims:
        b = lookup.get(c.claim_id)
        if not b or str(b["evidence_id"]) != c.evidence_id or c.quote != b["statement"]:
            return AnswerValidation(False, parsed.decision, [], [], "quote_mismatch")
        if c.claim_id in seen:
            continue
        seen.add(c.claim_id)
        claims.append({"claim_id": c.claim_id, "evidence_id": c.evidence_id, "quote": c.quote})
    sentences = []
    limit = LEVEL_MAX.get(level, 4)
    for i, s in enumerate(parsed.explanation):
        result = check_sentence(s.text.strip(), s.claim_ids, statements)
        if i >= limit:
            result.kept = False
            result.reasons.append("too_many_sentences")
        sentences.append(result)
    return AnswerValidation(True, parsed.decision, claims, sentences)


def valid_source_selection(output: Any, page_ids: list[str]) -> bool:
    from metis.llm.contracts import SourceSelection

    try:
        parsed = SourceSelection.model_validate(output)
    except (ValidationError, TypeError):
        return False
    ids = [r.page_id for r in parsed.reviews]
    return len(ids) == len(set(ids)) and set(ids) == set(page_ids)
