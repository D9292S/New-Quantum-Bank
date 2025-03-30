"""Unit tests for Utility cog functionality."""

import os
import sys
import unittest
from unittest.mock import MagicMock

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


@pytest.mark.unit
class TestUtilityCog(unittest.TestCase):
    """Test cases for utility cog functionality."""

    def setUp(self):
        """Set up test environment."""
        # Import after path setup to ensure correct imports
        from cogs.utility import Utility

        # Create a mock bot
        self.bot = MagicMock()
        self.bot.user = MagicMock()
        self.bot.user.id = 123456789
        self.bot.user.name = "TestBot"

        # Create the cog
        self.cog = Utility(self.bot)

    def test_init(self):
        """Test initialization of the cog."""
        # Check that start_time is set
        self.assertTrue(hasattr(self.cog, "start_time"))
        self.assertIsInstance(self.cog.start_time, float)

        # Check that logger is set up
        self.assertTrue(hasattr(self.cog, "logger"))

        # Verify bot reference is correct
        self.assertEqual(self.cog.bot, self.bot)


if __name__ == "__main__":
    unittest.main()
