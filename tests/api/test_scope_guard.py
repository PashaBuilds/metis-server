"""Kapsam metadata'dan karar verilir: model kapsamı uymayan kanıtla cevap verirse deterministik NEEDS_SCOPE.

Canlı modelle bulundu (2026-10-18): iki DeepSeek modeli de kapsamı boş bir kanıtı, alıntı metnindeki kart adına bakıp
kapsamlı bir soruya cevap olarak kullandı. Kurgusal veri.
"""

from __future__ import annotations

from metis.llm.validators import validate_answer

STATEMENT = "Kurgusal R7 kartında normal modda alım tamponu 384 bayttır."
BUNDLE = [{"claim_id": "c1", "evidence_id": "e1", "statement": STATEMENT, "scope": {}}]
ANSWER = {
    "decision": "SUPPORTED",
    "claims": [{"claim_id": "c1", "evidence_id": "e1", "quote": STATEMENT}],
    "explanation": [{"text": "Normal modda alım tamponu 384 bayttır.", "claim_ids": ["c1"]}],
}


def test_answer_from_unscoped_evidence_for_scoped_question_becomes_needs_scope():
    v = validate_answer(ANSWER, BUNDLE, scope={"kart": ["R7"]})
    assert v.structure_ok and v.decision == "NEEDS_SCOPE" and v.claims == [] and v.sentences == []
    assert v.guard == "scope" and v.model_decision == "SUPPORTED"


def test_matching_or_independent_scope_keeps_answer():
    for scope in ({"kart": ["R7"]}, {"kart": ["*"]}):
        bundle = [{**BUNDLE[0], "scope": scope}]
        v = validate_answer(ANSWER, bundle, scope={"kart": ["R7"]})
        assert v.decision == "SUPPORTED" and v.guard == ""


def test_no_selector_or_bundle_without_scope_metadata_is_unchanged():
    assert validate_answer(ANSWER, BUNDLE).decision == "SUPPORTED"
    bare = [{k: v for k, v in BUNDLE[0].items() if k != "scope"}]
    assert validate_answer(ANSWER, bare, scope={"kart": ["R7"]}).decision == "SUPPORTED"
