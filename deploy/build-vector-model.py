"""Vektör arama model eklentisi ZIP'i (yalnız geliştirme bilgisayarında, internetle).

    python deploy/build-vector-model.py [--model bge-m3|e5-base] [--cache <klasör>]

Modeller ve ONNX int8 hâlleri aşağıda sabit revizyon ve dosya özetleriyle tanımlı — özet tutmazsa durur. ZIP: model
klasörü (model + MODEL.json + NOTICE.txt + LICENSE.txt + MODEL-CARD.md), kurulum betiği `vektor-modeli-kur.ps1`,
`SHA256SUMS`. Betik modeli `<METIS kökü>\\models\\vektor-modeli`'ye kurar (2.0.25'ten beri). Model değişmedikçe yeniden
derlenmez; METIS sürümünden bağımsızdır.

- `bge-m3` (`METIS-vektor-modeli-bge-m3-1.zip`, 2.0.25): BAAI/bge-m3 (MIT), ONNX int8 `Xenova/bge-m3`. 2026-10-27 kıyasında
  (kurgusal 5 bin sayfa, 44 soru) konu dışı soruyu ilgili sorudan en iyi ayıran model; sorgu ≈ 18 ms, gömme e5-base'in
  ≈ üçte biri hızında.
- `e5-base` (`METIS-vektor-modeli-e5-base-1.zip`, 2.0.20): intfloat/multilingual-e5-base (MIT), ONNX int8
  `Xenova/multilingual-e5-base`.
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
MODELS: dict[str, dict] = {
    "bge-m3": {
        "name": "METIS-vektor-modeli-bge-m3-1",
        "dir": "bge-m3",
        "repo": "Xenova/bge-m3",
        "revision": "4de13258303883538bd53b696b452bf8099f0858",
        "files": {
            "config.json": "734a79bf12d388c1467a4e3ab625f45de7f6906cffcfb93a1eca1787504bed95",
            "tokenizer.json": "6710678b12670bc442b99edc952c4d996ae309a7020c1fa0096dd245c2faf790",
            "tokenizer_config.json": "7e4c1cc848840aeccdd763458c18dd525eb0f795c992e00ebe9c28554e7db2d4",
            "special_tokens_map.json": "8c785abebea9ae3257b61681b4e6fd8365ceafde980c21970d001e834cf10835",
            "onnx/model_quantized.onnx": "0826f8c1ab9edf1801db86c61919d4d108e8bfc0b809ec823ad366882ff0b77d",
        },
        "model_json": {
            "id": "bge-m3@4de1325",
            "dim": 1024,
            "query_prefix": "",
            "passage_prefix": "",
            "max_tokens": 512,
            "onnx": "onnx/model_quantized.onnx",
            "pooling": "cls",
            # Kurgusal 5 bin sayfalık sette kalibre (2026-10-27, e5 ile aynı kural): konu dışı sorularda en yüksek
            # benzerlik 0,541; ilgili bloklarda en düşük 0,474, %10'luk dilim 0,560. admit = konu dışı en yüksek + 0,02
            # (yukarı yuvarlanmış), min = admit − 0,04.
            "min_score": 0.53,
            "admit_score": 0.57,
        },
        "upstream": "BAAI/bge-m3",
        "upstream_revision": "5617a9f61b028005a4858fdac845db406aefb181",
        "upstream_files": {"README.md": "0b81ccf9134e5874d620a86e6905062ea999e779c34eb1a7e65eaeb7fe00e450"},  # license: mit
        "copyright": "the authors of BAAI/bge-m3 (see MODEL-CARD.md)",
    },
    "e5-base": {
        "name": "METIS-vektor-modeli-e5-base-1",
        "dir": "multilingual-e5-base",
        "repo": "Xenova/multilingual-e5-base",
        "revision": "1ec9243030a27d1a115d5c340572074c125b58b2",
        "files": {
            "config.json": "4c27930e59106027abab56f7531c1fa6b14bbf31e8229ec36d68affa4e869bcd",
            "tokenizer.json": "62c24cdc13d4c9952d63718d6c9fa4c287974249e16b7ade6d5a85e7bbb75626",
            "tokenizer_config.json": "efb5c0d09722e5fe59a462cd2a9976ee216d55b037597d997cd3fe833216da15",
            "special_tokens_map.json": "06e405a36dfe4b9604f484f6a1e619af1a7f7d09e34a8555eb0b77b66318067f",
            "onnx/model_quantized.onnx": "df7a9a29309e3ad491e1783adf8baee710262cc06079c7cbab63c630277fac94",
        },
        "model_json": {
            "id": "multilingual-e5-base@1ec9243",
            "dim": 768,
            "query_prefix": "query: ",
            "passage_prefix": "passage: ",
            "max_tokens": 512,
            "onnx": "onnx/model_quantized.onnx",
            # Kurgusal sette kalibre (2026-10-25): konu dışı sorularda en yüksek benzerlik 0,802; ilgili bloklarda en düşük
            # 0,775, %10'luk dilim 0,817. min_score altı yok sayılır; yalnız vektörle bulunan sayfa admit_score'u geçmelidir.
            "min_score": 0.78,
            "admit_score": 0.82,
        },
        "upstream": "intfloat/multilingual-e5-base",
        "upstream_revision": "d128750597153bb5987e10b1c3493a34e5a4502a",
        "upstream_files": {"README.md": "9d129cb0b912b55c7b5378f976a9c35ae4796c80466b659ad63930d8ca090fca"},  # license: mit
        "copyright": "the authors of intfloat/multilingual-e5-base (Wang et al.; see MODEL-CARD.md)",
    },
}
MIT = """MIT License

