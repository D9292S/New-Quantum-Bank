import discord
from discord.ext import commands, tasks
import time
import datetime
import asyncio
import psutil
import platform
import matplotlib.pyplot as plt
import io
from typing import Dict, List, Any, Optional
import logging
import os
from helpers import cached
import random

logger = logging.getLogger('performance')

COG_METADATA = {
    "name": "performance_monitor",
    "enabled": True,
    "version": "1.0",
    "description": "Performance monitoring and benchmarking"
}

async def setup(bot):
    # Create the cog instance
    cog = PerformanceMonitor(bot)
    bot.add_cog(cog)
    await cog.cog_load()

class PerformanceMonitor(commands.Cog):
    """Performance monitoring and benchmarking tools"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db = None
        self.logger = logging.getLogger('performance')
        self._metrics_history = []
        self._start_time = time.time()
        self._last_command_time = {}
        self._command_counts = {}
        self._command_times = {}
        self._process = psutil.Process()
        
        # Tracking intervals (in minutes)
        self._intervals = {
            "1h": 60,    # 1 hour: 1 sample per minute
            "6h": 360,   # 6 hours: 1 sample per 6 minutes
            "24h": 1440, # 24 hours: 1 sample per 24 minutes
            "7d": 10080  # 7 days: 1 sample per 168 minutes
        }
        
        # Initialize metrics storage
        self._interval_data = {interval: [] for interval in self._intervals}
        
    async def cog_load(self):
        """Called when the cog is loaded"""
        self.db = self.bot.get_cog('Database')
        if self.db:
            # Create indexes for metrics collection
            await self._setup_indexes()
        
        # Don't start tasks yet, wait for bot's on_ready event
        # Tasks will be started by start_tasks method
        
    async def _setup_indexes(self):
        """Set up database indexes for metrics collection"""
        if not self.db:
            self.logger.warning("Database cog not available, skipping index creation")
            return
            
        try:
            # Make sure db.db is properly initialized
            if not hasattr(self.db, 'db') or self.db.db is None:
                self.logger.warning("Database connection not initialized, skipping index creation")
                return
            
            # Check if performance_metrics collection exists
            if not hasattr(self.db.db, 'performance_metrics'):
                self.logger.warning("performance_metrics collection not available, skipping index creation")
                return
            
            # Create timestamp index
            await self.db.db.performance_metrics.create_index("timestamp")
            
            # Create compound index for type and timestamp
            await self.db.db.performance_metrics.create_index(
                [("metric_type", 1), ("timestamp", -1)]
            )
            
            # Create TTL index with a different name to avoid conflicts
            try:
                await self.db.db.performance_metrics.create_index(
                    "timestamp", 
                    name="timestamp_ttl_index",
                    expireAfterSeconds=2592000  # 30 days in seconds
                )
                self.logger.info("Successfully created TTL index for performance metrics")
            except Exception as e:
                # If index already exists with a different name but same options, it's okay
                if "already exists with a different name" in str(e):
                    self.logger.info("TTL index already exists with a different name")
                else:
                    # Drop the existing index and recreate it with TTL if possible
                    try:
                        await self.db.db.performance_metrics.drop_index("timestamp_1")
                        await self.db.db.performance_metrics.create_index(
                            "timestamp", 
                            name="timestamp_ttl_index",
                            expireAfterSeconds=2592000  # 30 days in seconds
                        )
                        self.logger.info("Successfully recreated TTL index for performance metrics")
                    except Exception as inner_e:
                        self.logger.error(f"Could not recreate TTL index: {inner_e}")
        except Exception as e:
            self.logger.error(f"Failed to create indexes for metrics: {e}")
    
    def cog_unload(self):
        """Called when the cog is unloaded"""
        self._collect_metrics.cancel()
        self._clean_old_metrics.cancel()
    
    @tasks.loop(minutes=1)
    async def _collect_metrics(self):
        """Collect performance metrics every minute"""
        try:
            # Get current metrics
            metrics = self.bot.get_system_metrics()
            
            # Add timestamp
            metrics["timestamp"] = time.time()
            
            # Store metrics
            self._metrics_history.append(metrics)
            
            # Update interval data
            self._update_interval_data(metrics)
            
            # Save to database if available
            if self.db is not None and hasattr(self.db, 'db') and self.db.db is not None:
                try:
                    # Check if performance_metrics collection exists
                    if hasattr(self.db.db, 'performance_metrics'):
                        await self.db.db.performance_metrics.insert_one(metrics)
                    else:
                        # Only log this once in a while to avoid spam
                        if random.random() < 0.1:  # 10% chance to log
                            self.logger.warning("performance_metrics collection not available")
                except Exception as e:
                    self.logger.error(f"Failed to save metrics to database: {e}")
        except Exception as e:
            self.logger.error(f"Error collecting metrics: {e}")
    
    @_collect_metrics.before_loop
    async def before_collect_metrics(self):
        """Wait for the bot to be ready before starting the task"""
        await self.bot.wait_until_ready()
        
        # Wait a random short time to prevent all shards collecting at once
        await asyncio.sleep(2)
    
    @tasks.loop(hours=1)
    async def _clean_old_metrics(self):
        """Clean up old metrics to prevent memory issues"""
        # Keep only the last 24 hours of per-minute metrics in memory
        now = time.time()
        one_day_ago = now - 86400  # 24 hours in seconds
        
        self._metrics_history = [
            m for m in self._metrics_history if m.get("timestamp", 0) >= one_day_ago
        ]
    
    def _update_interval_data(self, metrics):
        """Update interval data for each tracking interval"""
        now = time.time()
        
        for interval, minutes in self._intervals.items():
            # Calculate seconds
            seconds = minutes * 60
            
            # Clean old data
            self._interval_data[interval] = [
                m for m in self._interval_data[interval] 
                if now - m.get("timestamp", 0) <= seconds
            ]
            
            # Check if we need to add this sample
            if not self._interval_data[interval] or \
               now - self._interval_data[interval][-1].get("timestamp", 0) >= (seconds / 60):
                self._interval_data[interval].append(metrics)
    
    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        """Record command execution time"""
        command_name = ctx.command.qualified_name
        end_time = time.time()
        
        # Only measure if we have a start time
        if command_name in self._last_command_time:
            # Get execution time
            start_time = self._last_command_time.pop(command_name)
            execution_time = end_time - start_time
            
            # Update command stats
            if command_name not in self._command_times:
                self._command_times[command_name] = []
            
            self._command_times[command_name].append(execution_time)
            
            # Keep only last 100 executions
            if len(self._command_times[command_name]) > 100:
                self._command_times[command_name] = self._command_times[command_name][-100:]
            
            # Update count
            self._command_counts[command_name] = self._command_counts.get(command_name, 0) + 1
    
    @commands.Cog.listener()
    async def on_command(self, ctx):
        """Record when a command starts"""
        command_name = ctx.command.qualified_name
        self._last_command_time[command_name] = time.time()
    
    @discord.slash_command(name="benchmark", description="Run performance tests on various components")
    async def benchmark(self, ctx):
        """Run performance tests on various components"""
        # Send initial response
        message = await ctx.respond("Running benchmarks, please wait...", ephemeral=False)
        
        try:
            # Run the benchmarks
            benchmark_results = await self._run_benchmarks()
            
            # Create report embed
            report_embed = discord.Embed(
                title="🔍 Performance Benchmark Results",
                description="Detailed performance metrics for system components",
                color=discord.Color.blue()
            )
            
            # Database performance
            db_metrics = benchmark_results.get("db", {})
            report_embed.add_field(
                name="🗄️ Database Performance",
                value=(
                    f"Read (Cached): {db_metrics.get('read_cached', 0):.2f} ms\n"
                    f"Read (Uncached): {db_metrics.get('read_uncached', 0):.2f} ms\n"
                    f"Write: {db_metrics.get('write', 0):.2f} ms\n"
                    f"Query: {db_metrics.get('query', 0):.2f} ms\n"
                    f"Cache Benefit: {db_metrics.get('cache_benefit', 0):.1f}x faster"
                ),
                inline=False
            )
            
            # API Performance
            api_metrics = benchmark_results.get("api", {})
            report_embed.add_field(
                name="🌐 API Performance",
                value=(
                    f"Discord API: {api_metrics.get('discord_api', 0):.2f} ms\n"
                    f"HTTP Get: {api_metrics.get('http_get', 0):.2f} ms\n"
                    f"HTTP Post: {api_metrics.get('http_post', 0):.2f} ms"
                ),
                inline=False
            )
            
            # Serialization
            ser_metrics = benchmark_results.get("serialization", {})
            report_embed.add_field(
                name="📦 Serialization",
                value=(
                    f"JSON (standard): {ser_metrics.get('json', 0):.2f} ms\n"
                    f"orjson: {ser_metrics.get('orjson', 0):.2f} ms\n"
                    f"msgpack: {ser_metrics.get('msgpack', 0):.2f} ms"
                ),
                inline=False
            )
            
            # Memory operations
            mem_metrics = benchmark_results.get("memory_ops", {})
            report_embed.add_field(
                name="💾 Memory Operations",
                value=(
                    f"Dict Access (10K): {mem_metrics.get('dict_access', 0):.2f} ms\n"
                    f"List Iteration (10K): {mem_metrics.get('list_iteration', 0):.2f} ms\n"
                    f"String Concat (1K): {mem_metrics.get('string_concat', 0):.2f} ms"
                ),
                inline=False
            )
            
            # System Info
            sys_info = self.bot.get_system_metrics()
            report_embed.add_field(
                name="🖥️ System Info",
                value=(
                    f"OS: {platform.system()} {platform.release()}\n"
                    f"Python: {platform.python_version()}\n"
                    f"CPU Cores: {psutil.cpu_count(logical=True)}\n"
                    f"Memory: {sys_info.get('total_memory_gb', 0):.1f} GB"
                ),
                inline=False
            )
            
            # Set timestamp
            report_embed.timestamp = datetime.datetime.now()
            
            # Edit the original message with the embed
            if hasattr(message, "edit"):
                await message.edit(embed=report_embed)
            else:
                await ctx.edit(embed=report_embed)
            
        except Exception as e:
            self.bot.log.error(f"Error running benchmarks: {e}")
            if hasattr(message, "edit"):
                await message.edit(content=f"Error running benchmarks: {e}")
            else:
                await ctx.edit(content=f"Error running benchmarks: {e}")
    
    @commands.slash_command(name="perfgraph", description="Show performance graphs over time")
    @commands.has_permissions(administrator=True)
    async def performance_graph(self, ctx, metric: discord.Option(str, 
                                                                 "Metric to graph", 
                                                                 choices=["memory", "cpu", "latency", "commands"]),
                               timespan: discord.Option(str,
                                                       "Time span to show",
                                                       choices=["1h", "6h", "24h", "7d"])):
        """Generate and display performance graphs over time"""
        await ctx.defer()
        
        # Get data for the requested interval
        interval_data = self._interval_data.get(timespan, [])
        
        if not interval_data:
            await ctx.respond("No performance data available for the selected timespan. Try again later.")
            return
        
        try:
            # Generate graph
            plt.figure(figsize=(10, 6))
            plt.grid(True, alpha=0.3)
            
            timestamps = [datetime.datetime.fromtimestamp(m.get("timestamp", 0)) for m in interval_data]
            
            if metric == "memory":
                values = [m.get("memory_usage_mb", 0) for m in interval_data]
                plt.plot(timestamps, values, marker='o', linestyle='-', color='blue')
                plt.title(f'Memory Usage Over {timespan}')
                plt.ylabel('Memory (MB)')
                plt.fill_between(timestamps, values, alpha=0.2, color='blue')
                
            elif metric == "cpu":
                values = [m.get("cpu_percent", 0) for m in interval_data]
                plt.plot(timestamps, values, marker='o', linestyle='-', color='green')
                plt.title(f'CPU Usage Over {timespan}')
                plt.ylabel('CPU (%)')
                plt.fill_between(timestamps, values, alpha=0.2, color='green')
                
            elif metric == "latency":
                values = [m.get("latency", 0) for m in interval_data]
                plt.plot(timestamps, values, marker='o', linestyle='-', color='red')
                plt.title(f'Discord API Latency Over {timespan}')
                plt.ylabel('Latency (ms)')
                plt.fill_between(timestamps, values, alpha=0.2, color='red')
                
            elif metric == "commands":
                values = [m.get("command_count", 0) for m in interval_data]
                # Convert to commands per minute rate
                for i in range(1, len(values)):
                    if timestamps[i-1] != timestamps[i]:  # Avoid div by zero
                        time_diff = (timestamps[i] - timestamps[i-1]).total_seconds() / 60
                        count_diff = values[i] - values[i-1]
                        values[i-1] = count_diff / time_diff if time_diff > 0 else 0
                values.pop()  # Remove last item as it doesn't have a next value to compare with
                timestamps.pop()  # Keep timestamps and values same length
                
                if values:  # Only plot if we have values after processing
                    plt.plot(timestamps, values, marker='o', linestyle='-', color='purple')
                    plt.title(f'Commands Per Minute Over {timespan}')
                    plt.ylabel('Commands/min')
                    plt.fill_between(timestamps, values, alpha=0.2, color='purple')
            
            plt.xticks(rotation=45)
            plt.tight_layout()
            
            # Save plot to buffer
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            plt.close()
            
            # Create file and send
            file = discord.File(buf, filename=f"{metric}_{timespan}.png")
            
            # Create embed
            embed = self.bot.Embed(
                title=f"Performance Graph: {metric.capitalize()}",
                description=f"Performance data over the last {timespan}"
            )
            embed.set_image(url=f"attachment://{metric}_{timespan}.png")
            
            await ctx.respond(embed=embed, file=file)
        except Exception as e:
            self.logger.error(f"Error generating performance graph: {e}")
            # Create a simple error embed
            error_embed = self.bot.Embed(
                title="Error Generating Graph",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            error_embed.add_field(
                name="Available Data Points", 
                value=f"{len(interval_data)} data points for {timespan}"
            )
            error_embed.add_field(
                name="Possible Solution",
                value="Try a different timespan or wait for more data to be collected"
            )
            await ctx.respond(embed=error_embed)
    
    @commands.slash_command(name="cmdstats", description="Show command execution statistics")
    @commands.has_permissions(administrator=True)
    async def command_stats(self, ctx):
        """Show statistics about command usage and performance"""
        if not self._command_times:
            await ctx.respond("No command statistics available yet.")
            return
        
        # Sort commands by average execution time
        sorted_commands = sorted(
            self._command_times.items(),
            key=lambda x: sum(x[1]) / len(x[1]) if x[1] else 0,
            reverse=True
        )
        
        # Create embed
        embed = self.bot.Embed(
            title="Command Performance Statistics",
            description="Average execution time and usage count for commands"
        )
        
        # Add top 10 slowest commands
        for cmd_name, times in sorted_commands[:10]:
            avg_time = sum(times) / len(times) if times else 0
            count = self._command_counts.get(cmd_name, 0)
            
            embed.add_field(
                name=cmd_name,
                value=f"**Avg Time:** {avg_time*1000:.2f} ms\n"
                      f"**Count:** {count}\n"
                      f"**Min:** {min(times)*1000:.2f} ms\n"
                      f"**Max:** {max(times)*1000:.2f} ms",
                inline=True
            )
        
        await ctx.respond(embed=embed)
    
    async def _run_benchmarks(self):
        """Run comprehensive performance tests"""
        results = {
            "db": {},
            "api": {},
            "serialization": {},
            "memory_ops": {}
        }
        
        # Run database benchmarks
        results["db"] = await self._benchmark_database()
        
        # Run API benchmarks
        results["api"] = await self._benchmark_api()
        
        # Run serialization benchmarks
        results["serialization"] = await self._benchmark_serialization()
        
        # Run memory operation benchmarks
        results["memory_ops"] = await self._benchmark_memory_ops()
        
        return results
        
    async def get_cache_stats(self):
        """Get detailed cache statistics for admin commands"""
        stats = {
            'hits': 0,
            'misses': 0,
            'total_lookups': 0,
            'hit_rate': 0.0,
            'items_cached': 0,
            'memory_usage': 0.0,
            'avg_item_size': 0.0,
            'namespaces': {},
            'cache_benefit': 0.0,
            'avg_latency_improvement': 0.0,
            'last_cleanup': None
        }
        
        # Try to get account cog which has the cache
        accounts_cog = self.bot.get_cog('Account')
        if not accounts_cog or not hasattr(accounts_cog, 'cache') or not accounts_cog.cache:
            return stats
            
        cache = accounts_cog.cache
        
        # Get basic hit/miss stats
        stats['hits'] = getattr(cache, 'hits', 0)
        stats['misses'] = getattr(cache, 'misses', 0)
        stats['total_lookups'] = stats['hits'] + stats['misses']
        
        # Calculate hit rate
        if stats['total_lookups'] > 0:
            stats['hit_rate'] = stats['hits'] / stats['total_lookups']
            
        # Get namespace stats if available
        if hasattr(cache, 'get_namespace_stats') and callable(cache.get_namespace_stats):
            try:
                namespace_stats = await cache.get_namespace_stats()
                stats['namespaces'] = namespace_stats
                stats['items_cached'] = sum(namespace_stats.values())
            except Exception as e:
                self.bot.log.error(f"Error getting namespace stats: {e}")
                
        # Estimate memory usage based on database benchmark results
        db_metrics = self._interval_data.get('db_metrics', {})
        if db_metrics and 'cache_benefit' in db_metrics:
            stats['cache_benefit'] = db_metrics['cache_benefit']
            stats['avg_latency_improvement'] = db_metrics.get('latency_improvement', 0)
            
        # Get last cleanup time if available
        if hasattr(cache, 'last_cleanup'):
            stats['last_cleanup'] = cache.last_cleanup
            
        # Try to estimate memory usage
        try:
            import psutil
            process = psutil.Process()
            # Rough estimate - cache typically uses ~20% of bot's memory
            stats['memory_usage'] = process.memory_info().rss / (1024 * 1024) * 0.2
            
            # Calculate average item size if we have items
            if stats['items_cached'] > 0:
                stats['avg_item_size'] = (stats['memory_usage'] * 1024) / stats['items_cached']
        except Exception as e:
            self.bot.log.error(f"Error calculating cache memory usage: {e}")
            
        return stats

    async def start_tasks(self):
        """Start background tasks (should be called from on_ready)"""
        # Start background tasks
        self._collect_metrics.start()
        self._clean_old_metrics.start()
        self.logger.info("Started performance monitoring tasks")

    async def _benchmark_database(self):
        """Run database benchmarks"""
        results = {}
        if hasattr(self.bot, 'db') and self.bot.db:
            db = self.bot.db.db
            
            # Test cached read
            start = time.perf_counter()
            for _ in range(5):
                await db.settings.find_one({"_id": "global"})
            end = time.perf_counter()
            cached_read_time = (end - start) * 1000 / 5
            results["read_cached"] = cached_read_time
            
            # Test uncached read (with unique IDs)
            start = time.perf_counter()
            for i in range(5):
                await db.settings.find_one({"_id": f"benchmark_{i}_{time.time()}"})
            end = time.perf_counter()
            uncached_read_time = (end - start) * 1000 / 5
            results["read_uncached"] = uncached_read_time
            
            # Calculate cache benefit
            if uncached_read_time > 0:
                results["cache_benefit"] = uncached_read_time / cached_read_time
                results["latency_improvement"] = uncached_read_time - cached_read_time
            
            # Test write
            start = time.perf_counter()
            doc_id = f"benchmark_{time.time()}"
            await db.performance_test.insert_one({
                "_id": doc_id,
                "timestamp": time.time(),
                "data": "benchmark_data",
                "ttl": time.time() + 60  # Auto-delete after 60 seconds
            })
            end = time.perf_counter()
            results["write"] = (end - start) * 1000
            
            # Test query
            start = time.perf_counter()
            await db.performance_test.find({"timestamp": {"$gt": time.time() - 3600}}).limit(10).to_list(10)
            end = time.perf_counter()
            results["query"] = (end - start) * 1000
            
        return results
        
    async def _benchmark_api(self):
        """Run API benchmarks"""
        results = {}
        
        # Discord API
        start = time.perf_counter()
        await self.bot.application_info()
        end = time.perf_counter()
        results["discord_api"] = (end - start) * 1000
        
        # HTTP performance
        if hasattr(self.bot, 'http_session'):
            # HTTP GET
            start = time.perf_counter()
            async with self.bot.http_session.get("https://discord.com/api/v10") as resp:
                await resp.text()
            end = time.perf_counter()
            results["http_get"] = (end - start) * 1000
            
            # HTTP POST
            start = time.perf_counter()
            payload = {"benchmark": True, "timestamp": time.time()}
            try:
                async with self.bot.http_session.post(
                    "https://httpbin.org/post", 
                    json=payload
                ) as resp:
                    await resp.json()
            except:
                # Fallback if httpbin is down
                pass
            end = time.perf_counter()
            results["http_post"] = (end - start) * 1000
            
        return results
        
    async def _benchmark_serialization(self):
        """Run serialization benchmarks"""
        results = {}
        
        test_obj = {
            "nested": {
                "data": [i for i in range(100)],
                "text": "benchmark" * 100
            },
            "values": [{"id": i, "name": f"item_{i}"} for i in range(100)]
        }
        
        # Standard JSON
        import json
        start = time.perf_counter()
        json_data = json.dumps(test_obj)
        _ = json.loads(json_data)
        end = time.perf_counter()
        results["json"] = (end - start) * 1000
        
        # orjson (if available)
        try:
            import orjson
            start = time.perf_counter()
            orjson_data = orjson.dumps(test_obj)
            _ = orjson.loads(orjson_data)
            end = time.perf_counter()
            results["orjson"] = (end - start) * 1000
        except ImportError:
            pass
        
        # msgpack (if available)
        try:
            import msgpack
            start = time.perf_counter()
            msgpack_data = msgpack.packb(test_obj)
            _ = msgpack.unpackb(msgpack_data)
            end = time.perf_counter()
            results["msgpack"] = (end - start) * 1000
        except ImportError:
            pass
            
        return results
        
    async def _benchmark_memory_ops(self):
        """Run memory operation benchmarks"""
        results = {}
        
        # Dictionary access
        start = time.perf_counter()
        d = {str(i): i for i in range(10000)}
        for i in range(10000):
            _ = d[str(i)]
        end = time.perf_counter()
        results["dict_access"] = (end - start) * 1000
        
        # List iteration
        start = time.perf_counter()
        l = list(range(10000))
        total = 0
        for item in l:
            total += item
        end = time.perf_counter()
        results["list_iteration"] = (end - start) * 1000
        
        # String concatenation
        start = time.perf_counter()
        result = ""
        for i in range(1000):
            result += f"item_{i}"
        end = time.perf_counter()
        results["string_concat"] = (end - start) * 1000
        
        return results 