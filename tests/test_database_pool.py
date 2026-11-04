from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.database import pool as pool_module
from app.database.settings import DatabaseSettings


class _FakePool:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _reset_pool_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pool_module, "_pool", None)
    monkeypatch.setattr(pool_module, "_settings", None)
    monkeypatch.setattr(pool_module, "_last_attempt_at", None)


def _database_settings() -> DatabaseSettings:
    return DatabaseSettings(
        backend="postgresql", host="db.example.test", port=5432, database="demo", user="demo"
    )


def _patch_clock(monkeypatch: pytest.MonkeyPatch, clock: dict[str, float]) -> None:
    monkeypatch.setattr(pool_module, "time", SimpleNamespace(monotonic=lambda: clock["now"]))


def test_get_pool_requires_initialization() -> None:
    with pytest.raises(RuntimeError, match="not initialized"):
        asyncio.run(pool_module.get_pool())


def test_pool_recovers_after_database_becomes_available(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 100.0}
    _patch_clock(monkeypatch, clock)
    fake_pool = _FakePool()
    calls: list[dict[str, object]] = []

    async def create_pool(**kwargs: object) -> _FakePool:
        calls.append(kwargs)
        if len(calls) == 1:
            raise TimeoutError("database stopped")
        return fake_pool

    monkeypatch.setattr(pool_module, "asyncpg", SimpleNamespace(create_pool=create_pool))

    with pytest.raises(TimeoutError):
        asyncio.run(pool_module.init_pool(_database_settings()))
    assert calls[0]["timeout"] == pool_module._CONNECT_TIMEOUT_SECONDS

    clock["now"] = 110.0
    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        asyncio.run(pool_module.get_pool())
    assert len(calls) == 1

    clock["now"] = 131.0
    assert asyncio.run(pool_module.get_pool()) is fake_pool
    assert asyncio.run(pool_module.get_pool()) is fake_pool
    assert len(calls) == 2


def test_failed_recovery_is_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 100.0}
    _patch_clock(monkeypatch, clock)
    calls = 0

    async def create_pool(**_: object) -> _FakePool:
        nonlocal calls
        calls += 1
        raise TimeoutError("database stopped")

    monkeypatch.setattr(pool_module, "asyncpg", SimpleNamespace(create_pool=create_pool))
    with pytest.raises(TimeoutError):
        asyncio.run(pool_module.init_pool(_database_settings()))

    clock["now"] = 140.0
    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        asyncio.run(pool_module.get_pool())
    clock["now"] = 150.0
    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        asyncio.run(pool_module.get_pool())
    assert calls == 2


def test_close_pool_resets_recovery_state(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_pool = _FakePool()

    async def create_pool(**_: object) -> _FakePool:
        return fake_pool

    monkeypatch.setattr(pool_module, "asyncpg", SimpleNamespace(create_pool=create_pool))
    asyncio.run(pool_module.init_pool(_database_settings()))
    asyncio.run(pool_module.close_pool())

    assert fake_pool.closed
    with pytest.raises(RuntimeError, match="not initialized"):
        asyncio.run(pool_module.get_pool())