Copyright (c) {copyright}

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation
files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy,
modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""
NOTICE = """METIS vektör arama modeli

Model: {upstream} — MIT lisansı (LICENSE.txt; model kartı MODEL-CARD.md, revizyon {upstream_revision})
ONNX int8 dönüşümü: {repo}, revizyon {revision}
Dosyalar değiştirilmeden alınmıştır; özetler SHA256SUMS'ta. METIS bu modeli yalnız yerel CPU'da, internetsiz kullanır.
"""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(rel: str, cache: Path, repo: str, revision: str, files: dict[str, str]) -> Path:
    target = cache / repo.replace("/", "_") / rel
    if target.is_file() and sha256(target) == files[rel]:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://huggingface.co/{repo}/resolve/{revision}/{rel}"
    print(f"indiriliyor: {url}")
    with urllib.request.urlopen(url, timeout=600) as resp, target.open("wb") as out:  # noqa: S310 — sabit https adresi
        shutil.copyfileobj(resp, out)
    if sha256(target) != files[rel]:
        target.unlink()
        raise SystemExit(f"özet tutmadı: {rel}")
    return target


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=sorted(MODELS), default="bge-m3")
    ap.add_argument("--cache", default=str(ROOT / "dist" / "vektor-modeli-cache"))
    ap.add_argument("--out", default=str(ROOT / "dist"))
    args = ap.parse_args()
    spec = MODELS[args.model]
    cache, out = Path(args.cache), Path(args.out)
    name = spec["name"]
    stage = out / name
    if stage.exists():
        shutil.rmtree(stage)
    model = stage / spec["dir"]
    for rel in spec["files"]:
        dest = model / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fetch(rel, cache, spec["repo"], spec["revision"], spec["files"]), dest)
    (model / "MODEL.json").write_text(json.dumps(spec["model_json"], indent=2) + "\n", encoding="utf-8")
    (model / "NOTICE.txt").write_text(NOTICE.format(**spec), encoding="utf-8")
    (model / "LICENSE.txt").write_text(MIT.format(copyright=spec["copyright"]), encoding="utf-8")
    card = fetch("README.md", cache, spec["upstream"], spec["upstream_revision"], spec["upstream_files"])
    shutil.copy2(card, model / "MODEL-CARD.md")
    script = ROOT / "deploy" / "windows" / "vektor-modeli-kur.ps1"
    (stage / script.name).write_bytes(b"\xef\xbb\xbf" + script.read_bytes().removeprefix(b"\xef\xbb\xbf"))
    rows = [f"{sha256(p)}  {p.relative_to(stage).as_posix()}" for p in sorted(stage.rglob("*")) if p.is_file()]
    (stage / "SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="utf-8")
    zpath = out / f"{name}.zip"
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(stage.rglob("*")):
            if p.is_file():
                z.write(p, f"{name}/{p.relative_to(stage).as_posix()}")
    digest = sha256(zpath)
    (out / f"{name}.zip.sha256").write_text(f"{digest}  {zpath.name}\n", encoding="utf-8")
    print(f"model eklentisi hazır: {zpath} ({zpath.stat().st_size / 1e6:.1f} MB) sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
