import asyncio
import logging
import os
import random
import re
import string
import time
import uuid
from datetime import datetime, timedelta
from functools import wraps
from typing import Any

import discord
from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import (
    ConnectionFailure,
    NetworkTimeout,
    OperationFailure,
    ServerSelectionTimeoutError,
)

from helpers.exceptions import (
    AccountNotFoundError,
    CreditScoreError,
    DatabaseError,
    InsufficientCreditScoreError,
    InsufficientFundsError,
    LoanAlreadyExistsError,
    LoanError,
    LoanLimitError,
    ValidationError,
)

# Import our new optimizations
try:
    from optimizations.db_performance import (
        query_timing,
        db_retry,
        cacheable_query,
        get_query_cache,
        QueryProfiler,
        get_index_recommender,
        BatchProcessor,
    )
    from optimizations.mongodb_improvements import optimize_query, smart_cache, execute_bulk_write, BulkOperations
    OPTIMIZATIONS_AVAILABLE = True
except ImportError:
    # Fallback if optimizations aren't available
    OPTIMIZATIONS_AVAILABLE = False
    
    # Define dummy decorators for compatibility
    def query_timing(*args, **kwargs):
        def decorator(func):
            return func
        return decorator if not callable(args[0]) else decorator(args[0])
        
    def db_retry(*args, **kwargs):
        def decorator(func):
            return func
        return decorator if not callable(args[0]) else decorator(args[0])
        
    def cacheable_query(*args, **kwargs):
        def decorator(func):
            return func
        return decorator if not callable(args[0]) else decorator(args[0])
    
    # Dummy functions
    optimize_query = lambda query: query


class PerformanceMonitor:
    def __init__(self):
        self.operation_times: dict[str, list[float]] = {}
        self.logger = logging.getLogger("bot")

    def record_operation(self, operation_name: str, duration: float):
        if operation_name not in self.operation_times:
            self.operation_times[operation_name] = []
        self.operation_times[operation_name].append(duration)

        # Keep only last 1000 operations
        if len(self.operation_times[operation_name]) > 1000:
            self.operation_times[operation_name] = self.operation_times[operation_name][-1000:]

    def get_average_time(self, operation_name: str) -> float:
        if operation_name not in self.operation_times or not self.operation_times[operation_name]:
            return 0.0
        return sum(self.operation_times[operation_name]) / len(self.operation_times[operation_name])

    def log_slow_operations(self, threshold: float = 1.0):
        for operation, times in self.operation_times.items():
            avg_time = self.get_average_time(operation)
            if avg_time > threshold:
                self.logger.info(
                    {
                        "event": "Slow operation detected",
                        "operation": operation,
                        "avg_time": f"{avg_time:.2f}s",
                        "level": "warning",
                    }
                )


def measure_performance(operation_name=None):
    """
    Decorator to measure the performance of database operations.

    Args:
        operation_name (str, optional): Custom name for the operation.
            If not provided, function name will be used.

    Returns:
        The decorated function.
    """
    # For direct application of decorator without arguments
    if callable(operation_name):
        func = operation_name
        operation_name = func.__name__

        @wraps(func)
        async def direct_wrapper(*args, **kwargs):
            # Skip performance monitoring if first argument is a class instance
            # and it has no db attribute or db is None
            if (
                args
                and hasattr(args[0], "db")
                and (args[0].db is None or not hasattr(args[0], "connected") or not args[0].connected)
            ):
                # Just execute the function without monitoring
                return await func(*args, **kwargs)

            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                execution_time = (time.perf_counter() - start_time) * 1000  # Convert to ms

                # Log performance data if the class instance has performance_monitor
                if args and hasattr(args[0], "performance_monitor"):
                    args[0].performance_monitor.record_operation(operation_name, execution_time)

                return result
            except Exception as e:
                execution_time = (time.perf_counter() - start_time) * 1000  # Convert to ms
                if args and hasattr(args[0], "logger"):
                    args[0].logger.error(f"Error in {operation_name}: {str(e)} (took {execution_time:.2f}ms)")
                raise

        return direct_wrapper

    # For application of decorator with arguments
    def decorator(func):
        op_name = operation_name or func.__name__

        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Skip performance monitoring if first argument is a class instance
            # and it has no db attribute or db is None, or not connected
            if (
                args
                and hasattr(args[0], "db")
                and (args[0].db is None or not hasattr(args[0], "connected") or not args[0].connected)
            ):
                # Just execute the function without monitoring
                return await func(*args, **kwargs)

            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                execution_time = (time.perf_counter() - start_time) * 1000  # Convert to ms

                # Log performance data if the class instance has performance_monitor
                if args and hasattr(args[0], "performance_monitor"):
                    args[0].performance_monitor.record_operation(op_name, execution_time)

                    # Log slow operations
                    if execution_time > 500:  # 500 ms threshold for slow operations
                        if hasattr(args[0], "logger"):
                            args[0].logger.warning(f"Slow operation '{op_name}': {execution_time:.2f}ms")

                return result
            except Exception as e:
                execution_time = (time.perf_counter() - start_time) * 1000  # Convert to ms
                if args and hasattr(args[0], "logger"):
                    args[0].logger.error(f"Error in {op_name}: {str(e)} (took {execution_time:.2f}ms)")
                raise

        return wrapper

    return decorator


COG_METADATA = {
    "name": "database",
    "enabled": True,
    "version": "1.0",
    "description": "Handles MongoDB operations for the banking bot",
}


async def setup(bot):
    bot.add_cog(Database(bot))


