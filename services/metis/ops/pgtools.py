"""pg_dump / pg_restore çağrıları. Parola komut satırına değil ortam değişkenine (PGPASSWORD) verilir."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit


class PgToolError(RuntimeError):
    pass


def libpq_parts(url: str) -> dict[str, str]:
    """SQLAlchemy URL'sini libpq parametrelerine ayırır (parola ayrı döner, loglanmaz)."""
    raw = url.replace("postgresql+psycopg://", "postgresql://", 1)
    p = urlsplit(raw)
    return {
        "host": p.hostname or "127.0.0.1",
        "port": str(p.port or 5432),
        "user": unquote(p.username or ""),
        "password": unquote(p.password or ""),
        "dbname": p.path.lstrip("/") or "postgres",
    }


def with_dbname(url: str, dbname: str) -> str:
    head, _, _ = url.rpartition("/")
    return f"{head}/{dbname}"


def tool(name: str) -> str:
    """PG istemci araçları: METIS_PG_BIN (Windows'ta ör. C:\\Program Files\\PostgreSQL\\16\\bin) veya PATH."""
    pg_bin = os.getenv("METIS_PG_BIN", "")
    exe = name + (".exe" if os.name == "nt" else "")
    if pg_bin and (Path(pg_bin) / exe).is_file():
        return str(Path(pg_bin) / exe)
    found = shutil.which(name)
    if not found:
        raise PgToolError(f"{name} bulunamadı. PostgreSQL istemci araçlarını kur veya METIS_PG_BIN ayarla.")
    return found


def _env(parts: dict[str, str]) -> dict[str, str]:
    env = dict(os.environ)
    env.update({"PGHOST": parts["host"], "PGPORT": parts["port"], "PGUSER": parts["user"], "PGDATABASE": parts["dbname"]})
    if parts["password"]:
        env["PGPASSWORD"] = parts["password"]
    return env


def run(name: str, args: list[str], url: str, timeout: int = 3600) -> subprocess.CompletedProcess[str]:
    parts = libpq_parts(url)
    # errors="replace": Türkçe Windows'ta (cp1254) PG araçlarının çıktısında çözülemeyen bayt olursa hata iletisi kaybolmasın.
    proc = subprocess.run([tool(name), *args], env=_env(parts), capture_output=True, text=True, errors="replace", timeout=timeout, check=False)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout).strip().replace(parts["password"] or "\0", "***")[-2000:]
        raise PgToolError(f"{name} başarısız (kod {proc.returncode}): {msg}")
    return proc


def dump(url: str, target: Path) -> None:
    run("pg_dump", ["--format=custom", "--no-owner", "--compress=6", f"--file={target}"], url)


def restore(url: str, source: Path) -> None:
    run("pg_restore", ["--no-owner", "--exit-on-error", "--single-transaction", f"--dbname={libpq_parts(url)['dbname']}", str(source)], url)


def version(name: str) -> str:
    return subprocess.run([tool(name), "--version"], capture_output=True, text=True, errors="replace", check=False).stdout.strip()
