"""Unit tests for the launcher module."""

import os
import sys
import unittest
from unittest.mock import patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest

import launcher


@pytest.mark.unit
class TestLauncher(unittest.TestCase):
    """Test cases for launcher.py functionality."""

    def test_parse_arguments_defaults(self):
        """Test argument parser default values."""
        with patch("sys.argv", ["launcher.py"]):
            args = launcher.parse_arguments()
            self.assertFalse(args.debug)
            self.assertIsNone(args.shards)
            self.assertIsNone(args.shardids)
            self.assertIsNone(args.cluster)
            self.assertIsNone(args.clusters)
            self.assertEqual(args.performance, "medium")
            self.assertEqual(args.log_level, "normal")

    def test_parse_arguments_custom(self):
        """Test argument parser with custom values."""
        with patch(
            "sys.argv",
            [
                "launcher.py",
                "--debug",
                "--shards",
                "3",
                "--performance",
                "high",
                "--log-level",
                "verbose",
            ],
        ):
            args = launcher.parse_arguments()
            self.assertTrue(args.debug)
            self.assertEqual(args.shards, 3)
            self.assertEqual(args.performance, "high")
            self.assertEqual(args.log_level, "verbose")

    def test_calculate_shards_for_cluster(self):
        """Test shard calculation for clusters."""
        # Test even distribution
        self.assertEqual(launcher.calculate_shards_for_cluster(0, 2, 4), [0, 1])
        self.assertEqual(launcher.calculate_shards_for_cluster(1, 2, 4), [2, 3])

        # Test uneven distribution
        self.assertEqual(launcher.calculate_shards_for_cluster(0, 2, 5), [0, 1, 2])
        self.assertEqual(launcher.calculate_shards_for_cluster(1, 2, 5), [3, 4])

    def test_log_setup(self):
        """Test that log setup works correctly."""
        with patch("logging.getLogger"), patch("logging.handlers.RotatingFileHandler"):
            categories = launcher.setup_logging("normal")
            self.assertIsNotNone(categories)
            self.assertIn("bot", categories)
            self.assertIn("commands", categories)
            self.assertIn("database", categories)


if __name__ == "__main__":
    unittest.main()
