"""Alembic ortamı. Migration'lar yalnız sahip (owner) rolüyle çalışır."""

from alembic import context
from sqlalchemy import create_engine, pool

from metis.core import models  # noqa: F401  (metadata kaydı)
from metis.core.config import get_settings
from metis.core.db import Base

target_metadata = Base.metadata


def run_migrations_online() -> None:
    url = context.config.attributes.get("url") or get_settings().owner_database_url
    connectable = create_engine(url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
