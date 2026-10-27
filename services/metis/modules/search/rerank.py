"""Yerel yeniden sıralayıcı (cross-encoder): soru ile aday bölüm birlikte okunur, 0–1 ilgi puanı. ONNX, CPU, internetsiz.

Model ayrı eklenti ZIP'iyle gelir (`METIS_RERANKER_MODEL_DIR`, varsayılan `<METIS kökü>/models/yeniden-siralayici`).
Dizin: `MODEL.json` (`id`, `kind: "reranker"`, `onnx`, `max_tokens`), `tokenizer.json`, ONNX dosyası.
Yalnız Mentor kullanır: soru başına en çok `CANDIDATES` aday, her biri en çok `MAX_TOKENS` belirteç; adaylar arama
sırasıyla `BATCH`'lik partilerle okunur ve `BUDGET_S` dolunca kalanlar arama sırasında bırakılır (geliştirme
bilgisayarında kısa bölümlerde 30 aday ≈ 1–2 sn; uzun bölümlerde bütçe ≈ 4 sn'de keser). Arama kutusu hızlı kalır. Model yoksa ya da yüklenemezse METIS çökmez: Mentor arama sırasıyla sürer (`reranker_status` nedenini söyler).
Puan sıralama içindir, kanıt değildir: aday eklemez, çıkarmaz.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from metis.core.config import get_settings

log = logging.getLogger("metis.rerank")
CANDIDATES = 30
BATCH = 8
MAX_TOKENS = 256  # soru + başlık + bölüm; tipik bölüm sığar, uzun paragraf kesilir
BUDGET_S = 4.0
_lock = threading.Lock()
_state: dict = {}


def model_dir() -> Path:
    env = os.getenv("METIS_RERANKER_MODEL_DIR", "").strip()
    if env:
        return Path(env)
    return get_settings().data_dir.parent / "models" / "yeniden-siralayici"


@dataclass
class Reranker:
    model_id: str
    _session: object
    _tokenizer: object
    _inputs: set[str]

    def scores(self, query: str, texts: list[str]) -> list[float]:
        out: list[float] = []
        for i in range(0, len(texts), BATCH):
            enc = self._tokenizer.encode_batch([(query, t) for t in texts[i : i + BATCH]])  # type: ignore[attr-defined]
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            feeds = {"input_ids": ids, "attention_mask": mask, "token_type_ids": np.zeros_like(ids)}
            logits = self._session.run(None, {k: v for k, v in feeds.items() if k in self._inputs})[0].reshape(-1)  # type: ignore[attr-defined]
            out.extend((1.0 / (1.0 + np.exp(-logits.astype(np.float64)))).tolist())
        return out


def _load(path: Path) -> Reranker:
    import onnxruntime as ort
    from tokenizers import Tokenizer

    meta = json.loads((path / "MODEL.json").read_text(encoding="utf-8"))
    if meta.get("kind") != "reranker":
        raise ValueError("MODEL.json kind is not 'reranker'")
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = max(1, min(6, (os.cpu_count() or 2) // 2))  # Mentor beklerken; worker aynı makinede
    session = ort.InferenceSession(str(path / meta.get("onnx", "onnx/model_quantized.onnx")), opts, providers=["CPUExecutionProvider"])
    tokenizer = Tokenizer.from_file(str(path / "tokenizer.json"))
    tokenizer.enable_truncation(min(int(meta.get("max_tokens", MAX_TOKENS)), MAX_TOKENS))
    tokenizer.enable_padding()
    rr = Reranker(model_id=str(meta["id"]), _session=session, _tokenizer=tokenizer, _inputs={i.name for i in session.get_inputs()})
    probe = rr.scores("kontrol", ["kontrol", "başka"])  # yanlış çıktı biçimli model "hazır" görünmesin
    if len(probe) != 2 or not np.isfinite(probe).all():
        raise ValueError(f"reranker output {probe!r}, expected 2 finite scores")
    return rr


def _ensure() -> None:
    if _state:
        return
    with _lock:
        if _state:
            return
        path = model_dir()
        if not (path / "MODEL.json").is_file():
            _state.update(state="absent", model_id=None, reason="model_not_installed", reranker=None)
            return
        try:
            rr = _load(path)
        except Exception as exc:  # noqa: BLE001 — bozuk/eksik model Mentor'u düşürmez
            log.warning("reranker model could not be loaded", extra={"event": type(exc).__name__})
            _state.update(state="error", model_id=None, reason=f"{type(exc).__name__}: {str(exc)[:200]}", reranker=None)
            return
        _state.update(state="ready", model_id=rr.model_id, reason=None, reranker=rr)


_loader: threading.Thread | None = None


def preload() -> None:
    """Modeli arka planda yükle (API açılışında; ilk Mentor sorusu ve Sistem durumu yüklemeyi beklemez)."""
    global _loader
    if _state or (_loader is not None and _loader.is_alive()) or not (model_dir() / "MODEL.json").is_file():
        return
    _loader = threading.Thread(target=_ensure, name="metis-reranker-load", daemon=True)
    _loader.start()


def join_loader(timeout: float) -> None:
    if _loader is not None:
        _loader.join(timeout)


def get_reranker(wait: bool = True) -> Reranker | None:
    """`wait=False` (Mentor): yüklenmemişse beklemez, yüklemeyi arka planda başlatır ve None döner (arama sırası)."""
    if not wait and not _state:
        preload()
        return None
    _ensure()
    return _state.get("reranker")


def reranker_status(load: bool = True) -> dict:
    """`load=False` (Sistem durumu): modeli yüklemez; yükleniyorsa `loading`, kurulu değilse `absent`."""
    if not load and not _state:
        if not (model_dir() / "MODEL.json").is_file():
            return {"state": "absent", "model_id": None, "reason": "model_not_installed"}
        preload()
        return {"state": "loading", "model_id": None, "reason": None}
    _ensure()
    return {k: _state.get(k) for k in ("state", "model_id", "reason")}


def reset() -> None:
    join_loader(60)
    with _lock:
        _state.clear()


def order(reranker: Reranker, query: str, texts: list[str]) -> tuple[list[int], int]:
    """(yeni sıra, puanlanan aday sayısı). Adaylar arama sırasıyla partilerle puanlanır; bir sonraki parti `BUDGET_S`'i
    aşacaksa durulur. Puanlananlar puana göre (eşitlikte arama sırası) başa, kalanlar arama sırasıyla arkaya."""
    import time

    scores: list[float] = []
    start = time.perf_counter()
    last = 0.0
    for i in range(0, len(texts), BATCH):
        elapsed = time.perf_counter() - start
        if scores and elapsed + last > BUDGET_S:
            break
        t = time.perf_counter()
        scores.extend(reranker.scores(query, texts[i : i + BATCH]))
        last = time.perf_counter() - t
    n = len(scores)
    return sorted(range(n), key=lambda i: (-scores[i], i)) + list(range(n, len(texts))), n
