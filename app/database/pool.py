from __future__ import annotations

import time
from typing import Optional

import asyncpg

from .settings import DatabaseSettings

_CONNECT_TIMEOUT_SECONDS = 10
_RETRY_INTERVAL_SECONDS = 30.0

_pool: Optional[asyncpg.Pool] = None
_settings: Optional[DatabaseSettings] = None
_last_attempt_at: Optional[float] = None


async def init_pool(settings: DatabaseSettings) -> asyncpg.Pool:
    global _pool, _settings, _last_attempt_at
    _settings = settings
    async def register_vector_codec(conn):
        try:
            await conn.set_type_codec(
                'vector',
                encoder=lambda v: '[' + ','.join(str(x) for x in v) + ']',
                decoder=lambda s: [float(x) for x in s.strip('[]').split(',')],
                schema='public',
                format='text',
            )
        except Exception:
            pass
    if _pool is None:
        _last_attempt_at = time.monotonic()
        pool = await asyncpg.create_pool(
            host=settings.host,
            port=settings.port,
            database=settings.database,
            user=settings.user,
            password=settings.password,
            ssl=settings.ssl_mode or "require",
            min_size=1,
            max_size=10,
            timeout=_CONNECT_TIMEOUT_SECONDS,
            init=register_vector_codec,
        )
        if _pool is None:
            _pool = pool
        else:
            await pool.close()
    return _pool

async def get_pool() -> asyncpg.Pool:
    """Return the pool, retrying a failed initialization at most every 30 seconds."""
    if _pool is not None:
        return _pool
    if _settings is None:
        raise RuntimeError("Database pool not initialized. Call init_pool() first.")
    if (
        _last_attempt_at is not None
        and time.monotonic() - _last_attempt_at < _RETRY_INTERVAL_SECONDS
    ):
        raise RuntimeError("Database temporarily unavailable.")
    try:
        return await init_pool(_settings)
    except Exception as exc:
        raise RuntimeError("Database temporarily unavailable.") from exc

async def close_pool() -> None:
    """Close the database connection pool."""
    global _pool, _settings, _last_attempt_at
    if _pool is not None:
        await _pool.close()
        _pool = None
    _settings = None
    _last_attempt_at = None
