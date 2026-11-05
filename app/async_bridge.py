"""Run coroutines on the API server's event loop from worker threads.

The asyncpg pool belongs to the loop that created it (the FastAPI server loop). Code that
runs in worker threads (fraud orchestrators, Agent Framework sync tools) cannot await on
that pool from its own loop, so it hands the coroutine to the server loop and waits.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Coroutine, Optional, TypeVar

T = TypeVar("T")

_server_loop: Optional[asyncio.AbstractEventLoop] = None


class ServerLoopUnavailable(RuntimeError):
    """No usable server loop: not registered, stopped, or this thread would block it."""


def register_server_loop(loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
    """Record the server loop (call from a FastAPI startup handler)."""
    global _server_loop
    _server_loop = loop or asyncio.get_running_loop()


def is_server_loop(loop: Optional[asyncio.AbstractEventLoop]) -> bool:
    return loop is not None and loop is _server_loop


def server_loop_available() -> bool:
    """True when a coroutine can be handed to the server loop from this thread."""
    loop = _server_loop
    if loop is None or loop.is_closed() or not loop.is_running():
        return False
    try:
        return asyncio.get_running_loop() is not loop
    except RuntimeError:
        return True


def run_on_server_loop(coro: Coroutine[Any, Any, T], timeout: float) -> T:
    """Run ``coro`` on the server loop and wait for its result from this thread.

    Raises ServerLoopUnavailable when there is no running server loop, or when called from
    the server loop's own thread (waiting there would deadlock). Raises TimeoutError after
    ``timeout`` seconds (the coroutine is cancelled).
    """
    loop = _server_loop
    try:
        current = asyncio.get_running_loop()
    except RuntimeError:
        current = None
    if loop is None or loop.is_closed() or not loop.is_running() or current is loop:
        coro.close()
        raise ServerLoopUnavailable("server event loop not available from this thread")
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(timeout)
    except concurrent.futures.TimeoutError as exc:
        future.cancel()
        raise TimeoutError(f"server loop call exceeded {timeout:.0f}s") from exc
