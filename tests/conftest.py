"""Shared pytest fixtures for meta_harney tests."""

import pytest


@pytest.fixture(autouse=True)
def _isolate_event_loop():
    """Default-on: each test gets a fresh event loop via pytest-asyncio's auto mode."""
    yield
