"""Yedek ve geri yükleme (brief 5.9).

Arşiv (`metis-backup-YYYYmmdd-HHMMSS.zip`, üzerine yazılmaz):
- `db.dump`: `pg_dump -Fc` (tutarlı anlık görüntü)
- `blobs/xx/<sha256>`: içerik adresli kaynak dosyaları (dökümden SONRA listelenir → dökümün ihtiyaç duyduğu her blob var)
- `manifest.json`: sürüm, migration revizyonu, ana anahtar parmak izi (anahtarın kendisi DEĞİL), döküm SHA-256'sı,
  blob listesi, tablo satır sayıları.

Ana anahtar arşive girmez; ayrı ve güvenli saklanmalıdır. Geri yükleme yalnız boş bir veritabanına yapılır ve
mevcut ana anahtarın parmak izi arşivdekiyle eşleşmelidir (aksi hâlde sağlayıcı anahtarları çözülemez).
Tatbikat (`--rehearsal`): geçici bir veritabanına yükler, satır sayılarını ve blobları doğrular, veritabanını siler.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
from sqlalchemy import create_engine, text

from metis import __version__
from metis.core.blobs import HEX64, blob_path
from metis.core.config import get_settings
from metis.core.security import load_master_key
from metis.ops import pgtools

FORMAT = "metis-v2-backup-1"
NAME = re.compile(r"^metis-backup-\d{8}-\d{6}\.zip$")
MAX_MANIFEST = 64 * 1024 * 1024


class RestoreRefused(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def backups_dir() -> Path:
    return get_settings().data_dir / "backups"


def _psycopg_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _table_counts(url: str) -> dict[str, int]:
    with psycopg.connect(_psycopg_url(url)) as conn:
        names = [r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")]
        return {n: conn.execute(f'SELECT count(*) FROM "{n}"').fetchone()[0] for n in names if n != "alembic_version"}  # type: ignore[index]


def _revision(url: str) -> str | None:
    with psycopg.connect(_psycopg_url(url)) as conn:
        exists = conn.execute("SELECT to_regclass('public.alembic_version')").fetchone()[0]  # type: ignore[index]
        return conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] if exists else None  # type: ignore[index]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def key_fingerprint() -> str:
    return hashlib.sha256(load_master_key()).hexdigest()


def create_backup(destination: Path | None = None) -> dict[str, Any]:
    settings = get_settings()
    stamp = datetime.now(UTC)
    target = destination or backups_dir() / f"metis-backup-{stamp.strftime('%Y%m%d-%H%M%S')}.zip"
    if target.exists():
        raise FileExistsError(f"Yedek hedefi zaten var; üzerine yazılmaz: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    url = settings.owner_database_url
    with tempfile.TemporaryDirectory(prefix="metis-backup-") as tmp:
        dump_file = Path(tmp) / "db.dump"
        pgtools.dump(url, dump_file)
        counts = _table_counts(url)
        blobs = []
        root = settings.blob_dir
        if root.exists():
            for p in sorted(root.glob("??/*")):
                if p.is_file() and HEX64.match(p.name):
                    digest = _sha256_file(p)
                    if digest != p.name:
                        raise ValueError(f"Blob bütünlük hatası: {p.name}")
                    blobs.append({"sha256": digest, "size": p.stat().st_size})
        manifest = {
            "format": FORMAT,
            "metis_version": __version__,
            "created_at": stamp.isoformat(),
            "migration_revision": _revision(url),
            "master_key_fingerprint": key_fingerprint(),
            "db_dump_sha256": _sha256_file(dump_file),
            "db_dump_bytes": dump_file.stat().st_size,
            "pg_dump": pgtools.version("pg_dump"),
            "table_counts": counts,
            "blobs": blobs,
        }
        partial = target.with_name(target.name + ".partial")
        with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as z:
            z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            z.write(dump_file, "db.dump")
            for b in blobs:
                z.write(blob_path(b["sha256"]), f"blobs/{b['sha256'][:2]}/{b['sha256']}")
        os.replace(partial, target)
    result = {
        "ok": True,
        "file": str(target),
        "sha256": _sha256_file(target),
        "bytes": target.stat().st_size,
        "at": stamp.isoformat(),
        "blobs": len(blobs),
        "rows": sum(counts.values()),
        "migration_revision": manifest["migration_revision"],
    }
    marker = backups_dir() / "last-backup.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def prune_backups(keep_days: int) -> list[str]:
    """`keep_days`'ten eski varsayılan yedekleri siler; en yeni yedek her zaman kalır."""
    files = sorted((p for p in backups_dir().glob("metis-backup-*.zip") if NAME.match(p.name)), key=lambda p: p.name)
    cutoff = datetime.now(UTC) - timedelta(days=keep_days)
    removed = []
    for p in files[:-1]:
        taken = datetime.strptime(p.name[13:28], "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
        if taken < cutoff:
            p.unlink()
            removed.append(p.name)
    return removed


def latest_backup() -> Path | None:
    files = sorted(p for p in backups_dir().glob("metis-backup-*.zip") if NAME.match(p.name))
    return files[-1] if files else None


# ------------------------------------------------------------------ geri yükleme


def _open_archive(archive: Path) -> tuple[zipfile.ZipFile, dict[str, Any]]:
    if not archive.is_file():
        raise RestoreRefused("NOT_FOUND", "Yedek arşivi bulunamadı.")
    try:
        z = zipfile.ZipFile(archive)
    except zipfile.BadZipFile:
        raise RestoreRefused("CORRUPT", "Yedek arşivi okunamadı (ZIP değil).") from None
    try:
        info = z.getinfo("manifest.json")
        if info.file_size > MAX_MANIFEST:
            raise RestoreRefused("CORRUPT", "manifest.json boyutu geçersiz.")
        manifest = json.loads(z.read(info))
    except (KeyError, ValueError):
        z.close()
        raise RestoreRefused("CORRUPT", "manifest.json okunamadı.") from None
    if manifest.get("format") != FORMAT:
        z.close()
        raise RestoreRefused("UNSUPPORTED", "Desteklenmeyen yedek biçimi.")
    return z, manifest


def _verify_archive(z: zipfile.ZipFile, manifest: dict[str, Any], work: Path) -> Path:
    if manifest.get("master_key_fingerprint") != key_fingerprint():
        raise RestoreRefused("KEY_MISMATCH", "Ana anahtar bu yedeği alan kurulumunkiyle eşleşmiyor; sağlayıcı anahtarları çözülemez. Doğru master.key dosyasını yapılandır.")
    dump_file = work / "db.dump"
    with z.open("db.dump") as src, dump_file.open("wb") as dst:
        shutil.copyfileobj(src, dst)
    if _sha256_file(dump_file) != manifest.get("db_dump_sha256"):
        raise RestoreRefused("HASH_MISMATCH", "Veritabanı dökümünün özeti uyuşmuyor.")
    for b in manifest.get("blobs", []):
        digest = str(b.get("sha256", ""))
        if not HEX64.match(digest):
            raise RestoreRefused("BAD_HASH", "Manifestte geçersiz blob özeti.")
        try:
            data = z.read(f"blobs/{digest[:2]}/{digest}")  # yol yalnız doğrulanmış özetten türetilir
        except KeyError:
            raise RestoreRefused("MISSING_BLOB", f"Blob eksik: {digest}") from None
        if hashlib.sha256(data).hexdigest() != digest:
            raise RestoreRefused("HASH_MISMATCH", f"Blob özeti uyuşmuyor: {digest}")
    return dump_file


def _require_empty_db(url: str) -> None:
    with psycopg.connect(_psycopg_url(url)) as conn:
        n = conn.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]  # type: ignore[index]
    if n:
        raise RestoreRefused("TARGET_NOT_EMPTY", "Hedef veritabanı boş değil. Yeni, boş bir veritabanı oluştur (migrate çalıştırmadan) ve METIS_DATABASE_URL'yi ona yönelt.")


