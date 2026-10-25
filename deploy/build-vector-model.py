"""Vektör arama model eklentisi ZIP'i (yalnız geliştirme bilgisayarında, internetle): `METIS-vektor-modeli-e5-base-1.zip`.

    python deploy/build-vector-model.py [--cache <klasör>]

Model `intfloat/multilingual-e5-base` (MIT), ONNX int8 hâli `Xenova/multilingual-e5-base`; revizyon ve dosya özetleri
aşağıda sabittir — özet tutmazsa durur. ZIP: `multilingual-e5-base/` (model + MODEL.json + NOTICE.txt), kurulum betiği
`vektor-modeli-kur.ps1`, `SHA256SUMS`. Model değişmedikçe yeniden derlenmez; METIS sürümünden bağımsızdır.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "METIS-vektor-modeli-e5-base-1"
MODEL_DIR = "multilingual-e5-base"
REPO = "Xenova/multilingual-e5-base"
REVISION = "1ec9243030a27d1a115d5c340572074c125b58b2"
FILES = {
    "config.json": "4c27930e59106027abab56f7531c1fa6b14bbf31e8229ec36d68affa4e869bcd",
    "tokenizer.json": "62c24cdc13d4c9952d63718d6c9fa4c287974249e16b7ade6d5a85e7bbb75626",
    "tokenizer_config.json": "efb5c0d09722e5fe59a462cd2a9976ee216d55b037597d997cd3fe833216da15",
    "special_tokens_map.json": "06e405a36dfe4b9604f484f6a1e619af1a7f7d09e34a8555eb0b77b66318067f",
    "onnx/model_quantized.onnx": "df7a9a29309e3ad491e1783adf8baee710262cc06079c7cbab63c630277fac94",
}
MODEL_JSON = {
    "id": f"multilingual-e5-base@{REVISION[:7]}",
    "dim": 768,
    "query_prefix": "query: ",
    "passage_prefix": "passage: ",
    "max_tokens": 512,
    "onnx": "onnx/model_quantized.onnx",
}
NOTICE = f"""METIS vektör arama modeli

Model: intfloat/multilingual-e5-base — MIT lisansı (Hugging Face model kartı: https://huggingface.co/intfloat/multilingual-e5-base)
ONNX int8 dönüşümü: {REPO}, revizyon {REVISION}
Dosyalar değiştirilmeden alınmıştır; özetler SHA256SUMS'ta. METIS bu modeli yalnız yerel CPU'da, internetsiz kullanır.
"""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(rel: str, cache: Path) -> Path:
    target = cache / rel
    if target.is_file() and sha256(target) == FILES[rel]:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://huggingface.co/{REPO}/resolve/{REVISION}/{rel}"
    print(f"indiriliyor: {url}")
    with urllib.request.urlopen(url, timeout=600) as resp, target.open("wb") as out:  # noqa: S310 — sabit https adresi
        shutil.copyfileobj(resp, out)
    if sha256(target) != FILES[rel]:
        target.unlink()
        raise SystemExit(f"özet tutmadı: {rel}")
    return target


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=str(ROOT / "dist" / "vektor-modeli-cache"))
    ap.add_argument("--out", default=str(ROOT / "dist"))
    args = ap.parse_args()
    cache, out = Path(args.cache), Path(args.out)
    stage = out / NAME
    if stage.exists():
        shutil.rmtree(stage)
    model = stage / MODEL_DIR
    for rel in FILES:
        dest = model / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fetch(rel, cache), dest)
    (model / "MODEL.json").write_text(json.dumps(MODEL_JSON, indent=2) + "\n", encoding="utf-8")
    (model / "NOTICE.txt").write_text(NOTICE, encoding="utf-8")
    script = ROOT / "deploy" / "windows" / "vektor-modeli-kur.ps1"
    (stage / script.name).write_bytes(b"\xef\xbb\xbf" + script.read_bytes().removeprefix(b"\xef\xbb\xbf"))
    rows = [f"{sha256(p)}  {p.relative_to(stage).as_posix()}" for p in sorted(stage.rglob("*")) if p.is_file()]
    (stage / "SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="utf-8")
    zpath = out / f"{NAME}.zip"
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(stage.rglob("*")):
            if p.is_file():
                z.write(p, f"{NAME}/{p.relative_to(stage).as_posix()}")
    digest = sha256(zpath)
    (out / f"{NAME}.zip.sha256").write_text(f"{digest}  {zpath.name}\n", encoding="utf-8")
    print(f"model eklentisi hazır: {zpath} ({zpath.stat().st_size / 1e6:.1f} MB) sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
