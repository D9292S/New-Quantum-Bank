import asyncio
import logging
import os
import platform
from datetime import datetime

import discord
import psutil
from discord import Option
from discord.ext import commands

COG_METADATA = {
    "name": "admin_performance",
    "enabled": True,
    "version": "1.0",
    "description": "Administrative commands for performance monitoring and management"
}

async def setup(bot):
    """Add the cog to the bot"""
    # Create the cog instance
    cog = AdminPerformance(bot)
    bot.add_cog(cog)
    # Explicitly call cog_load to handle any async initialization
    await cog.cog_load()

class AdminPerformance(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger('performance')
        # Initialize maintenance mode attributes
        self.bot.maintenance_mode = False
        self.bot.maintenance_message = None
        # Initialize dependency attributes
        self.perf_monitor = None
        # Periods for statistics (in seconds)
        self.periods = {
            "5m": 300,
            "15m": 900,
            "1h": 3600,
            "24h": 86400
        }

    async def cog_load(self):
        """Called when the cog is loaded"""
        self.logger.info("Admin Performance cog loaded")
        
        # Try to get the performance monitor from the mongo cog instead
        mongo_cog = self.bot.get_cog('Database')
        
        # Initialize performance_monitor attribute if not already exists
        if not hasattr(self.bot, 'performance_monitor'):
            if mongo_cog and hasattr(mongo_cog, 'performance_monitor'):
                self.bot.performance_monitor = mongo_cog.performance_monitor
                self.logger.info("Performance monitor initialized from Database cog")
            else:
                # Create an empty performance monitor as a fallback
                from cogs.mongo import PerformanceMonitor
                self.bot.performance_monitor = PerformanceMonitor()
                self.logger.warning("Created fallback performance monitor")
        
        # We'll try to reset metrics later once performance_monitor is available
        self._metrics_reset_pending = True
        
        # Try to initialize dependencies - will retry if not available
        asyncio.create_task(self._init_dependencies())

    async def _init_dependencies(self):
        """Initialize dependencies with retry logic"""
        # Wait for bot to be fully ready
        if not self.bot.is_ready():
            await self.bot.wait_until_ready()
        
        # Wait a bit to allow other cogs to load
        await asyncio.sleep(2)
        
        attempts = 0
        max_attempts = 5
        retry_delay = 2  # seconds
        
        while attempts < max_attempts:
            # First check if bot.performance_monitor is already set
            if hasattr(self.bot, 'performance_monitor') and self.bot.performance_monitor is not None:
                self.logger.info("Found existing performance_monitor attribute")
                break
            
            # Try to get performance monitor from Database cog
            mongo_cog = self.bot.get_cog('Database')
            if mongo_cog and hasattr(mongo_cog, 'performance_monitor'):
                self.bot.performance_monitor = mongo_cog.performance_monitor
                self.logger.info("Successfully initialized performance monitor from Database cog")
                
                # Reset metrics if needed
                if self._metrics_reset_pending and hasattr(self.bot.performance_monitor, 'reset_metrics'):
                    try:
                        self.bot.performance_monitor.reset_metrics()
                        self.logger.info("Performance metrics reset on startup")
                        self._metrics_reset_pending = False
                    except Exception as e:
                        self.logger.error(f"Failed to reset metrics: {e}")
                break
            
            attempts += 1
            if attempts < max_attempts:
                self.logger.warning(f"Performance monitor not found yet, retrying in {retry_delay}s ({attempts}/{max_attempts})")
                await asyncio.sleep(retry_delay)
            else:
                # Create a fallback if all attempts failed
                from cogs.mongo import PerformanceMonitor
                self.bot.performance_monitor = PerformanceMonitor()
                self.logger.warning("Created fallback performance monitor after maximum attempts")
            
        # Even if initialization fails, don't raise an error
        # Individual commands will handle missing dependencies

    @commands.Cog.listener()
    async def on_application_command(self, ctx):
        """Intercept commands to check for maintenance mode"""
        # Skip checks for admin commands and in DMs
        if not ctx.guild:
            return
            
        # Check if user is owner using a safer approach
        is_owner = False
        try:
            if hasattr(self.bot, "is_owner") and callable(self.bot.is_owner):
                is_owner = await self.bot.is_owner(ctx.author)
        except Exception:
            # Fallback if is_owner check fails
            is_owner = False
            
        if is_owner:
            return

        # Check if in maintenance mode
        if getattr(self.bot, 'maintenance_mode', False):
            # Allow admins to bypass maintenance mode
            if not ctx.author.guild_permissions.administrator:
                message = getattr(self.bot, 'maintenance_message', 
                                 "Bot is currently in maintenance mode. Please try again later.")
                await ctx.respond(message, ephemeral=True)
                # Cancel command execution
                return False

    @discord.slash_command(description="View detailed status of all bot shards")
    @commands.has_permissions(administrator=True)
    async def shard_status(self, ctx):
        """Display detailed information about all shards and clusters"""
        # Create embed
        embed = discord.Embed(
            title="🔹 Shard Status",
            description="Running with sharding configuration",
            color=discord.Color.blue()
        )
        
        # Get shard information
        if self.bot.shard_count > 1:
            for shard_id in range(self.bot.shard_count):
                is_current = self.bot.shard_id == shard_id
                latency = self.bot.latency if is_current else "N/A"
                latency_str = f"{latency*1000:.2f}ms" if isinstance(latency, float) else "N/A"
                
                # Count guilds in this shard
                if is_current:
                    guild_count = len([g for g in self.bot.guilds if g.shard_id == shard_id])
                else:
                    guild_count = "N/A"
                
                # Add to embed
                embed.add_field(
                    name=f"Shard {shard_id}" + (" (current)" if is_current else ""),
                    value=(
                        f"Status: {'Connected' if is_current else 'Unknown'}\n"
                        f"Latency: {latency_str}\n"
                        f"Guilds: {guild_count}"
                    ),
                    inline=True
                )
        else:
            # No sharding
            embed.add_field(
                name="Single Shard Mode",
                value=(
                    f"Status: Connected\n"
                    f"Latency: {self.bot.latency*1000:.2f}ms\n"
                    f"Guilds: {len(self.bot.guilds)}"
                ),
                inline=False
            )
        
        # Add cluster information if available
        if hasattr(self.bot, 'config') and self.bot.config.CLUSTER_ID is not None:
            embed.add_field(
                name="Cluster Information",
                value=(
                    f"Cluster ID: {self.bot.config.CLUSTER_ID}\n"
                    f"Total Clusters: {self.bot.config.TOTAL_CLUSTERS}\n"
                    f"Shards in Cluster: {self.bot.config.SHARD_IDS}"
                ),
                inline=False
            )
        
        await ctx.respond(embed=embed)

    @discord.slash_command(description="Check memory and CPU usage of the bot")
    @commands.has_permissions(administrator=True)
    async def resource_usage(self, ctx):
        """Display detailed resource usage statistics"""
        # Send initial response
        await ctx.defer()
        
        # Get basic system info
        process = psutil.Process()
        memory_usage = process.memory_info().rss / (1024 * 1024)  # Convert to MB
        cpu_percent = process.cpu_percent(interval=0.5)
        thread_count = process.num_threads()
        
        # Get uptime
        uptime_seconds = (datetime.now() - datetime.fromtimestamp(process.create_time())).total_seconds()
        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{int(days)}d {int(hours)}h {int(minutes)}m {int(seconds)}s"
        
        # Create embed
        embed = discord.Embed(
            title="📊 Resource Usage",
            description="Current system resource utilization",
            color=discord.Color.green()
        )
        
        # System resources section
        embed.add_field(
            name="🖥️ System Resources",
            value=(
                f"Memory Usage: {memory_usage:.2f} MB\n"
                f"CPU Usage: {cpu_percent:.2f}%\n"
                f"Threads: {thread_count}\n"
                f"Uptime: {uptime_str}"
            ),
            inline=False
        )
        
        # Bot statistics section
        total_users = sum(guild.member_count for guild in self.bot.guilds)
        embed.add_field(
            name="🤖 Bot Statistics",
            value=(
                f"Guilds: {len(self.bot.guilds)}\n"
                f"Users: {total_users}\n"
                f"Commands: {len(self.bot.application_commands)}\n"
                f"Shards: {self.bot.shard_count}"
            ),
            inline=False
        )
        
        # System info section
        embed.add_field(
            name="💻 System Info",
            value=(
                f"OS: {platform.system()} {platform.release()}\n"
                f"Python: {platform.python_version()}\n"
                f"Discord.py: {discord.__version__}\n"
                f"Performance Mode: {self.bot.config.PERFORMANCE_MODE if hasattr(self.bot, 'config') else 'N/A'}"
            ),
            inline=False
        )
        
        # Add disk info
        try:
            disk = psutil.disk_usage('/')
            embed.add_field(
                name="💾 Disk Usage",
                value=(
                    f"Total: {disk.total / (1024**3):.2f} GB\n"
                    f"Used: {disk.used / (1024**3):.2f} GB\n"
                    f"Free: {disk.free / (1024**3):.2f} GB\n"
                    f"Percent: {disk.percent}%"
                ),
                inline=False
            )
        except Exception as e:
            self.logger.error(f"Error getting disk usage: {e}")
            embed.add_field(
                name="💾 Disk Usage",
                value="Error retrieving disk information",
                inline=False
            )
        
        await ctx.followup.send(embed=embed)

    @discord.slash_command(description="Reload a specific cog")
    @commands.has_permissions(administrator=True)
    async def reload_cog(self, ctx, 
                         cog_name: discord.Option(str, "Name of the cog to reload", 
                         choices=["accounts", "admin", "admin_performance", "anime", "mongo", "performance_monitor", "utility"])):
        """Reload a specific cog without restarting the bot"""
        try:
            # Send initial response
            await ctx.respond(f"🔄 Attempting to reload the `{cog_name}` cog...")
            
            # Format cog name
            full_cog_name = f"cogs.{cog_name}"
            
            # Attempt to reload the cog
            try:
                # Unload first if it's loaded
                for loaded_cog in list(self.bot.extensions.keys()):
                    if loaded_cog.lower() == full_cog_name.lower():
                        await self.bot.unload_extension(loaded_cog)
                        break
                
                # Then load it again - properly await the extension loading
                await self.bot.load_extension(full_cog_name)
                
                # Inform of success
                await ctx.edit_original_response(content=f"✅ Successfully reloaded the `{cog_name}` cog!")
                self.logger.info(f"Cog {cog_name} reloaded by {ctx.author} ({ctx.author.id})")
            except Exception as e:
                # Handle loading error
                await ctx.edit_original_response(content=f"❌ Error reloading cog: {str(e)}")
                self.logger.error(f"Error reloading cog {cog_name}: {str(e)}")
                
        except Exception as e:
            await ctx.respond(f"❌ An unexpected error occurred: {str(e)}")

    @discord.slash_command(description="Toggle maintenance mode")
    @commands.has_permissions(administrator=True)
    async def maintenance_mode(self, ctx, 
                             mode: discord.Option(bool, "Enable or disable maintenance mode"),
                             message: discord.Option(str, "Custom maintenance message", required=False)):
        """Put the bot in maintenance mode with custom message"""
        try:
            if mode:
                # Enable maintenance mode
                self.bot.maintenance_mode = True
                self.bot.maintenance_message = message or "Bot is currently undergoing maintenance. Please try again later."
                
                # Update bot status
                activity = discord.Activity(type=discord.ActivityType.playing, name="🛠️ Maintenance Mode")
                await self.bot.change_presence(activity=activity, status=discord.Status.dnd)
                
                # Respond to command
                embed = discord.Embed(
                    title="🛠️ Maintenance Mode Enabled",
                    description="The bot is now in maintenance mode.",
                    color=discord.Color.orange()
                )
                embed.add_field(name="Maintenance Message", value=self.bot.maintenance_message, inline=False)
                
                await ctx.respond(embed=embed)
                
                # Log the maintenance mode activation
                self.logger.warning(f"Maintenance mode enabled by {ctx.author} ({ctx.author.id})")
                
            else:
                # Disable maintenance mode
                self.bot.maintenance_mode = False
                self.bot.maintenance_message = None
                
                # Restore normal status
                activity_status = getattr(self.bot.config, "ACTIVITY_STATUS", "Quantum Bank | /help") if hasattr(self.bot, "config") else "Quantum Bank | /help"
                activity = discord.Activity(type=discord.ActivityType.listening, name=activity_status)
                await self.bot.change_presence(activity=activity, status=discord.Status.online)
                
                # Respond to command
                embed = discord.Embed(
                    title="✅ Maintenance Mode Disabled",
                    description="The bot has returned to normal operation.",
                    color=discord.Color.green()
                )
                
                await ctx.respond(embed=embed)
                
                # Log the maintenance mode deactivation
                self.logger.info(f"Maintenance mode disabled by {ctx.author} ({ctx.author.id})")
                
        except Exception as e:
            await ctx.respond(f"❌ Error toggling maintenance mode: {str(e)}")

    @discord.slash_command(description="View cache statistics and performance metrics")
    @commands.has_permissions(administrator=True)
    async def cache_stats(self, ctx):
        """View detailed cache statistics and performance metrics"""
        try:
            # Check if performance monitor is initialized
            if not self.perf_monitor:
                # Try to get it again, in case it wasn't available during cog_load
                self.perf_monitor = self.bot.get_cog('PerformanceMonitor')
                
            if not self.perf_monitor:
                await ctx.respond("❌ Performance monitor cog is not loaded or not available.")
                return
                
            # Get cache manager from accounts cog, if available
            accounts_cog = self.bot.get_cog('Account')
            
            # Create embed
            embed = discord.Embed(
                title="🔄 Cache Statistics",
                description="Performance metrics for the bot's caching system",
                color=discord.Color.blue()
            )
            
            # Try to get detailed cache stats if available
            cache_stats = {}
            try:
                if hasattr(self.perf_monitor, 'get_cache_stats') and callable(self.perf_monitor.get_cache_stats):
                    cache_stats = await self.perf_monitor.get_cache_stats()
            except Exception as e:
                self.logger.error(f"Error getting cache stats: {e}")
                cache_stats = {}
                
            if cache_stats:
                # Add cache hit/miss stats
                hit_rate = cache_stats.get('hit_rate', 0) * 100
                embed.add_field(
                    name="🎯 Cache Performance",
                    value=(
                        f"Hit Rate: {hit_rate:.2f}%\n"
                        f"Hits: {cache_stats.get('hits', 0)}\n"
                        f"Misses: {cache_stats.get('misses', 0)}\n"
                        f"Total Lookups: {cache_stats.get('total_lookups', 0)}"
                    ),
                    inline=False
                )
                
                # Add size stats
                embed.add_field(
                    name="📦 Cache Size",
                    value=(
                        f"Items Cached: {cache_stats.get('items_cached', 0)}\n"
                        f"Memory Usage: {cache_stats.get('memory_usage', 0):.2f} MB\n"
                        f"Average Item Size: {cache_stats.get('avg_item_size', 0):.2f} KB"
                    ),
                    inline=False
                )
                
                # Add namespace stats
                namespaces = cache_stats.get('namespaces', {})
                namespace_text = ""
                for name, count in namespaces.items():
                    namespace_text += f"{name}: {count} items\n"
                
                embed.add_field(
                    name="🏷️ Cache Namespaces",
                    value=namespace_text or "No namespace data available",
                    inline=False
                )
                
                # Add cache efficiency
                latency_improvement = cache_stats.get('avg_latency_improvement', 0)
                embed.add_field(
                    name="⚡ Efficiency Metrics",
                    value=(
                        f"Avg. Latency Improvement: {latency_improvement:.2f}ms\n"
                        f"Cache Benefit: {cache_stats.get('cache_benefit', 0):.1f}x faster\n"
                        f"Last Cleanup: {cache_stats.get('last_cleanup', 'Never')}"
                    ),
                    inline=False
                )
            # Basic cache info if detailed stats not available
            elif accounts_cog and hasattr(accounts_cog, 'cache'):
                cache = accounts_cog.cache
                if cache:
                    embed.add_field(
                        name="🔄 Cache Status",
                        value="Cache is active but detailed metrics unavailable",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="⚠️ Cache Status",
                        value="Cache appears to be inactive or not initialized",
                        inline=False
                    )
            else:
                embed.add_field(
                    name="❌ Cache Information",
                    value="Cache statistics are not available. Make sure performance monitoring is enabled.",
                    inline=False
                )
            
            # Performance monitor metrics - safely get system metrics
            metrics = {}
            try:
                if hasattr(self.bot, 'get_system_metrics') and callable(self.bot.get_system_metrics):
                    metrics = self.bot.get_system_metrics() or {}
            except Exception as e:
                self.logger.error(f"Error getting system metrics: {e}")
                
            if metrics:
                embed.add_field(
                    name="📈 Current Performance",
                    value=(
                        f"Memory: {metrics.get('memory_usage_mb', 0):.2f} MB\n"
                        f"CPU: {metrics.get('cpu_percent', 0):.2f}%\n"
                        f"Latency: {metrics.get('latency', 0):.2f}ms\n"
                        f"Commands/min: {metrics.get('commands_per_minute', 0):.1f}"
                    ),
                    inline=False
                )
            
            await ctx.respond(embed=embed)
            
        except Exception as e:
            self.logger.error(f"Error retrieving cache statistics: {e}")
            await ctx.respond(f"❌ Error retrieving cache statistics: {str(e)}")

    @commands.is_owner()
    @commands.slash_command(name="perf", description="Monitor bot performance")
    async def performance(self, ctx):
        """Root command for performance monitoring"""
        pass  # This is a parent command

    @commands.is_owner()
    @commands.slash_command(name="perf_metrics", description="Show bot performance metrics")
    async def performance_metrics(self, ctx, period: discord.Option(str, "Time period", choices=["5m", "15m", "1h", "24h"]) = "15m"):
        """Show performance metrics for various bot operations"""
        try:
            self.logger.info(f"Performance metrics requested by {ctx.author.name} for period {period}")
            
            # Check if performance monitor is available
            if not hasattr(self.bot, 'performance_monitor') or self.bot.performance_monitor is None:
                await ctx.respond("⚠️ Performance monitoring system is not available.", ephemeral=True)
                return
            
            # Try one more time to get it if needed
            if self.bot.performance_monitor is None and self.perf_monitor:
                self.bot.performance_monitor = self.perf_monitor
            
            # Get the corresponding time window in seconds
            time_window = self.periods.get(period, 900)  # Default to 15 minutes
            
            # Get performance metrics
            metrics = self.bot.performance_monitor.get_metrics(time_window)
            
            if not metrics:
                await ctx.respond("No performance data available for the selected period.")
                return
            
            # Create formatted output
            embed = discord.Embed(
                title=f"Bot Performance Metrics ({period})",
                description=f"Statistics for the last {self._format_time(time_window)}",
                color=discord.Color.blue()
            )
            
            # Add overall statistics
            total_ops = sum(metric.get("count", 0) for metric in metrics.values())
            avg_times = [metric.get("avg_time", 0) for metric in metrics.values() if "avg_time" in metric]
            overall_avg = sum(avg_times) / len(avg_times) if avg_times else 0
            
            embed.add_field(
                name="Summary",
                value=f"Total Operations: {total_ops}\n"
                     f"Overall Avg Response: {overall_avg:.2f}ms",
                inline=False
            )
            
            # Add specifics for each operation type
            for op_name, metric in sorted(metrics.items(), key=lambda x: x[1].get("avg_time", 0), reverse=True):
                if metric.get("count", 0) == 0:
                    continue
                
                embed.add_field(
                    name=f"{op_name.replace('_', ' ').title()}",
                    value=f"Count: {metric.get('count', 0)}\n"
                         f"Avg: {metric.get('avg_time', 0):.2f}ms\n"
                         f"Max: {metric.get('max_time', 0):.2f}ms",
                    inline=True
                )
            
            await ctx.respond(embed=embed)
            
        except Exception as e:
            await ctx.respond("An error occurred while fetching performance metrics.", ephemeral=True)
            self.logger.error(f"Error in performance_metrics command: {str(e)}")

    @commands.is_owner()
    @commands.slash_command(name="perf_reset", description="Reset performance metrics")
    async def reset_metrics(self, ctx):
        """Reset all performance metrics"""
        try:
            # Check if performance monitor is available
            if not hasattr(self.bot, 'performance_monitor') or self.bot.performance_monitor is None:
                await ctx.respond("⚠️ Performance monitoring system is not available.", ephemeral=True)
                return
            
            # Try one more time to get it if needed
            if self.bot.performance_monitor is None and self.perf_monitor:
                self.bot.performance_monitor = self.perf_monitor
            
            self.bot.performance_monitor.reset_metrics()
            self.logger.info(f"Performance metrics reset by {ctx.author.name}")
            await ctx.respond("✅ Performance metrics have been reset.", ephemeral=True)
        except Exception as e:
            await ctx.respond("An error occurred while resetting metrics.", ephemeral=True)
            self.logger.error(f"Error in reset_metrics command: {str(e)}")

    @commands.is_owner()
    @commands.slash_command(name="perf_slow", description="Show slowest operations")
    async def slow_operations(self, ctx, threshold: discord.Option(float, "Time threshold in ms", min_value=50.0, max_value=10000.0) = 500.0, count: discord.Option(int, "Number of operations to show", min_value=1, max_value=25) = 10):
        """Show the slowest operations recorded"""
        try:
            self.logger.info(f"Slow operations requested by {ctx.author.name} (threshold: {threshold}ms, count: {count})")
            
            # Check if performance monitor is available
            if not hasattr(self.bot, 'performance_monitor') or self.bot.performance_monitor is None:
                await ctx.respond("⚠️ Performance monitoring system is not available.", ephemeral=True)
                return
            
            # Try one more time to get it if needed
            if self.bot.performance_monitor is None and self.perf_monitor:
                self.bot.performance_monitor = self.perf_monitor
            
            # Get slow operations
            slow_ops = self.bot.performance_monitor.get_slow_operations(threshold, count)
            
            if not slow_ops:
                await ctx.respond(f"No operations slower than {threshold}ms found.", ephemeral=True)
                return
            
            # Create formatted output
            embed = discord.Embed(
                title=f"Slow Operations (>{threshold}ms)",
                description=f"Showing up to {count} slowest operations",
                color=discord.Color.gold()
            )
            
            for i, op in enumerate(slow_ops, 1):
                timestamp = op.get("timestamp", datetime.utcnow()).strftime("%Y-%m-%d %H:%M:%S")
                embed.add_field(
                    name=f"{i}. {op.get('operation', 'Unknown')} ({op.get('execution_time', 0):.2f}ms)",
                    value=f"Time: {timestamp}\n"
                         f"Context: {op.get('context', 'N/A')}",
                    inline=False
                )
            
            await ctx.respond(embed=embed)
            
        except Exception as e:
            await ctx.respond("An error occurred while fetching slow operations.", ephemeral=True)
            self.logger.error(f"Error in slow_operations command: {str(e)}")

    @commands.is_owner()
    @commands.slash_command(name="logs", description="View bot logs")
    async def logs(self, ctx, 
                  category: discord.Option(str, "Log category", 
                                          choices=["bot", "commands", "database", "performance", "errors"]) = "bot",
                  lines: discord.Option(int, "Number of lines to display", min_value=5, max_value=50) = 20):
        """Display recent log entries from specified category"""
        try:
            log_file = f"logs/{category}.log"
            
            if not os.path.exists(log_file):
                await ctx.respond(f"Log file for '{category}' does not exist or is empty.", ephemeral=True)
                return
            
            self.logger.info(f"Logs requested by {ctx.author.name}: category={category}, lines={lines}")
            
            # Read the last N lines from the log file
            log_lines = self._read_last_n_lines(log_file, lines)
            
            if not log_lines:
                await ctx.respond(f"No log entries found for '{category}'.", ephemeral=True)
                return
            
            # Format the log entries
            formatted_logs = "```\n"
            for line in log_lines:
                # Truncate long lines to prevent discord message size issues
                if len(line) > 100:
                    line = line[:97] + "..."
                formatted_logs += f"{line}\n"
            formatted_logs += "```"
            
            embed = discord.Embed(
                title=f"{category.title()} Logs",
                description=f"Last {len(log_lines)} log entries",
                color=discord.Color.blue()
            )
            
            await ctx.respond(formatted_logs, ephemeral=True)
            
        except Exception as e:
            await ctx.respond(f"An error occurred while retrieving logs: {str(e)}", ephemeral=True)
            self.logger.error(f"Error in logs command: {str(e)}")

    def _read_last_n_lines(self, file_path, n):
        """Read the last N lines from a file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                lines = file.readlines()
                return lines[-n:] if len(lines) >= n else lines
        except Exception as e:
            self.logger.error(f"Error reading log file {file_path}: {str(e)}")
            return []

    def _format_time(self, seconds):
        """Format seconds into a human-readable time string"""
        if seconds < 60:
            return f"{seconds} seconds"
        elif seconds < 3600:
            return f"{seconds // 60} minutes"
        elif seconds < 86400:
            hours = seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''}"
        else:
            days = seconds // 86400
            return f"{days} day{'s' if days != 1 else ''}"

    @commands.is_owner()
    @commands.slash_command(name="clear_logs", description="Clear logs for a specific category")
    async def clear_logs(self, ctx, 
                        category: Option(str, "Log category", 
                                         choices=["all", "bot", "commands", "database", "performance", "errors"]) = "all"):
        """Clear log files for a specified category"""
        try:
            self.logger.info(f"Log clearing requested by {ctx.author.name}: category={category}")
            
            if category == "all":
                # Clear all log files
                categories = ["bot", "commands", "database", "performance", "errors"]
                cleared = []
                
                for cat in categories:
                    log_file = f"logs/{cat}.log"
                    if os.path.exists(log_file):
                        with open(log_file, 'w') as f:
                            f.write("")
                        cleared.append(cat)
                        
                if cleared:
                    await ctx.respond(f"✅ Cleared logs for categories: {', '.join(cleared)}", ephemeral=True)
                else:
                    await ctx.respond("No log files found to clear.", ephemeral=True)
            else:
                # Clear specific category
                log_file = f"logs/{category}.log"
                
                if os.path.exists(log_file):
                    with open(log_file, 'w') as f:
                        f.write("")
                    await ctx.respond(f"✅ Cleared logs for category: {category}", ephemeral=True)
                else:
                    await ctx.respond(f"Log file for '{category}' does not exist.", ephemeral=True)
                
        except Exception as e:
            await ctx.respond(f"An error occurred while clearing logs: {str(e)}", ephemeral=True)
            self.logger.error(f"Error in clear_logs command: {str(e)}") 