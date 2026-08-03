# LexChiapas migration policy (see also alembic/README):
#
# - This project never used Alembic before the "baseline schema real"
#   revision. Every column/table that exists in the real DB before that
#   revision was added by hand (ALTER TABLE ... ADD COLUMN IF NOT EXISTS /
#   CREATE TABLE IF NOT EXISTS) with no script left in the repo. The
#   baseline revision documents that starting state; it must NOT be run
#   with `alembic upgrade head` against a fresh/empty DB (it does not
#   create tables) -- it exists only so `alembic stamp head` can mark an
#   already-populated real DB as "up to date" and so future diffs are
#   computed against a known point.
# - From now on: change a model in app/models/*.py, then run
#   `alembic revision --autogenerate -m "..."`, READ the generated diff by
#   hand (autogenerate is not perfect, especially around pgvector's
#   `vector` type and JSONB defaults), and only then `alembic upgrade head`.
#   Do not go back to manual ALTER TABLE statements.
# - database_url always comes from app.config.get_settings() (same .env /
#   DATABASE_URL as app/database.py) -- never hardcode a DB URL/credentials
#   in alembic.ini or here.

from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Make sure "app" is importable when alembic is invoked from the lexchiapas/
# project root (alembic.ini has prepend_sys_path = . which already covers
# this, but importing here explicitly fails loudly and early if cwd is wrong
# instead of silently using the placeholder URL from alembic.ini).
from app.config import get_settings
from app.database import Base
import app.models  # noqa: F401 -- registers all model classes on Base.metadata

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url from the real app settings (DATABASE_URL in .env),
# instead of whatever is (or isn't) in alembic.ini.
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


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
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
