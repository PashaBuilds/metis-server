#!/usr/bin/env python3
"""METIS sunucu kurulum paketi üretir (tek ZIP, internetsiz kurulum).

    python deploy/build-bundle.py                    # Windows paketi: dist/METIS-<sürüm>-server-win64.zip
    python deploy/build-bundle.py --target linux64   # Linux paketi (systemd): dist/METIS-<sürüm>-server-linux64.zip
    python deploy/build-bundle.py --locked           # indirilen tekerlekler deploy/locks/<hedef>.lock ile birebir olmalı

İçerik (win64): gömülü Python 3.12 (python.org embeddable), pip zipapp, hash-kilitli wheelhouse (cp312 win_amd64),
derlenmiş web arayüzü, WinSW servis sarmalayıcısı, kurulum/yükseltme betikleri, BASLA.txt, KURULUM.md, SHA256SUMS.
Dış ikililer sabit sürüm + sabit SHA-256 ile indirilir (deploy/.cache'te önbelleklenir); özet uyuşmazsa üretim durur.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "deploy" / ".cache"
LOCKS = ROOT / "deploy" / "locks"

# Sabit sürümler ve ilk indirmede kaydedilen SHA-256'lar (değiştirmek bilinçli bir karardır).
EXTERNAL = {
    "python": ("https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip", "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"),
    "pip": ("https://bootstrap.pypa.io/pip/zipapp/pip-24.3.1.pyz", "c59df64b826d5baa978829fd1e1b3ea2e748f73dce7cce58d09aa28a1c9323a7"),
    "winsw": ("https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe", "05b82d46ad331cc16bdc00de5c6332c1ef818df8ceefcd49c726553209b3a0da"),
}
PLATFORM = {
    "win64": ["--platform", "win_amd64"],
    "linux64": ["--platform", "manylinux2014_x86_64", "--platform", "manylinux_2_17_x86_64", "--platform", "manylinux_2_28_x86_64"],
}


def sh(cmd: list[str], **kw) -> None:  # noqa: ANN003
    print("+", " ".join(cmd), flush=True)
    # Windows'ta npm gibi araçlar .cmd'dir; CreateProcess yalnız .exe'yi çözer, tam yol verilmeli.
    exe = shutil.which(cmd[0]) or cmd[0]
    subprocess.run([exe, *cmd[1:]], check=True, **kw)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(name: str) -> Path:
    url, digest = EXTERNAL[name]
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / url.rsplit("/", 1)[1]
    if not target.exists():
        print(f"indiriliyor: {url}", flush=True)
        tmp = target.with_suffix(".partial")
        with urllib.request.urlopen(url, timeout=120) as r, tmp.open("wb") as f:  # noqa: S310 — sabit https adresi
            shutil.copyfileobj(r, f)
        tmp.replace(target)
    if sha256(target) != digest:
        raise SystemExit(f"SHA-256 uyuşmuyor: {target.name} (beklenen {digest}). Üretim durduruldu.")
    return target


def version() -> str:
    text = (ROOT / "services" / "metis" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'__version__ = "([^"]+)"', text)
    assert m
    return m.group(1)


def build_wheelhouse(target: str, wheelhouse: Path, lock: Path | None = None) -> list[str]:
    """Kilit verilirse üçüncü taraf paketler tam olarak kilitteki sürüm ve hash'lerle indirilir (tekrarlanabilir
    derleme; PyPI'da yeni sürüm çıkması paketi değiştirmez). Kilit yoksa bağımlılıklar çözülür."""
    wheelhouse.mkdir(parents=True)
    sh([sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", str(wheelhouse), str(ROOT)])
    own = next(wheelhouse.glob("metis-*.whl"))
    if lock is not None:
        sh([
            sys.executable, "-m", "pip", "download", "--only-binary=:all:", *PLATFORM[target],
            "--python-version", "3.12", "--implementation", "cp", "--abi", "cp312", "--abi", "abi3", "--abi", "none",
            "--no-deps", "--require-hashes", "-d", str(wheelhouse), "-r", str(lock),
        ])
    else:
        sh([
            sys.executable, "-m", "pip", "download", "--only-binary=:all:", *PLATFORM[target],
            "--python-version", "3.12", "--implementation", "cp", "--abi", "cp312", "--abi", "abi3", "--abi", "none",
            "-d", str(wheelhouse), str(own),
        ])
    complete_for_target(target, wheelhouse)
    lines = []
    for whl in sorted(wheelhouse.glob("*.whl")):
        name, ver = whl.name.split("-")[:2]
        lines.append(f"{name.replace('_', '-').lower()}=={ver} --hash=sha256:{sha256(whl)}")
    return lines


TARGET_ENV = {
    "win64": {"sys_platform": "win32", "platform_system": "Windows", "os_name": "nt", "platform_machine": "AMD64"},
    "linux64": {"sys_platform": "linux", "platform_system": "Linux", "os_name": "posix", "platform_machine": "x86_64"},
}


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def complete_for_target(target: str, wheelhouse: Path) -> None:
    """`pip download --platform` ortam işaretlerini (ör. `tzdata; sys_platform == "win32"`) derleme makinesine göre
    değerlendirir; hedefte gereken ama atlanan bağımlılıkları hedef ortamıyla değerlendirip ekler."""
    from packaging.markers import default_environment
    from packaging.requirements import Requirement

    env = {**default_environment(), "python_version": "3.12", "python_full_version": "3.12.10", "implementation_name": "cpython", "platform_python_implementation": "CPython", **TARGET_ENV[target]}
    for _ in range(5):
        present = {_norm(w.name.split("-")[0]) for w in wheelhouse.glob("*.whl")}
        missing: set[str] = set()
        for whl in wheelhouse.glob("*.whl"):
            with zipfile.ZipFile(whl) as z:
                meta = next(n for n in z.namelist() if n.endswith(".dist-info/METADATA"))
                for line in z.read(meta).decode("utf-8", "replace").splitlines():
                    if not line.startswith("Requires-Dist:"):
                        continue
                    req = Requirement(line.split(":", 1)[1].strip())
                    if req.marker is None or not req.marker.evaluate({**env, "extra": ""}):
                        continue
                    if _norm(req.name) not in present:
                        missing.add(str(req).split(";")[0].strip())
        if not missing:
            return
        print(f"hedef platform için eksik bağımlılıklar: {sorted(missing)}")
        sh([
            sys.executable, "-m", "pip", "download", "--only-binary=:all:", *PLATFORM[target],
            "--python-version", "3.12", "--implementation", "cp", "--abi", "cp312", "--abi", "abi3", "--abi", "none",
            "-d", str(wheelhouse), *sorted(missing),
        ])
    raise SystemExit("Bağımlılık tamamlama 5 turda bitmedi.")


def check_lock(target: str, lines: list[str], update: bool) -> None:
    lock = LOCKS / f"{target}.lock"
    third_party = [ln for ln in lines if not ln.startswith("metis==")]
    if update or not lock.exists():
        LOCKS.mkdir(parents=True, exist_ok=True)
        lock.write_text("# deploy/build-bundle.py ile üretildi; değişiklik inceleme gerektirir.\n" + "\n".join(third_party) + "\n", encoding="utf-8")
        print(f"kilit dosyası yazıldı: {lock.relative_to(ROOT)}")
        return
    expected = [ln for ln in lock.read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")]
    if expected != third_party:
        diff = sorted(set(expected) ^ set(third_party))
        raise SystemExit("İndirilen bağımlılıklar kilit dosyasıyla uyuşmuyor:\n  " + "\n  ".join(diff[:20]) + "\nBilinçli bir yükseltmeyse --update-lock ile yeniden üret.")


def write_sums(folder: Path) -> None:
    rows = []
    for p in sorted(folder.rglob("*")):
        if p.is_file() and p.name != "SHA256SUMS":
            rows.append(f"{sha256(p)}  {p.relative_to(folder).as_posix()}")
    (folder / "SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="utf-8")


def zip_dir(folder: Path, out: Path) -> None:
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(folder.rglob("*")):
            if p.is_file():
                z.write(p, f"{folder.name}/{p.relative_to(folder).as_posix()}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows konsolunda Türkçe iletiler bozulmasın
        sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["win64", "linux64"], default="win64")
    ap.add_argument("--out", default=str(ROOT / "dist"))
    ap.add_argument("--skip-web-build", action="store_true", help="apps/web/dist hazırsa yeniden derleme")
    ap.add_argument("--locked", action="store_true", help="kilit dosyası yoksa veya farklıysa dur")
    ap.add_argument("--update-lock", action="store_true")
    ap.add_argument("--version-suffix", default="", help="yalnız yükseltme testi için (ör. +test1)")
    args = ap.parse_args()

    ver = version() + args.version_suffix
    out_dir = Path(args.out)
    name = f"METIS-{ver}-server-{args.target}"
    stage = out_dir / name
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    if not args.skip_web_build:
        sh(["npm", "run", "build:web"], cwd=ROOT)
    web = ROOT / "apps" / "web" / "dist"
    if not (web / "index.html").is_file():
        raise SystemExit("apps/web/dist/index.html yok; önce web arayüzünü derle.")
    shutil.copytree(web, stage / "web")

    lock = LOCKS / f"{args.target}.lock"
    if args.locked and not lock.exists():
        raise SystemExit("--locked verildi ama kilit dosyası yok.")
    # --locked: kilitten kur; kilitte eksik bir bağımlılık varsa complete_for_target onu indirir ve check_lock durur.
    lines = build_wheelhouse(args.target, stage / "wheelhouse", lock if args.locked and not args.update_lock else None)
    check_lock(args.target, lines, args.update_lock)
    (stage / "requirements.lock").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if args.target == "win64":
        (stage / "runtime").mkdir()
        shutil.copy2(fetch("python"), stage / "runtime" / "python-embed-amd64.zip")
        shutil.copy2(fetch("pip"), stage / "runtime" / "pip.pyz")
        shutil.copy2(fetch("winsw"), stage / "runtime" / "WinSW-x64.exe")
        for f in (ROOT / "deploy" / "windows").iterdir():
            if f.suffix == ".ps1":
                # Windows PowerShell 5.1 BOM'suz UTF-8'i ANSI okur; Türkçe metin için BOM şart.
                (stage / f.name).write_bytes(b"\xef\xbb\xbf" + f.read_bytes().removeprefix(b"\xef\xbb\xbf"))
            elif f.is_file():
                shutil.copy2(f, stage / f.name)
    else:
        for f in (ROOT / "deploy" / "linux").iterdir():
            if f.is_file():
                shutil.copy2(f, stage / f.name)
    shutil.copy2(ROOT / "docs" / "KURULUM.md", stage / "KURULUM.md")
    (stage / "VERSION").write_text(ver + "\n", encoding="utf-8")
    (stage / "bundle.json").write_text(json.dumps({"version": ver, "target": args.target, "python": "3.12", "wheels": len(lines)}, indent=2) + "\n", encoding="utf-8")
    write_sums(stage)
    archive = out_dir / f"{name}.zip"
    zip_dir(stage, archive)
    (out_dir / f"{name}.zip.sha256").write_text(f"{sha256(archive)}  {archive.name}\n", encoding="utf-8")
    print(f"paket hazır: {archive} ({archive.stat().st_size / 1024 / 1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
