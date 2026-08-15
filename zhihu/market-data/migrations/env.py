from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from market_data.db import CoreBase, RawBase, StagingBase
from market_data.models import core, raw, staging  # noqa: F401


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

DOMAIN_CONFIG = {
    "staging": (StagingBase.metadata, "MARKET_STAGING_DATABASE_URL"),
    "raw": (RawBase.metadata, "MARKET_RAW_DATABASE_URL"),
    "core": (CoreBase.metadata, "MARKET_CORE_DATABASE_URL"),
}


def selected_domain() -> str:
    domain = context.get_x_argument(as_dictionary=True).get("domain")
    if domain not in DOMAIN_CONFIG:
        raise RuntimeError("Alembic requires -x domain=staging|raw|core")
    return domain


domain = selected_domain()
target_metadata, url_env_name = DOMAIN_CONFIG[domain]
database_url = os.getenv(url_env_name)
if not database_url:
    raise RuntimeError(f"{url_env_name} must be set; domains never share an implicit database")
config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=f"alembic_version_{domain}",
    )
    with context.begin_transaction():
        context.run_migrations(domain=domain)


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            version_table=f"alembic_version_{domain}",
        )
        with context.begin_transaction():
            context.run_migrations(domain=domain)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
