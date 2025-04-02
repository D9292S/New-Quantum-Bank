"""
Feature flag utility functions to interact with DevCycle feature flags.

This module provides a simple interface for checking feature flags throughout the codebase.
"""

import functools
import logging
from typing import Any, Callable, Optional, TypeVar, cast

import discord

# Type variables for better type hinting
T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])

# Initialize logger
logger = logging.getLogger("bot")


def get_feature_manager(bot) -> Optional[Any]:
    """
    Get the feature flag manager cog from the bot.
    
    Args:
        bot: The bot instance to get the feature manager from
        
    Returns:
        The feature manager cog or None if not found
    """
    try:
        return bot.get_cog("FeatureFlags")
    except Exception as e:
        logger.error(f"Error getting feature flag manager: {str(e)}")
        return None


def is_feature_enabled(
    bot, feature_key: str, user_id: Optional[str] = None, guild_id: Optional[str] = None, default: bool = False
) -> bool:
    """
    Check if a feature is enabled for a specific user/guild.
    
    Args:
        bot: The bot instance to check the feature flag
        feature_key: The feature flag key to check
        user_id: The user ID to check against (optional)
        guild_id: The guild ID to check against (optional)
        default: Default value if flag doesn't exist or error occurs
        
    Returns:
        Whether the feature is enabled
    """
    feature_manager = get_feature_manager(bot)
    if not feature_manager:
        return default
        
    return feature_manager.is_enabled(feature_key, user_id, guild_id, default)


def get_feature_variable(
    bot, feature_key: str, user_id: Optional[str] = None, guild_id: Optional[str] = None, default: Any = None
) -> Any:
    """
    Get a feature variable value for a specific user/guild.
    
    Args:
        bot: The bot instance to get the feature variable
        feature_key: The feature variable key to retrieve
        user_id: The user ID to check against (optional)
        guild_id: The guild ID to check against (optional)
        default: Default value if variable doesn't exist or error occurs
        
    Returns:
        The variable value
    """
    feature_manager = get_feature_manager(bot)
    if not feature_manager:
        return default
        
    return feature_manager.get_variable(feature_key, user_id, guild_id, default)


def feature_flag(feature_key: str, default: bool = False) -> Callable[[F], F]:
    """
    Decorator to conditionally enable a command based on a feature flag.
    
    This decorator should be applied after the command decorator.
    
    Args:
        feature_key: The feature flag key to check
        default: Default value if flag doesn't exist or error occurs
        
    Returns:
        Decorator function that enables/disables the command based on the feature flag
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(self, ctx: discord.ApplicationContext, *args, **kwargs):
            # Get user and guild IDs from context
            user_id = str(ctx.author.id)
            guild_id = str(ctx.guild.id) if ctx.guild else None
            
            # Check if feature is enabled
            if not is_feature_enabled(self.bot, feature_key, user_id, guild_id, default):
                await ctx.respond(
                    "⚠️ This feature is currently disabled or not available to you.",
                    ephemeral=True
                )
                return
                
            # Feature is enabled, execute the command
            return await func(self, ctx, *args, **kwargs)
            
        return cast(F, wrapper)
    return decorator


def percentage_rollout(bot, feature_key: str, percentage: int, user_id: str) -> bool:
    """
    Helper function for manual percentage-based rollout if DevCycle is not available.
    
    Args:
        bot: The bot instance
        feature_key: Feature key for consistent hashing
        percentage: Percentage of users that should have the feature (0-100)
        user_id: User ID to check
        
    Returns:
        Whether the user has the feature enabled
    """
    # First try DevCycle if available
    feature_manager = get_feature_manager(bot)
    if feature_manager and feature_manager.initialized:
        return feature_manager.is_enabled(feature_key, user_id)
        
    # Fallback to simple percentage rollout using hash
    if percentage <= 0:
        return False
    if percentage >= 100:
        return True
        
    # Create a hash of the feature key and user ID
    # This ensures the same user always gets the same result for a given feature
    import hashlib
    hash_input = f"{feature_key}:{user_id}"
    hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
    
    # Calculate percentage (0-100)
    user_percentage = hash_value % 100
    
    # Enable for users that fall within the percentage bucket
    return user_percentage < percentage 