"""
Helper utilities for the Quantum Bank Discord bot.

This package contains various helper functions and classes used throughout the bot.
"""

# Import constants for easy access
from .cache_manager import CacheManager, cached

# Import advanced scalability helpers
from .connection_pool import ConnectionPoolManager
from .constants import *

# Import rate limiter
from .rate_limiter import RateLimiter, cooldown, rate_limit
from .shard_manager import ShardManager

# Version info
__version__ = "1.0.0"

__all__ = ["RateLimiter", "rate_limit", "cooldown", "ConnectionPoolManager", "CacheManager", "cached", "ShardManager"]
