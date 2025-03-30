import asyncio
import os
import sys
import unittest
from unittest import mock

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


@pytest.mark.integration
@pytest.mark.database
class TestMongoDBConnection(unittest.TestCase):
    """Integration tests for MongoDB connection functionality."""

    def setUp(self):
        """Set up test environment."""
        # Mock environment variables
        self.env_patcher = mock.patch.dict(
            "os.environ", {"MONGODB_URI": "mongodb://localhost:27017", "MONGODB_DB_NAME": "test_db"}
        )
        self.env_patcher.start()

        # Import modules after environment setup
        from cogs.mongo import Database

        self.mongo_class = Database

        # Create a mock bot with config
        self.mock_bot = mock.MagicMock()
        self.mock_bot.config = mock.MagicMock()
        self.mock_bot.config.MONGO_URI = "mongodb://localhost:27017"

        # Create a new event loop for testing (not get_event_loop)
        self.loop = asyncio.new_event_loop()
        self.mock_bot.loop = self.loop

        # Create a patch for the performance monitoring coroutine
        self.perf_monitor_patcher = mock.patch.object(
            Database, "_run_performance_monitoring", new_callable=mock.AsyncMock
        )
        self.perf_monitor_mock = self.perf_monitor_patcher.start()

    def tearDown(self):
        """Clean up after tests."""
        self.env_patcher.stop()
        self.perf_monitor_patcher.stop()
        self.loop.close()

    def test_mongodb_instance_creation(self):
        """Test that MongoDB class can be instantiated."""
        mongodb = self.mongo_class(self.mock_bot)
        self.assertIsNotNone(mongodb)

    @unittest.skip("Skip actual connection test unless running with real MongoDB")
    def test_mongodb_connection(self):
        """Test actual connection to MongoDB (requires running MongoDB instance)."""
        # This test is skipped by default because it requires a real MongoDB instance
        # Remove the skip decorator to run this test with a local MongoDB

        async def run_test():
            mongodb = self.mongo_class(self.mock_bot)
            await mongodb._force_connection()
            return await mongodb.check_connection()

        # Run the async test
        result = self.loop.run_until_complete(run_test())

        self.assertTrue(result)

    def test_mongodb_uri_parsing(self):
        """Test that MongoDB URI is parsed correctly."""
        # We'll test the class instantiation with different URI formats
        test_cases = [
            "mongodb://localhost:27017",
            "mongodb://user:pass@localhost:27017",
            "mongodb+srv://user:pass@cluster.example.com",
        ]

        for uri in test_cases:
            self.mock_bot.config.MONGO_URI = uri
            mongodb = self.mongo_class(self.mock_bot)
            self.assertEqual(mongodb.mongo_uri, uri)


if __name__ == "__main__":
    unittest.main()
