"""Testler için deterministik sahte gömme: katlanmış sözcüklerin karma kovaları (kelime örtüşmesi ≈ benzerlik)."""

from __future__ import annotations

import hashlib
import re

import numpy as np

from metis.modules.search.text import fold

DIM = 64


class FakeEmbedder:
    model_id = "kurgusal-gomme@1"
    dim = DIM

    def __init__(self, synonyms: dict[str, str] | None = None) -> None:
        self.synonyms = synonyms or {}  # ör. {"busy": "mesgul"}: diller arası eşleşmeyi taklit eder

    def embed(self, texts: list[str], kind: str) -> np.ndarray:
        out = np.zeros((len(texts), DIM), dtype=np.float32)
        for i, t in enumerate(texts):
            for w in re.findall(r"\w+", fold(t)):
                w = self.synonyms.get(w, w)
                out[i, int(hashlib.md5(w.encode()).hexdigest(), 16) % DIM] += 1.0  # noqa: S324 — kurgusal test karması
            n = np.linalg.norm(out[i])
            if n:
                out[i] /= n
        return out
