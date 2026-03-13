"""
Async SQLAlchemy engine and session factory.

- pool_size=5: steady-state connections for concurrent batch inserts
- max_overflow=10: burst capacity during heavy ingestion
- expire_on_commit=False: read attributes after commit without extra DB hit
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings

engine = create_async_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=10,
    echo=False,
    connect_args={"prepared_statement_cache_size": 0, "statement_cache_size": 0},
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
