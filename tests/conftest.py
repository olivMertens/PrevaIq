"""Shared pytest configuration for the test suite."""

from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip integration tests (live PostgreSQL / Azure OpenAI) unless RUN_INTEGRATION_TESTS=1."""
    if os.getenv("RUN_INTEGRATION_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="integration test: set RUN_INTEGRATION_TESTS=1 to run it")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
