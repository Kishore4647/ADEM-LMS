from alembic import context

from app import models
from app.core.database import Base, engine

if context.is_offline_mode():
    raise RuntimeError("Run migrations with an active database connection.")
else:
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=Base.metadata, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()
