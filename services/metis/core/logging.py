"""Yapılandırılmış JSON log, döner dosya. Anahtar/parola asla loglanmaz."""

from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import UTC, datetime
from pathlib import Path

from metis.core.audit import correlation_id

_configured = False
REDACT = ("password", "secret", "api_key", "token", "authorization", "cookie")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "at": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", "") or correlation_id.get(),
        }
        for key, value in record.__dict__.items():
            if key in ("code", "job_id", "worker", "path", "status", "duration_ms", "event"):
                data[key] = value
        for key in list(data):
            if any(r in key.lower() for r in REDACT):
                data[key] = "[redacted]"
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


def configure_logging(log_dir: Path, env: str, name: str = "metis") -> None:
    global _configured
    if _configured:
        return
    _configured = True
    root = logging.getLogger("metis")
    root.setLevel(logging.INFO)
    formatter = JsonFormatter()
    if env != "test":
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            log_dir / f"{name}.log", maxBytes=10 * 1024 * 1024, backupCount=10, encoding="utf-8"
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    stream.setLevel(logging.WARNING if env == "test" else logging.INFO)
    root.addHandler(stream)
