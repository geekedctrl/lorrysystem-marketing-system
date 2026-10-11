from alembic import context
from marketing_backend.db import engine, Base
from marketing_backend import models

with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
