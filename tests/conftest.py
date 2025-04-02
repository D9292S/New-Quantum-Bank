"""Pytest configuration for Quantum Superbot Discord bot tests."""

import asyncio
import os
import sys
import warnings
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Filter out AsyncMockMixin warnings globally
warnings.filterwarnings("ignore", message="coroutine '.*' was never awaited", 
                        category=RuntimeWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning, module="unittest.mock")
# Suppress sys:1 warning about coroutines
warnings.filterwarnings("ignore", category=RuntimeWarning)

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture
def mock_env():
    """Mock environment variables for testing."""
    with patch.dict(
        "os.environ",
        {
            "BOT_TOKEN": "test_token",
            "MONGODB_URI": os.environ.get(
                "MONGODB_URI",
                "mongodb+srv://ci-user:ci-password@placeholder-cluster.mongodb.net/"
                "quantum_test?retryWrites=true&w=majority"
            ),
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
    if sys.platform.startswith("win"):
        # On Windows, use the selector event loop policy for better performance
        policy = asyncio.WindowsSelectorEventLoopPolicy()
        asyncio.set_event_loop_policy(policy)
    else:
        # On other platforms, use the default policy
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
    # Use MongoDB Atlas connection from environment or default to a placeholder
    mock.config.MONGO_URI = os.environ.get(
        "MONGODB_URI",
        "mongodb+srv://ci-user:ci-password@placeholder-cluster.mongodb.net/"
        "quantum_test?retryWrites=true&w=majority"
    )
    mock.config.MONGO_DB_NAME = "superbot_test"
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


@pytest.fixture(scope="session", autouse=True)
def patch_performance_monitoring():
    """
    Patch the Database._run_performance_monitoring method to prevent unwaited coroutines.
    This is a session-wide patch that applies to all tests.
    """
    patchers = []

    try:
        # Import and patch the method in cogs.mongo module if it exists
        from cogs.mongo import Database

        patcher = patch.object(Database, "_run_performance_monitoring", return_value=None)
        patcher.start()
        patchers.append(patcher)
    except (ImportError, AttributeError):
        pass

    # Yield control to allow tests to run
    yield

    # Stop all started patchers
    for patcher in patchers:
        patcher.stop()


@pytest.fixture
def mock_mongo_db():
    """Create a mock MongoDB database object."""
    mock_db = MagicMock()

    # Setup collections
    mock_db.users = MagicMock()
    mock_db.accounts = MagicMock()
    mock_db.transactions = MagicMock()
    mock_db.loans = MagicMock()
    mock_db.stats = MagicMock()
    mock_db.guild_settings = MagicMock()

    # Setup common query methods
    for collection_name in [
        "users",
        "accounts",
        "transactions",
        "loans",
        "stats",
        "guild_settings",
    ]:
        collection = getattr(mock_db, collection_name)

        # Setup async methods with AsyncMock
        for method_name in ["find_one", "insert_one", "update_one", "delete_one", "aggregate"]:
            setattr(collection, method_name, AsyncMock())

        # Setup find with cursor
        collection.find = MagicMock()
        collection.find.return_value.to_list = AsyncMock(return_value=[])

    return mock_db


@pytest.fixture
def mock_db_client(mock_mongo_db):
    """Create a mock MongoDB client."""
    client = MagicMock()
    client.__getitem__.return_value = mock_mongo_db
    return client


@pytest.fixture
def mongo_uri():
    """Get MongoDB URI from environment or use default test value."""
    # Use MongoDB Atlas connection instead of localhost
    return os.environ.get(
        "MONGODB_URI",
        "mongodb+srv://ci-user:ci-password@placeholder-cluster.mongodb.net/"
        "quantum_test?retryWrites=true&w=majority"
    )
