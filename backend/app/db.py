"""PostGIS connection pool."""
import asyncio
import os

import asyncpg

_pool: asyncpg.Pool | None = None

# The app can boot before Postgres is accepting TCP connections — on a cold
# `docker compose up`, and on Fly when both machines start together. Postgres
# also drops early connections when it restarts at the end of first-boot init,
# so retry rather than exiting and relying on the supervisor.
_CONNECT_ATTEMPTS = 12
_CONNECT_BACKOFF = 2.0


async def connect() -> asyncpg.Pool:
    global _pool
    dsn = os.environ.get("DATABASE_URL", "postgresql://map:map@localhost:5432/map")
    for attempt in range(1, _CONNECT_ATTEMPTS + 1):
        try:
            _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
            return _pool
        except (OSError, ConnectionError, asyncpg.PostgresError) as exc:
            if attempt == _CONNECT_ATTEMPTS:
                raise
            print(f"DB not ready ({exc.__class__.__name__}: {exc}); "
                  f"retry {attempt}/{_CONNECT_ATTEMPTS - 1} in {_CONNECT_BACKOFF}s",
                  flush=True)
            await asyncio.sleep(_CONNECT_BACKOFF)
    raise RuntimeError("unreachable")


async def disconnect() -> None:
    if _pool is not None:
        await _pool.close()


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call connect() first")
    return _pool
