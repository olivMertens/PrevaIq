from __future__ import annotations

import asyncio
import importlib
import sys
import time

from ..config import Settings
from ..utils import setup_logging

logger = setup_logging()


async def warmup_chat(settings: Settings) -> dict[str, float] | None:
    if not settings.openai.endpoint:
        logger.warning("Chat runtime not initialized: OpenAI endpoint is not configured")
        return None
    started = time.perf_counter()
    module = await asyncio.to_thread(importlib.import_module, "app.agents.agents")
    imports_ms = round((time.perf_counter() - started) * 1000, 1)
    try:
        timings = await module.initialize_chat_runtime(settings)
    except BaseException:
        await module.close_chat_runtime()
        raise
    timings["imports_ms"] = imports_ms
    timings["total_ms"] = round((time.perf_counter() - started) * 1000, 1)
    logger.info("Chat runtime ready: timings_ms=%s", timings)
    return timings


async def shutdown_chat() -> None:
    module = sys.modules.get("app.agents.agents")
    if module is not None:
        await module.close_chat_runtime()