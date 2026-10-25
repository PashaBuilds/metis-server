"""Testler için deterministik sahte gömme: katlanmış sözcüklerin karma kovaları (kelime örtüşmesi ≈ benzerlik)."""

from __future__ import annotations

import hashlib
import re

import numpy as np

from metis.modules.search.text import fold

DIM = 1024  # geniş: kova çakışması (sahte benzerlik) olmasın


class FakeEmbedder:
    model_id = "kurgusal-gomme@1"
    dim = DIM
    min_score = 0.1
    admit_score = 0.3

    def __init__(self, synonyms: dict[str, str] | None = None) -> None:
        self.synonyms = synonyms or {}  # ör. {"busy": "mesgul"}: diller arası eşleşmeyi taklit eder

    def embed(self, texts: list[str], kind: str) -> np.ndarray:
        if any("ZEHIRLI" in t for t in texts):
            raise RuntimeError("kurgusal gömme hatası")
        out = np.zeros((len(texts), DIM), dtype=np.float32)
        for i, t in enumerate(texts):
            for w in re.findall(r"\w+", fold(t)):
                w = self.synonyms.get(w, w)
                out[i, int(hashlib.md5(w.encode()).hexdigest(), 16) % DIM] += 1.0  # noqa: S324 — kurgusal test karması
            n = np.linalg.norm(out[i])
            if n:
                out[i] /= n
        return out
