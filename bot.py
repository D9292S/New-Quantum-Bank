import asyncio
import aiohttp
import time
import importlib
import os
import logging
import discord
import structlog
import coloredlogs
import re
from expiringdict import ExpiringDict

import helpers

class ClusterBot(discord.Bot):
    class BlueEmbed(discord.Embed):
        def __init__(self, **kwargs):
            color = kwargs.pop('color', helpers.constants.BLUE)
            super().__init__(color=color, **kwargs)
        
    class Embed(discord.Embed):
        def __init__(self, **kwargs):
            color = kwargs.pop('color', helpers.constants.PINK)
            super().__init__(color=color, **kwargs)
            
    def __init__(self, **kwargs):
        self._token = kwargs.pop("token", None)
        if not self._token:
            raise ValueError("BOT_TOKEN must be provided via .env or as an argument")

        self.config = kwargs.pop("config", None)
        if self.config is None:
            try:
                self.config = __import__('config')
            except ImportError:
                self.config = type('Config', (), {'DEBUG': False})
        
        self.menus = ExpiringDict(max_len=300, max_age_seconds=300)

        intents = kwargs.pop("intents", discord.Intents.default())
        if not intents.message_content:
            intents.message_content = True
        
        super().__init__(command_prefix="!", intents=intents, **kwargs)
        
        self.activity = discord.Game(name="POKE LEGENDS")
        self.setup_logging()

    class CustomFormatter(logging.Formatter):
        def format(self, record):
            msg = super().format(record)
            msg = re.sub(r'(\w+)=(\S+)', r'\033[94m\1\033[0m=\033[97m\2\033[0m', msg)
            return msg

    def setup_logging(self):
        self.log: structlog.BoundLogger = structlog.get_logger()
        timestamper = structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S")
        shared_processors = [structlog.stdlib.add_log_level, timestamper]

        structlog.configure(
            processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.KeyValueRenderer(),
            ],
        )
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.DEBUG if self.config.DEBUG else logging.INFO)

        # Always enable colored logs, adjust level based on DEBUG
        coloredlogs.install(
            level='DEBUG' if self.config.DEBUG else 'INFO',
            logger=root_logger,
            fmt="%(asctime)s | [%(levelname)s] | %(message)s",
            field_styles={
                'asctime': {'color': 'yellow', 'bold': True},
                'levelname': {'color': 'cyan', 'bold': True},
                'message': {'color': 'white'},
            },
            level_styles={
                'debug': {'color': 'blue', 'bold': True},
                'info': {'color': 'green', 'bold': True},
                'warning': {'color': 'yellow', 'bold': True},
                'error': {'color': 'red', 'bold': True},
                'critical': {'color': 'magenta', 'bold': True},
            }
        )        
            
    async def setup_cogs(self):
        start_time = time.time()
        cog_dir = "cogs"
        cog_files = [f[:-3] for f in os.listdir(cog_dir) if f.endswith(".py") and f != "__init__.py"]
        enabled_cogs = []

        for cog_name in cog_files:
            try:
                module = importlib.import_module(f"cogs.{cog_name}")
                metadata = getattr(module, "COG_METADATA", {"enabled": True})
                if self.config.DEBUG:
                    self.log.debug(f"Cog {cog_name} metadata: {metadata}")
                if metadata.get("enabled", True):
                    enabled_cogs.append(cog_name)
                else:
                    self.log.info(f"Skipping disabled cog: {cog_name}")
            except ImportError as e:
                self.log.error(f"Failed to import cog {cog_name}", exc_info=e)

        self.log.info("Starting cog setup", extra={"cog_count": len(enabled_cogs), "cogs": enabled_cogs})

        self.http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=100, ttl_dns_cache=300, enable_cleanup_closed=True)
        )

        cache_config = getattr(self.config, "cache", {})
        self._cache = {
            'commands': {},
            'cooldowns': ExpiringDict(max_len=cache_config.get("cooldowns_max_len", 1000), max_age_seconds=cache_config.get("cooldowns_max_age", 60)),
            'user_settings': ExpiringDict(max_len=cache_config.get("user_settings_max_len", 10000), max_age_seconds=cache_config.get("user_settings_max_age", 300)),
            'guild_settings': ExpiringDict(max_len=cache_config.get("guild_settings_max_len", 1000), max_age_seconds=cache_config.get("guild_settings_max_age", 300)),
        }

        semaphore = asyncio.Semaphore(10)
        cog_tasks = []
        for cog_name in enabled_cogs:
            if cog_name in self.cogs:
                self.log.info(f"Skipping already loaded cog: {cog_name}")
                continue
            self.log.info(f"Preparing to load cog: {cog_name}")
            cog_tasks.append(self._load_cog(cog_name, semaphore))

        results = await asyncio.gather(*cog_tasks, return_exceptions=True)
        for cog_name, result in zip(enabled_cogs, results):
            if isinstance(result, Exception):
                self.log.error(f"Cog {cog_name} failed to load", exc_info=result)

        elapsed_time = time.time() - start_time
        self.log.info("Finished loading cogs", extra={"elapsed_time": f"{elapsed_time:.2f}s"})

    async def _load_cog(self, cog_name: str, semaphore: asyncio.Semaphore):
        async with semaphore:
            try:
                module = importlib.import_module(f"cogs.{cog_name}")
                await module.setup(self)
                self.log.info(f"Successfully loaded cog: {cog_name}")
            except ImportError as e:
                self.log.error(f"Failed to import cog {cog_name} - module not found or invalid", exc_info=e)
                raise
            except AttributeError as e:
                self.log.error(f"Cog {cog_name} is missing a setup function", exc_info=e)
                raise
            except Exception as e:
                self.log.error(f"Error during setup of cog {cog_name}", exc_info=e)
                raise
            
    def run(self, *args, **kwargs):
        self.log.info("Starting bot run")
        if os.name == 'nt' and not isinstance(asyncio.get_event_loop_policy(), asyncio.WindowsSelectorEventLoopPolicy):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            self.log.info("Set WindowsSelectorEventLoopPolicy for compatibility")
        
        try:
            super().run(self._token, *args, **kwargs)
        except KeyboardInterrupt:
            self.log.info("Bot stopped via keyboard interrupt")
            asyncio.run(self.close())
        except Exception as e:
            self.log.error("Failed to start bot", exc_info=e)
            asyncio.run(self.close())
            raise
        finally:
            self.log.info("Bot run completed")

    async def on_connect(self):
        self.log.info("Bot connected to Discord")
        latency = self.latency * 1000
        self.log.info(f"Gateway latency: {latency:.2f}ms")
        try:
            await self.setup_cogs()
        except Exception as e:
            self.log.error("Failed to setup cogs during on_connect", exc_info=e)
            raise

    async def on_ready(self):
        start_time = time.time()
        self.log.info("Bot is ready!")
        self.log.info(f"Logged in as {self.user.name} (ID: {self.user.id})")
        
        guild_count = len(self.guilds)
        self.log.info(f"Connected to {guild_count} guilds")
        
        # Sync commands with Discord
        try:
            # Sync commands globally
            synced = await self.sync_commands()
            if synced is not None:
                self.log.info(f"Synced {len(synced)} application commands")
            else:
                self.log.info("Commands were already synced")
        except Exception as e:
            self.log.error(f"Failed to sync application commands: {e}")
        
        app_commands = [cmd.name for cmd in self.application_commands]
        self.log.info(f"Registered application commands: {app_commands}")
        
        self.log.info(f"Pycord version: {discord.__version__}")
        
        elapsed_time = time.time() - start_time
        self.log.info(f"Ready event processed in {elapsed_time:.2f}s")
            
    async def close(self):
        self.log.info("Initiating bot shutdown")
        try:
            if hasattr(self, "http_session") and not self.http_session.closed:
                await self.http_session.close()
                self.log.info("Closed HTTP session")
            
            self._cache.clear()
            self.log.info("Cleared caches")
                
        except Exception as e:
            self.log.error("Error during shutdown", exc_info=e)
        finally:
            await super().close()
            self.log.info("Bot shutdown complete")