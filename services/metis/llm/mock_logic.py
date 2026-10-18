"""Kurgusal (deterministik) referans model mantığı — YALNIZ test ve geliştirme içindir.

Bu bir dil modeli değildir: prompt sözleşmelerindeki karar prosedürlerini basit kurallarla uygular.
"Mock modelde %100" sonucu hattın (pipeline, doğrulayıcı, kayıt) doğruluğunu gösterir; gerçek model
kalitesi hakkında hiçbir şey söylemez. Fixture model kimlikleri bilinçli hata modlarını taklit eder.
"""

from __future__ import annotations

import re
from typing import Any

from metis.modules.scopes.semantics import DIMENSIONS, matches_scope, normalize_scope, overlaps

STOP = {
    "nedir", "nasıl", "kaç", "mi", "mı", "mu", "mü", "ne", "hangi", "için", "ile", "ve", "veya", "bir", "bu", "da", "de",
    "olarak", "göre", "neden", "midir", "mıdır", "olan", "the", "what", "how", "is", "of", "kartında", "kartının",
    "kartlarının", "kartı", "kart", "önceki", "kuralları", "yok", "say", "yaz", "yayımla", "onayla",
}
EXPLAIN = ("açıkla", "özetle", "anlat", "explain", "summar")
CARD_LIKE = re.compile(r"^[A-Za-z]{1,4}-?\d{1,4}[A-Za-z]?$")


def _fold(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").casefold()


def _words(s: str) -> list[str]:
    return re.findall(r"[\wçğıöşü]+(?:\(\))?", _fold(s))


def _stem(w: str) -> str:
    return w[:5]


def _match(a: str, b: str) -> bool:
    if a == b:
        return True
    if len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a)):
        return True
    return len(a) >= 5 and len(b) >= 5 and _stem(a) == _stem(b)


def _scope_words(evidence: list[dict]) -> set[str]:
    out = set()
    for e in evidence:
        for vals in normalize_scope(e.get("scope")).values():
            for v in vals:
                out.update(_words(v))
    return out


def _content(text: str, exclude: set[str]) -> list[str]:
    return [w for w in _words(text) if len(w) >= 3 and w not in STOP and w not in exclude and not w.isdigit()]


# ---------------------------------------------------------------- evidence-explain-v1


def _flatten_evidence(evidence: list[dict]) -> list[dict]:
    """v2 biçimi {claim_id, evidence_id, statement, scope} veya v1 biçimi {evidence_id, approved_claims[]}."""
    out = []
    for e in evidence:
        if "statement" in e:
            out.append(e)
        else:
            for i, s in enumerate(e.get("approved_claims", [])):
                out.append({"claim_id": f"{e['evidence_id']}#{i}", "evidence_id": e["evidence_id"], "statement": s, "scope": e.get("scope")})
    return out


def _numbers_stripped(s: str) -> str:
    return " ".join(w for w in _words(s) if not w.isdigit())


