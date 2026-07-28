from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from play_api.main import app


@pytest.fixture
def start_play_client() -> Iterator[Callable[[], TestClient]]:
    """Start lifespan after each test has installed its environment overrides."""

    clients: list[TestClient] = []

    def start() -> TestClient:
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield start

    for client in reversed(clients):
        client.__exit__(None, None, None)
