"""
Alembic env.py — connects Alembic to our models and database.

Key changes from the default:
- Imports our Base.metadata so autogenerate can detect our tables
- Reads DB URL from src.config instead of alembic.ini (no hardcoded creds)
- Uses sync_database_url because Alembic runs synchronously
"""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

from src.config import settings
from src.db.models import Base  # noqa: F401 — import triggers model registration

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# This is what Alembic reads to know which tables/columns to create
target_metadata = Base.metadata

# PostGIS ships with tiger geocoder and topology tables — ignore them
EXCLUDE_TABLES = {
    "spatial_ref_sys", "topology", "layer",
    # Tiger geocoder tables
    "tabblock", "tabblock20", "bg", "tract", "faces", "edges", "addr",
    "addrfeat", "featnames", "cousub", "county", "state", "place", "zcta5",
    "zip_lookup", "zip_lookup_all", "zip_lookup_base", "zip_state", "zip_state_loc",
    "county_lookup", "countysub_lookup", "place_lookup", "state_lookup",
    "street_type_lookup", "direction_lookup", "secondary_unit_lookup",
    "loader_lookuptables", "loader_platform", "loader_variables",
    "geocode_settings", "geocode_settings_default",
    "pagc_gaz", "pagc_lex", "pagc_rules",
}


def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table" and name in EXCLUDE_TABLES:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=settings.sync_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(settings.sync_database_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