def evidence_answer(payload: dict, mode: str = "reference") -> dict:
    question = payload.get("question") or ""
    selector = normalize_scope(payload.get("scope"))
    level = payload.get("level") or "short"
    claims = _flatten_evidence(payload.get("evidence") or [])
    empty = {"explanation": [], "claims": []}
    if not claims:
        return {"decision": "NO_EVIDENCE", **empty}
    if mode != "scope-violator":
        applicable = [c for c in claims if matches_scope(c.get("scope"), selector)]
        if not applicable:
            return {"decision": "NEEDS_SCOPE", **empty}
        # Soruda adı geçen kart/proje, kanıt kapsamında yoksa kapsam aktarılamaz.
        scope_vals = {_fold(v) for c in applicable for d in DIMENSIONS for v in normalize_scope(c.get("scope"))[d] if v != "*"}
        all_card_like = {v for v in scope_vals if CARD_LIKE.match(v)}
        for tok in re.findall(r"[A-Za-z]{1,4}-?\d{1,4}[A-Za-z]?", question):
            t = _fold(tok)
            if all_card_like and CARD_LIKE.match(t) and t not in scope_vals:
                return {"decision": "NEEDS_SCOPE", **empty}
    else:
        applicable = claims
    if payload.get("conflict"):
        return {"decision": "CONFLICTING", **empty}
    exclude = _scope_words(applicable)
    general = any(k in _fold(question) for k in EXPLAIN)
    parts = [p for p in re.split(r"\s+ve\s+|,|;", question) if p.strip()]
    q_words = _content(question, exclude)
    scored = []
    for c in applicable:
        cw = _content(c["statement"], exclude)
        score = sum(1 for q in q_words if any(_match(q, w) for w in cw))
        scored.append((score, c))
    relevant = [c for s, c in scored if s > 0] if not general else [c for _, c in scored]
    if not relevant:
        return {"decision": "NO_EVIDENCE", **empty}
    # aynı özellik, farklı sayı, örtüşen kapsam → çelişki
    for i, a in enumerate(relevant):
        for b in relevant[i + 1 :]:
            if a["statement"] != b["statement"] and _numbers_stripped(a["statement"]) == _numbers_stripped(b["statement"]) and overlaps(a.get("scope"), b.get("scope")):
                return {"decision": "CONFLICTING", **empty}
    decision = "SUPPORTED"
    if len(parts) > 1 and not general:
        answered = 0
        for p in parts:
            pw = _content(p, exclude)
            if not pw or any(any(_match(q, w) for w in _content(c["statement"], exclude)) for q in pw for c in relevant):
                answered += 1
        if answered < len(parts):
            decision = "PARTIAL"
    best = max(s for s, _ in scored) if scored else 0
    if not general and best > 0 and len(relevant) > 1:
        top = [c for s, c in scored if s == best]
        # karşılaştırma/çok parçalı sorularda tüm ilgili iddialar kalır
        if len(parts) == 1 and not re.search(r"göre|değiş|karşılaştır|ve", _fold(question)):
            relevant = top
    limit = {"short": 2, "steps": 4, "detailed": 4}.get(level, 2)
    quoted = [{"claim_id": str(c["claim_id"]), "evidence_id": str(c["evidence_id"]), "quote": c["statement"]} for c in relevant]
    explanation = [{"text": c["statement"], "claim_ids": [str(c["claim_id"])]} for c in relevant[:limit]]
    if mode == "liar":
        explanation = [{"text": _inflate_numbers(s["text"]) + " Ayrıca FAKE_REG_9 kaydı kullanılır.", "claim_ids": s["claim_ids"]} for s in explanation]
    if mode == "fake-source":
        quoted = [{**q, "claim_id": "uydurma-iddia"} for q in quoted]
    return {"decision": decision, "explanation": explanation, "claims": quoted}


def _inflate_numbers(text: str) -> str:
    return re.sub(r"\d+", lambda m: str(int(m.group(0)) + 1), text)


def liar_on_abstain(payload: dict) -> dict:
    """Yalancı model: çekimser olması gereken yerde de destekli cevap uydurur."""
    claims = _flatten_evidence(payload.get("evidence") or [])
    if not claims:
        return {"decision": "SUPPORTED", "explanation": [{"text": "Tampon 4096 bayttır.", "claim_ids": ["yok"]}], "claims": [{"claim_id": "yok", "evidence_id": "yok", "quote": "Tampon 4096 bayttır."}]}
    c = claims[0]
    return {"decision": "SUPPORTED", "explanation": [{"text": _inflate_numbers(c["statement"]), "claim_ids": [str(c["claim_id"])]}], "claims": [{"claim_id": str(c["claim_id"]), "evidence_id": str(c["evidence_id"]), "quote": c["statement"]}]}


# ---------------------------------------------------------------- source selection


def source_selection(payload: dict) -> dict:
    q_words = _content(payload.get("question") or "", set())
    reviews = []
    for p in payload.get("pages", []):
        text = p.get("title", "") + " " + " ".join(p.get("statements", []))
        hit = any(any(_match(q, w) for w in _content(text, set())) for q in q_words)
        reviews.append({"page_id": p["page_id"], "relevance": "relevant" if hit else "irrelevant", "reason": "Soru ile ortak kavram içeriyor." if hit else "Soruyla ilgili bir iddia içermiyor."})
    return {"reviews": reviews}


# ---------------------------------------------------------------- extract-claims-v2

INJECTION = re.compile(r"<\s*/?\s*system|\[s[iİ]stem|talimat|ignore previous|önceki talimat|api anahtar", re.IGNORECASE)
UNDECIDED = re.compile(r"henüz|sonra belirlenecek|kararlaştırılmadı|öneri|önerisi|belirlenmedi|değerlendiriliyor|tbd", re.IGNORECASE)
CONDITION = re.compile(r"((?:yalnız|sadece)?\s*[\wçğıöşü]+\s+mod(?:u|un)?nda|[\wçğıöşü]+\s+durumunda|[\wçğıöşü]+\s+koşullarında)", re.IGNORECASE)


