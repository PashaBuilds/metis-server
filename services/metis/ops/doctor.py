"""`metis doctor`: kurulum ve çalışma durumu denetimi. Kritik denetimlerden biri başarısızsa `ready=false`.

Her denetim: {name, ok, critical, detail}. Sırlar (ana anahtar, parolalar) hiçbir zaman çıktıya yazılmaz.
"""

from __future__ import annotations

import json
import platform
import random
import shutil
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from metis import __version__
from metis.core.config import get_settings


def _check(name: str, critical: bool, fn: Callable[[], tuple[bool, str]]) -> dict[str, Any]:
    try:
        ok, detail = fn()
    except Exception as exc:  # noqa: BLE001 — denetim sonucu olarak raporlanır
        ok, detail = False, f"{type(exc).__name__}: {str(exc)[:300]}"
    return {"name": name, "ok": ok, "critical": critical, "detail": detail}


def run_doctor() -> dict[str, Any]:  # noqa: C901
    settings = get_settings()
    checks: list[dict[str, Any]] = []

    def config() -> tuple[bool, str]:
        problems = []
        if settings.is_production and not settings.public_url.startswith("https://"):
            problems.append("METIS_PUBLIC_URL https:// olmalı")
        if settings.is_production and not settings.endpoint_allowlist:
            problems.append("METIS_ENDPOINT_ALLOWLIST boş (model eklenemez)")
        return not problems, "; ".join(problems) or f"profil={settings.env}, adres={settings.public_url}"

    def master_key() -> tuple[bool, str]:
        from metis.core.security import load_master_key

        key = load_master_key()
        where = settings.master_key_file or "METIS_MASTER_KEY ortam değişkeni"
        return len(key) == 32, f"32 bayt ana anahtar yüklendi ({where})"

    def database() -> tuple[bool, str]:
        from sqlalchemy import text

        from metis.core.db import engine

        with engine().connect() as conn:
            version = conn.execute(text("SHOW server_version")).scalar()
            role = conn.execute(text("SELECT current_user")).scalar()
        major = int(str(version).split(".")[0])
        return major >= 16, f"PostgreSQL {version}, rol {role}"

    def migration() -> tuple[bool, str]:
        from metis.core.db import reader
        from metis.modules.system.service import expected_revision, migration_revision

        with reader() as db:
            current = migration_revision(db)
        expected = expected_revision()
        return current == expected, f"mevcut {current}, beklenen {expected}" + ("" if current == expected else " → `metis migrate` çalıştır")

    def trgm() -> tuple[bool, str]:
        from metis.core.db import reader
        from metis.modules.system.service import trgm_available

        with reader() as db:
            ok = trgm_available(db)
        return ok, "pg_trgm kurulu (bulanık sembol araması açık)" if ok else "pg_trgm yok; bulanık sembol araması kapalı (diğer arama çalışır)"

    def data_dir() -> tuple[bool, str]:
        d = settings.data_dir
        d.mkdir(parents=True, exist_ok=True)
        probe = d / f".doctor-{uuid.uuid4().hex}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        usage = shutil.disk_usage(d)
        free_gb = usage.free / 1024**3
        return free_gb >= 2, f"{d} yazılabilir, boş alan {free_gb:.1f} GB" + ("" if free_gb >= 2 else " (2 GB altı)")

    def blobs() -> tuple[bool, str]:
        from sqlalchemy import select

        from metis.core.blobs import read_blob
        from metis.core.db import reader
        from metis.core.models import SourceRevision

        with reader() as db:
            digests = list(db.scalars(select(SourceRevision.sha256).distinct()))
        sample = random.sample(digests, min(50, len(digests)))
        bad = []
        for d in sample:
            try:
                read_blob(d)
            except (OSError, ValueError):
                bad.append(d[:12])
        return not bad, f"{len(sample)}/{len(digests)} kaynak dosyası örneklendi" + (f"; bozuk/eksik: {', '.join(bad)}" if bad else ", hepsi sağlam")

    def static() -> tuple[bool, str]:
        index = settings.static_dir / "index.html"
        return index.is_file(), f"web arayüzü {settings.static_dir}" if index.is_file() else f"{index} yok (arayüz derlenmemiş)"

    def backup() -> tuple[bool, str]:
        from metis.ops.pgtools import version

        marker = settings.data_dir / "backups" / "last-backup.json"
        pg = version("pg_dump")
        if not marker.is_file():
            return False, f"Henüz yedek alınmadı ({pg}). `metis backup` çalıştır ve zamanlanmış görevi kur."
        info = json.loads(marker.read_text(encoding="utf-8"))
        age_h = (datetime.now(UTC) - datetime.fromisoformat(info["at"])).total_seconds() / 3600
        return age_h <= 36, f"son yedek {age_h:.0f} saat önce: {info.get('file')} ({pg})"

    def queue() -> tuple[bool, str]:
        from sqlalchemy import func, select

        from metis.core.db import reader, utcnow
        from metis.core.models import Job

        with reader() as db:
            expired = db.scalar(select(func.count()).select_from(Job).where(Job.state == "running", Job.lease_until < utcnow())) or 0
            waiting = db.scalar(select(func.count()).select_from(Job).where(Job.state == "queued")) or 0
            oldest = db.scalar(select(func.min(Job.created_at)).where(Job.state == "queued"))
        wait_min = (utcnow() - oldest).total_seconds() / 60 if oldest else 0
        ok = expired == 0 and wait_min < 30
        return ok, f"bekleyen {waiting}, en eski {wait_min:.0f} dk, süresi dolmuş lease {expired}" + ("" if ok else " → worker servisini kontrol et")

    checks.append(_check("Yapılandırma", True, config))
    checks.append(_check("Ana anahtar", True, master_key))
    checks.append(_check("Veritabanı bağlantısı", True, database))
    checks.append(_check("Şema sürümü", True, migration))
    checks.append(_check("Veri dizini ve disk", True, data_dir))
    checks.append(_check("Web arayüzü", True, static))
    checks.append(_check("Kaynak dosyaları bütünlüğü", True, blobs))
    checks.append(_check("Bulanık arama (pg_trgm)", False, trgm))
    checks.append(_check("Yedek", False, backup))
    checks.append(_check("İş kuyruğu", False, queue))
    ready = all(c["ok"] for c in checks if c["critical"])
    return {"ready": ready, "version": __version__, "profile": settings.env, "host": platform.node(), "checks": checks}
