"""Kapsam semantiği — birim ve property testleri (saf fonksiyonlar)."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from metis.modules.scopes.semantics import (
    DIMENSIONS,
    disjoint,
    matches_scope,
    mismatched_dimensions,
    normalize_scope,
    overlaps,
    same_scope,
)

values = st.lists(st.sampled_from(["A", "B", "C", "*"]), max_size=3)
scopes = st.fixed_dictionaries({d: values for d in DIMENSIONS})


def test_empty_selector_matches_everything():
    assert matches_scope({"kart": []}, {})
    assert matches_scope({"kart": ["K1"]}, None)
    assert matches_scope({}, {"kart": []})


def test_unspecified_does_not_match_populated_selector():
    assert not matches_scope({"domain": []}, {"domain": ["Gömülü"]})


def test_independent_matches_any_selector():
    assert matches_scope({"kart": ["*"]}, {"kart": ["K1"]})


def test_or_within_and_across():
    item = {"kart": ["K1", "K2"], "proje": ["Atlas"]}
    assert matches_scope(item, {"kart": ["K2", "K9"]})
    assert not matches_scope(item, {"kart": ["K2"], "proje": ["Orion"]})
    assert mismatched_dimensions(item, {"kart": ["K2"], "proje": ["Orion"]}) == ["proje"]


def test_case_insensitive_compare_but_preserve_display():
    assert matches_scope({"kart": ["vpk120"]}, {"kart": ["VPK120"]})
    assert normalize_scope({"kart": [" VPK120 ", "vpk120"]})["kart"] == ["VPK120"]


def test_legacy_platform_hardware_mapping():
    assert normalize_scope({"platform": "Atlas", "hardware": "K1"}) == {
        "domain": [],
        "yatt": [],
        "kart": ["K1"],
        "proje": ["Atlas"],
    }
    assert normalize_scope({"dimensions": {"card": ["K1"], "project": ["Atlas"], "domain": [], "yatt": ["Y"]}})[
        "yatt"
    ] == ["Y"]


def test_independent_and_unspecified_differ():
    assert not same_scope({"kart": ["*"]}, {"kart": []})


def test_overlaps_unknown_is_uncertain_not_disjoint():
    assert overlaps({"kart": []}, {"kart": ["K1"]})
    assert disjoint({"kart": ["K1"]}, {"kart": ["K2"]})
    assert overlaps({"kart": ["*"]}, {"kart": ["K2"]})


@given(scopes)
def test_property_normalize_idempotent(s):
    assert normalize_scope(normalize_scope(s)) == normalize_scope(s)


@given(scopes)
def test_property_self_match_when_fully_specified(s):
    n = normalize_scope(s)
    assert matches_scope(n, n)


@given(scopes, scopes)
def test_property_overlap_symmetric(a, b):
    assert overlaps(a, b) == overlaps(b, a)


@given(scopes)
def test_property_empty_selector_never_restricts(s):
    assert matches_scope(s, {})


@given(scopes, scopes)
def test_property_match_implies_no_mismatch(a, b):
    assert matches_scope(a, b) == (mismatched_dimensions(a, b) == [])