def _sentences(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for part in re.split(r"(?<=[.!?])\s+", line):
            part = part.strip()
            if part:
                out.append(part)
    return out


def extract(payload: dict) -> dict:
    text = payload.get("text") or ""
    claims, decisions = [], []
    for s in _sentences(text):
        if INJECTION.search(s) or not s.endswith((".", "!")) or len(s) < 8:
            continue
        if UNDECIDED.search(s):
            decisions.append({"description": "Kaynakta henüz karara bağlanmamış bir konu var.", "quote": s})
            continue
        words = re.findall(r"[\wçğıöşüÇĞİÖŞÜ()]+", s)
        subject = words[0] if words else s[:20]
        m = CONDITION.search(s)
        num = re.search(r"\d", s)
        attribute = " ".join(words[1:3]) if len(words) > 2 else "ifade"
        if num:
            before = s[: num.start()].split()
            attribute = " ".join(before[-2:]) if before else attribute
        claims.append({"subject": subject, "attribute": attribute or "ifade", "value": s, "condition": m.group(1).strip() if m else "", "quote": s})
    return {"claims": claims, "open_decisions": decisions, "scope_questions": []}


# ---------------------------------------------------------------- page-diff-v4 / v5

ANTONYMS = [("etkin", "devre dışı"), ("açık", "kapalı"), ("aktif", "pasif"), ("kullanılır", "kullanılmaz"), ("vardır", "yoktur")]


def _bytes_normalized(s: str) -> list[float]:
    from metis.llm.validators import quantities

    return sorted(round(q.key()[0], 6) for q in quantities(s))  # birim normalize (0,5 KiB = 512 bayt)


def _polarity(s: str) -> set[str]:
    f = _fold(s)
    out = set()
    for a, b in ANTONYMS:
        if b in f:
            out.add(b)
        elif a in f:
            out.add(a)
    return out


def page_diff(payload: dict) -> dict:
    note = payload.get("kayit_a") or ""
    page = payload.get("kayit_b") or ""
    if re.search(r"yürürlükten kaldırıldı|yerine geçer|geçersiz kılındı", _fold(note)):
        return {"verdict": "supersede", "reason": "Yeni kayıt mevcut bilginin kaldırıldığını açıkça söylüyor.", "new_facts": []}
    page_sents = _sentences(page)
    conflict, extra = False, []
    for s in _sentences(note):
        sw = _content(s, set())
        best, best_score = None, 0.0
        for p in page_sents:
            pw = _content(p, set())
            if not sw or not pw:
                continue
            score = sum(1 for w in sw if any(_match(w, x) for x in pw)) / len(sw)
            if score > best_score:
                best, best_score = p, score
        if best is None or best_score < 0.3:
            extra.append(s)
            continue
        qs, qb = _bytes_normalized(s), _bytes_normalized(best)
        if _polarity(s) and _polarity(best) and _polarity(s) != _polarity(best):
            conflict = True
        elif qs and qb and not set(qs) <= set(qb):  # yeni kayıttaki her değer mevcutta geçmeli
            conflict = True
        elif bool(qs) != bool(qb) and best_score < 0.6:
            extra.append(s)
    if conflict:
        return {"verdict": "conflict_candidate", "reason": "Aynı özellik için uyumsuz değer veya durum bildiriliyor.", "new_facts": []}
    if extra:
        return {"verdict": "addition", "reason": "Yeni kayıt uyumlu ek bilgi içeriyor.", "new_facts": extra}
    return {"verdict": "no_change", "reason": "Yeni kayıt mevcut bilgiye bir şey eklemiyor.", "new_facts": []}


# ---------------------------------------------------------------- claim-conflict-v3

EXCLUSIVE_MODE = re.compile(r"mod", re.IGNORECASE)
VAGUE = re.compile(r"bazı|bazen|gerektiğinde|duruma göre", re.IGNORECASE)
RANGE = re.compile(r"(\d+)\s*(?:ile|-|–)\s*(\d+)")


def judge(payload: dict) -> dict:
    left, right = payload.get("kayit_a") or {}, payload.get("kayit_b") or {}
    ls, rs = left.get("scope") or {}, right.get("scope") or {}
    if not overlaps(ls, rs):
        return {"verdict": "scope_disjoint", "reason": "Kayıtlar farklı kart veya projeler için geçerli."}
    text_r = _fold(right.get("quote", "") + " " + right.get("value", ""))
    text_l = _fold(left.get("quote", "") + " " + left.get("value", ""))
    if "yürürlükten kaldırıldı" in text_r or "yürürlükten kaldırıldı" in text_l:
        return {"verdict": "supersede", "reason": "Bir kayıt diğerini açıkça yürürlükten kaldırıyor."}
    lc, rc = (ls.get("condition") or "").strip(), (rs.get("condition") or "").strip()
    if lc != rc and (lc or rc):
        if VAGUE.search(lc) or VAGUE.search(rc):
            return {"verdict": "underspecified", "reason": "Koşullar karar vermek için yeterince belirli değil."}
        lr, rr = RANGE.search(lc), RANGE.search(rc)
        if lr and rr:
            a1, a2, b1, b2 = map(int, (*lr.groups(), *rr.groups()))
            if max(a1, b1) <= min(a2, b2):
                return {"verdict": "conflict", "reason": "Koşul aralıkları örtüşüyor ve değerler farklı."}
            return {"verdict": "scope_disjoint", "reason": "Koşul aralıkları ayrık."}
        if EXCLUSIVE_MODE.search(lc) and EXCLUSIVE_MODE.search(rc):
            return {"verdict": "scope_disjoint", "reason": "Birbirini dışlayan çalışma modları."}
    if left.get("value") != right.get("value"):
        return {"verdict": "conflict", "reason": "Aynı özellik için farklı değerler bildiriliyor."}
    return {"verdict": "compatible", "reason": "Kayıtlar uyumlu."}


# ---------------------------------------------------------------- relation-v3


def relation(payload: dict) -> dict:
    a = payload.get("kayit_a") or ""
    b = payload.get("kayit_b") or ""
    a = a if isinstance(a, str) else a.get("text", "")
    b = b if isinstance(b, str) else " ".join([b.get("title", ""), *b.get("statements", [])])
    aw, bw = set(_content(a, set())), set(_content(b, set()))
    shared = {w for w in aw if any(_match(w, x) for x in bw)}
    if len(shared) >= 2:
        return {"verdict": "relation", "predicate": "explains", "reason": "Kayıtlar aynı bileşeni ve kavramları anlatıyor."}
    return {"verdict": "no_relation", "predicate": "", "reason": "Ortak bir kavram yok; yalnız sayı veya genel sözcük paylaşılıyor."}


# ---------------------------------------------------------------- draft-refinement-v2 / conflict-resolution-v1


def refine(payload: dict) -> dict:
    claims = (payload.get("draft") or {}).get("claims") or []
    return {"paragraphs": [{"text": c.get("statement", ""), "claim_indices": [i]} for i, c in enumerate(claims)] or [{"text": "—", "claim_indices": [0]}]}


def resolution(payload: dict) -> dict:
    sides = payload.get("pages") or []
    options = []
    if len(sides) >= 2:
        for i, keep in enumerate(sides[:2]):
            other = sides[1 - i]
            options.append(
                {
                    "title": f"{keep['title']} korunsun",
                    "rationale": "Bu seçenek, insan doğrulaması bu kaydı desteklerse uygulanır.",
                    "prerequisite": "Kaynak ölçümü veya güncel veri sayfası ile doğrulanmalı.",
                    "keep_page_ids": [keep["page_id"]],
                    "retire_page_ids": [other["page_id"]],
                    "evidence": [{"evidence_id": s["evidence_id"], "quote": s["statement"]} for side in (keep, other) for s in side.get("statements_detail", [])][:20] or [{"evidence_id": "x", "quote": "x"}, {"evidence_id": "y", "quote": "y"}],
                }
            )
    return {"summary": "İki onaylı kayıt aynı özellik için farklı değer bildiriyor.", "questions": ["Hangi ölçüm veya veri sayfası güncel değeri doğruluyor?"], "options": options}


def respond(prompt_id: str, payload: Any, remote_id: str) -> dict:
    mode = remote_id.removeprefix("fixture-")
    if prompt_id == "evidence-explain-v1":
        if mode == "liar":
            expected = evidence_answer(payload)
            if expected["decision"] not in ("SUPPORTED", "PARTIAL"):
                return liar_on_abstain(payload)
            return evidence_answer(payload, "liar")
        if mode in ("fake-source", "scope-violator"):
            return evidence_answer(payload, mode)
        if mode == "one-slip":
            # Tek bir vakada (R8 sorusu) kapsamı yok sayar; geri kalanı referansla aynı (yüksek ortalama + 1 kritik hata).
            if "R8 tampon" in (payload.get("question") or ""):
                return evidence_answer(payload, "scope-violator")
            return evidence_answer(payload)
        return evidence_answer(payload)
    if prompt_id == "mentor-source-selection-v1":
        return source_selection(payload)
    if prompt_id == "extract-claims-v2":
        return extract(payload)
    if prompt_id in ("page-diff-v4", "page-diff-v5"):
        return page_diff(payload)
    if prompt_id == "claim-conflict-v3":
        return judge(payload)
    if prompt_id == "relation-v3":
        return relation(payload)
    if prompt_id in ("draft-refinement-v1", "draft-refinement-v2"):
        return refine(payload)
    if prompt_id == "conflict-resolution-v1":
        return resolution(payload)
    return {"error": "unknown prompt"}
