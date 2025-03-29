"""Pytest configuration for Quantum Bank Discord bot tests."""

import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture
def mock_env():
    """Mock environment variables for testing."""
    with patch.dict(
        "os.environ",
        {
            "BOT_TOKEN": "test_token",
            "MONGODB_URI": "mongodb://localhost:27017",
            "MONGODB_DB_NAME": "test_db",
            "DEBUG_MODE": "False",
            "PERFORMANCE_MODE": "LOW",
            "SHARD_COUNT": "1",
            "CLUSTER_ID": "0",
        },
    ):
        yield


@pytest.fixture(scope="session")
def event_loop_policy():
    """Configure the event loop policy for tests."""
    policy = asyncio.get_event_loop_policy()
    return policy


# Set asyncio_mode to "auto" to use the fixture's event loop
pytest_plugins = ["pytest_asyncio"]
asyncio_mode = "auto"


@pytest.fixture
def mock_bot():
    """Create a mock bot instance for testing."""
    mock = MagicMock()
    mock.config = MagicMock()
    mock.config.MONGO_URI = "mongodb://localhost:27017"
    mock.config.MONGO_DB_NAME = "banking_bot"
    # Use get_running_loop instead of get_event_loop
    mock.loop = asyncio.get_running_loop()
    return mock


@pytest.fixture
def mock_ctx():
    """Create a mock Discord context for command testing."""
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 987654321
    ctx.guild.name = "Test Server"
    ctx.author = MagicMock()
    ctx.author.id = 111222333
    ctx.author.name = "Test User"
    ctx.channel = MagicMock()
    ctx.channel.id = 444555666
    ctx.channel.send = MagicMock()
    return ctx