def _check_restored(url: str, manifest: dict[str, Any], blob_root: Path | None, z: zipfile.ZipFile) -> dict[str, Any]:
    counts = _table_counts(url)
    expected = manifest.get("table_counts", {})
    mismatched = {k: (expected.get(k), counts.get(k)) for k in set(expected) | set(counts) if expected.get(k) != counts.get(k)}
    if mismatched:
        raise RestoreRefused("VERIFY_FAILED", f"Geri yüklenen satır sayıları uyuşmuyor: {sorted(mismatched)[:10]}")
    if _revision(url) != manifest.get("migration_revision"):
        raise RestoreRefused("VERIFY_FAILED", "Migration revizyonu uyuşmuyor.")
    names = set(z.namelist())
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            needed = {r[0] for r in conn.execute(text("SELECT DISTINCT sha256 FROM source_revisions"))}
            attached = {r[0] for r in conn.execute(text("SELECT DISTINCT sha256 FROM attachments"))}
    finally:
        engine.dispose()

    def absent(digests: set[str]) -> list[str]:
        return sorted(d for d in digests if f"blobs/{d[:2]}/{d}" not in names and not (blob_root and blob_path(d, blob_root).is_file()))

    if missing := absent(needed):
        raise RestoreRefused("VERIFY_FAILED", f"{len(missing)} kaynak revizyonunun dosyası yedekte yok.")
    if missing := absent(attached):
        raise RestoreRefused("VERIFY_FAILED", f"{len(missing)} ekin dosyası yedekte yok.")
    return {"rows": sum(counts.values()), "tables": len(counts), "source_files": len(needed), "attachment_files": len(attached)}


