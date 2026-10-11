"""Faz 10: yedek → boş DB'ye geri yükleme turu, tatbikat, doctor (izole PG + gerçek pg_dump/pg_restore)."""

from __future__ import annotations

import json
import uuid
import zipfile
from pathlib import Path

import psycopg
import pytest

from metis.core.config import get_settings
from metis.ops import backup as ops
from metis.ops.doctor import run_doctor
from metis.ops.pgtools import with_dbname
from tests.conftest import ADMIN_DSN
from tests.kb import publish_note


@pytest.fixture
def populated(team) -> dict:  # noqa: ANN001
    page = publish_note(team["contributor"], team["reviewer"], team["pid"], "UART hızı", "UART hata ayıklama hızı 115200 baud olarak ayarlanır.")
    return {**team, "page": page}


@pytest.fixture
def empty_db():  # noqa: ANN201
    name = f"metis_restore_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    yield with_dbname(get_settings().owner_database_url, name)
    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def test_backup_restore_roundtrip_into_empty_db(populated, empty_db, tmp_path: Path) -> None:  # noqa: ANN001
    result = ops.create_backup(tmp_path / "y.zip")
    assert result["ok"] and result["blobs"] >= 1 and result["rows"] > 0
    marker = json.loads((get_settings().data_dir / "backups" / "last-backup.json").read_text(encoding="utf-8"))
    assert marker["sha256"] == result["sha256"]
    with zipfile.ZipFile(tmp_path / "y.zip") as z:
        manifest = json.loads(z.read("manifest.json"))
        assert "master_key" not in json.dumps(manifest).replace("master_key_fingerprint", "")
    with pytest.raises(FileExistsError):
        ops.create_backup(tmp_path / "y.zip")  # üzerine yazılmaz
    data_dir = tmp_path / "restored-data"
    out = ops.restore_backup(tmp_path / "y.zip", database_url=empty_db, data_dir=data_dir)
    assert out["ok"], out
    assert out["rows"] == result["rows"]
    with psycopg.connect(empty_db.replace("+psycopg", "")) as conn:
        titles = [r[0] for r in conn.execute("SELECT title FROM page_revisions")]
        assert "UART hızı" in titles
        # değişmezlik trigger'ı geri yüklenen DB'de de çalışıyor
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute("UPDATE page_revisions SET title='x'")
    assert len(list((data_dir / "blobs").glob("??/*"))) == result["blobs"]
    # ikinci geri yükleme: hedef artık boş değil
    again = ops.restore_backup(tmp_path / "y.zip", database_url=empty_db, data_dir=data_dir)
    assert again == {"ok": False, "code": "TARGET_NOT_EMPTY", "message": again["message"]}


def test_rehearsal_restores_verifies_and_drops(populated, tmp_path: Path) -> None:  # noqa: ANN001
    ops.create_backup(tmp_path / "y.zip")
    out = ops.rehearse_restore(tmp_path / "y.zip")
    assert out["ok"], out
    assert out["mode"] == "rehearsal" and out["source_files"] >= 1
    with psycopg.connect(ADMIN_DSN) as conn:
        left = conn.execute("SELECT count(*) FROM pg_database WHERE datname LIKE 'metis_rehearsal_%'").fetchone()[0]
    assert left == 0


def _tamper(src: Path, dst: Path, name: str, data: bytes | None) -> None:
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for item in zin.infolist():
            if item.filename == name:
                if data is not None:
                    zout.writestr(name, data)
                continue
            zout.writestr(item, zin.read(item))


def test_tampered_archives_are_refused(populated, tmp_path: Path, empty_db) -> None:  # noqa: ANN001
    ops.create_backup(tmp_path / "y.zip")
    with zipfile.ZipFile(tmp_path / "y.zip") as z:
        blob = next(n for n in z.namelist() if n.startswith("blobs/"))
    _tamper(tmp_path / "y.zip", tmp_path / "a.zip", blob, b"degisti")
    assert ops.rehearse_restore(tmp_path / "a.zip")["code"] == "HASH_MISMATCH"
    _tamper(tmp_path / "y.zip", tmp_path / "b.zip", blob, None)
    assert ops.rehearse_restore(tmp_path / "b.zip")["code"] == "MISSING_BLOB"
    _tamper(tmp_path / "y.zip", tmp_path / "c.zip", "db.dump", b"PGDMP-bozuk")
    assert ops.restore_backup(tmp_path / "c.zip", database_url=empty_db)["code"] == "HASH_MISMATCH"
    (tmp_path / "d.zip").write_bytes(b"zip degil")
    assert ops.rehearse_restore(tmp_path / "d.zip")["code"] == "CORRUPT"
    # hedef DB'ye hiçbir şey yazılmadı
    with psycopg.connect(empty_db.replace("+psycopg", "")) as conn:
        assert conn.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0] == 0


def test_restore_refuses_other_master_key(populated, tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    ops.create_backup(tmp_path / "y.zip")
    monkeypatch.setattr(ops, "key_fingerprint", lambda: "0" * 64)
    out = ops.rehearse_restore(tmp_path / "y.zip")
    assert out["code"] == "KEY_MISMATCH"


def test_prune_keeps_newest(tmp_path: Path) -> None:
    d = get_settings().data_dir / "backups"
    d.mkdir(parents=True, exist_ok=True)
    for name in ("metis-backup-20200101-000000.zip", "metis-backup-20200102-000000.zip"):
        (d / name).write_bytes(b"x")
    removed = ops.prune_backups(30)
    assert removed == ["metis-backup-20200101-000000.zip"]
    assert (d / "metis-backup-20200102-000000.zip").exists()
    (d / "metis-backup-20200102-000000.zip").unlink()


def test_doctor_reports_checks_without_secrets(populated, tmp_path: Path) -> None:  # noqa: ANN001
    static = get_settings().static_dir
    static.mkdir(parents=True, exist_ok=True)
    (static / "index.html").write_text("<!doctype html>", encoding="utf-8")
    report = run_doctor()
    by = {c["name"]: c for c in report["checks"]}
    assert report["ready"] is True, report
    assert by["Şema sürümü"]["ok"] and by["Kaynak dosyaları bütünlüğü"]["ok"]
    assert "metis-dev" not in json.dumps(report)  # DB parolası çıktıda yok
    # eksik blob kritik hata olarak raporlanır
    for p in get_settings().blob_dir.glob("??/*"):
        p.rename(p.with_suffix(".moved"))
    report = run_doctor()
    assert report["ready"] is False
    assert not {c["name"]: c for c in report["checks"]}["Kaynak dosyaları bütünlüğü"]["ok"]
    for p in get_settings().blob_dir.glob("??/*.moved"):
        p.rename(p.with_suffix(""))
