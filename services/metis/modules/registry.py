"""Tüm modül router'larını tek yerde bağlar."""

from __future__ import annotations

import importlib

from fastapi import FastAPI

MODULES = [
    "system",
    "auth",
    "directory",
    "projects",
    "scopes",
    "sources",
    "knowledge",
    "changes",
    "attachments",
    "search",
    "mentor",
    "jobs",
    "health",
    "map",
    "lab",
    "export",
    "feedback",
    "external",
]


def include_routers(app: FastAPI, prefix: str) -> None:
    for name in MODULES:
        try:
            module = importlib.import_module(f"metis.modules.{name}.router")
        except ModuleNotFoundError as exc:
            if exc.name == f"metis.modules.{name}.router":
                continue  # modül henüz yazılmadı
            raise
        app.include_router(module.router, prefix=prefix)
