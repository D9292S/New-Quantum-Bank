"""Pytest configuration for Quantum Bank Discord bot tests."""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

@pytest.fixture
def mock_env():
    """Mock environment variables for testing."""
    with patch.dict('os.environ', {
        'BOT_TOKEN': 'test_token',
        'MONGODB_URI': 'mongodb://localhost:27017',
        'MONGODB_DB_NAME': 'test_db',
        'DEBUG_MODE': 'False',
        'PERFORMANCE_MODE': 'LOW',
        'SHARD_COUNT': '1',
        'CLUSTER_ID': '0'
    }):
        yield

@pytest.fixture
def mock_bot():
    """Create a mock Discord bot for testing."""
    bot = MagicMock()
    bot.loop = MagicMock()
    bot.user = MagicMock()
    bot.user.name = "Quantum Bank"
    bot.user.id = 123456789
    return bot

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