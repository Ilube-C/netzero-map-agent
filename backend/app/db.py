"""PostGIS connection pool."""
import os

import asyncpg

_pool: asyncpg.Pool | None = None


async def connect() -> asyncpg.Pool:
    global _pool
    dsn = os.environ.get("DATABASE_URL", "postgresql://map:map@localhost:5432/map")
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
    return _pool


async def disconnect() -> None:
    if _pool is not None:
        await _pool.close()


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call connect() first")
    return _pool