class Database(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("database")
        self.client = None
        self.db = None
        self.connected = False
        self.connection_retries = 0
        self.max_retries = 5  # Increased from 3
        self.retry_delay = 5  # seconds
        self.mongo_uri = self.bot.config.mongo_uri
        
        # Initialize performance tracking
        self.performance_monitor = PerformanceMonitor()
        
        # Initialize optimizations if available
        if OPTIMIZATIONS_AVAILABLE:
            self.query_profiler = QueryProfiler
            self.index_recommender = get_index_recommender()
            
            # Create batch processor for transaction logging
            self.transaction_batch = BatchProcessor(
                batch_size=50,
                max_delay=2.0,
                processor_func=self._process_transaction_batch
            )

        if not self.mongo_uri:
            self.logger.error("MONGO_URI is not set in config")
            return

        if not (self.mongo_uri.startswith("mongodb://") or self.mongo_uri.startswith("mongodb+srv://")):
            self.logger.error(f"Invalid MONGO_URI format: {self.mongo_uri[:10]}...")
            return

        # Always use a fixed database name to avoid extraction issues
        db_name = "banking_bot"  # Default database name

        # Log MongoDB connection details (without credentials)
        self._log_mongo_connection_details(db_name)

        # Initialize client in __init__ with basic settings
        try:
            self.client = AsyncIOMotorClient(
                self.mongo_uri,
                serverSelectionTimeoutMS=5000,  # 5 seconds timeout
                connectTimeoutMS=10000,  # 10 seconds connect timeout
                socketTimeoutMS=30000,  # 30 seconds socket timeout
                maxPoolSize=100,  # Increase pool size for better concurrency
                minPoolSize=10,  # Keep minimum connections open
                maxIdleTimeMS=45000,  # Close idle connections after 45 seconds
                waitQueueTimeoutMS=1000,  # Wait 1 second for a connection from pool
            )
            
            # Set database reference in __init__ but don't check connectivity yet
            self.db = self.client[db_name]  # Set db reference but don't access it yet
            
            # Register index recommendations if available
            if OPTIMIZATIONS_AVAILABLE and hasattr(self, 'index_recommender'):
                # Register known indexes for accounts collection
                self.index_recommender.register_index("accounts", ["user_id"])
                self.index_recommender.register_index("accounts", ["guild_id"])
                self.index_recommender.register_index("accounts", ["balance"])
                
                # Register known indexes for transactions collection
                self.index_recommender.register_index("transactions", ["user_id"])
                self.index_recommender.register_index("transactions", ["timestamp"])
                self.index_recommender.register_index("transactions", ["transaction_type"])
                
        except Exception as e:
            self.logger.error(f"Failed to initialize MongoDB client: {e}")

    # New method: Batch processor for transactions
    async def _process_transaction_batch(self, transactions):
        """Process a batch of transactions"""
        if not self.db or not self.connected:
            self.logger.error("Cannot process transaction batch - no database connection")
            return

        try:
            # Use the bulk operation helper
            start_time = time.time()
            result = await self.db.transactions.insert_many(transactions)
            duration = time.time() - start_time
            
            # Record metrics
            if OPTIMIZATIONS_AVAILABLE:
                self.query_profiler.record_query(
                    collection="transactions",
                    operation="insert_many",
                    query={"count": len(transactions)},
                    duration=duration,
                    success=True,
                    result_size=len(transactions)
                )
                
            self.logger.info(f"Processed batch of {len(transactions)} transactions in {duration:.3f}s")
            return result
        except Exception as e:
            self.logger.error(f"Error processing transaction batch: {e}")
            # For critical failures, attempt one-by-one insert
            successful = 0
            for transaction in transactions:
                try:
                    await self.db.transactions.insert_one(transaction)
                    successful += 1
                except Exception:
                    pass
            self.logger.warning(f"Fallback processing: {successful}/{len(transactions)} transactions saved")

    @commands.slash_command(description="View database performance metrics")
    @commands.has_permissions(administrator=True)
    async def performance_metrics(self, ctx):
        """View database performance metrics and index recommendations"""
        if not self.connected:
            await ctx.respond("❌ Database is not connected", ephemeral=True)
            return

        # Create embed for performance metrics
        embed = discord.Embed(title="Database Performance Metrics", color=discord.Color.blue())
        
        # Add basic performance data
        ping_time = await self._measure_ping_time()
        embed.add_field(name="Database Ping", value=f"{ping_time:.2f}ms", inline=True)
        
        # Add operation performance data from our class
        for operation, times in self.performance_monitor.operation_times.items():
            if times:
                avg = sum(times) / len(times)
                embed.add_field(name=f"{operation}", value=f"{avg:.2f}ms avg ({len(times)} calls)", inline=True)

        # If optimizations are available, add more detailed metrics
        if OPTIMIZATIONS_AVAILABLE:
            stats = self.query_profiler.get_stats()
            if stats["total_queries"] > 0:
                embed.add_field(
                    name="Total Queries", 
                    value=f"{stats['total_queries']} (Avg: {stats['avg_query_time']:.3f}s)", 
                    inline=False
                )
                
                # Add cache statistics
                cache_stats = stats.get("cache", {})
                if cache_stats:
                    cache_hit_ratio = cache_stats.get("hit_ratio", 0) * 100
                    embed.add_field(
                        name="Cache Statistics", 
                        value=f"Size: {cache_stats.get('size', 0)}/{cache_stats.get('max_size', 0)}\n" 
                              f"Hit Ratio: {cache_hit_ratio:.1f}%",
                        inline=True
                    )
                
                # Add slow query information
                if stats["slow_queries"] > 0:
                    slowest = stats["slowest_query"]
                    embed.add_field(
                        name="Slow Queries", 
                        value=f"{stats['slow_queries']} detected\nSlowest: {slowest['time']:.3f}s",
                        inline=True
                    )
            
            # Add index recommendations
            recommendations = self.index_recommender.get_recommendations()
            if recommendations:
                rec_text = ""
                for collection, indexes in recommendations.items():
                    if indexes:
                        fields = ", ".join(indexes[0]["fields"])
                        count = indexes[0]["count"]
                        rec_text += f"{collection}: {fields} ({count} queries)\n"
                
                if rec_text:
                    embed.add_field(name="Index Recommendations", value=rec_text, inline=False)

        # Send the embed
        await ctx.respond(embed=embed)

    @measure_performance
    @db_retry(max_attempts=5, retry_delay=1.0)
    async def _execute_with_retry(self, operation_name, operation_func, max_retries=3):
        """Execute a database operation with retry logic"""
        retries = 0
        last_error = None
        
        while retries <= max_retries:
            try:
                # Apply query optimization if this is a find operation
                if operation_name.startswith("find") and len(operation_func.args) > 0:
                    # Get the query argument (usually first arg)
                    query_arg = operation_func.args[0]
                    if isinstance(query_arg, dict):
                        # Optimize the query
                        optimized_query = optimize_query(query_arg)
                        # Replace the original query with optimized version
                        operation_func.args = (optimized_query,) + operation_func.args[1:]
                
                # Execute the operation
                result = await operation_func()
                return result
            except (ConnectionFailure, ServerSelectionTimeoutError, NetworkTimeout) as e:
                retries += 1
                last_error = e
                
                if retries <= max_retries:
                    # Exponential backoff
                    delay = 0.5 * (2 ** retries)
                    self.logger.warning(
                        f"Database operation '{operation_name}' failed, retrying in {delay:.1f}s: {str(e)}"
                    )
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(f"Database operation '{operation_name}' failed after {retries} retries: {str(e)}")
            except Exception as e:
                # For other exceptions, don't retry
                self.logger.error(f"Database operation '{operation_name}' error: {str(e)}")
                raise
                
        # If we get here, all retries failed
        raise last_error or DatabaseError(f"Operation {operation_name} failed after {max_retries} attempts")

    @measure_performance("log_transaction")
    @query_timing(collection="transactions", operation="insert")
    async def log_transaction(
        self,
        user_id: str,
        transaction_type: str,
        amount: int | float,
        description: str = None,
        receiver_id: str = None,
        balance_before: float = None,
        balance_after: float = None,
    ) -> str | None:
        """
        Log a transaction in the transactions collection.

        Args:
            user_id: The ID of the user making the transaction
            transaction_type: The type of transaction (deposit, withdraw, transfer, etc.)
            amount: The amount of the transaction
            description: Optional description of the transaction
            receiver_id: Optional ID of the user receiving the transaction (for transfers)
            balance_before: Optional balance before the transaction
            balance_after: Optional balance after the transaction

        Returns:
            The ID of the inserted transaction, or None if the insertion failed
        """
        if not self.db or not self.connected:
            self.logger.error("Cannot log transaction - no database connection")
            return None

        # Validate inputs
        if not self._validate_id(user_id):
            self.logger.error(f"Invalid user_id for transaction log: {user_id}")
            return None

        if receiver_id and not self._validate_id(receiver_id):
            self.logger.error(f"Invalid receiver_id for transaction log: {receiver_id}")
            return None

        transaction = {
            "user_id": user_id,
            "transaction_type": transaction_type,
            "amount": amount,
            "timestamp": datetime.utcnow(),
        }

        if description:
            transaction["description"] = self._sanitize_input(description)[:100]  # Limit description length

        if receiver_id:
            transaction["receiver_id"] = receiver_id

        if balance_before is not None:
            transaction["balance_before"] = balance_before

        if balance_after is not None:
            transaction["balance_after"] = balance_after

        # Use batch processing if available
        if OPTIMIZATIONS_AVAILABLE and hasattr(self, 'transaction_batch'):
            try:
                # Add to batch processor
                await self.transaction_batch.add(transaction)
                # We don't have the transaction ID immediately when using batch processing
                # but we return a placeholder that indicates success
                return "batch_processing"
            except Exception as e:
                self.logger.error(f"Error adding transaction to batch: {e}")
                # Fall back to direct insert on error
        
        # Direct insert if not using batch processing or batch failed
        try:
            result = await self.db.transactions.insert_one(transaction)
            return str(result.inserted_id)
        except Exception as e:
            self.logger.error(f"Failed to log transaction: {e}")
            return None

    @measure_performance
    @query_timing(collection="accounts", operation="find")
    @cacheable_query(ttl=300)  # Cache for 5 minutes
    async def get_account(self, user_id, guild_id):
        """Get a user's account"""
        if not self.db or not self.connected:
            self.logger.error("Cannot get account - no database connection")
            return None

        if not self._validate_id(user_id) or not self._validate_id(guild_id):
            return None

        try:
            # Apply query optimization
            query = optimize_query({"user_id": user_id, "guild_id": guild_id})
            
            account = await self.db.accounts.find_one(query)
            return account
        except Exception as e:
            self.logger.error(f"Failed to get account: {e}")
            return None

    @measure_performance
    @query_timing(collection="accounts", operation="update")
    async def update_balance(self, user_id, guild_id, amount, transaction_type, reason=None):
        """Update a user's balance with optimized queries and error handling"""
        if not self.db or not self.connected:
            self.logger.error("Cannot update balance - no database connection")
            raise DatabaseError("Database not connected")

        if not self._validate_id(user_id) or not self._validate_id(guild_id):
            raise ValidationError("Invalid user_id or guild_id")

        try:
            # Get the current account
            account = await self.get_account(user_id, guild_id)
            if not account:
                raise AccountNotFoundError(f"Account for user {user_id} not found")

            # Calculate new balance
            current_balance = account.get("balance", 0)
            new_balance = current_balance + amount

            # Check for negative balance
            if new_balance < 0 and transaction_type not in ["loan", "admin_adjust"]:
                raise InsufficientFundsError(f"Insufficient funds. Current balance: {current_balance}")

            # Update the account
            result = await self.db.accounts.update_one(
                {"user_id": user_id, "guild_id": guild_id},
                {"$set": {"balance": new_balance, "last_transaction": datetime.utcnow()}},
            )

            if result.modified_count == 0:
                raise DatabaseError("Failed to update balance, no document modified")

            # Log the transaction
            await self.log_transaction(
                user_id=user_id,
                transaction_type=transaction_type,
                amount=amount,
                description=reason,
                balance_before=current_balance,
                balance_after=new_balance,
            )

            # Invalidate cache for this account to ensure fresh data
            if OPTIMIZATIONS_AVAILABLE:
                cache = get_query_cache()
                # Construct a key pattern similar to what cacheable_query would use
                cache_key_pattern = f"get_account:{user_id}:{guild_id}"
                for key in list(cache.cache.keys()):
                    if cache_key_pattern in key:
                        del cache.cache[key]

            # Return account info with updated balance
            return {"user_id": user_id, "guild_id": guild_id, "balance": new_balance, "previous_balance": current_balance}

        except (AccountNotFoundError, InsufficientFundsError) as e:
            # Re-raise known exceptions
            raise
        except Exception as e:
            self.logger.error(f"Failed to update balance: {e}")
            raise DatabaseError(f"Database error: {str(e)}")

    # Add new method to get database performance stats
    async def get_db_performance_stats(self):
        """Get comprehensive database performance statistics"""
        if not OPTIMIZATIONS_AVAILABLE:
            return {
                "optimizations_enabled": False,
                "basic_metrics": {op: self.performance_monitor.get_average_time(op) for op in self.performance_monitor.operation_times}
            }
            
        # Get query stats from profiler
        query_stats = self.query_profiler.get_stats()
        
        # Get cache stats
        cache_stats = get_query_cache().stats()
        
        # Get index recommendations
        index_recommendations = self.index_recommender.get_recommendations(min_occurrences=5)
        
        # Get batch processor stats if available
        batch_stats = {}
        if hasattr(self, 'transaction_batch'):
            batch_stats = self.transaction_batch.stats()
            
        # Build comprehensive stats
        return {
            "optimizations_enabled": True,
            "query_stats": query_stats,
            "cache_stats": cache_stats,
            "batch_stats": batch_stats,
            "index_recommendations": index_recommendations,
            "connection_retries": self.connection_retries,
            "ping_time_ms": await self._measure_ping_time(),
        }

    # Override cog_unload to clean up resources
    async def cog_unload(self):
        """Clean up resources when the cog is unloaded"""
        # Close MongoDB connection
        if self.client:
            self.client.close()
            self.logger.info("MongoDB connection closed")
            
        # Flush any pending transaction batches
        if OPTIMIZATIONS_AVAILABLE and hasattr(self, 'transaction_batch'):
            await self.transaction_batch.flush()
            self.logger.info("Transaction batch flushed")

        # Base implementation
        self.logger.info("Database cog unloaded")

    async def _force_connection(self):
        """Try a more direct approach to connect to MongoDB"""
        self.logger.info("Attempting forced connection to MongoDB...")

        try:
            # Reset client
            if self.client:
                try:
                    self.client.close()
                except Exception as e:
                    # Log the error instead of silently ignoring it
                    self.logger.debug(f"Non-critical error closing MongoDB client: {str(e)}")
                    # We still want to continue with creating a new client

            # Create a fresh client with simplified settings - minimal parameters for reliability
            self.logger.info("Creating fresh MongoDB client...")
            mongo_uri = os.getenv("MONGO_URI")  # Get directly from environment for reliability
            if not mongo_uri:
                mongo_uri = self.mongo_uri  # Fall back to config

            if not mongo_uri:
                self.logger.error("No MongoDB URI available")
                return False

            self.client = AsyncIOMotorClient(
                mongo_uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                socketTimeoutMS=10000,
            )

            # Always use a fixed database name
            db_name = "banking_bot"

            # Get the database directly using indexing instead of get_database
            self.db = self.client[db_name]

            # Simple ping test
            self.logger.info("Testing forced connection...")
            await self.client.admin.command("ping")

            # Mark as connected
            self.connected = True
            self.logger.info("Forced connection successful!")

            # Try to get and log server info
            try:
                server_info = await self.client.admin.command("serverStatus")
                version = server_info.get("version", "unknown")
                uptime_hours = round(server_info.get("uptime", 0) / 3600, 1)
                connections = server_info.get("connections", {})
                current = connections.get("current", "N/A")
                available = connections.get("available", "N/A")

                self.logger.info(
                    f"MongoDB server: v{version}, uptime: {uptime_hours}h, "
                    f"connections: {current}/{current+available}"
                )
            except Exception as e:
                self.logger.warning(f"Connected but couldn't get server info: {str(e)}")

            return True

        except Exception as e:
            self.logger.error(f"Forced connection failed: {str(e)}")
            self.connected = False
            return False

    async def _test_connection(self):
        """Test the MongoDB connection and retry if needed"""
        retry_count = 0
        max_retries = self.max_retries
        delay = self.retry_delay

        # Print URI details for debugging (without exposing credentials)
        uri_parts = self.mongo_uri.split("@")
        safe_uri = uri_parts[-1] if len(uri_parts) > 1 else self.mongo_uri.split("://")[-1]
        self.logger.info(f"Testing connection to MongoDB at {safe_uri}")

        while retry_count <= max_retries:
            try:
                # Try to ping the database
                self.logger.info(f"Connection attempt {retry_count+1}/{max_retries+1} to MongoDB")

                # Add timeout to prevent getting stuck
                ping_task = self.client.admin.command("ping")
                await asyncio.wait_for(ping_task, timeout=5.0)

                self.connected = True
                self.logger.info("Successfully connected to MongoDB")
                return True

            except TimeoutError:
                retry_count += 1
                self.connection_retries += 1

                self.logger.error("MongoDB ping timed out after 5 seconds")

                if retry_count <= max_retries:
                    wait_time = delay * retry_count
                    self.logger.warning(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    self.logger.error(f"Failed to connect to MongoDB after {max_retries} attempts")
                    self.logger.warning("Bot will operate in degraded mode without database functionality")
                    break

            except Exception as e:
                retry_count += 1
                self.connection_retries += 1

                # Log the error details
                self.logger.error(f"MongoDB Error: {str(e)}")
                self.logger.error(f"Error type: {type(e).__name__}")

                if retry_count <= max_retries:
                    wait_time = delay * retry_count
                    self.logger.warning(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    self.logger.error(f"Failed to connect to MongoDB after {max_retries} attempts")
                    self.logger.warning("Bot will operate in degraded mode without database functionality")
                    break

        # Set connected to false but don't set db to None (for retry attempts)
        self.connected = False
        return False

    def _ensure_collections_exist(self):
        """Ensure that all required collections exist in the database"""
        if self.db is None:
            return

        # Define required collections to prevent NoneType attribute errors
        required_collections = [
            "accounts",
            "transactions",
            "settings",
            "performance_metrics",
            "credit_scores",
            "loans",
            "kyc_records",
            "admin",
        ]

        # Access each collection to ensure it exists
        for collection in required_collections:
            _ = self.db[collection]

    async def _measure_ping_time(self):
        """Measure the database ping time in milliseconds"""

        if self.db is None:
            self.logger.error("Cannot measure ping time: database not initialized")
            return -1

        try:
            start_time = time.perf_counter()
            await self.client.admin.command("ping")
            end_time = time.perf_counter()

            ping_time = (end_time - start_time) * 1000

            if ping_time > 1000:
                self.logger.warning(f"Database ping time is high: {ping_time:.2f}ms")

            return ping_time
        except Exception as e:
            self.logger.error(f"Error measuring ping time: {str(e)}")
            return -1

    @measure_performance
    async def _periodic_performance_check(self):
        """Periodically check and log database performance metrics"""
        try:
            if not self.connected or self.db is None:
                self.logger.warning("Skipping performance check: not connected to database")

                # Try to reconnect if we lost the connection
                if hasattr(self, "last_reconnect_attempt"):
                    # Don't attempt reconnection too frequently
                    time_since_last_attempt = time.time() - self.last_reconnect_attempt
                    if time_since_last_attempt > 300:  # 5 minutes between attempts
                        self.logger.info("Attempting to reconnect to MongoDB...")
                        success = await self._force_connection()
                        self.last_reconnect_attempt = time.time()
                        if success:
                            self.logger.info("Successfully reconnected to MongoDB")
                        else:
                            self.logger.warning("Failed to reconnect to MongoDB")
                else:
                    # First reconnection attempt
                    self.logger.info("First attempt to reconnect to MongoDB...")
                    success = await self._force_connection()
                    self.last_reconnect_attempt = time.time()
                    if success:
                        self.logger.info("Successfully reconnected to MongoDB")
                    else:
                        self.logger.warning("Failed to reconnect to MongoDB")
                return

            # Measure ping time
            ping_time = await self._measure_ping_time()
            if ping_time < 0:
                self.logger.warning("Could not measure MongoDB ping time")
                return

            # Check connection pool stats if available
            if hasattr(self.client, "get_io_loop"):
                try:
                    server_status = await self.client.admin.command("serverStatus")
                    connections = server_status.get("connections", {})

                    metrics = {
                        "ping_ms": round(ping_time, 2),
                        "total_connections": connections.get("current", "N/A"),
                        "available_connections": connections.get("available", "N/A"),
                        "timestamp": datetime.utcnow().isoformat(),
                    }

                    # Log performance metrics
                    self.logger.info(
                        f"MongoDB Performance: Ping={metrics['ping_ms']}ms, "
                        f"Connections={metrics['total_connections']}, "
                        f"Available={metrics['available_connections']}"
                    )

                    # Store metrics in database if connected
                    if self.connected and self.db is not None:
                        try:
                            await self.db.performance_metrics.insert_one(metrics)
                        except OperationFailure as e:
                            # Check if this is a permissions error for Atlas
                            if "not allowed to do action" in str(e):
                                self.logger.warning("Skipping metrics storage - insufficient Atlas permissions")
                            else:
                                self.logger.error(f"Failed to store metrics: {str(e)}")
                        except Exception as e:
                            self.logger.error(f"Unexpected error storing metrics: {str(e)}")
                except OperationFailure as e:
                    # Check if this is a permissions error for Atlas
                    if "not allowed to do action" in str(e):
                        self.logger.warning(
                            f"Limited permissions on Atlas - skipping detailed metrics collection: {str(e)}"
                        )
                    else:
                        self.logger.error(f"Failed to collect MongoDB metrics: {str(e)}")
                        # Check if we should try to reconnect
                        if "connection" in str(e).lower():
                            self.logger.warning("Connection may have been lost, marking as disconnected")
                            self.connected = False
                except Exception as e:
                    self.logger.error(f"Failed to collect MongoDB metrics: {str(e)}")
                    # Check if we should try to reconnect
                    if "connection" in str(e).lower():
                        self.logger.warning("Connection may have been lost, marking as disconnected")
                        self.connected = False
        except Exception as e:
            self.logger.error(f"Performance check error: {str(e)}")
            # Check if this seems like a connection error
            if "connection" in str(e).lower():
                self.logger.warning("Connection may have been lost during performance check, marking as disconnected")
                self.connected = False

    @measure_performance("create_loan")
    async def create_loan(self, user_id: str, amount: float, term_months: int) -> bool:
        """Create a loan for a user"""
        try:
            account = await self.get_account(user_id)
            if not account:
                raise AccountNotFoundError(f"No account found for user ID: {user_id}")

            # Check if user already has an active loan
            if account.get("loan") and account["loan"].get("status") == "active":
                raise LoanAlreadyExistsError("You already have an active loan")

            # Check credit score
            credit_score = account.get("credit_score", 600)

            # Check if credit score is sufficient for the loan amount
            if amount > 1000 and credit_score < 550:
                raise InsufficientCreditScoreError(
                    f"Your credit score ({credit_score}) is too low for a loan of ${amount:,.2f}. Work on improving your score by making regular transactions and maintaining a positive balance."
                )

            if amount > 5000 and credit_score < 600:
                raise InsufficientCreditScoreError(
                    f"Your credit score ({credit_score}) is too low for a loan of ${amount:,.2f}. Work on improving your score by making regular transactions and maintaining a positive balance."
                )

            if amount > 10000 and credit_score < 650:
                raise InsufficientCreditScoreError(
                    f"Your credit score ({credit_score}) is too low for a loan of ${amount:,.2f}. Work on improving your score by making regular transactions and maintaining a positive balance."
                )

            # Calculate user's credit limit based on account history, balance, and credit score
            # Higher credit scores allow for higher loan limits
            credit_multiplier = self._get_credit_multiplier(credit_score)
            credit_limit = account["balance"] * credit_multiplier

            if amount > credit_limit:
                raise LoanLimitError(f"Loan amount exceeds your credit limit of ${credit_limit:,.2f}")

            # Adjust loan interest rate based on credit score
            # Better credit scores get lower interest rates
            interest_rate = self._get_interest_rate_by_credit_score(credit_score)

            # Calculate monthly payment (simple calculation)
            total_interest = (amount * interest_rate * term_months) / (12 * 100)
            total_repayment = amount + total_interest
            monthly_payment = total_repayment / term_months

            # Calculate loan dates
            start_date = datetime.utcnow()
            next_payment_date = start_date + timedelta(days=30)
            end_date = start_date + timedelta(days=30 * term_months)

            # Create loan object
            loan_data = {
                "amount": amount,
                "interest_rate": interest_rate,
                "term_months": term_months,
                "monthly_payment": monthly_payment,
                "remaining_amount": total_repayment,
                "next_payment_date": next_payment_date,
                "start_date": start_date,
                "end_date": end_date,
                "status": "active",
            }

            # Update account with loan and add loan amount to balance
            async with await self.client.start_session() as session:
                async with session.start_transaction():
                    # Add loan to account
                    update_result = await self.db.accounts.update_one(
                        {"user_id": user_id},
                        {
                            "$set": {"loan": loan_data, "last_updated": datetime.utcnow()},
                            "$inc": {"balance": amount},
                        },
                    )

                    if update_result.modified_count == 0:
                        raise DatabaseError("Failed to create loan")

                    # Update credit history for taking a loan (small negative impact)
                    await self.update_credit_score(
                        user_id=user_id,
                        action="loan_taken",
                        change=-5,
                        reason=f"Took a loan of ${amount:,.2f}",
                    )

                    # Log loan transaction
                    await self.log_transaction(
                        user_id=user_id,
                        transaction_type="loan_received",
                        amount=amount,
                        description=f"Loan received for {term_months} months at {interest_rate}% interest",
                        balance_before=account["balance"],
                        balance_after=account["balance"] + amount,
                    )

                    return True

        except Exception as e:
            if isinstance(
                e,
                (
                    AccountNotFoundError,
                    LoanAlreadyExistsError,
                    LoanLimitError,
                    InsufficientCreditScoreError,
                    DatabaseError,
                ),
            ):
                raise e
            self.logger.error(
                {
                    "event": "Failed to create loan",
                    "error": str(e),
                    "user_id": user_id,
                    "level": "error",
                }
            )
            raise DatabaseError(f"Failed to create loan: {str(e)}")

    @measure_performance("repay_loan")
    async def repay_loan(self, user_id: str, amount: float = None) -> dict[str, Any]:
        """Repay a loan (either specific amount or monthly payment)"""
        try:
            account = await self.get_account(user_id)
            if not account:
                raise AccountNotFoundError(f"No account found for user ID: {user_id}")

            # Check if user has an active loan
            if not account.get("loan") or account["loan"].get("status") != "active":
                raise LoanError("You don't have an active loan to repay")

            loan = account["loan"]

            # If no amount specified, use monthly payment
            if amount is None:
                amount = loan["monthly_payment"]

            # Check if user has enough balance
            if account["balance"] < amount:
                raise InsufficientFundsError(f"Insufficient funds to make loan payment of ${amount:,.2f}")

            # If payment amount is greater than remaining amount, adjust to pay off the loan
            if amount > loan["remaining_amount"]:
                amount = loan["remaining_amount"]

            # Calculate new remaining amount
            new_remaining = loan["remaining_amount"] - amount
            new_status = "active" if new_remaining > 0 else "paid"

            # Calculate next payment date (30 days from today if still active)
            next_payment_date = datetime.utcnow() + timedelta(days=30) if new_status == "active" else None

            async with await self.client.start_session() as session:
                async with session.start_transaction():
                    # Update loan info
                    update_data = {
                        "balance": account["balance"] - amount,
                        "last_updated": datetime.utcnow(),
                    }

                    if new_status == "paid":
                        # Loan is fully paid, remove it
                        update_data["loan"] = None

                        # Significant credit score boost for fully paying off a loan
                        await self.update_credit_score(
                            user_id=user_id,
                            action="loan_fully_paid",
                            change=25,
                            reason=f"Fully repaid loan of ${loan['amount']:,.2f}",
                        )
                    else:
                        # Update loan details
                        loan_update = loan.copy()
                        loan_update["remaining_amount"] = new_remaining
                        loan_update["next_payment_date"] = next_payment_date
                        loan_update["status"] = new_status
                        update_data["loan"] = loan_update

                        # Small credit score boost for making a payment on time
                        current_time = datetime.utcnow()
                        if loan["next_payment_date"] >= current_time:
                            await self.update_credit_score(
                                user_id=user_id,
                                action="on_time_payment",
                                change=5,
                                reason=f"Made on-time loan payment of ${amount:,.2f}",
                            )
                        else:
                            # Late payment has negative impact
                            days_late = (current_time - loan["next_payment_date"]).days
                            if days_late > 0:
                                await self.update_credit_score(
                                    user_id=user_id,
                                    action="late_payment",
                                    change=-5 * min(days_late // 7 + 1, 5),  # Max -25 points for very late payments
                                    reason=f"Made loan payment {days_late} days late",
                                )

                    # Update account
                    update_result = await self.db.accounts.update_one({"user_id": user_id}, {"$set": update_data})

                    if update_result.modified_count == 0:
                        raise DatabaseError("Failed to process loan payment")

                    # Log repayment transaction
                    transaction_desc = "Loan repayment"
                    if new_status == "paid":
                        transaction_desc = "Final loan repayment - loan fully paid"

                    await self.log_transaction(
                        user_id=user_id,
                        transaction_type="loan_payment",
                        amount=amount,
                        description=transaction_desc,
                        balance_before=account["balance"],
                        balance_after=account["balance"] - amount,
                    )

                    # Return payment result
                    return {
                        "amount_paid": amount,
                        "remaining_amount": new_remaining,
                        "status": new_status,
                        "fully_paid": new_status == "paid",
                    }

        except Exception as e:
            if isinstance(e, (AccountNotFoundError, LoanError, InsufficientFundsError, DatabaseError)):
                raise e
            self.logger.error(
                {
                    "event": "Failed to process loan payment",
                    "error": str(e),
                    "user_id": user_id,
                    "level": "error",
                }
            )
            raise DatabaseError(f"Failed to process loan payment: {str(e)}")

    @measure_performance("check_loan_status")
    async def check_loan_status(self, user_id: str) -> dict[str, Any] | None:
        """Check status of a user's loan"""
        try:
            account = await self.get_account(user_id)
            if not account:
                raise AccountNotFoundError(f"No account found for user ID: {user_id}")

            # Check if user has a loan
            if not account.get("loan"):
                return None

            loan = account["loan"]

            # Calculate progress
            if loan["status"] == "paid":
                progress = 100.0
            else:
                paid_amount = loan["amount"] - (
                    loan["remaining_amount"] / (1 + (loan["interest_rate"] * loan["term_months"]) / (12 * 100))
                )
                progress = (paid_amount / loan["amount"]) * 100

            # Calculate days until next payment or overdue
            if loan["status"] == "active":
                now = datetime.utcnow()
                next_payment = loan["next_payment_date"]
                days_to_payment = (next_payment - now).days
                is_overdue = days_to_payment < 0
            else:
                days_to_payment = 0
                is_overdue = False

            # Format loan data for response
            return {
                "amount": loan["amount"],
                "interest_rate": loan["interest_rate"],
                "term_months": loan["term_months"],
                "monthly_payment": loan["monthly_payment"],
                "remaining_amount": loan["remaining_amount"],
                "next_payment_date": loan["next_payment_date"] if loan["status"] == "active" else None,
                "start_date": loan["start_date"],
                "end_date": loan["end_date"],
                "status": loan["status"],
                "progress_percent": progress,
                "days_to_next_payment": days_to_payment if loan["status"] == "active" else None,
                "is_overdue": is_overdue,
            }

        except Exception as e:
            if isinstance(e, AccountNotFoundError):
                raise e
            self.logger.error(
                {
                    "event": "Failed to check loan status",
                    "error": str(e),
                    "user_id": user_id,
                    "level": "error",
                }
            )
            raise DatabaseError(f"Failed to check loan status: {str(e)}")

    def _get_credit_multiplier(self, credit_score: int) -> float:
        """Calculate credit multiplier based on credit score"""
        if credit_score >= 800:
            return 10.0  # Excellent credit - can borrow up to 10x balance
        elif credit_score >= 750:
            return 8.0  # Very good credit
        elif credit_score >= 700:
            return 6.0  # Good credit
        elif credit_score >= 650:
            return 4.0  # Fair credit
        elif credit_score >= 600:
            return 3.0  # Poor credit
        elif credit_score >= 550:
            return 2.0  # Very poor credit
        else:
            return 1.0  # Bad credit - can only borrow up to 1x balance

    def _get_interest_rate_by_credit_score(self, credit_score: int) -> float:
        """Calculate interest rate based on credit score"""
        if credit_score >= 800:
            return 8.0  # Excellent credit - lowest interest rate
        elif credit_score >= 750:
            return 9.0  # Very good credit
        elif credit_score >= 700:
            return 10.0  # Good credit
        elif credit_score >= 650:
            return 11.0  # Fair credit
        elif credit_score >= 600:
            return 12.0  # Poor credit
        elif credit_score >= 550:
            return 14.0  # Very poor credit
        else:
            return 16.0  # Bad credit - highest interest rate

    # Added for backwards compatibility
    def _calculate_credit_limit_multiplier(self, credit_score: int) -> float:
        """Calculate credit limit multiplier based on credit score"""
        return self._get_credit_multiplier(credit_score)

    def _calculate_loan_interest_rate(self, credit_score: int) -> float:
        """Calculate loan interest rate based on credit score"""
        return self._get_interest_rate_by_credit_score(credit_score)

    @measure_performance("update_credit_score")
    async def update_credit_score(self, user_id: str, action: str, change: int, reason: str) -> dict:
        """
        Update a user's credit score based on their actions
        """
        # Get account
        account = await self.get_account(user_id)

        if not account:
            raise AccountNotFoundError(f"Account not found for user {user_id}")

        # Get current credit score and ensure it's within valid range after change
        current_score = account.get("credit_score", 600)
        new_score = max(300, min(850, current_score + change))

        # Create credit history event
        timestamp = datetime.datetime.now(datetime.UTC)
        credit_event = {
            "date": timestamp,
            "action": action,
            "change": change,
            "reason": reason,
            "old_score": current_score,
            "new_score": new_score,
        }

        # Update account with new credit score and add to history
        filter_query = {"user_id": user_id}
        update_query = {
            "$set": {"credit_score": new_score},
            "$push": {"credit_history": credit_event},
        }

        try:
            result = await self.db.accounts.update_one(filter_query, update_query)

            if result.modified_count == 0:
                raise CreditScoreError(f"Failed to update credit score for user {user_id}")

            return {
                "user_id": user_id,
                "old_score": current_score,
                "new_score": new_score,
                "change": change,
                "action": action,
                "timestamp": timestamp,
            }

        except Exception as e:
            self.logger.error(
                {
                    "event": "Error updating credit score",
                    "error": str(e),
                    "user_id": user_id,
                    "level": "error",
                }
            )
            raise CreditScoreError(f"Error updating credit score: {str(e)}")

    async def get_credit_report(self, user_id: str) -> dict:
        """
        Generate a detailed credit report for a user
        """
        # Get account
        account = await self.get_account(user_id)

        if not account:
            raise AccountNotFoundError(f"Account not found for user {user_id}")

        # Extract basic credit information
        credit_score = account.get("credit_score", 600)
        credit_history = account.get("credit_history", [])

        # Calculate account age in days
        created_at = account.get("created_at", datetime.datetime.now(datetime.UTC))
        account_age_days = (datetime.datetime.now(datetime.UTC) - created_at).days

        # Get recent transactions (last 30 days)
        thirty_days_ago = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=30)

        transactions_query = {"user_id": user_id, "timestamp": {"$gte": thirty_days_ago}}

        try:
            recent_transactions = []
            async for transaction in self.db.transactions.find(transactions_query).sort("timestamp", -1):
                recent_transactions.append(transaction)

            transaction_count_30d = len(recent_transactions)

            # Calculate average balance from recent transactions
            if transaction_count_30d > 0:
                average_balance = account.get("balance", 0)
            else:
                average_balance = account.get("balance", 0)

            # Check if user has an active loan
            loan = await self.get_active_loan(user_id)
            has_active_loan = loan is not None

            loan_repayment_status = "N/A"
            if has_active_loan:
                if loan.get("overdue_days", 0) > 0:
                    loan_repayment_status = f"Overdue ({loan['overdue_days']} days)"
                else:
                    loan_repayment_status = "Current"

            # Calculate credit benefits based on score
            credit_limit_multiplier = self._calculate_credit_limit_multiplier(credit_score)
            loan_interest_rate = self._calculate_loan_interest_rate(credit_score)

            # Get credit rating
            credit_rating = "Unknown"
            if credit_score >= 800:
                credit_rating = "Excellent"
            elif credit_score >= 750:
                credit_rating = "Very Good"
            elif credit_score >= 700:
                credit_rating = "Good"
            elif credit_score >= 650:
                credit_rating = "Fair"
            elif credit_score >= 600:
                credit_rating = "Poor"
            elif credit_score >= 550:
                credit_rating = "Very Poor"
            else:
                credit_rating = "Bad"

            # Get recent credit events
            recent_credit_events = []
            if credit_history:
                # Sort by date and get the 10 most recent
                sorted_history = sorted(
                    credit_history, key=lambda x: x.get("date", datetime.datetime.min), reverse=True
                )
                recent_credit_events = sorted_history[:10]

            # Build and return the credit report
            credit_report = {
                "user_id": user_id,
                "credit_score": credit_score,
                "credit_rating": credit_rating,
                "account_age_days": account_age_days,
                "transaction_count_30d": transaction_count_30d,
                "average_balance": average_balance,
                "has_active_loan": has_active_loan,
                "loan_repayment_status": loan_repayment_status,
                "credit_limit_multiplier": credit_limit_multiplier,
                "loan_interest_rate": loan_interest_rate,
                "recent_credit_events": recent_credit_events,
            }

            return credit_report

        except Exception as e:
            self.logger.error(
                {
                    "event": "Error generating credit report",
                    "error": str(e),
                    "user_id": user_id,
                    "level": "error",
                }
            )
            raise CreditScoreError(f"Error generating credit report: {str(e)}")

    @measure_performance("get_all_accounts")
    async def get_all_accounts(self) -> list[dict[str, Any]]:
        """Get all accounts in the system"""
        try:
            # Check if db is available
            if self.db is None:
                return []

            async def _fetch_accounts():
                return await self.db.accounts.find().to_list(None)

            # Use retry mechanism for better reliability
            return await self._execute_with_retry("get_all_accounts", _fetch_accounts)
        except Exception as e:
            self.logger.error({"event": "Failed to get all accounts", "error": str(e), "level": "error"})
            return []

    @measure_performance("get_accounts_with_active_loans")
    async def get_accounts_with_active_loans(self) -> list[dict[str, Any]]:
        """Get all accounts with active loans"""
        try:
            # Check if db is available
            if self.db is None:
                return []

            # Use a simple query to find accounts with active loans
            # This query is more efficient than getting all accounts and filtering in Python
            async def _fetch_accounts_with_loans():
                return await self.db.accounts.find({"loan.status": "active"}).to_list(None)

            return await self._execute_with_retry("get_accounts_with_active_loans", _fetch_accounts_with_loans)
        except Exception as e:
            self.logger.error(
                {
                    "event": "Failed to get accounts with active loans",
                    "error": str(e),
                    "level": "error",
                }
            )
            return []

    @measure_performance("get_recent_transactions")
    @smart_cache(ttl=300)  # 5 minutes cache
    async def get_recent_transactions(self, user_id: str, days: int = 30) -> list[dict[str, Any]]:
        """Get recent transactions for a user within the specified number of days"""
        try:
            if not self._validate_id(user_id):
                raise ValidationError("Invalid user ID format")

            # Calculate date range
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

            # Add projection to limit returned fields
            projection = {"user_id": 1, "transaction_type": 1, "amount": 1, "timestamp": 1, "description": 1, "_id": 1}

            # Optimize query with date range filter
            query = optimize_query({"user_id": user_id, "timestamp": {"$gte": start_date, "$lte": end_date}})

            cursor = self.db.transactions.find(query, projection)
            cursor.sort("timestamp", -1)

            return await cursor.to_list(length=None)
        except Exception as e:
            self.logger.error(f"Error getting recent transactions: {str(e)}")
            return []

    @measure_performance
    @smart_cache(ttl=300)  # 5 minutes cache
    async def get_active_loan(self, user_id: str) -> dict[str, Any] | None:
        """Get active loan for a user"""
        try:
            if not self._validate_id(user_id):
                raise ValidationError("Invalid user ID format")

            account = await self.get_account(user_id)
            if not account:
                return None

            loan = account.get("loan")
            if not loan or loan.get("status") != "active":
                return None

            return loan
        except Exception as e:
            self.logger.error(
                {
                    "event": "Failed to get active loan",
                    "error": str(e),
                    "user_id": user_id,
                    "level": "error",
                }
            )
            return None

    def _log_mongo_connection_details(self, db_name=None):
        """Log MongoDB connection details without exposing credentials"""
        try:
            # Extract and sanitize connection information
            if self.mongo_uri:
                # Parse the connection string to extract the host
                host_part = None

                if self.mongo_uri.startswith("mongodb+srv://"):
                    # Parse for mongodb+srv:// format
                    if "@" in self.mongo_uri:
                        # Format: mongodb+srv://username:password@host/database
                        host_part = self.mongo_uri.split("@")[1].split("/")[0]
                    else:
                        # Format: mongodb+srv://host/database
                        host_part = self.mongo_uri.split("://")[1].split("/")[0]
                else:
                    # Parse for standard mongodb:// format
                    if "@" in self.mongo_uri:
                        # Format: mongodb://username:password@host:port/database
                        host_part = self.mongo_uri.split("@")[1].split("/")[0]
                    else:
                        # Format: mongodb://host:port/database
                        host_part = self.mongo_uri.split("://")[1].split("/")[0]

                # Use provided db_name or default
                if db_name is None:
                    db_name = "banking_bot"

                self.logger.info(f"MongoDB connection configured for host: {host_part}, database: {db_name}")
        except Exception as e:
            self.logger.error(f"Error parsing MongoDB connection details: {str(e)}")

    async def _log_server_info(self):
        """Log detailed MongoDB server information after successful connection"""
        if self.db is None or not self.connected:
            return

        try:
            # Get server info
            server_info = await self.client.admin.command("serverStatus")

            # Extract relevant information
            version = server_info.get("version", "unknown")
            uptime_hours = round(server_info.get("uptime", 0) / 3600, 1)
            connections = server_info.get("connections", {})
            current_connections = connections.get("current", 0)
            available_connections = connections.get("available", 0)

            # Log the information
            self.logger.info(f"Connected to MongoDB version {version} (uptime: {uptime_hours} hours)")
            self.logger.info(f"MongoDB connections: {current_connections} active, {available_connections} available")

            # Log storage engine info if available
            storage_engine = server_info.get("storageEngine", {}).get("name", "unknown")
            if storage_engine:
                self.logger.info(f"MongoDB storage engine: {storage_engine}")

        except Exception as e:
            self.logger.error(f"Error retrieving MongoDB server info: {str(e)}")

    async def _setup_ttl_index(self):
        """Set up TTL index for transaction expiry"""
        if self.db is None:
            self.logger.error("Cannot setup TTL index: database not initialized")
            return False

        try:
            # Check if index already exists
            indexes = await self.db.transactions.index_information()

            # Check for TTL indexes
            ttl_index_exists = False
            for index_name, index_info in indexes.items():
                if "expireAfterSeconds" in index_info:
                    ttl_index_exists = True
                    self.logger.info(f"TTL index already exists with name: {index_name}")
                    break

            if not ttl_index_exists:
                try:
                    # Create TTL index on timestamp field
                    result = await self.db.transactions.create_index(
                        [("timestamp", ASCENDING)],
                        expireAfterSeconds=60 * 60 * 24 * 30,  # 30 days
                        name="transaction_expiry_ttl",
                    )
                    self.logger.info(f"Created TTL index on transactions collection: {result}")
                except OperationFailure as e:
                    # Handle permission denied errors gracefully
                    if "not allowed to do action [createIndex]" in str(e):
                        self.logger.warning("Skipping TTL index creation - insufficient permissions on Atlas")
                        # Consider the operation successful anyway
                        return True
                    else:
                        raise

            return True
        except Exception as e:
            self.logger.error(f"Failed to create TTL index: {str(e)}")
            return False

    async def _run_performance_monitoring(self):
        """
        Periodically monitor database performance metrics.
        This method is mocked in tests to avoid actual monitoring during testing.
        """
        try:
            while True:
                # Log current performance metrics if available
                if hasattr(self, 'performance_monitor'):
                    self.performance_monitor.log_slow_operations()
                
                # Wait before next check (5 minutes)
                await asyncio.sleep(300)
        except asyncio.CancelledError:
            # Gracefully handle cancellation
            self.logger.info("Performance monitoring task cancelled")
        except Exception as e:
            self.logger.error(f"Error in performance monitoring: {e}")
