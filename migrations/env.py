from abacus import models  # noqa: F401 -- register tables for Alembic metadata
from abacus.config import administrator_database_url
from abacus.db import Base
from alembic import context
from sqlalchemy import create_engine

engine = create_engine(administrator_database_url(), hide_parameters=True)

if context.is_offline_mode():
    context.configure(
        url=engine.url.render_as_string(hide_password=False),
        target_metadata=Base.metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
