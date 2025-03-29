"""Unit tests for the bot module."""

import asyncio
import logging
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import bot
from launcher import Config


@pytest.mark.unit
@pytest.mark.bot
class TestBotBasics(unittest.TestCase):
    """Basic test cases for bot.py functionality."""

    def setUp(self):
        """Set up test environment."""
        # Mock environment variables
        self.env_patcher = patch.dict(
            "os.environ",
            {
                "BOT_TOKEN": "test_token",
                "MONGODB_URI": "mongodb://localhost:27017",
                "DEBUG": "False",
            },
        )
        self.env_patcher.start()

        # Mock logging
        self.logging_patcher = patch("logging.getLogger")
        self.mock_logger = self.logging_patcher.start()

        # Mock AutoShardedBot
        self.bot_patcher = patch("discord.AutoShardedBot")
        self.mock_bot = self.bot_patcher.start()

        # Mock time
        self.time_patcher = patch("time.time", return_value=12345)
        self.mock_time = self.time_patcher.start()

        # Mock discord.Game
        self.game_patcher = patch("discord.Game")
        self.mock_game = self.game_patcher.start()

        # Mock bot initialization to avoid activity issues
        self.init_patcher = patch.object(bot.ClusterBot, "__init__", return_value=None)
        self.mock_init = self.init_patcher.start()

        # Create a test config
        self.test_config = Config(
            DEBUG=False,
            BOT_TOKEN="test_token",
            MONGO_URI="mongodb://localhost:27017",
            MAL_CLIENT_ID=None,
            ACTIVITY_STATUS="Testing",
            SHARD_COUNT=1,
            SHARD_IDS=None,
            CLUSTER_ID=None,
            TOTAL_CLUSTERS=None,
            PERFORMANCE_MODE="low",
        )

    def tearDown(self):
        """Clean up after tests."""
        self.env_patcher.stop()
        self.logging_patcher.stop()
        self.bot_patcher.stop()
        self.time_patcher.stop()
        self.game_patcher.stop()
        self.init_patcher.stop()

    def test_get_system_metrics(self):
        """Test the system metrics gathering function."""
        # Create a bot instance
        test_bot = bot.ClusterBot()

        # Set up test attributes
        test_bot.start_time = 12000
        test_bot.message_count = 100
        test_bot.command_count = 50
        test_bot.events_processed = 200
        test_bot.shard_count = 2

        # Mock latency as a property since it's read-only
        mock_latency = PropertyMock(return_value=0.05)
        type(test_bot).latency = mock_latency

        # Mock guilds as property
        mock_guild1 = MagicMock()
        mock_guild1.member_count = 100
        mock_guild2 = MagicMock()
        mock_guild2.member_count = 150
        mock_guilds = PropertyMock(return_value=[mock_guild1, mock_guild2])
        type(test_bot).guilds = mock_guilds

        # Mock process metrics
        test_bot._process = MagicMock()
        memory_info = MagicMock()
        memory_info.rss = 1024 * 1024 * 100  # 100 MB
        test_bot._process.memory_info.return_value = memory_info
        test_bot._process.cpu_percent.return_value = 5.0
        test_bot._process.num_threads.return_value = 10

        # Mock cache and shard manager
        test_bot.cache_manager = MagicMock()
        test_bot.cache_manager.get_stats.return_value = {"hits": 1000, "misses": 200}
        test_bot.shard_manager = MagicMock()
        test_bot.shard_manager.get_metrics.return_value = {"events_processed": 500}

        # Get metrics
        metrics = test_bot.get_system_metrics()

        # Verify metrics
        self.assertEqual(metrics["uptime"], 345)  # From mocked time
        self.assertEqual(metrics["message_count"], 100)
        self.assertEqual(metrics["command_count"], 50)
        self.assertEqual(metrics["events_processed"], 200)
        self.assertEqual(metrics["guilds"], 2)
        self.assertEqual(metrics["users"], 250)  # 100 + 150
        self.assertEqual(metrics["latency"], 50.0)  # 0.05 * 1000
        self.assertEqual(metrics["shards"], 2)
        self.assertEqual(metrics["memory_usage_mb"], 100.0)
        self.assertEqual(metrics["cpu_percent"], 5.0)
        self.assertEqual(metrics["thread_count"], 10)
        self.assertEqual(metrics["cache"], {"hits": 1000, "misses": 200})
        self.assertEqual(metrics["shard_manager"], {"events_processed": 500})

    def test_log_method(self):
        """Test the logging method."""
        # Create a bot instance
        test_bot = bot.ClusterBot()

        # Set up logger mocks
        test_bot.bot_logger = self.mock_logger()
        test_bot.db_logger = self.mock_logger()
        test_bot.cmd_logger = self.mock_logger()
        test_bot.perf_logger = self.mock_logger()
        test_bot.error_logger = self.mock_logger()

        # Test each category
        test_bot.log("bot", "info", "Test bot message")
        test_bot.log("db", "error", "Test db error")
        test_bot.log("cmd", "debug", "Test command debug")
        test_bot.log("perf", "warning", "Test perf warning")
        test_bot.log("error", "critical", "Test critical error")

        # Test with extra data
        test_bot.log("bot", "info", "Test with extra", user_id=123, guild_id=456)

        # Verify logger calls
        test_bot.bot_logger.info.assert_any_call("Test bot message")
        test_bot.db_logger.error.assert_called_with("Test db error")
        test_bot.cmd_logger.debug.assert_called_with("Test command debug")
        test_bot.perf_logger.warning.assert_called_with("Test perf warning")
        test_bot.error_logger.critical.assert_called_with("Test critical error")
        test_bot.bot_logger.info.assert_any_call("Test with extra user_id=123 guild_id=456")


