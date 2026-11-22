from sqlalchemy import create_engine

from alembic import context
from app import models  # noqa: F401  (register tables)
from app.config import get_settings
from app.db import Base, engine_kwargs

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=get_settings().effective_migration_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    url = get_settings().effective_migration_url
    engine = create_engine(url, **engine_kwargs(url))
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
