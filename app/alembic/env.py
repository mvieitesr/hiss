import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Alembic Config object
config = context.config

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Ensure repo root and app/ are on sys.path so `import app.app.models` works.
# env.py is at app/alembic/env.py -> two levels up is repo root.
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# repo_root must come before app_dir so `import app.app` resolves to outer `app` + inner `app`
for p in (app_dir, repo_root):
    if p not in sys.path:
        sys.path.insert(0, p)

# Import models' metadata — target for autogenerate and migrations.
from app.app.extensions import db  # noqa: E402
import app.app.models  # noqa: E402, F401 — ensure models are imported

target_metadata = db.metadata


def _to_psycopg_uri(uri: str) -> str:
    if uri.startswith("postgres://"):
        return uri.replace("postgres://", "postgresql+psycopg://", 1)
    if uri.startswith("postgresql://"):
        return uri.replace("postgresql://", "postgresql+psycopg://", 1)
    return uri


def get_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        url = config.get_main_option("sqlalchemy.url") or ""
    url = _to_psycopg_uri(url)
    if not url:
        url = "sqlite:///:memory:"
    return url


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {}) or {}
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
