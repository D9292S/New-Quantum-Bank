"""
Configuration management for Quantum Bank Bot.
This module provides a centralized configuration class with validation.
"""

import os
from dataclasses import dataclass, field


# Configuration validation error
class ConfigurationError(Exception):
    """Raised when configuration is invalid."""

    pass


@dataclass
class BotConfig:
    """
    Bot configuration with validation.

    This class loads configuration from environment variables and command-line arguments,
    validates it, and provides a centralized access point for all configuration needs.
    """

    # Required settings
    bot_token: str

    # Database settings
    mongo_uri: str | None = None

    # Bot settings
    activity_status: str = "Quantum Bank | /help"
    debug: bool = False

    # Optional API keys
    mal_client_id: str | None = None

    # Performance settings
    performance_mode: str = "medium"  # low, medium, high

    # Sharding configuration
    shard_count: int = 1
    shard_ids: list[int] | None = None

    # Clustering configuration
    cluster_id: int | None = None
    total_clusters: int | None = None

    # Heroku specific config
    port: int = int(os.environ.get("PORT", 8080))

    # Derived settings
    is_clustered: bool = field(init=False)
    is_sharded: bool = field(init=False)

    def __post_init__(self):
        """Perform post-initialization validation and setup."""
        self.is_clustered = self.cluster_id is not None and self.total_clusters is not None
        self.is_sharded = self.shard_count > 1 or (self.shard_ids is not None and len(self.shard_ids) > 0)

        # Validate required settings
        if not self.bot_token:
            raise ConfigurationError("BOT_TOKEN is required")

        # Ensure performance_mode is valid
        if self.performance_mode.lower() not in ["low", "medium", "high"]:
            print(f"Warning: Invalid performance_mode '{self.performance_mode}'. Using 'medium' instead.")
            self.performance_mode = "medium"

        # Validate clustering configuration
        if self.cluster_id is not None and self.total_clusters is None:
            raise ConfigurationError("TOTAL_CLUSTERS must be set when CLUSTER_ID is provided")

        if self.cluster_id is not None and self.total_clusters is not None:
            if self.cluster_id >= self.total_clusters:
                raise ConfigurationError(
                    f"CLUSTER_ID ({self.cluster_id}) must be less than TOTAL_CLUSTERS ({self.total_clusters})"
                )

    @classmethod
    def from_env(cls, override_args=None):
        """
        Create a configuration instance from environment variables.

        Args:
            override_args: Optional argparse Namespace to override env vars

        Returns:
            BotConfig: A validated configuration instance
        """
        # Load from environment variables
        config = cls(
            # Required settings
            bot_token=os.getenv("BOT_TOKEN", ""),
            # Database settings - check for MONGODB_URI first, then fall back to MONGO_URI for backwards compatibility
            mongo_uri=os.getenv("MONGODB_URI") or os.getenv("MONGO_URI"),
            # Bot settings
            activity_status=os.getenv("ACTIVITY_STATUS", "Quantum Bank | /help"),
            debug=os.getenv("DEBUG", "").lower() in ["true", "1", "t", "yes"],
            # Optional API keys
            mal_client_id=os.getenv("MAL_CLIENT_ID"),
            # Performance settings
            performance_mode=os.getenv("PERFORMANCE_MODE", "medium").lower(),
            # Sharding configuration
            shard_count=int(os.getenv("SHARD_COUNT", "1")),
            # Clustering configuration
            cluster_id=int(os.getenv("CLUSTER_ID")) if os.getenv("CLUSTER_ID") else None,
            total_clusters=int(os.getenv("TOTAL_CLUSTERS")) if os.getenv("TOTAL_CLUSTERS") else None,
            # Heroku specific config
            port=int(os.getenv("PORT", 8080)),
        )

        # Override with command-line arguments if provided
        if override_args:
            if hasattr(override_args, "debug") and override_args.debug:
                config.debug = True

            if hasattr(override_args, "performance") and override_args.performance:
                config.performance_mode = override_args.performance

            if hasattr(override_args, "shards") and override_args.shards:
                config.shard_count = override_args.shards

            if hasattr(override_args, "shardids") and override_args.shardids:
                # Parse comma-separated list of shard IDs
                config.shard_ids = [int(s.strip()) for s in override_args.shardids.split(",")]

            if hasattr(override_args, "cluster") and override_args.cluster is not None:
                config.cluster_id = override_args.cluster

            if hasattr(override_args, "clusters") and override_args.clusters:
                config.total_clusters = override_args.clusters

        return config

    def summary(self):
        """Return a dictionary summarizing the configuration."""
        return {
            "debug": self.debug,
            "performance_mode": self.performance_mode,
            "mongo_uri_set": self.mongo_uri is not None,
            "mal_client_id_set": self.mal_client_id is not None,
            "shard_count": self.shard_count,
            "shard_ids": self.shard_ids,
            "cluster_id": self.cluster_id,
            "total_clusters": self.total_clusters,
            "is_sharded": self.is_sharded,
            "is_clustered": self.is_clustered,
            "port": self.port,
        }
