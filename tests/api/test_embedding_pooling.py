"""Gömme havuzlama (MODEL.json `pooling`): e5 ailesi ortalama, bge-m3 ilk belirteç (CLS) kullanır."""

from __future__ import annotations

import numpy as np
import pytest

from metis.modules.search.embedding import pool


def _batch() -> tuple[np.ndarray, np.ndarray]:
    out = np.array([[[3.0, 4.0], [1.0, 0.0], [9.0, 9.0]]], dtype=np.float32)  # 1 metin, 3 belirteç, 2 boyut
    mask = np.array([[1, 1, 0]], dtype=np.int64)  # son belirteç dolgu
    return out, mask


def test_mean_pooling_ignores_padding_and_normalises():
    out, mask = _batch()
    vec = pool(out, mask, "mean")
    expected = np.array([2.0, 2.0]) / np.linalg.norm([2.0, 2.0])
    assert np.allclose(vec[0], expected)


def test_cls_pooling_uses_first_token():
    out, mask = _batch()
    vec = pool(out, mask, "cls")
    assert np.allclose(vec[0], [0.6, 0.8])


def test_pooling_is_part_of_model_identity():
    """Aynı `id` ile havuzlaması değiştirilen modelin eski (başka havuzlamalı) vektörleri kullanılmamalı."""
    from metis.modules.search.embedding import effective_model_id

    assert effective_model_id("e5@1", "mean") == "e5@1"  # mevcut kurulumların vektörleri geçerli kalır
    assert effective_model_id("e5@1", "cls") == "e5@1#cls"


def test_unknown_pooling_is_rejected():
    out, mask = _batch()
    with pytest.raises(ValueError):
        pool(out, mask, "max")
