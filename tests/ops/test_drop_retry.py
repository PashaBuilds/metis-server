"""Geri yükleme tatbikatının geçici veritabanı silinirken o anda bağlı bir arka plan süreci (ör. autovacuum) olabilir;
süper kullanıcı olmayan rol onu sonlandıramaz ("permission denied to terminate process"). Süreç kısa sürede biter:
silme yeniden denenir (2026-10-19, yerel derlemede ve testte görüldü)."""

from __future__ import annotations

import psycopg
import pytest


class _Conn:
    def __init__(self, calls: list[str], fail: int) -> None:
        self.calls, self.fail = calls, fail

    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, *exc) -> None:  # noqa: ANN002
        return None

    def execute(self, sql: str) -> None:
        self.calls.append(sql)
        if len(self.calls) <= self.fail:
            raise psycopg.errors.InsufficientPrivilege("permission denied to terminate process")


def test_drop_database_retries_until_background_process_ends(monkeypatch):  # noqa: ANN001
    from metis.ops import backup

    calls: list[str] = []
    monkeypatch.setattr(backup.psycopg, "connect", lambda *a, **k: _Conn(calls, fail=2))
    monkeypatch.setattr(backup.time, "sleep", lambda s: None)
    backup.drop_database("postgresql://kurgu@127.0.0.1/postgres", "metis_rehearsal_x")
    assert calls == ['DROP DATABASE IF EXISTS "metis_rehearsal_x" WITH (FORCE)'] * 3


def test_drop_database_gives_up_after_attempts(monkeypatch):  # noqa: ANN001
    from metis.ops import backup

    calls: list[str] = []
    monkeypatch.setattr(backup.psycopg, "connect", lambda *a, **k: _Conn(calls, fail=99))
    monkeypatch.setattr(backup.time, "sleep", lambda s: None)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        backup.drop_database("postgresql://kurgu@127.0.0.1/postgres", "metis_rehearsal_x", attempts=3)
    assert len(calls) == 3
