"""Ölçek: okunabilirlik süzgeci büyük projede de çalışır (bağımsız inceleme bulgusu, 2026-10-26)."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from metis.core.access import unreadable_revisions
from metis.core.db import transaction
from metis.core.models import User


def test_unreadable_revisions_handles_more_ids_than_bind_parameters(team):  # noqa: ANN001
    """On binlerce revizyonlu projede sorgu PostgreSQL'in parametre sınırına (65535) takılmamalı."""
    ids = [uuid.uuid4() for _ in range(40_000)]
    with transaction() as db:
        user = db.scalars(select(User).where(User.username == "okan")).one()
        assert unreadable_revisions(db, user, uuid.UUID(team["pid"]), ids) == set()
