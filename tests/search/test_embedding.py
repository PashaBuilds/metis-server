"""Yerel gömme modeli (İş 3): yoksa ya da bozuksa METIS çökmez; varsa normalize vektör üretir."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from metis.modules.search import embedding


@pytest.fixture(autouse=True)
def _fresh():  # noqa: ANN202
    embedding.reset()
    yield
    embedding.reset()


def test_absent_model_dir(tmp_path: Path, monkeypatch):  # noqa: ANN001
    monkeypatch.setenv("METIS_EMBEDDING_MODEL_DIR", str(tmp_path / "yok"))
    assert embedding.embedder_status()["state"] == "absent"
    assert embedding.get_embedder() is None


def test_broken_model_reports_error(tmp_path: Path, monkeypatch):  # noqa: ANN001
    (tmp_path / "onnx").mkdir()
    (tmp_path / "onnx" / "model_quantized.onnx").write_bytes(b"bozuk")
    (tmp_path / "tokenizer.json").write_text("{}", encoding="utf-8")
    (tmp_path / "MODEL.json").write_text(json.dumps({"id": "kurgu", "dim": 4}), encoding="utf-8")
    monkeypatch.setenv("METIS_EMBEDDING_MODEL_DIR", str(tmp_path))
    st = embedding.embedder_status()
    assert st["state"] == "error" and st["reason"]
    assert embedding.get_embedder() is None


@pytest.mark.skipif(not os.getenv("METIS_TEST_EMBEDDING_MODEL_DIR"), reason="gerçek model dizini verilmedi")
def test_real_model_embeds(monkeypatch):  # noqa: ANN001
    monkeypatch.setenv("METIS_EMBEDDING_MODEL_DIR", os.environ["METIS_TEST_EMBEDDING_MODEL_DIR"])
    e = embedding.get_embedder()
    assert e is not None and embedding.embedder_status()["state"] == "ready"
    p = e.embed(["PERST# sinyali en az 100 ms aktif tutulur.", "Konsol 115200 baud hızındadır."], "passage")
    q = e.embed(["PERST# ne kadar süre tutulur?"], "query")[0]
    assert p.shape == (2, e.dim) and np.allclose(np.linalg.norm(p, axis=1), 1, atol=1e-3)
    assert float(p[0] @ q) > float(p[1] @ q)
