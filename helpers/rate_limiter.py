import asyncio
import logging
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger("bot")


class RateLimiter:
    """Rate limiter for controlling command and API usage"""

    def __init__(self):
        # Store rate limits by key (user_id, guild_id, etc.)
        self._rate_limits: Dict[str, Dict[str, Any]] = {}

        # Different buckets for different types of rate limits
        self._buckets = {
            "global": {},  # Global rate limits
            "user": {},  # Per-user rate limits
            "guild": {},  # Per-guild rate limits
            "channel": {},  # Per-channel rate limits
            "command": {},  # Per-command rate limits
        }

        # Clean up task
        self._cleanup_task = None

    def start_cleanup(self):
        """Start periodic cleanup of expired rate limits"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_old_entries())

    async def _cleanup_old_entries(self):
        """Periodically clean up expired rate limit entries"""
        try:
            while True:
                now = time.time()
                # Clean up each bucket
                for bucket_name, bucket in self._buckets.items():
                    expired_keys = []
                    for key, data in bucket.items():
                        if data["reset_at"] < now:
                            expired_keys.append(key)

                    # Remove expired entries
                    for key in expired_keys:
                        bucket.pop(key, None)

                # Run every 5 minutes
                await asyncio.sleep(300)
        except asyncio.CancelledError:
            logger.info("Rate limiter cleanup task cancelled")
        except Exception as e:
            logger.error(f"Error in rate limiter cleanup: {e}")

    def is_rate_limited(self, bucket: str, key: str, limit: int, window: int) -> Tuple[bool, float]:
        """
        Check if a key is rate limited

        Args:
            bucket: The type of rate limit ('global', 'user', 'guild', etc.)
            key: The key to check (user_id, guild_id, etc.)
            limit: Maximum number of uses in the time window
            window: Time window in seconds

        Returns:
            Tuple of (is_limited, retry_after)
        """
        # Get the bucket
        if bucket not in self._buckets:
            return False, 0

        bucket_data = self._buckets[bucket]
        now = time.time()

        # Check if key exists in bucket
        if key not in bucket_data:
            # First use, create new entry
            bucket_data[key] = {"count": 1, "reset_at": now + window}
            return False, 0

        # Get existing data
        data = bucket_data[key]

        # Check if the window has reset
        if data["reset_at"] < now:
            # Reset the counter for a new window
            data["count"] = 1
            data["reset_at"] = now + window
            return False, 0

        # Check if over the limit
        if data["count"] >= limit:
            retry_after = data["reset_at"] - now
            return True, retry_after

        # Increment the counter
        data["count"] += 1
        return False, 0

    def increment(self, bucket: str, key: str, limit: int, window: int) -> Tuple[bool, float]:
        """
        Increment usage counter and check if rate limited

        Args:
            bucket: The type of rate limit ('global', 'user', 'guild', etc.)
            key: The key to check (user_id, guild_id, etc.)
            limit: Maximum number of uses in the time window
            window: Time window in seconds

        Returns:
            Tuple of (is_limited, retry_after)
        """
        # Ensure bucket exists
        if bucket not in self._buckets:
            self._buckets[bucket] = {}

        bucket_data = self._buckets[bucket]
        now = time.time()

        # Check if key exists in bucket
        if key not in bucket_data:
            # First use, create new entry
            bucket_data[key] = {"count": 1, "reset_at": now + window}
            return False, 0

        # Get existing data
        data = bucket_data[key]

        # Check if the window has reset
        if data["reset_at"] < now:
            # Reset the counter for a new window
            data["count"] = 1
            data["reset_at"] = now + window
            return False, 0

        # Check if over the limit
        if data["count"] >= limit:
            retry_after = data["reset_at"] - now
            return True, retry_after

        # Increment the counter
        data["count"] += 1
        return False, 0

    def reset(self, bucket: str, key: str):
        """Reset the rate limit for a specific key"""
        if bucket in self._buckets and key in self._buckets[bucket]:
            del self._buckets[bucket][key]


# Decorator for rate limiting commands
def rate_limit(limit: int, window: int, *, key_func: Optional[Callable] = None, bucket: str = "user"):
    """
    Decorator to apply rate limiting to commands

    Args:
        limit: Maximum number of uses in the time window
        window: Time window in seconds
        key_func: Function to generate the rate limit key (default: user ID)
        bucket: Rate limit bucket type (default: 'user')

    Example:
        @rate_limit(5, 60)  # 5 uses per minute per user
        async def some_command(ctx):
            ...
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(self, ctx, *args, **kwargs):
            # Get or create rate limiter
            if not hasattr(self.bot, "rate_limiter"):
                self.bot.rate_limiter = RateLimiter()
                self.bot.rate_limiter.start_cleanup()

            # Generate the rate limit key
            if key_func:
                key = str(key_func(ctx))
            elif bucket == "user":
                key = str(ctx.author.id)
            elif bucket == "guild":
                key = str(ctx.guild.id) if ctx.guild else "dm"
            elif bucket == "channel":
                key = str(ctx.channel.id)
            elif bucket == "command":
                key = func.__name__
            elif bucket == "global":
                key = "global"
            else:
                key = str(ctx.author.id)  # Default to user ID

            # Check rate limit
            is_limited, retry_after = self.bot.rate_limiter.increment(bucket, key, limit, window)

            if is_limited:
                # Format the retry time
                if retry_after >= 60:
                    time_str = f"{retry_after // 60}m {retry_after % 60}s"
                else:
                    time_str = f"{retry_after:.1f}s"

                await ctx.respond(f"⏳ You're using this command too quickly. Please wait {time_str}.", ephemeral=True)
                return

            # Execute the command
            return await func(self, ctx, *args, **kwargs)

        return wrapper

    return decorator


# Per-user cooldown decorator
def cooldown(rate: int, per: float, bucket_type="user"):
    """
    Simpler cooldown decorator that works like discord.py's cooldown

    Args:
        rate: Number of uses allowed
        per: Time period in seconds
        bucket_type: The type of cooldown ('user', 'guild', 'channel', 'global')

    Example:
        @cooldown(1, 30)  # Once per 30 seconds per user
        async def some_command(ctx):
            ...
    """
    return rate_limit(rate, per, bucket=bucket_type)