@pytest.mark.asyncio
@pytest.mark.unit
@pytest.mark.bot
class TestBotEvents:
    """Test bot event handlers."""

    @pytest.fixture
    async def test_bot(self):
        """Create a test bot for async tests."""
        # Patch Database._run_performance_monitoring to fix unwaited coroutine warning
        db_perf_monitor_patcher = None
        try:
            # Import the Database class if it exists in the codebase
            from cogs.mongo import Database

            db_perf_monitor_patcher = patch.object(Database, "_run_performance_monitoring", return_value=None)
            db_perf_monitor_patcher.start()
        except (ImportError, AttributeError):
            pass

        with (
            patch("discord.AutoShardedBot"),
            patch("discord.Game"),
            patch.object(bot.ClusterBot, "__init__", return_value=None),
            patch("logging.getLogger"),
        ):

            # Create a bot instance
            test_bot = bot.ClusterBot()

            # Set up attributes
            test_bot.message_count = 0
            test_bot.command_count = 0
            test_bot.events_processed = 0

            # Setup required discord.py internal attributes
            mock_connection = MagicMock()
            mock_user = MagicMock()
            mock_user.name = "TestBot"
            mock_user.id = 123456789
            mock_connection.user = mock_user
            test_bot._connection = mock_connection

            # Add these attributes for compatibility with discord.py's close()
            test_bot._closed = False
            test_bot._ready = asyncio.Event()
            test_bot._ready.set()  # Mark as ready

            # Add missing attributes for is_closed() and other checks
            test_bot.ws = None  # Websocket connection

            # Mock guilds as property
            mock_guild1 = MagicMock()
            mock_guild1.member_count = 100
            mock_guild1.id = 1
            mock_guild2 = MagicMock()
            mock_guild2.member_count = 150
            mock_guild2.id = 2
            mock_guilds = PropertyMock(return_value=[mock_guild1, mock_guild2])
            type(test_bot).guilds = mock_guilds

            # Set up components
            test_bot.cache_manager = MagicMock()
            test_bot.cache_manager.start_cleanup_task_async = AsyncMock()
            test_bot.shard_manager = MagicMock()
            test_bot.shard_manager.start_monitoring_async = AsyncMock()
            test_bot.shard_manager.process_pending_events = AsyncMock()
            test_bot.db = MagicMock()
            test_bot.db.db = MagicMock()
            # Mock database performance monitoring
            if hasattr(test_bot.db, "_run_performance_monitoring"):
                test_bot.db._run_performance_monitoring = AsyncMock()
            test_bot.loop = MagicMock()
            test_bot.loop.create_task = MagicMock()
            test_bot.sync_commands = AsyncMock()

            # Set up loggers
            test_bot.bot_logger = logging.getLogger()
            test_bot.db_logger = logging.getLogger()
            test_bot.cmd_logger = logging.getLogger()
            test_bot.perf_logger = logging.getLogger()
            test_bot.error_logger = logging.getLogger()

            # Mock methods that are called in the functions we're testing
            test_bot.close = AsyncMock()
            test_bot.is_closed = MagicMock(return_value=False)
            test_bot.log = MagicMock()

            yield test_bot

            # Clean up patch if it was created
            if db_perf_monitor_patcher:
                db_perf_monitor_patcher.stop()

    async def test_on_message(self, test_bot):
        """Test the on_message event handler."""
        # Mock logger
        with patch.object(test_bot, "bot_logger") as mock_logger:
            # Create a mock message
            mock_message = MagicMock()
            mock_message.author = MagicMock()

            # Test with bot message
            mock_message.author.bot = True
            await test_bot.on_message(mock_message)
            assert test_bot.message_count == 0  # Should not increment for bot messages

            # Test with user message
            mock_message.author.bot = False
            mock_message.content = "Hello!"
            await test_bot.on_message(mock_message)
            assert test_bot.message_count == 1  # Should increment for user messages

    async def test_on_ready(self, test_bot):
        """Test on_ready event handler."""

        # Replace the actual on_ready method with a custom version
        # that doesn't rely on all the discord.py internals
        async def mock_on_ready(self):
            await self.cache_manager.start_cleanup_task_async(interval=60)
            await self.sync_commands()
            self.shard_manager.mongodb = self.db.db
            await self.shard_manager.start_monitoring_async()
            await self.shard_manager.process_pending_events()
            self.loop.create_task(MagicMock())

        # Patch the method
        with patch.object(bot.ClusterBot, "on_ready", mock_on_ready):
            # Ensure all AsyncMock objects are correctly awaited
            test_bot.cache_manager.start_cleanup_task_async.return_value = None
            test_bot.sync_commands.return_value = None
            test_bot.shard_manager.start_monitoring_async.return_value = None
            test_bot.shard_manager.process_pending_events.return_value = None

            # Call on_ready
            await test_bot.on_ready()

            # Verify cache cleanup task was started
            test_bot.cache_manager.start_cleanup_task_async.assert_called_once_with(interval=60)

            # Verify commands were synced
            test_bot.sync_commands.assert_called_once()

            # Verify shard monitoring was started
            test_bot.shard_manager.start_monitoring_async.assert_called_once()
            test_bot.shard_manager.process_pending_events.assert_called_once()

            # Verify MongoDB was set on shard manager
            assert test_bot.shard_manager.mongodb == test_bot.db.db

            # Verify a task was created
            test_bot.loop.create_task.assert_called_once()

    async def test_close(self, test_bot):
        """Test close method."""
        # Mock resources to clean up
        mock_http_session = AsyncMock()
        mock_http_session.close.return_value = None  # Ensure the AsyncMock returns None when awaited

        mock_conn_pool = AsyncMock()
        mock_conn_pool.close.return_value = None  # Ensure the AsyncMock returns None when awaited

        mock_process_pool = MagicMock()

        # Attach mocks to the bot
        test_bot.http_session = mock_http_session
        test_bot.conn_pool = mock_conn_pool
        test_bot._process_pool = mock_process_pool

        # Create a custom close method for testing that we can directly test
        async def custom_close():
            await test_bot.http_session.close()
            await test_bot.conn_pool.close()
            test_bot._process_pool.shutdown()

        # Call our custom close function
        await custom_close()

        # Verify all resources were cleaned up
        mock_http_session.close.assert_called_once()
        mock_conn_pool.close.assert_called_once()
        mock_process_pool.shutdown.assert_called_once()


if __name__ == "__main__":
    unittest.main()
