from abacus import models  # noqa: F401 -- register tables for Alembic metadata
from abacus.db import Base, engine
from alembic import context

if context.is_offline_mode():
    context.configure(
        url=str(engine.url), target_metadata=Base.metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
