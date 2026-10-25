"""Worker süreci: N genel slot + 1 ayrı benchmark slotu (benchmark hazırlığı bloke etmez) + bakım zamanlayıcısı.

Öncelik: kullanıcı etkileşimli işler (prepare/refine) > havuz denetimi > bakım > benchmark.
Mentor sorguları API süreçlerinde çalışır ve kuyruğa hiç girmez (her zaman önce).
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import threading
import time
import uuid

from metis.core.config import get_settings
from metis.core.db import transaction
from metis.core.logging import configure_logging
from metis.worker.runtime import AwaitInput, BudgetExceeded, JobContext, JobFailed, LeaseLost, claim

log = logging.getLogger("metis.worker")
_stop = threading.Event()


def run_job(ctx: JobContext) -> None:
    try:
        if ctx.kind == "prepare_draft":
            from metis.worker.prepare import run_prepare

            run_prepare(ctx)
        elif ctx.kind == "refine_draft":
            from metis.worker.refine import run_refine

            run_refine(ctx)
        elif ctx.kind in ("audit_pool", "maintenance"):
            from metis.modules.health.maintenance import run_maintenance_job

            run_maintenance_job(ctx)
        elif ctx.kind == "benchmark":
            run_benchmark_job(ctx)
        else:
            ctx.finish("failed", "Bilinmeyen görev türü.", error_code="UNKNOWN_KIND")
    except LeaseLost:
        log.warning("lease lost", extra={"job_id": str(ctx.job_id)})
    except AwaitInput as exc:
        questions = exc.questions
        _safe(ctx, "await", questions=questions)
    except BudgetExceeded as exc:
        _safe(ctx, "finish", state="budget_exceeded", summary="Görev bütçesi aşıldı; kısmi sonuçlar korunuyor. Kaynakları daraltıp yeniden dene.", error_code=f"BUDGET_{str(exc).upper()}")
    except JobFailed as exc:
        _safe(ctx, "finish", state="failed", summary=exc.summary, error_code=exc.code)
    except Exception:  # noqa: BLE001
        log.exception("job crashed", extra={"job_id": str(ctx.job_id)})
        _safe(ctx, "finish", state="failed", summary="Beklenmeyen bir hata oldu; yeniden deneyebilirsin.", error_code="INTERNAL")


def _safe(ctx: JobContext, action: str, **kw: object) -> None:
    try:
        if action == "await":
            ctx.await_input(kw["questions"])  # type: ignore[arg-type]
        else:
            ctx.finish(kw["state"], kw["summary"], error_code=kw.get("error_code"))  # type: ignore[arg-type]
    except LeaseLost:
        log.warning("lease lost before finish", extra={"job_id": str(ctx.job_id)})


def run_benchmark_job(ctx: JobContext) -> None:
    from metis.modules.lab.service import execute_benchmark

    with transaction() as db:
        job = ctx.guard(db)
        run_id = uuid.UUID(job.inputs["run_id"])

    def should_stop() -> bool:
        try:
            with transaction() as db:
                ctx.guard(db)
            return False
        except LeaseLost:
            return True

    metrics = execute_benchmark(run_id, should_stop)
    if metrics.get("skipped"):
        ctx.finish("completed", "Benchmark zaten tamamlanmış.")
        return
    ctx.finish("completed", f"Benchmark tamamlandı: {metrics['passed']}/{metrics['n']} geçti, kritik hata {metrics['critical_errors']}.", report={"metrics": metrics})


def slot_loop(worker_id: str, benchmark: bool, once: bool = False, idle: float = 1.0) -> int:
    done = 0
    while not _stop.is_set():
        try:
            ctx = claim(worker_id, benchmark)
        except Exception:  # noqa: BLE001
            log.exception("claim failed")
            ctx = None
        if ctx is None:
            if once:
                return done
            _stop.wait(idle)
            continue
        run_job(ctx)
        done += 1
    return done


def scheduler_loop(interval: float = 60.0) -> None:
    from metis.modules.health.maintenance import schedule_due_jobs

    while not _stop.is_set():
        try:
            schedule_due_jobs()
        except Exception:  # noqa: BLE001
            log.exception("scheduler tick failed")
        _stop.wait(interval)


def embed_loop(idle: float = 20.0) -> None:
    """Vektör kanalı (2026-10-25): model kuruluysa vektörü olmayan blokları sırayla hesaplar; iş yoksa bekler."""
    from metis.core.db import transaction
    from metis.modules.search.vectors import embed_missing

    while not _stop.is_set():
        try:
            with transaction() as db:
                n = embed_missing(db, limit=64)
        except Exception:  # noqa: BLE001
            log.exception("embedding tick failed")
            n = 0
        if n:
            log.info("passages embedded", extra={"event": n})
        _stop.wait(0.1 if n else idle)


def run_forever(slots: int = 2, once: bool = False) -> None:
    settings = get_settings()
    configure_logging(settings.log_dir, settings.env, name="metis-worker")
    base = f"{socket.gethostname()}:{os.getpid()}"
    if once:
        n = slot_loop(f"{base}:0", benchmark=False, once=True) + slot_loop(f"{base}:b", benchmark=True, once=True)
        log.info("worker once finished", extra={"event": n})
        return
    signal.signal(signal.SIGTERM, lambda *_: _stop.set())
    signal.signal(signal.SIGINT, lambda *_: _stop.set())
    threads = [threading.Thread(target=slot_loop, args=(f"{base}:{i}", False), daemon=True) for i in range(max(1, slots))]
    threads.append(threading.Thread(target=slot_loop, args=(f"{base}:b", True), daemon=True))
    threads.append(threading.Thread(target=scheduler_loop, daemon=True))
    threads.append(threading.Thread(target=embed_loop, daemon=True))
    for t in threads:
        t.start()
    log.info("worker started", extra={"event": f"slots={slots}"})
    while not _stop.is_set():
        time.sleep(0.5)
    for t in threads:
        t.join(timeout=15)
