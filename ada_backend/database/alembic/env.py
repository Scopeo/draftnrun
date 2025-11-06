from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from settings import settings
from ada_backend.database.models import Base
from ada_backend.database import trace_models  # noqa: F401  # Import to register trace models with Base.metadata
from ada_backend.database.setup_db import get_db_url

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
config.set_main_option("sqlalchemy.url", get_db_url())
is_sqlite = settings.ADA_DB_DRIVER == "sqlite"

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


# Define a custom include_object function to ignore NUMERIC to UUID changes in SQLite
def include_object(object, name, type_, reflected, compare_to):
    """
    Custom filter function to determine which database objects should be included in migrations.

    This function specifically excludes UUID to NUMERIC type changes in SQLite databases,
    which are false positives due to SQLite's limited type system.
    """
    if type_ == "column" and is_sqlite:
        # Check if this is a UUID to NUMERIC change (or vice versa)
        if (
            isinstance(object.type, postgresql.UUID)
            and hasattr(compare_to, "type")
            and isinstance(compare_to.type, sa.NUMERIC)
        ):
            # Exclude UUID to NUMERIC type changes in SQLite
            return False

    # Ignore APScheduler tables - they are managed by APScheduler itself
    if type_ == "table" and name == "apscheduler_jobs":
        return False

    # Exclude tables in test schema
    if type_ == "table" and str(object.schema) == "test_schema":
        return False
    # Exclude test schemas themselves
    if type_ == "schema" and name == "test_schema":
        return False

    return True  # Include all other objects


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,  # Add the custom include_object function
        # Enable reflection of non-public schemas
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = context.config.attributes.get("connection", None)
    if connectable is None:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,  # Add the custom include_object function
            # Enable reflection of non-public schemas
            include_schemas=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