def restore_backup(archive: Path, database_url: str | None = None, data_dir: Path | None = None) -> dict[str, Any]:
    settings = get_settings()
    url = database_url or settings.owner_database_url
    blob_root = (data_dir / "blobs") if data_dir else settings.blob_dir
    try:
        z, manifest = _open_archive(archive)
        with z, tempfile.TemporaryDirectory(prefix="metis-restore-") as tmp:
            dump_file = _verify_archive(z, manifest, Path(tmp))
            _require_empty_db(url)
            pgtools.restore(url, dump_file)
            for b in manifest.get("blobs", []):
                target = blob_path(b["sha256"], blob_root)
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    partial = target.with_name(f"{target.name}.{uuid.uuid4().hex}.tmp")
                    partial.write_bytes(z.read(f"blobs/{b['sha256'][:2]}/{b['sha256']}"))
                    os.replace(partial, target)
            check = _check_restored(url, manifest, blob_root, z)
    except RestoreRefused as exc:
        return {"ok": False, "code": exc.code, "message": exc.message}
    except pgtools.PgToolError as exc:
        return {"ok": False, "code": "PG_RESTORE_FAILED", "message": str(exc)}
    return {"ok": True, "mode": "restore", "archive": str(archive), "created_at": manifest.get("created_at"), **check, "note": "Oturumlar geri yüklenen veriyle birlikte gelir; güvenlik için servisleri yeniden başlatıp kullanıcılardan yeniden giriş yapmalarını iste."}


def drop_database(admin_url: str, name: str, attempts: int = 10) -> None:
    """Geçici veritabanını siler. O anda bağlı bir arka plan süreci (ör. autovacuum) varsa süper kullanıcı olmayan rol
    onu sonlandıramaz ("permission denied to terminate process"); süreç kısa sürede biter, yeniden denenir."""
    for attempt in range(attempts):
        try:
            with psycopg.connect(admin_url, autocommit=True) as conn:
                conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            return
        except psycopg.errors.InsufficientPrivilege:
            if attempt == attempts - 1:
                raise
            time.sleep(1)

def rehearse_restore(archive: Path) -> dict[str, Any]:
    """Geçici veritabanına geri yükler, doğrular ve siler. Canlı veritabanına ve blob deposuna dokunmaz."""
    settings = get_settings()
    base = settings.owner_database_url
    name = f"metis_rehearsal_{uuid.uuid4().hex[:10]}"
    admin_url = _psycopg_url(pgtools.with_dbname(base, "postgres"))
    started = datetime.now(UTC)
    try:
        z, manifest = _open_archive(archive)
    except RestoreRefused as exc:
        return {"ok": False, "code": exc.code, "message": exc.message}
    with z, tempfile.TemporaryDirectory(prefix="metis-rehearsal-") as tmp:
        try:
            dump_file = _verify_archive(z, manifest, Path(tmp))
            with psycopg.connect(admin_url, autocommit=True) as conn:
                conn.execute(f'CREATE DATABASE "{name}"')
            url = pgtools.with_dbname(base, name)
            pgtools.restore(url, dump_file)
            check = _check_restored(url, manifest, None, z)
        except RestoreRefused as exc:
            return {"ok": False, "code": exc.code, "message": exc.message}
        except pgtools.PgToolError as exc:
            return {"ok": False, "code": "PG_RESTORE_FAILED", "message": str(exc)}
        finally:
            drop_database(admin_url, name)
    result = {"ok": True, "mode": "rehearsal", "archive": str(archive), "created_at": manifest.get("created_at"), **check, "seconds": round((datetime.now(UTC) - started).total_seconds(), 1)}
    marker = backups_dir() / "last-rehearsal.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
