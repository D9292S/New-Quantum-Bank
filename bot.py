import asyncio
import importlib
import logging
import math
import os
import time
from typing import Any, Dict

import aiohttp
import discord
import psutil
from expiringdict import ExpiringDict

import helpers
from helpers import CacheManager, ConnectionPoolManager, ShardManager


class ClusterBot(discord.AutoShardedBot):
    class BlueEmbed(discord.Embed):
        def __init__(self, **kwargs):
            color = kwargs.pop("color", helpers.constants.BLUE)
            super().__init__(color=color, **kwargs)

    class Embed(discord.Embed):
        def __init__(self, **kwargs):
            color = kwargs.pop("color", helpers.constants.PINK)
            super().__init__(color=color, **kwargs)

    def __init__(self, **kwargs):
        self._token = kwargs.pop("token", None)
        if not self._token:
            raise ValueError("BOT_TOKEN must be provided via .env or as an argument")

        self.config = kwargs.pop("config", None)
        if self.config is None:
            try:
                self.config = __import__("config")
            except ImportError:
                self.config = type("Config", (), {"DEBUG": False})

        # Performance tracking
        self.start_time = time.time()
        self.message_count = 0
        self.command_count = 0
        self.events_processed = 0

        # Menu tracking
        self.menus = ExpiringDict(max_len=300, max_age_seconds=300)

        # Custom sharding setup
        self.shard_count = kwargs.pop("shard_count", None)
        self.shard_ids = kwargs.pop("shard_ids", None)

        # Set up intents
        intents = kwargs.pop("intents", discord.Intents.default())
        if not intents.message_content:
            intents.message_content = True

        # Initialize the bot with prefix commands support and slash commands
        super().__init__(
            command_prefix=self._get_prefix,
            intents=intents,
            shard_count=self.shard_count,
            shard_ids=self.shard_ids,
            **kwargs,
        )

        # Set activity status
        self.activity = discord.Game(name=self.config.ACTIVITY_STATUS)

        # Set up logging
        self.setup_logging()

        # Set up performance managers
        self._init_performance_managers()

        # Hook setup
        self._setup_hooks()

        # Process pool for CPU-bound tasks
        self._process_pool = None

        # System info for monitoring
        self._process = psutil.Process()

    async def _get_prefix(self, bot, message):
        """Dynamic prefix getter - allows for custom prefixes per guild"""
        default_prefix = "!"

        # If DM, just use the default prefix
        if not message.guild:
            return default_prefix

        # Try to get custom prefix from cache or database
        custom_prefix = None
        guild_id = str(message.guild.id)

        if hasattr(self, "_cache") and "guild_settings" in self._cache:
            guild_settings = self._cache["guild_settings"].get(guild_id)
            if guild_settings and "prefix" in guild_settings:
                custom_prefix = guild_settings["prefix"]

        # If not in cache and we have database access, try to get from DB
        if not custom_prefix and hasattr(self, "db") and self.db:
            try:
                # Note: this implementation depends on having a database method to get guild settings
                guild_settings = await self.db.get_guild_settings(guild_id)
                if guild_settings and "prefix" in guild_settings:
                    custom_prefix = guild_settings["prefix"]

                    # Cache the result if we have a cache
                    if hasattr(self, "_cache") and "guild_settings" in self._cache:
                        self._cache["guild_settings"][guild_id] = guild_settings
            except Exception as e:
                self.log("error", "error", f"Error getting guild prefix: {e}")

        return custom_prefix or default_prefix

    def _setup_hooks(self):
        """Set up hooks for various events to enhance performance"""
        self._before_invoke = self._record_command_usage

    async def _record_command_usage(self, ctx):
        """Record command usage statistics with proper categorization"""
        self.command_count += 1
        command_name = ctx.command.qualified_name if ctx.command else "unknown"

        # Log command usage to command category
        self.cmd_logger.info(
            f"Command executed: {command_name} by {ctx.author} in " + (f"guild {ctx.guild.name}" if ctx.guild else "DM")
        )

        # Store command usage in database for analytics if available
        if hasattr(self, "db") and self.db is not None:
            try:
                await self.db.log_command_usage(
                    command=command_name,
                    user_id=str(ctx.author.id),
                    guild_id=str(ctx.guild.id) if ctx.guild else None,
                    timestamp=time.time(),
                )
            except Exception as e:
                self.error_logger.error(f"Failed to log command usage in database: {str(e)}")

    def setup_logging(self):
        """Set up the bot's logger to use the categorized logging system"""
        # Get loggers for different categories
        self.bot_logger = logging.getLogger("bot")
        self.db_logger = logging.getLogger("database")
        self.cmd_logger = logging.getLogger("commands")
        self.perf_logger = logging.getLogger("performance")
        self.error_logger = logging.getLogger("errors")

        # Log startup information
        self.bot_logger.info(f"Bot instance initialized with {self.shard_count or 1} shards")
        if self.shard_ids:
            self.bot_logger.info(f"Running shards: {self.shard_ids}")

        if self.config.DEBUG:
            self.bot_logger.info("Debug mode enabled - verbose logging active")

    def log(self, category: str, level: str, message: str, **kwargs):
        """Log a message to the appropriate category"""
        # Map category names to logger objects
        loggers = {
            "bot": self.bot_logger,
            "db": self.db_logger,
            "cmd": self.cmd_logger,
            "perf": self.perf_logger,
            "error": self.error_logger,
        }

        # Get the appropriate logger
        logger = loggers.get(category, self.bot_logger)

        # Get the log method based on level
        log_method = getattr(logger, level.lower(), logger.info)

        # Format extra data for structured logging
        if kwargs:
            # Convert any non-string values to strings for better logging
            for key, value in kwargs.items():
                if not isinstance(value, (str, int, float, bool, type(None))):
                    kwargs[key] = str(value)

            # Format as structured log message
            structured_message = f"{message} " + " ".join(f"{k}={v}" for k, v in kwargs.items())
            log_method(structured_message)
        else:
            log_method(message)

    def setup_process_pool(self, max_workers=None):
        """Setup process pool for CPU-bound tasks"""
        import concurrent.futures

        if max_workers is None:
            # Use half the available CPUs by default
            max_workers = max(1, os.cpu_count() // 2)

        self._process_pool = concurrent.futures.ProcessPoolExecutor(max_workers=max_workers)
        self.log("perf", "info", f"Process pool initialized with {max_workers} workers")

    async def run_in_process_pool(self, func, *args, **kwargs):
        """Run a CPU-bound function in the process pool"""
        if self._process_pool is None:
            self.setup_process_pool()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._process_pool, lambda: func(*args, **kwargs))

    def _init_performance_managers(self):
        """Initialize performance and scalability managers"""
        # Initialize connection pool manager
        mongo_uri = getattr(self.config, "MONGO_URI", None)
        self.conn_pool = ConnectionPoolManager(mongo_uri=mongo_uri, max_mongo_pool_size=100, max_http_connections=100)

        # Initialize cache manager with reasonable defaults
        self.cache_manager = CacheManager(
            ttl_seconds=300,  # 5 minute default TTL
            max_size=10000,  # Up to 10K items in memory
            enable_stats=True,
        )

        # Prepare cache cleanup task (will be started properly in on_ready)
        self.cache_manager.start_cleanup_task(interval=60)  # Clean every minute

        # Initialize shard manager (mongo DB will be set later)
        self.shard_manager = ShardManager(self, mongodb=None)
        # Prepare shard monitoring (will be started in on_ready)
        self.shard_manager.start_monitoring()

    async def setup_cogs(self):
        start_time = time.time()

        # Use provided initial_cogs list if available, otherwise use default
        if hasattr(self, "initial_cogs"):
            cog_order = self.initial_cogs
        else:
            cog_order = ["mongo", "accounts", "admin", "anime", "utility"]

        enabled_cogs = []

        for cog_name in cog_order:
            try:
                module = importlib.import_module(f"cogs.{cog_name}")
                metadata = getattr(module, "COG_METADATA", {"enabled": True})
                if self.config.DEBUG:
                    self.log("debug", "info", f"Cog {cog_name} metadata: {metadata}")
                if metadata.get("enabled", True):
                    enabled_cogs.append(cog_name)
                else:
                    self.log("info", "info", f"Skipping disabled cog: {cog_name}")
            except ImportError as e:
                self.log("error", "error", f"Failed to import cog {cog_name}", exc_info=e)
                # Don't raise error for performance_monitor to allow backward compatibility
                if cog_name != "performance_monitor":
                    raise

        self.log(
            "info",
            "info",
            "Starting cog setup",
            extra={"cog_count": len(enabled_cogs), "cogs": enabled_cogs},
        )

        # Initialize HTTP session with optimized settings using connection pool
        self.http_session = await self.conn_pool.get_http_session()
        if not self.http_session:
            # Fallback to creating a basic session
            self.http_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"User-Agent": f"QuantumBank Discord Bot {getattr(self, 'version', '1.0.0')}"},
            )

        # Initialize caches with configs
        cache_config = getattr(self.config, "cache", {})
        self._cache = {
            "commands": {},
            "cooldowns": ExpiringDict(
                max_len=cache_config.get("cooldowns_max_len", 1000),
                max_age_seconds=cache_config.get("cooldowns_max_age", 60),
            ),
            "user_settings": ExpiringDict(
                max_len=cache_config.get("user_settings_max_len", 10000),
                max_age_seconds=cache_config.get("user_settings_max_age", 300),
            ),
            "guild_settings": ExpiringDict(
                max_len=cache_config.get("guild_settings_max_len", 1000),
                max_age_seconds=cache_config.get("guild_settings_max_age", 300),
            ),
        }

        # Use semaphore to limit concurrent cog loading
        semaphore = asyncio.Semaphore(10)
        cog_tasks = []
        for cog_name in enabled_cogs:
            if cog_name in self.cogs:
                self.log("info", "info", f"Skipping already loaded cog: {cog_name}")
                continue
            self.log("info", "info", f"Preparing to load cog: {cog_name}")
            cog_tasks.append(self._load_cog(cog_name, semaphore))

        # Load cogs concurrently
        results = await asyncio.gather(*cog_tasks, return_exceptions=True)
        for cog_name, result in zip(enabled_cogs, results):
            if isinstance(result, Exception):
                self.log("error", "error", f"Cog {cog_name} failed to load", exc_info=result)

        elapsed_time = time.time() - start_time
        self.log("info", "info", "Finished loading cogs", extra={"elapsed_time": f"{elapsed_time:.2f}s"})

    async def _load_cog(self, cog_name: str, semaphore: asyncio.Semaphore):
        async with semaphore:
            try:
                module = importlib.import_module(f"cogs.{cog_name}")
                await module.setup(self)
                self.log("info", "info", f"Successfully loaded cog: {cog_name}")
            except ImportError as e:
                self.log(
                    "error",
                    "error",
                    f"Failed to import cog {cog_name} - module not found or invalid",
                    exc_info=e,
                )
                raise
            except AttributeError as e:
                self.log("error", "error", f"Cog {cog_name} is missing a setup function", exc_info=e)
                raise
            except Exception as e:
                self.log("error", "error", f"Error during setup of cog {cog_name}", exc_info=e)
                raise

    async def on_message(self, message):
        # Skip messages from bots
        if message.author.bot:
            return

        # Log message processing
        self.log("debug", "debug", f"Processing message from {message.author}: {message.content[:50]}...")

        # We don't need to manually process commands in pycord 2.x when using application commands
        # The following line is causing the error and should be removed
        # await self.process_commands(message)

        # Increment message counter
        self.message_count += 1

    async def handle_guild_message(self, message: discord.Message):
        """Handle guild-specific message processing"""
        # This would contain any guild-specific processing
        # that should happen for every message
        pass

    def calculate_recommended_shards(self):
        """Calculate the recommended number of shards for the bot"""
        try:
            # Get the recommended shard count from Discord
            data = discord.http.Route.get("/gateway/bot")
            response = self.http.request(data)

            if "shards" in response:
                return response["shards"]
            return 1
        except Exception as e:
            self.log("error", "error", f"Failed to get recommended shard count: {e}")
            # The old formula: 1 per 1000 guilds
            return max(1, math.ceil(len(self.guilds) / 1000))

    def run(self, *args, **kwargs):
        """Run the bot with auto-sharding and proper event loop setup"""
        self.log("info", "info", "Starting bot run")

        # Set event loop policy for Windows if needed
        if os.name == "nt" and not isinstance(asyncio.get_event_loop_policy(), asyncio.WindowsSelectorEventLoopPolicy):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            self.log("info", "info", "Set WindowsSelectorEventLoopPolicy for compatibility")

        # Set up a fresh event loop
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.log("info", "info", "Set up fresh event loop")
        except RuntimeError:
            # If we're already in an event loop, just use the current one
            loop = asyncio.get_event_loop()
            self.log("info", "info", "Using existing event loop")

        # Initialize process pool
        self.setup_process_pool()

        try:
            # Let discord.py handle the event loop
            super().run(self._token, *args, **kwargs)
        except KeyboardInterrupt:
            self.log("info", "info", "Bot stopped via keyboard interrupt")
            if not loop.is_closed():
                loop.run_until_complete(self.close())
        except Exception as e:
            self.log("error", "error", "Failed to start bot", exc_info=e)
            if not loop.is_closed():
                loop.run_until_complete(self.close())
            raise
        finally:
            # Cleanup
            if self._process_pool:
                self._process_pool.shutdown(wait=False)

            # Close the event loop
            try:
                if not loop.is_closed():
                    # Cancel all running tasks
                    for task in asyncio.all_tasks(loop):
                        task.cancel()

                    # Run the loop until all tasks are cancelled
                    loop.run_until_complete(loop.shutdown_asyncgens())
                    loop.close()
            except Exception as e:
                self.log("error", "error", f"Error closing event loop: {e}")

            self.log("info", "info", "Bot run completed")

    async def on_connect(self):
        """Handle bot connection to Discord"""
        self.log("info", "info", "Bot connected to Discord")
        latency = self.latency * 1000
        self.log("info", "info", f"Gateway latency: {latency:.2f}ms")

        # Log shard information
        if self.shard_count:
            self.log("info", "info", f"Bot running with {self.shard_count} shards")
        else:
            self.log("info", "info", "Bot running in single-shard mode")

        try:
            await self.setup_cogs()
        except Exception as e:
            self.log("error", "error", "Failed to setup cogs during on_connect", exc_info=e)
            raise

    async def on_ready(self):
        """Handle bot ready event with enhanced metrics"""
        start_time = time.time()
        self.log("info", "info", "Bot is ready!")
        self.log("info", "info", f"Logged in as {self.user.name} (ID: {self.user.id})")

        # Start async tasks now that the event loop is running
        if hasattr(self, "cache_manager"):
            await self.cache_manager.start_cleanup_task_async(interval=60)
            self.log("info", "info", "Started cache cleanup task")

        # Guild stats
        guild_count = len(self.guilds)
        member_count = sum(g.member_count for g in self.guilds)
        self.log("info", "info", f"Connected to {guild_count} guilds with {member_count:,} members")

        # Shard stats if sharded
        if self.shard_count and self.shard_count > 1:
            shard_guild_counts = {}
            for guild in self.guilds:
                shard_id = (guild.id >> 22) % self.shard_count
                if shard_id not in shard_guild_counts:
                    shard_guild_counts[shard_id] = 0
                shard_guild_counts[shard_id] += 1

            self.log("info", "info", f"Shard distribution: {shard_guild_counts}")

        # Memory usage
        try:
            import psutil

            process = psutil.Process()
            memory_info = process.memory_info()
            self.log("info", "info", f"Memory usage: {memory_info.rss / 1024 / 1024:.2f} MB")
        except ImportError:
            pass

        # Sync commands with Discord
        try:
            # Sync commands globally
            synced = await self.sync_commands()
            if synced is not None:
                self.log("info", "info", f"Synced {len(synced)} application commands")
            else:
                self.log("info", "info", "Commands were already synced")
        except Exception as e:
            self.log("error", "error", f"Failed to sync application commands: {e}")

        app_commands = [cmd.name for cmd in self.application_commands]
        self.log("info", "info", f"Registered application commands: {app_commands}")

        # Start performance monitoring tasks if available
        perf_monitor = self.get_cog("PerformanceMonitor")
        if perf_monitor:
            await perf_monitor.start_tasks()
            self.log("info", "info", "Started performance monitoring tasks")

        self.log("info", "info", f"Pycord version: {discord.__version__}")

        # Set up shard monitoring now that we're connected
        if hasattr(self, "db") and self.db:
            # Update shard manager with MongoDB connection
            self.shard_manager.mongodb = self.db.db

            # Start shard monitoring
            await self.shard_manager.start_monitoring_async()

            # Process any pending cross-shard events
            await self.shard_manager.process_pending_events()

            # Start background task to process cross-shard events
            self._start_shard_event_processor()

        elapsed_time = time.time() - start_time
        self.log("info", "info", f"Ready event processed in {elapsed_time:.2f}s")

    def _start_shard_event_processor(self):
        """Start background task to process inter-shard events"""

        async def process_events_task():
            try:
                while not self.is_closed():
                    try:
                        # Process events every 5 seconds
                        await self.shard_manager.process_pending_events()
                    except Exception as e:
                        self.log("error", "error", f"Error processing shard events: {e}")

                    await asyncio.sleep(5)
            except asyncio.CancelledError:
                self.log("info", "info", "Shard event processor task cancelled")

        self.loop.create_task(process_events_task())

    async def close(self):
        """Clean up resources on bot shutdown"""
        # Close connection pools cleanly
        if hasattr(self, "conn_pool"):
            await self.conn_pool.close()

        # Close HTTP session explicitly if we didn't use connection pool
        if hasattr(self, "http_session") and self.http_session:
            await self.http_session.close()

        # Close process pool if used
        if self._process_pool:
            self._process_pool.shutdown()

        # Call parent close to handle Discord cleanup
        await super().close()

    def get_system_metrics(self) -> Dict[str, Any]:
        """Get detailed system metrics for monitoring"""
        metrics = {
            "uptime": time.time() - self.start_time,
            "message_count": self.message_count,
            "command_count": self.command_count,
            "events_processed": self.events_processed,
            "guilds": len(self.guilds),
            "users": sum(g.member_count for g in self.guilds),
            "latency": self.latency * 1000,  # in ms
            "shards": self.shard_count,
        }

        # Add process metrics
        try:
            metrics["memory_usage_mb"] = self._process.memory_info().rss / 1024 / 1024
            metrics["cpu_percent"] = self._process.cpu_percent(interval=0.1)
            metrics["thread_count"] = self._process.num_threads()
        except Exception:
            pass

        # Add cache metrics if available
        if hasattr(self, "cache_manager"):
            metrics["cache"] = self.cache_manager.get_stats()

        # Add shard metrics if available
        if hasattr(self, "shard_manager"):
            metrics["shard_manager"] = self.shard_manager.get_metrics()

        return metrics
