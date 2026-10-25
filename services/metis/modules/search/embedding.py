"""Yerel gömme (embedding) modeli: ONNX Runtime + tokenizers, CPU, internetsiz. Tasarım bölüm 6.

Model ayrı eklenti ZIP'iyle gelir (`METIS_EMBEDDING_MODEL_DIR`, varsayılan `<METIS kökü>/models/multilingual-e5-base`).
Dizin: `MODEL.json` (`id`, `dim`, `query_prefix`, `passage_prefix`, `max_tokens`, `onnx`), `tokenizer.json`, ONNX dosyası.
Model yoksa ya da yüklenemezse METIS çökmez: arama yalnız kelime kanalıyla sürer (`embedder_status` nedenini söyler).
Süreç başına bir kez yüklenir (API süreçleri sorgu, worker bloklar için).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

from metis.core.config import get_settings

log = logging.getLogger("metis.embedding")
_lock = threading.Lock()
_state: dict = {}


def model_dir() -> Path:
    env = os.getenv("METIS_EMBEDDING_MODEL_DIR", "").strip()
    if env:
        return Path(env)
    return get_settings().data_dir.parent / "models" / "multilingual-e5-base"


@dataclass
class Embedder:
    model_id: str
    dim: int
    query_prefix: str
    passage_prefix: str
    # Kalibre eşikler (MODEL.json): bu benzerliğin altı yok sayılır; yalnız vektörle bulunan sayfa admit_score'u geçmeli.
    # Eşik verilmemiş modelde yalnız vektörle sayfa eklenmez (güvenli varsayılan).
    min_score: float
    admit_score: float
    _session: object
    _tokenizer: object
    _inputs: set[str]

    def embed(self, texts: list[str], kind: Literal["query", "passage"]) -> np.ndarray:
        prefix = self.query_prefix if kind == "query" else self.passage_prefix
        enc = self._tokenizer.encode_batch([prefix + t for t in texts])  # type: ignore[attr-defined]
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        feeds = {"input_ids": ids, "attention_mask": mask, "token_type_ids": np.zeros_like(ids)}
        out = self._session.run(None, {k: v for k, v in feeds.items() if k in self._inputs})[0]  # type: ignore[attr-defined]
        vec = (out * mask[..., None]).sum(axis=1) / np.maximum(mask.sum(axis=1, keepdims=True), 1)
        norm = np.linalg.norm(vec, axis=1, keepdims=True)
        return (vec / np.maximum(norm, 1e-12)).astype(np.float32)


def _load(path: Path) -> Embedder:
    import onnxruntime as ort
    from tokenizers import Tokenizer

    meta = json.loads((path / "MODEL.json").read_text(encoding="utf-8"))
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = max(1, min(4, (os.cpu_count() or 2) // 2))  # API ve worker aynı makinede
    session = ort.InferenceSession(str(path / meta.get("onnx", "onnx/model_quantized.onnx")), opts, providers=["CPUExecutionProvider"])
    tokenizer = Tokenizer.from_file(str(path / "tokenizer.json"))
    tokenizer.enable_truncation(int(meta.get("max_tokens", 512)))
    tokenizer.enable_padding()
    emb = Embedder(
        model_id=str(meta["id"]),
        dim=int(meta["dim"]),
        query_prefix=str(meta.get("query_prefix", "query: ")),
        passage_prefix=str(meta.get("passage_prefix", "passage: ")),
        min_score=float(meta.get("min_score", 0.0)),
        admit_score=float(meta.get("admit_score", 1.01)),
        _session=session,
        _tokenizer=tokenizer,
        _inputs={i.name for i in session.get_inputs()},
    )
    probe = emb.embed(["kontrol"], "query")  # yanlış çıktı biçimli model "hazır" görünmesin
    if probe.shape != (1, emb.dim) or not np.isfinite(probe).all():
        raise ValueError(f"model output shape {probe.shape}, expected (1, {emb.dim})")
    return emb


def _ensure() -> None:
    if _state:
        return
    with _lock:
        if _state:
            return
        path = model_dir()
        if not (path / "MODEL.json").is_file():
            _state.update(state="absent", model_id=None, reason="model_not_installed", embedder=None)
            return
        try:
            emb = _load(path)
        except Exception as exc:  # noqa: BLE001 — bozuk/eksik model aramayı düşürmez
            log.warning("embedding model could not be loaded", extra={"event": type(exc).__name__})
            _state.update(state="error", model_id=None, reason=f"{type(exc).__name__}: {str(exc)[:200]}", embedder=None)
            return
        _state.update(state="ready", model_id=emb.model_id, reason=None, embedder=emb)


def get_embedder() -> Embedder | None:
    _ensure()
    return _state.get("embedder")


def embedder_status() -> dict:
    _ensure()
    return {k: _state.get(k) for k in ("state", "model_id", "reason")}


def use_for_tests(embedder: object) -> None:
    """Testler: deterministik sahte gömmeyi süreç modeli olarak kurar."""
    with _lock:
        _state.clear()
        _state.update(state="ready", model_id=getattr(embedder, "model_id", "test"), reason=None, embedder=embedder)


def reset() -> None:
    """Testler ve yapılandırma değişikliği için: bir sonraki çağrı modeli yeniden arar."""
    with _lock:
        _state.clear()
