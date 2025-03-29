import asyncio
import logging
import os
import platform
import time
from typing import Any, Dict, List, Optional

import psutil

logger = logging.getLogger("bot")


class ShardManager:
    """
    Advanced shard management with features for:
    - Inter-shard communication
    - Shard health monitoring
    - Shard status reporting
    - Automatic shard failure detection
    """

    def __init__(self, bot, mongodb=None):
        self.bot = bot
        self.mongodb = mongodb
        self._shard_health_checks = {}
        self._shard_statuses = {}
        self._shard_events = asyncio.Queue()
        self._monitor_task = None
        self._cluster_id = getattr(bot.config, "CLUSTER_ID", 0)
        self._total_clusters = getattr(bot.config, "TOTAL_CLUSTERS", 1)
        self._lock = asyncio.Lock()

        # Metrics
        self._metrics = {
            "events_sent": 0,
            "events_received": 0,
            "health_checks": 0,
            "start_time": time.time(),
        }

        # Performance metrics
        self._process = psutil.Process()

    def start_monitoring(self):
        """Prepare shard monitoring task"""
        # We'll just prepare the monitoring, but not start the task yet
        # The actual task will be started by start_monitoring_async
        logger.info("Prepared shard monitoring")

    async def start_monitoring_async(self):
        """Start shard monitoring task (async version)"""
        if self._monitor_task is None:
            self._monitor_task = asyncio.create_task(self._monitor_shards())
            logger.info("Started shard monitoring task")

    async def _monitor_shards(self):
        """Monitor shard health and performance"""
        try:
            while True:
                await self._update_shard_status()
                await asyncio.sleep(30)  # Update every 30 seconds
                self._metrics["health_checks"] += 1
        except asyncio.CancelledError:
            logger.info("Shard monitoring task cancelled")
        except Exception as e:
            logger.error(f"Error in shard monitoring task: {e}")

    async def _update_shard_status(self):
        """Update status of this bot's shards in the database"""
        if not self.mongodb:
            return

        try:
            # Get memory usage
            memory_info = self._process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024

            # Get CPU usage
            cpu_percent = self._process.cpu_percent(interval=0.5)

            # Get shard latencies
            latencies = {}
            for shard_id in self.bot.shard_ids or [0]:
                latency = self.bot.latency
                if hasattr(self.bot, "get_shard"):
                    shard = self.bot.get_shard(shard_id)
                    if shard:
                        latency = shard.latency
                latencies[str(shard_id)] = latency

            # Calculate uptime
            uptime = time.time() - self._metrics["start_time"]

            # Gather guild count per shard
            guild_count = {}
            for guild in self.bot.guilds:
                shard_id = guild.shard_id
                guild_count[str(shard_id)] = guild_count.get(str(shard_id), 0) + 1

            # Update statuses in DB
            status_data = {
                "cluster_id": self._cluster_id,
                "shard_ids": self.bot.shard_ids or [0],
                "status": "online",
                "latencies": latencies,
                "memory_mb": memory_mb,
                "cpu_percent": cpu_percent,
                "guild_count": guild_count,
                "uptime": uptime,
                "last_updated": time.time(),
                "bot_version": getattr(self.bot, "version", "1.0.0"),
                "python_version": platform.python_version(),
                "system": f"{platform.system()} {platform.release()}",
                "process_id": os.getpid(),
                "thread_count": self._process.num_threads(),
            }

            # Save to DB for dashboard/monitoring
            await self.mongodb.shard_status.update_one(
                {"cluster_id": self._cluster_id}, {"$set": status_data}, upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating shard status: {e}")

    async def get_all_shard_statuses(self) -> List[Dict[str, Any]]:
        """Get status of all shards across all clusters"""
        if not self.mongodb:
            return []

        try:
            # Get statuses from last 5 minutes only
            cutoff_time = time.time() - 300
            cursor = self.mongodb.shard_status.find({"last_updated": {"$gt": cutoff_time}})

            # Convert to list
            statuses = await cursor.to_list(length=100)
            return statuses
        except Exception as e:
            logger.error(f"Error getting all shard statuses: {e}")
            return []

    async def get_guild_shard(self, guild_id: int) -> Optional[int]:
        """Calculate which shard a guild belongs to"""
        try:
            if hasattr(self.bot, "get_shard_id"):
                return self.bot.get_shard_id(guild_id)

            # Manual calculation according to Discord's sharding formula
            # guild_id % num_shards = shard_id
            shard_count = self.bot.shard_count or 1
            return guild_id % shard_count
        except Exception as e:
            logger.error(f"Error calculating guild shard: {e}")
            return None

    async def send_cross_shard_event(
        self,
        event_type: str,
        data: Dict[str, Any],
        target_shards: Optional[List[int]] = None,
        include_self: bool = False,
    ) -> bool:
        """
        Send an event to other shards/clusters

        Args:
            event_type: Type of event (e.g., "guild_update", "member_join")
            data: Event data
            target_shards: Specific target shards (None = all)
            include_self: Whether to process the event locally too
        """
        if not self.mongodb:
            return False

        try:
            current_time = time.time()

            # Create event document
            event_doc = {
                "event_type": event_type,
                "data": data,
                "source_cluster": self._cluster_id,
                "target_shards": target_shards,
                "created_at": current_time,
                "expires_at": current_time + 300,  # 5 minute TTL
                "processed_by": [] if include_self else [self._cluster_id],
            }

            # Insert to database
            await self.mongodb.shard_events.insert_one(event_doc)

            self._metrics["events_sent"] += 1

            # If needed, process event locally too
            if include_self:
                await self._process_event(event_type, data)

            return True
        except Exception as e:
            logger.error(f"Error sending cross-shard event: {e}")
            return False

    async def process_pending_events(self) -> int:
        """Process pending events from other shards"""
        if not self.mongodb:
            return 0

        try:
            # Get all events not processed by this cluster
            current_time = time.time()
            query = {
                "expires_at": {"$gt": current_time},
                "processed_by": {"$ne": self._cluster_id},
                "$or": [
                    {"target_shards": None},  # Events for all shards
                    {"target_shards": {"$in": self.bot.shard_ids or [0]}},  # Events for specific shards
                ],
            }

            # Find events
            cursor = self.mongodb.shard_events.find(query)
            events = await cursor.to_list(length=100)

            # Process each event
            processed_count = 0
            for event in events:
                event_type = event["event_type"]
                data = event["data"]

                # Process the event
                await self._process_event(event_type, data)

                # Mark as processed
                await self.mongodb.shard_events.update_one(
                    {"_id": event["_id"]}, {"$addToSet": {"processed_by": self._cluster_id}}
                )

                processed_count += 1
                self._metrics["events_received"] += 1

            # Clean up old events (could be done less frequently)
            await self.mongodb.shard_events.delete_many({"expires_at": {"$lt": current_time}})

            return processed_count
        except Exception as e:
            logger.error(f"Error processing pending events: {e}")
            return 0

    async def _process_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Process a received event based on type"""
        try:
            if event_type == "cache_invalidate":
                # Invalidate cache entries
                if hasattr(self.bot, "cache_manager"):
                    namespace = data.get("namespace")
                    key = data.get("key")

                    if namespace and key:
                        await self.bot.cache_manager.delete(key, namespace)
                    elif namespace:
                        await self.bot.cache_manager.invalidate_namespace(namespace)

            elif event_type == "member_update":
                # Handle member update events
                guild_id = data.get("guild_id")
                user_id = data.get("user_id")

                if guild_id and user_id:
                    guild = self.bot.get_guild(guild_id)
                    if guild:
                        member = guild.get_member(user_id)
                        if member:
                            # Force member update
                            await guild.fetch_member(user_id)

            elif event_type == "guild_update":
                # Handle guild update events
                guild_id = data.get("guild_id")

                if guild_id:
                    guild = self.bot.get_guild(guild_id)
                    if guild:
                        # Force guild fetch
                        await self.bot.fetch_guild(guild_id)

            elif event_type == "command_disable":
                # Disable a command across all shards
                command_name = data.get("command_name")

                if command_name and hasattr(self.bot, "disable_command"):
                    await self.bot.disable_command(command_name)

            elif event_type == "command_enable":
                # Enable a command across all shards
                command_name = data.get("command_name")

                if command_name and hasattr(self.bot, "enable_command"):
                    await self.bot.enable_command(command_name)

            # Handle other event types as needed...

        except Exception as e:
            logger.error(f"Error processing event {event_type}: {e}")

    def get_metrics(self) -> Dict[str, Any]:
        """Get shard manager metrics"""
        return {
            "events_sent": self._metrics["events_sent"],
            "events_received": self._metrics["events_received"],
            "health_checks": self._metrics["health_checks"],
            "uptime": time.time() - self._metrics["start_time"],
            "cluster_id": self._cluster_id,
            "total_clusters": self._total_clusters,
            "managed_shards": self.bot.shard_ids or [0],
        }

    @staticmethod
    def calculate_shard_id(guild_id: int, shard_count: int) -> int:
        """Calculate which shard a guild belongs to"""
        return (guild_id >> 22) % shard_count
