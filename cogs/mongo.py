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
from typing import Any, Dict, List, Optional, Union

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

from helper.exceptions import (
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


class PerformanceMonitor:
    def __init__(self):
        self.operation_times: Dict[str, List[float]] = {}
        self.logger = logging.getLogger('bot')

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
                self.logger.info({
                    'event': 'Slow operation detected',
                    'operation': operation,
                    'avg_time': f"{avg_time:.2f}s",
                    'level': 'warning'
                })

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
            if args and hasattr(args[0], 'db') and (args[0].db is None or not hasattr(args[0], 'connected') or not args[0].connected):
                # Just execute the function without monitoring
                return await func(*args, **kwargs)
                
            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                execution_time = (time.perf_counter() - start_time) * 1000  # Convert to ms
                
                # Log performance data if the class instance has performance_monitor
                if args and hasattr(args[0], 'performance_monitor'):
                    args[0].performance_monitor.record_operation(operation_name, execution_time)
                
                return result
            except Exception as e:
                execution_time = (time.perf_counter() - start_time) * 1000  # Convert to ms
                if args and hasattr(args[0], 'logger'):
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
            if args and hasattr(args[0], 'db') and (args[0].db is None or not hasattr(args[0], 'connected') or not args[0].connected):
                # Just execute the function without monitoring
                return await func(*args, **kwargs)
                
            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                execution_time = (time.perf_counter() - start_time) * 1000  # Convert to ms
                
                # Log performance data if the class instance has performance_monitor
                if args and hasattr(args[0], 'performance_monitor'):
                    args[0].performance_monitor.record_operation(op_name, execution_time)
                    
                    # Log slow operations
                    if execution_time > 500:  # 500 ms threshold for slow operations
                        if hasattr(args[0], 'logger'):
                            args[0].logger.warning(f"Slow operation '{op_name}': {execution_time:.2f}ms")
                
                return result
            except Exception as e:
                execution_time = (time.perf_counter() - start_time) * 1000  # Convert to ms
                if args and hasattr(args[0], 'logger'):
                    args[0].logger.error(f"Error in {op_name}: {str(e)} (took {execution_time:.2f}ms)")
                raise
        
        return wrapper
    
    return decorator

COG_METADATA = {
    "name": "database",
    "enabled": True,
    "version": "1.0",
    "description": "Handles MongoDB operations for the banking bot"
}

async def setup(bot):
    bot.add_cog(Database(bot))

class Database(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger('database')
        self.client = None
        self.db = None
        self.connected = False
        self.connection_retries = 0
        self.max_retries = 5  # Increased from 3
        self.retry_delay = 5  # seconds
        self.mongo_uri = self.bot.config.MONGO_URI
        
        if not self.mongo_uri:
            self.logger.error("MONGO_URI is not set in config")
            return
        
        if not (self.mongo_uri.startswith('mongodb://') or self.mongo_uri.startswith('mongodb+srv://')):
            self.logger.error(f"Invalid MONGO_URI format: {self.mongo_uri[:10]}...")
            return
        
        # Always use a fixed database name to avoid extraction issues
        db_name = 'banking_bot'  # Default database name
        
        # Log MongoDB connection details (without credentials)
        self._log_mongo_connection_details(db_name)
        
        # Initialize client in __init__ with basic settings
        try:
            self.client = AsyncIOMotorClient(
                self.mongo_uri,
                maxPoolSize=10,
                minPoolSize=2,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                socketTimeoutMS=20000,
                retryWrites=True,
                retryReads=True,
                w="majority"
            )
            
            # Initialize the db attribute with the fixed database name
            self.db = self.client.get_database(db_name)
            
            self.logger.info("MongoDB client initialized - connection will be tested in cog_load")
        except Exception as e:
            self.logger.error(f"Failed to initialize MongoDB client: {str(e)}")
            self.client = None
            self.db = None
        
        self.performance_monitor = PerformanceMonitor()
        # Connection will be fully established in cog_load
        # Start the performance check
        self._start_performance_check()

    def _start_performance_check(self):
        """Start periodic performance monitoring tasks"""
        
        # Create task for periodic performance monitoring
        self.bot.loop.create_task(self._run_performance_monitoring())
        self.logger.info("Database performance monitoring started")
        
    async def _run_performance_monitoring(self):
        """Run performance monitoring at regular intervals"""
        try:
            # Wait for bot to be fully ready
            await self.bot.wait_until_ready()
            
            # Run the monitoring loop
            while not self.bot.is_closed():
                try:
                    if self.db is not None and self.connected:
                        await self._periodic_performance_check()
                    else:
                        self.logger.warning("Skipping performance check: not connected to database")
                except Exception as e:
                    self.logger.error(f"Error during periodic performance check: {str(e)}")
                    
                # Wait for next check interval
                await asyncio.sleep(300)  # Check every 5 minutes
        except Exception as e:
            self.logger.error(f"Performance monitoring task stopped: {str(e)}")

    @commands.slash_command(description="View database performance metrics")
    @commands.has_permissions(administrator=True)
    async def performance_metrics(self, ctx):
        """View database performance metrics"""
        try:
            metrics = self.performance_monitor.operation_times
            if not metrics:
                await ctx.respond("No performance metrics available yet.")
                return

            embed = discord.Embed(
                title="Database Performance Metrics",
                description="Average execution times for database operations",
                color=discord.Color.blue()
            )

            for operation, times in metrics.items():
                if times:  # Only show operations that have been recorded
                    avg_time = sum(times) / len(times)
                    count = len(times)
                    embed.add_field(
                        name=operation,
                        value=f"Average: {avg_time:.3f}s\nCount: {count}",
                        inline=False
                    )

            await ctx.respond(embed=embed, ephemeral=True)
        except Exception as e:
            self.logger.error({
                'event': 'Failed to get performance metrics',
                'error': str(e),
                'level': 'error'
            })
            await ctx.respond("Failed to get performance metrics.", ephemeral=True)

    async def cog_load(self):
        """Called when the cog is loaded"""
        self.logger.info("Loading Database cog")
        
        # Try to force a connection using a more direct approach
        await self._force_connection()
        
        # If we didn't succeed with the force method, try the normal way
        if not self.connected:
            self.logger.info("Forced connection failed, trying standard connection...")
            # Try to connect to the database (if we have a client)
            if self.client is not None:
                self.logger.info("Database client exists, attempting connection test...")
                try:
                    # Test the connection
                    connection_result = await self._test_connection()
                    self.logger.info(f"Connection test result: {connection_result}")
                    
                    # If connection test passes, set up collections
                    if self.connected:
                        self.logger.info("Connection successful, setting up collections...")
                        await self._ensure_collections_exist()
                        # Set up TTL index for expired transactions
                        await self._setup_ttl_index()
                        # Start the daily tasks
                        self._start_daily_tasks()
                        self.logger.info("Database cog fully loaded and connected")
                    else:
                        self.logger.warning("Database cog loaded but not connected to MongoDB")
                except Exception as e:
                    self.logger.error(f"Failed to complete Database cog initialization: {str(e)}", exc_info=True)
            else:
                self.logger.warning("Database cog loaded without MongoDB client initialization")
        else:
            self.logger.info("Forced connection successful, setting up collections...")
            await self._ensure_collections_exist()
            # Set up TTL index for expired transactions
            await self._setup_ttl_index()
            # Start the daily tasks
            self._start_daily_tasks()
            self.logger.info("Database cog fully loaded and connected with forced method")
    
    async def _force_connection(self):
        """Try a more direct approach to connect to MongoDB"""
        self.logger.info("Attempting forced connection to MongoDB...")
        
        try:
            # Reset client
            if self.client:
                try:
                    self.client.close()
                except:
                    pass
                
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
                socketTimeoutMS=10000
            )
            
            # Always use a fixed database name
            db_name = 'banking_bot'
            
            # Get the database directly using indexing instead of get_database
            self.db = self.client[db_name]
            
            # Simple ping test
            self.logger.info("Testing forced connection...")
            await self.client.admin.command('ping')
            
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
                
                self.logger.info(f"MongoDB server: v{version}, uptime: {uptime_hours}h, "
                                f"connections: {current}/{current+available}")
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
        uri_parts = self.mongo_uri.split('@')
        safe_uri = uri_parts[-1] if len(uri_parts) > 1 else self.mongo_uri.split('://')[-1]
        self.logger.info(f"Testing connection to MongoDB at {safe_uri}")
        
        while retry_count <= max_retries:
            try:
                # Try to ping the database
                self.logger.info(f"Connection attempt {retry_count+1}/{max_retries+1} to MongoDB")
                
                # Add timeout to prevent getting stuck
                ping_task = self.client.admin.command('ping')
                ping_result = await asyncio.wait_for(ping_task, timeout=5.0)
                
                self.connected = True
                self.logger.info("Successfully connected to MongoDB")
                return True
                
            except asyncio.TimeoutError:
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
            'accounts', 'transactions', 'settings', 'performance_metrics',
            'credit_scores', 'loans', 'kyc_records', 'admin'
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
            await self.client.admin.command('ping')
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
                if hasattr(self, 'last_reconnect_attempt'):
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
            if hasattr(self.client, 'get_io_loop'):
                try:
                    server_status = await self.client.admin.command('serverStatus')
                    connections = server_status.get('connections', {})
                    
                    metrics = {
                        'ping_ms': round(ping_time, 2),
                        'total_connections': connections.get('current', 'N/A'),
                        'available_connections': connections.get('available', 'N/A'),
                        'timestamp': datetime.utcnow().isoformat()
                    }
                    
                    # Log performance metrics
                    self.logger.info(f"MongoDB Performance: Ping={metrics['ping_ms']}ms, "
                                    f"Connections={metrics['total_connections']}, "
                                    f"Available={metrics['available_connections']}")
                    
                    # Store metrics in database if connected
                    if self.connected and self.db is not None:
                        try:
                            await self.db.performance_metrics.insert_one(metrics)
                        except OperationFailure as e:
                            # Check if this is a permissions error for Atlas
                            if 'not allowed to do action' in str(e):
                                self.logger.warning("Skipping metrics storage - insufficient Atlas permissions")
                            else:
                                self.logger.error(f"Failed to store metrics: {str(e)}")
                        except Exception as e:
                            self.logger.error(f"Unexpected error storing metrics: {str(e)}")
                except OperationFailure as e:
                    # Check if this is a permissions error for Atlas
                    if 'not allowed to do action' in str(e):
                        self.logger.warning(f"Limited permissions on Atlas - skipping detailed metrics collection: {str(e)}")
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

    @measure_performance
    async def _execute_with_retry(self, operation_name, operation_func, max_retries=3):
        """Execute a database operation with automatic retries for transient errors"""
        if self.db is None:
            self.logger.error(f"Cannot execute {operation_name}: database not initialized")
            return None
        
        retry_count = 0
        last_error = None
        start_time = time.perf_counter()
        
        while retry_count <= max_retries:
            try:
                # Execute the operation
                result = await operation_func()
                
                # Log success (with timing)
                execution_time = (time.perf_counter() - start_time) * 1000  # Convert to ms
                
                if execution_time > 500:  # Log slow operations
                    self.logger.warning(f"{operation_name} completed in {execution_time:.2f}ms (slow)")
                elif retry_count > 0:  # Log retry successes
                    self.logger.info(f"{operation_name} succeeded after {retry_count} retries (took {execution_time:.2f}ms)")
                
                return result
            except (ConnectionFailure, NetworkTimeout, ServerSelectionTimeoutError) as e:
                retry_count += 1
                last_error = e
                
                if retry_count <= max_retries:
                    # Exponential backoff
                    wait_time = 0.5 * (2 ** retry_count)  # 1, 2, 4 seconds...
                    self.logger.warning(f"{operation_name} failed with error: {str(e)}. Retrying in {wait_time:.1f}s ({retry_count}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    self.logger.error(f"{operation_name} failed after {max_retries} retries: {str(e)}")
            except Exception as e:
                # Non-retriable error
                self.logger.error(f"{operation_name} failed with non-retriable error: {str(e)}")
                last_error = e
                break
            
        # If we get here, all retries failed
        self.logger.error(f"{operation_name} operation failed: {str(last_error)}")
        return None

    async def _setup_collections(self):
        """Setup collections with proper validation"""
        try:
            # For MongoDB Atlas with limited user permissions, simply check collections
            # rather than trying to modify them
            if 'mongodb+srv' in self.mongo_uri:
                self.logger.info("Using MongoDB Atlas - skipping collection validation setup")
                return True
                
            # Continue with normal setup for non-Atlas connections
            # Setup accounts collection
            await self.db.command({
                "collMod": "accounts",
                "validator": {
                    "$jsonSchema": {
                        "bsonType": "object",
                        "required": ["user_id", "guild_id", "username", "branch_name", "balance", "created_at"],
                        "properties": {
                            "user_id": {"bsonType": "string"},
                            "guild_id": {"bsonType": "string"},
                            "username": {"bsonType": "string"},
                            "branch_name": {"bsonType": "string"},
                            "balance": {"bsonType": "number"},
                            "created_at": {"bsonType": "date"},
                            "upi_id": {"bsonType": "string"},
                            "interest_rate": {"bsonType": "number", "minimum": 0, "maximum": 100},
                            "last_interest_calculation": {"bsonType": "date"},
                            "account_type": {
                                "bsonType": "string",
                                "enum": ["savings", "checking", "fixed_deposit"]
                            },
                            "credit_score": {"bsonType": "number", "minimum": 300, "maximum": 850},
                            "credit_history": {
                                "bsonType": "array",
                                "items": {
                                    "bsonType": "object",
                                    "properties": {
                                        "date": {"bsonType": "date"},
                                        "action": {"bsonType": "string"},
                                        "change": {"bsonType": "number"},
                                        "reason": {"bsonType": "string"}
                                    }
                                }
                            },
                            "fixed_deposit": {
                                "bsonType": "object",
                                "properties": {
                                    "amount": {"bsonType": "number"},
                                    "term_months": {"bsonType": "int"},
                                    "maturity_date": {"bsonType": "date"},
                                    "interest_rate": {"bsonType": "number"}
                                }
                            },
                            "loan": {
                                "bsonType": "object",
                                "properties": {
                                    "amount": {"bsonType": "number"},
                                    "interest_rate": {"bsonType": "number"},
                                    "term_months": {"bsonType": "int"},
                                    "monthly_payment": {"bsonType": "number"},
                                    "remaining_amount": {"bsonType": "number"},
                                    "next_payment_date": {"bsonType": "date"},
                                    "start_date": {"bsonType": "date"},
                                    "end_date": {"bsonType": "date"},
                                    "status": {
                                        "bsonType": "string",
                                        "enum": ["active", "paid", "defaulted"]
                                    }
                                }
                            }
                        }
                    }
                }
            })
            return True
        except OperationFailure as e:
            # If we get permission denied, log a warning but don't fail
            if 'not allowed to do action' in str(e):
                self.logger.warning(f"Skipping collection setup - insufficient permissions: {str(e)}")
                return True
            self.logger.error(f"Failed to setup collections: {str(e)}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error in _setup_collections: {str(e)}")
            return False

    async def _setup_indexes(self):
        """Set up necessary indexes for collections"""
        try:
            # Account collection indexes
            await self.db.accounts.create_index("user_id", unique=True)
            await self.db.accounts.create_index("guild_id")
            await self.db.accounts.create_index([("branch_name", ASCENDING), ("balance", DESCENDING)])
            await self.db.accounts.create_index("upi_id", sparse=True)
            # Add indexes for account type and interest calculation
            await self.db.accounts.create_index([("account_type", ASCENDING)])
            await self.db.accounts.create_index([("account_type", ASCENDING), ("last_interest_calculation", ASCENDING)])
            # Add index for fixed deposits
            await self.db.accounts.create_index([("account_type", ASCENDING), ("fixed_deposit.maturity_date", ASCENDING)])
            
            # Transaction collection indexes
            await self.db.transactions.create_index("user_id")
            await self.db.transactions.create_index("timestamp")
            await self.db.transactions.create_index([("user_id", ASCENDING), ("timestamp", DESCENDING)])
            await self.db.transactions.create_index("receiver_id")
            # Add index for transaction type
            await self.db.transactions.create_index([("user_id", ASCENDING), ("type", ASCENDING), ("timestamp", DESCENDING)])
            
            # KYC attempts collection indexes
            await self.db.failed_kyc_attempts.create_index("User_Id")
            await self.db.failed_kyc_attempts.create_index("timestamp")
            await self.db.failed_kyc_attempts.create_index([("User_Id", ASCENDING), ("timestamp", DESCENDING)])
            
            # Guild commands collection indexes
            await self.db.guild_commands.create_index("guild_id", unique=True)
            
            # Add TTL index for cache collection
            await self.db.cache.create_index("expires_at", expireAfterSeconds=0)
            
            self.logger.info({
                'event': 'Database indexes created',
                'level': 'info'
            })
        except OperationFailure as e:
            raise DatabaseError(f"Failed to set up database indexes: {str(e)}")

    async def cog_unload(self):
        """Clean up database connections"""
        try:
            await self.client.close()
            self.logger.info({
                'event': 'Database connection closed',
                'level': 'info'
            })
        except Exception:
            pass

    def _validate_id(self, id_str: str) -> bool:
        """Validate Discord ID format with improved security checks"""
        # Discord IDs must be numeric and between 17-19 digits (snowflake format)
        if not id_str or not isinstance(id_str, str):
            return False
            
        # Check if ID contains only digits
        if not id_str.isdigit():
            return False
            
        # Verify ID length is valid for Discord snowflake
        id_length = len(id_str)
        if not (17 <= id_length <= 19):
            return False
            
        # Additional security check - validate timestamp portion of snowflake
        try:
            # Discord snowflakes have timestamp in the first 42 bits
            # This converts the ID to an integer, then bit-shifts to get the timestamp
            # 22 = number of bits for worker, process, and increment
            snowflake_int = int(id_str)
            timestamp_ms = (snowflake_int >> 22) + 1420070400000  # Discord epoch (2015-01-01T00:00:00.000Z)
            
            # Check if timestamp is in a reasonable range (between Discord epoch and current time + 1 day)
            current_ms = int(datetime.utcnow().timestamp() * 1000)
            
            # If timestamp from snowflake is before Discord's epoch or in the future (allowing 1 day for clock skew)
            if timestamp_ms < 1420070400000 or timestamp_ms > (current_ms + 86400000):
                return False
        except (ValueError, OverflowError):
            # Any failure in conversion should fail validation
            return False
                
        return True

    def _sanitize_input(self, input_str: str) -> str:
        """Sanitize input strings to prevent injection with stronger rules"""
        if not input_str:
            return ""
        # More strict sanitization to only allow alphanumeric, spaces, and common symbols
        sanitized = re.sub(r'[^a-zA-Z0-9\s\-_\.\,\:\;\(\)\[\]\{\}\!\?]', '', str(input_str))
        # Additional safety trims
        return sanitized.strip()[:500]  # Limit length to 500 chars for safety

    @measure_performance
    async def create_account(self, user_id, username, guild_id, guild_name, initial_balance=0):
        """Create a new bank account"""
        if self.db is None:
            self.logger.error(f"Cannot create account for {username}: database not initialized")
            return None
        
        try:
            # Check if account already exists to avoid duplicates
            existing = await self.db.accounts.find_one({"user_id": user_id, "guild_id": guild_id})
            if existing:
                self.logger.info(f"Account already exists for user {username} in guild {guild_name}")
                return existing
            
            # Create new account document
            account = {
                "user_id": user_id,
                "username": username,
                "guild_id": guild_id,
                "guild_name": guild_name,
                "balance": initial_balance,
                "created_at": datetime.utcnow(),
                "last_updated": datetime.utcnow(),
                "credit_score": 500,  # Default starting credit score
                "transaction_count": 0
            }
            
            # Insert the new account
            result = await self._execute_with_retry(
                f"Create account for {username}",
                lambda: self.db.accounts.insert_one(account)
            )
            
            if result:
                account['_id'] = result.inserted_id
                self.logger.info(f"Created new account for {username} in {guild_name}")
                return account
            else:
                self.logger.error(f"Failed to create account for {username} in {guild_name}")
                return None
        except Exception as e:
            self.logger.error(f"Error creating account for {username}: {str(e)}")
            return None

    @measure_performance
    async def get_account(self, user_id, guild_id):
        """Get a user's account by user_id and guild_id"""
        if self.db is None:
            self.logger.error(f"Cannot get account for user {user_id}: database not initialized")
            return None
        
        try:
            account = await self._execute_with_retry(
                f"Get account for user {user_id}",
                lambda: self.db.accounts.find_one({"user_id": user_id, "guild_id": guild_id})
            )
            
            if account:
                return account
            else:
                self.logger.info(f"No account found for user {user_id} in guild {guild_id}")
                return None
        except Exception as e:
            self.logger.error(f"Error retrieving account for user {user_id}: {str(e)}")
            return None

    @measure_performance
    async def update_balance(self, user_id, guild_id, amount, transaction_type, reason=None):
        """Update a user's balance with proper tracking"""
        if self.db is None:
            self.logger.error(f"Cannot update balance for user {user_id}: database not initialized")
            return False
        
        try:
            # Get current account
            account = await self.get_account(user_id, guild_id)
            if not account:
                self.logger.warning(f"Cannot update balance: No account found for user {user_id} in guild {guild_id}")
                return False
            
            # Calculate new balance
            current_balance = account.get('balance', 0)
            new_balance = current_balance + amount
            
            # Don't allow negative balances (unless it's a special transaction)
            if new_balance < 0 and transaction_type not in ['loan_disbursal', 'admin_adjustment']:
                self.logger.warning(f"Rejected negative balance update for user {user_id}: current={current_balance}, change={amount}")
                return False
            
            # Update account and create transaction record
            update_result = await self._execute_with_retry(
                f"Update balance for user {user_id}",
                lambda: self.db.accounts.update_one(
                    {"user_id": user_id, "guild_id": guild_id},
                    {
                        "$set": {
                            "balance": new_balance,
                            "last_updated": datetime.utcnow()
                        },
                        "$inc": {"transaction_count": 1}
                    }
                )
            )
            
            if not update_result or update_result.modified_count == 0:
                self.logger.error(f"Failed to update balance for user {user_id}")
                return False
            
            # Log the transaction
            transaction = {
                "user_id": user_id,
                "guild_id": guild_id,
                "username": account.get('username', 'Unknown'),
                "type": transaction_type,
                "amount": amount,
                "balance_before": current_balance,
                "balance_after": new_balance,
                "reason": reason or "No reason provided",
                "timestamp": datetime.utcnow()
            }
            
            transaction_result = await self._execute_with_retry(
                f"Log transaction for user {user_id}",
                lambda: self.db.transactions.insert_one(transaction)
            )
            
            if transaction_result:
                self.logger.info(f"Updated balance for {account.get('username', 'Unknown')}: {amount:+} ({transaction_type})")
                return True
            else:
                self.logger.error(f"Failed to log transaction for user {user_id}")
                return False
        except Exception as e:
            self.logger.error(f"Error updating balance for user {user_id}: {str(e)}")
            return False

    @measure_performance
    async def get_all_accounts(self):
        """Get all accounts in the system"""
        
        if self.db is None:
            self.logger.error("Cannot get accounts: database not initialized")
            return []
        
        try:
            accounts = await self._execute_with_retry(
                "Get all accounts",
                lambda: self.db.accounts.find().to_list(length=None)
            )
            
            return accounts or []
        except Exception as e:
            self.logger.error(f"Error retrieving all accounts: {str(e)}")
            return []

    @measure_performance("log_failed_kyc_attempt")
    async def log_failed_kyc_attempt(self, user_id: str, provided_user_id: str, 
                                   guild_id: str, provided_guild_id: str, reason: str) -> bool:
        """Log failed KYC attempts with validation"""
        try:
            if not all(self._validate_id(id) for id in [user_id, provided_user_id, guild_id, provided_guild_id]):
                raise ValidationError("Invalid Discord ID format")
                
            reason = self._sanitize_input(reason)
            
            failed_kyc_collection = self.db["failed_kyc_attempts"]
            await failed_kyc_collection.insert_one({
                "User_Id": user_id,
                "Provided_User_Id": provided_user_id,
                "Branch_Id": guild_id,
                "Provided_Branch_Id": provided_guild_id,
                "reason": reason,
                "timestamp": datetime.now()
            })
            return True
        except OperationFailure as e:
            raise DatabaseError(f"Failed to log KYC attempt: {str(e)}")
        except Exception as e:
            raise DatabaseError(f"Unexpected error in log_failed_kyc_attempt: {str(e)}")

    @measure_performance("log_transaction")
    async def log_transaction(self, user_id: str, transaction_type: str, amount: Union[int, float], 
                             description: str = None, receiver_id: str = None, 
                             balance_before: float = None, balance_after: float = None) -> Optional[str]:
        """
        Log a transaction with detailed information
        
        Args:
            user_id: The user's Discord ID
            transaction_type: Type of transaction (deposit, withdrawal, transfer, etc.)
            amount: Amount of money involved in the transaction
            description: Optional description of the transaction
            receiver_id: Optional recipient's Discord ID (for transfers)
            balance_before: Optional balance before the transaction
            balance_after: Optional balance after the transaction
            
        Returns:
            Transaction ID if successful, None otherwise
        """
        try:
            if not self._validate_id(user_id):
                raise ValidationError("Invalid sender Discord ID format")
                
            if receiver_id and not self._validate_id(receiver_id):
                raise ValidationError("Invalid receiver Discord ID format")
                
            if not isinstance(amount, (int, float)) or amount <= 0:
                raise ValidationError("Invalid transaction amount")
                
            # Create a unique transaction ID
            transaction_id = f"TXN-{int(time.time())}-{uuid.uuid4().hex[:8]}"
            
            # Sanitize inputs
            transaction_type = self._sanitize_input(transaction_type)
            if description:
                description = self._sanitize_input(description)
            
            # Create transaction document
            transaction = {
                "transaction_id": transaction_id,
                "user_id": user_id,
                "transaction_type": transaction_type,
                "amount": amount,
                "description": description,
                "receiver_id": receiver_id,
                "balance_before": balance_before,
                "balance_after": balance_after,
                "timestamp": datetime.utcnow()
            }
            
            # Insert transaction
            await self.db.transactions.insert_one(transaction)
            
            self.logger.info({
                'event': 'Transaction logged',
                'transaction_id': transaction_id,
                'user_id': user_id,
                'transaction_type': transaction_type,
                'amount': amount,
                'level': 'info'
            })
            
            return transaction_id
        except Exception as e:
            self.logger.error({
                'event': 'Error logging transaction',
                'error': str(e),
                'user_id': user_id,
                'transaction_type': transaction_type,
                'amount': amount,
                'level': 'error'
            })
            return None

    @measure_performance("get_transactions")
    async def get_transactions(self, user_id: str, limit: int = 10, skip: int = 0):
        """Get user transactions with pagination"""
        try:
            transactions = await self.db.transactions.find(
                {"user_id": user_id}
            ).sort("timestamp", -1).skip(skip).limit(limit).to_list(None)
            
            return transactions
        except Exception as e:
            self.logger.error({
                'event': 'Error fetching transactions',
                'error': str(e),
                'user_id': user_id,
                'level': 'error'
            })
            return []
            
    async def get_transactions_by_type_and_date(self, user_id: str, transaction_type: str, date: datetime.date):
        """Get user transactions of a specific type on a specific date"""
        try:
            # Create date range for the given date (from start to end of day)
            start_of_day = datetime.datetime.combine(date, datetime.time.min)
            end_of_day = datetime.datetime.combine(date, datetime.time.max)
            
            transactions = await self.db.transactions.find(
                {
                    "user_id": user_id,
                    "transaction_type": transaction_type,
                    "timestamp": {
                        "$gte": start_of_day,
                        "$lte": end_of_day
                    }
                }
            ).to_list(None)
            
            return transactions
        except Exception as e:
            self.logger.error({
                'event': 'Error fetching transactions by type and date',
                'error': str(e),
                'user_id': user_id,
                'transaction_type': transaction_type,
                'date': str(date),
                'level': 'error'
            })
            return []

    def generate_upi_id(self, user_id: str) -> str:
        """Generate a unique UPI ID"""
        if not self._validate_id(user_id):
            raise ValidationError("Invalid Discord ID format")
            
        bank_name = "quantumbank"
        random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
        return f"{user_id}@{bank_name}.{random_suffix}"

    @measure_performance("set_upi_id")
    async def set_upi_id(self, user_id: str) -> Optional[str]:
        """Set UPI ID with validation"""
        try:
            if not self._validate_id(user_id):
                raise ValidationError("Invalid Discord ID format")
                
            upi_id = self.generate_upi_id(user_id)
            accounts_collection = self.db["accounts"]
            
            async with await self.client.start_session() as session:
                async with session.start_transaction():
                    result = await accounts_collection.update_one(
                        {"user_id": user_id},
                        {
                            "$set": {
                                "upi_id": upi_id,
                                "last_updated": datetime.now()
                            }
                        },
                        upsert=False
                    )
                    return upi_id if result.modified_count > 0 else None
        except OperationFailure as e:
            raise DatabaseError(f"Failed to set UPI ID: {str(e)}")
        except Exception as e:
            raise DatabaseError(f"Unexpected error in set_upi_id: {str(e)}")

    async def get_leaderboard(self, branch_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get branch leaderboard with pagination"""
        try:
            branch_name = self._sanitize_input(branch_name)
            
            if not isinstance(limit, int) or limit <= 0 or limit > 100:
                raise ValidationError("Invalid limit value")
                
            cursor = self.db.accounts.find({"branch_name": branch_name})\
                .sort("balance", DESCENDING)\
                .limit(limit)
            return [doc async for doc in cursor]
        except OperationFailure as e:
            raise DatabaseError(f"Failed to get leaderboard: {str(e)}")
        except Exception as e:
            raise DatabaseError(f"Unexpected error in get_leaderboard: {str(e)}")

    @measure_performance("update_user_branch")
    async def update_user_branch(self, user_id: str, branch_id: str, branch_name: str) -> bool:
        """Update user's branch with validation"""
        try:
            if not self._validate_id(user_id) or not self._validate_id(branch_id):
                raise ValidationError("Invalid Discord ID format")
                
            branch_name = self._sanitize_input(branch_name)
            
            async with await self.client.start_session() as session:
                async with session.start_transaction():
                    result = await self.db.accounts.update_one(
                        {"user_id": user_id},
                        {
                            "$set": {
                                "branch_id": branch_id,
                                "branch_name": branch_name,
                                "last_updated": datetime.now()
                            }
                        },
                        upsert=False
                    )
                    return result.modified_count > 0
        except OperationFailure as e:
            raise DatabaseError(f"Failed to update user branch: {str(e)}")
        except Exception as e:
            raise DatabaseError(f"Unexpected error in update_user_branch: {str(e)}")

    @measure_performance("toggle_command")
    async def toggle_command(self, guild_id: str, command_name: str, status: bool) -> bool:
        """Toggle command status with validation"""
        try:
            if not self._validate_id(guild_id):
                raise ValidationError("Invalid Discord ID format")
                
            command_name = self._sanitize_input(command_name)
            
            async with await self.client.start_session() as session:
                async with session.start_transaction():
                    result = await self.db["guild_commands"].update_one(
                        {"guild_id": guild_id},
                        {"$set": {command_name: status}},
                        upsert=True
                    )
                    return result.modified_count > 0 or result.upserted_id is not None
        except OperationFailure as e:
            raise DatabaseError(f"Failed to toggle command: {str(e)}")
        except Exception as e:
            raise DatabaseError(f"Unexpected error in toggle_command: {str(e)}")

    async def get_command_status(self, guild_id: str, command_name: str) -> bool:
        """Get command status with error handling"""
        try:
            if not self._validate_id(guild_id):
                raise ValidationError("Invalid Discord ID format")
                
            command_name = self._sanitize_input(command_name)
            
            guild_commands = await self.db["guild_commands"].find_one({"guild_id": guild_id})
            return guild_commands.get(command_name, True) if guild_commands else True
        except OperationFailure as e:
            raise DatabaseError(f"Failed to get command status: {str(e)}")
        except Exception as e:
            raise DatabaseError(f"Unexpected error in get_command_status: {str(e)}")

    @measure_performance("ping_db")
    async def ping_db(self) -> bool:
        """Check if database connection is working"""
        try:
            # Check if client exists
            if self.client is None:
                self.logger.error({
                    'event': 'Database client is None',
                    'level': 'error'
                })
                return False
            
            # Just try a simple ping command on the database itself
            if self.db is not None:  # Changed this condition
                try:
                    ping_result = await self.db.command("ping")
                    if ping_result and ping_result.get('ok', 0) == 1:
                        return True
                except Exception as e:
                    self.logger.error(f"Ping command failed: {e}")
                    return False
            
            # If we got here, the ping failed or db is None
            return False
        except Exception as e:
            self.logger.error({
                'event': 'Unexpected database error during ping',
                'error': str(e),
                'level': 'error'
            })
            return False

    def _calculate_interest_rate_by_balance(self, balance: float) -> float:
        """Calculate interest rate based on account balance tiers"""
        if balance >= 1000000:  # $1M+
            return 5.0
        elif balance >= 500000:  # $500K+
            return 4.5
        elif balance >= 100000:  # $100K+
            return 4.0
        elif balance >= 50000:  # $50K+
            return 3.5
        elif balance >= 10000:  # $10K+
            return 3.0
        else:
            return 2.5  # Base rate

    async def calculate_interest(self, user_id: str) -> bool:
        """Calculate and apply interest for savings accounts"""
        try:
            account = await self.get_account(user_id)
            if not account or account.get('account_type') != 'savings':
                return False

            # Check if account balance has changed enough to adjust interest rate
            current_balance = account['balance']
            current_interest_rate = account.get('interest_rate', 2.5)
            
            # Calculate appropriate interest rate based on balance tiers
            new_interest_rate = self._calculate_interest_rate_by_balance(current_balance)
            
            # Update interest rate if it changed
            if new_interest_rate != current_interest_rate:
                await self.update_account(user_id, {"interest_rate": new_interest_rate})
                self.logger.info({
                    'event': 'Interest rate adjusted based on balance',
                    'user_id': user_id,
                    'previous_rate': current_interest_rate,
                    'new_rate': new_interest_rate,
                    'balance': current_balance,
                    'level': 'info'
                })
                # Use the new rate for calculation
                interest_rate = new_interest_rate
            else:
                interest_rate = current_interest_rate

            last_calculation = account.get('last_interest_calculation', account['created_at'])
            current_time = datetime.utcnow()

            # Calculate days since last interest calculation
            days = (current_time - last_calculation).days
            if days < 1:  # Minimum 1 day for interest calculation
                return False

            # Calculate interest (simple interest)
            balance = account['balance']
            interest = (balance * interest_rate * days) / (365 * 100)
            
            # Log calculation details for transparency
            self.logger.info({
                'event': 'Interest calculation',
                'user_id': user_id,
                'balance': balance,
                'interest_rate': interest_rate,
                'days_since_last_calc': days,
                'interest_amount': interest,
                'level': 'info'
            })

            # Update balance and last calculation time
            new_balance = balance + interest
            await self.update_balance(user_id, None, new_balance, 'interest_credit', f"Interest accrued at {interest_rate}%")
            
            # Update last interest calculation time
            await self.db.accounts.update_one(
                {"user_id": user_id},
                {"$set": {"last_interest_calculation": current_time}}
            )

            # Log interest transaction
            await self.log_transaction(
                user_id=user_id,
                txn_type='interest_credit',
                amount=interest,
                receiver_id=None
            )

            return True
        except Exception as e:
            self.logger.error({
                'event': 'Failed to calculate interest',
                'error': str(e),
                'user_id': user_id,
                'level': 'error'
            })
            return False

    async def set_account_type(self, user_id: str, account_type: str, interest_rate: float = None) -> bool:
        """Set account type and interest rate"""
        try:
            if account_type not in ['savings', 'checking', 'fixed_deposit']:
                raise ValidationError("Invalid account type")

            update_data = {"account_type": account_type}
            if account_type == 'savings' and interest_rate is not None:
                update_data["interest_rate"] = interest_rate
                update_data["last_interest_calculation"] = datetime.utcnow()

            result = await self.db.accounts.update_one(
                {"user_id": user_id},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except Exception as e:
            self.logger.error({
                'event': 'Failed to set account type',
                'error': str(e),
                'user_id': user_id,
                'account_type': account_type,
                'level': 'error'
            })
            return False

    async def create_fixed_deposit(self, user_id: str, fd_data: dict, new_balance: float) -> bool:
        """Create a Fixed Deposit and update account balance"""
        try:
            async with await self.client.start_session() as session:
                async with session.start_transaction():
                    # Update account balance and add FD details
                    result = await self.db.accounts.update_one(
                        {"user_id": user_id},
                        {
                            "$set": {
                                "balance": new_balance,
                                "fixed_deposit": fd_data,
                                "account_type": "fixed_deposit",
                                "last_updated": datetime.utcnow()
                            }
                        }
                    )
                    
                    if result.modified_count > 0:
                        # Log FD creation transaction
                        await self.log_transaction(
                            user_id=user_id,
                            txn_type='fd_created',
                            amount=fd_data['amount'],
                            receiver_id=None
                        )
                        return True
                    return False
        except Exception as e:
            self.logger.error({
                'event': 'Failed to create fixed deposit',
                'error': str(e),
                'user_id': user_id,
                'level': 'error'
            })
            return False

    async def check_fd_maturity(self, user_id: str) -> bool:
        """Check and process matured Fixed Deposits"""
        try:
            account = await self.get_account(user_id)
            if not account or not account.get('fixed_deposit'):
                return False

            fd = account['fixed_deposit']
            current_time = datetime.utcnow()

            # Check if FD has matured
            if current_time >= fd['maturity_date']:
                # Calculate final interest
                months = fd['term_months']
                interest = (fd['amount'] * fd['interest_rate'] * months) / (12 * 100)
                total_amount = fd['amount'] + interest

                async with await self.client.start_session() as session:
                    async with session.start_transaction():
                        # Update account balance and remove FD
                        result = await self.db.accounts.update_one(
                            {"user_id": user_id},
                            {
                                "$inc": {"balance": total_amount},
                                "$unset": {"fixed_deposit": ""},
                                "$set": {
                                    "account_type": "savings",
                                    "last_updated": current_time
                                }
                            }
                        )

                        if result.modified_count > 0:
                            # Log FD maturity transaction
                            await self.log_transaction(
                                user_id=user_id,
                                transaction_type='fd_matured',
                                amount=total_amount,
                                description="Fixed deposit matured with interest"
                            )
                            return True
                return False
            return False
        except Exception as e:
            self.logger.error({
                'event': 'Failed to check FD maturity',
                'error': str(e),
                'user_id': user_id,
                'level': 'error'
            })
            return False

    @measure_performance("create_loan")
    async def create_loan(self, user_id: str, amount: float, term_months: int) -> bool:
        """Create a loan for a user"""
        try:
            account = await self.get_account(user_id)
            if not account:
                raise AccountNotFoundError(f"No account found for user ID: {user_id}")
                
            # Check if user already has an active loan
            if account.get('loan') and account['loan'].get('status') == 'active':
                raise LoanAlreadyExistsError("You already have an active loan")
                
            # Check credit score
            credit_score = account.get('credit_score', 600)
            
            # Check if credit score is sufficient for the loan amount
            if amount > 1000 and credit_score < 550:
                raise InsufficientCreditScoreError(f"Your credit score ({credit_score}) is too low for a loan of ${amount:,.2f}. Work on improving your score by making regular transactions and maintaining a positive balance.")
            
            if amount > 5000 and credit_score < 600:
                raise InsufficientCreditScoreError(f"Your credit score ({credit_score}) is too low for a loan of ${amount:,.2f}. Work on improving your score by making regular transactions and maintaining a positive balance.")
            
            if amount > 10000 and credit_score < 650:
                raise InsufficientCreditScoreError(f"Your credit score ({credit_score}) is too low for a loan of ${amount:,.2f}. Work on improving your score by making regular transactions and maintaining a positive balance.")
                
            # Calculate user's credit limit based on account history, balance, and credit score
            # Higher credit scores allow for higher loan limits
            credit_multiplier = self._get_credit_multiplier(credit_score)
            credit_limit = account['balance'] * credit_multiplier
            
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
                "status": "active"
            }
            
            # Update account with loan and add loan amount to balance
            async with await self.client.start_session() as session:
                async with session.start_transaction():
                    # Add loan to account
                    update_result = await self.db.accounts.update_one(
                        {"user_id": user_id},
                        {
                            "$set": {
                                "loan": loan_data,
                                "last_updated": datetime.utcnow()
                            },
                            "$inc": {
                                "balance": amount
                            }
                        }
                    )
                    
                    if update_result.modified_count == 0:
                        raise DatabaseError("Failed to create loan")
                        
                    # Update credit history for taking a loan (small negative impact)
                    await self.update_credit_score(
                        user_id=user_id,
                        action="loan_taken",
                        change=-5,
                        reason=f"Took a loan of ${amount:,.2f}"
                    )
                        
                    # Log loan transaction
                    await self.log_transaction(
                        user_id=user_id,
                        transaction_type="loan_received",
                        amount=amount,
                        description=f"Loan received for {term_months} months at {interest_rate}% interest",
                        balance_before=account['balance'],
                        balance_after=account['balance'] + amount
                    )
                    
                    return True
                    
        except Exception as e:
            if isinstance(e, (AccountNotFoundError, LoanAlreadyExistsError, LoanLimitError, InsufficientCreditScoreError, DatabaseError)):
                raise e
            self.logger.error({
                'event': 'Failed to create loan',
                'error': str(e),
                'user_id': user_id,
                'level': 'error'
            })
            raise DatabaseError(f"Failed to create loan: {str(e)}")
            
    @measure_performance("repay_loan")
    async def repay_loan(self, user_id: str, amount: float = None) -> Dict[str, Any]:
        """Repay a loan (either specific amount or monthly payment)"""
        try:
            account = await self.get_account(user_id)
            if not account:
                raise AccountNotFoundError(f"No account found for user ID: {user_id}")
                
            # Check if user has an active loan
            if not account.get('loan') or account['loan'].get('status') != 'active':
                raise LoanError("You don't have an active loan to repay")
                
            loan = account['loan']
            
            # If no amount specified, use monthly payment
            if amount is None:
                amount = loan['monthly_payment']
                
            # Check if user has enough balance
            if account['balance'] < amount:
                raise InsufficientFundsError(f"Insufficient funds to make loan payment of ${amount:,.2f}")
                
            # If payment amount is greater than remaining amount, adjust to pay off the loan
            if amount > loan['remaining_amount']:
                amount = loan['remaining_amount']
                
            # Calculate new remaining amount
            new_remaining = loan['remaining_amount'] - amount
            new_status = "active" if new_remaining > 0 else "paid"
            
            # Calculate next payment date (30 days from today if still active)
            next_payment_date = datetime.utcnow() + timedelta(days=30) if new_status == "active" else None
            
            async with await self.client.start_session() as session:
                async with session.start_transaction():
                    # Update loan info
                    update_data = {
                        "balance": account['balance'] - amount,
                        "last_updated": datetime.utcnow()
                    }
                    
                    if new_status == "paid":
                        # Loan is fully paid, remove it
                        update_data["loan"] = None
                        
                        # Significant credit score boost for fully paying off a loan
                        await self.update_credit_score(
                            user_id=user_id,
                            action="loan_fully_paid",
                            change=25,
                            reason=f"Fully repaid loan of ${loan['amount']:,.2f}"
                        )
                    else:
                        # Update loan details
                        loan_update = loan.copy()
                        loan_update['remaining_amount'] = new_remaining
                        loan_update['next_payment_date'] = next_payment_date
                        loan_update['status'] = new_status
                        update_data["loan"] = loan_update
                        
                        # Small credit score boost for making a payment on time
                        current_time = datetime.utcnow()
                        if loan['next_payment_date'] >= current_time:
                            await self.update_credit_score(
                                user_id=user_id,
                                action="on_time_payment",
                                change=5,
                                reason=f"Made on-time loan payment of ${amount:,.2f}"
                            )
                        else:
                            # Late payment has negative impact
                            days_late = (current_time - loan['next_payment_date']).days
                            if days_late > 0:
                                await self.update_credit_score(
                                    user_id=user_id,
                                    action="late_payment",
                                    change=-5 * min(days_late // 7 + 1, 5),  # Max -25 points for very late payments
                                    reason=f"Made loan payment {days_late} days late"
                                )
                        
                    # Update account
                    update_result = await self.db.accounts.update_one(
                        {"user_id": user_id},
                        {"$set": update_data}
                    )
                    
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
                        balance_before=account['balance'],
                        balance_after=account['balance'] - amount
                    )
                    
                    # Return payment result
                    return {
                        "amount_paid": amount,
                        "remaining_amount": new_remaining,
                        "status": new_status,
                        "fully_paid": new_status == "paid"
                    }
                    
        except Exception as e:
            if isinstance(e, (AccountNotFoundError, LoanError, InsufficientFundsError, DatabaseError)):
                raise e
            self.logger.error({
                'event': 'Failed to process loan payment',
                'error': str(e),
                'user_id': user_id,
                'level': 'error'
            })
            raise DatabaseError(f"Failed to process loan payment: {str(e)}")
            
    @measure_performance("check_loan_status")
    async def check_loan_status(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Check status of a user's loan"""
        try:
            account = await self.get_account(user_id)
            if not account:
                raise AccountNotFoundError(f"No account found for user ID: {user_id}")
                
            # Check if user has a loan
            if not account.get('loan'):
                return None
                
            loan = account['loan']
            
            # Calculate progress
            if loan['status'] == 'paid':
                progress = 100.0
            else:
                paid_amount = loan['amount'] - (loan['remaining_amount'] / (1 + (loan['interest_rate'] * loan['term_months']) / (12 * 100)))
                progress = (paid_amount / loan['amount']) * 100
                
            # Calculate days until next payment or overdue
            if loan['status'] == 'active':
                now = datetime.utcnow()
                next_payment = loan['next_payment_date']
                days_to_payment = (next_payment - now).days
                is_overdue = days_to_payment < 0
            else:
                days_to_payment = 0
                is_overdue = False
                
            # Format loan data for response
            return {
                "amount": loan['amount'],
                "interest_rate": loan['interest_rate'],
                "term_months": loan['term_months'],
                "monthly_payment": loan['monthly_payment'],
                "remaining_amount": loan['remaining_amount'],
                "next_payment_date": loan['next_payment_date'] if loan['status'] == 'active' else None,
                "start_date": loan['start_date'],
                "end_date": loan['end_date'],
                "status": loan['status'],
                "progress_percent": progress,
                "days_to_next_payment": days_to_payment if loan['status'] == 'active' else None,
                "is_overdue": is_overdue
            }
            
        except Exception as e:
            if isinstance(e, AccountNotFoundError):
                raise e
            self.logger.error({
                'event': 'Failed to check loan status',
                'error': str(e),
                'user_id': user_id,
                'level': 'error'
            })
            raise DatabaseError(f"Failed to check loan status: {str(e)}")

    def _get_credit_multiplier(self, credit_score: int) -> float:
        """Calculate credit multiplier based on credit score"""
        if credit_score >= 800:
            return 10.0  # Excellent credit - can borrow up to 10x balance
        elif credit_score >= 750:
            return 8.0   # Very good credit
        elif credit_score >= 700:
            return 6.0   # Good credit
        elif credit_score >= 650:
            return 4.0   # Fair credit
        elif credit_score >= 600:
            return 3.0   # Poor credit
        elif credit_score >= 550:
            return 2.0   # Very poor credit
        else:
            return 1.0   # Bad credit - can only borrow up to 1x balance
            
    def _get_interest_rate_by_credit_score(self, credit_score: int) -> float:
        """Calculate interest rate based on credit score"""
        if credit_score >= 800:
            return 8.0    # Excellent credit - lowest interest rate
        elif credit_score >= 750:
            return 9.0    # Very good credit
        elif credit_score >= 700:
            return 10.0   # Good credit
        elif credit_score >= 650:
            return 11.0   # Fair credit
        elif credit_score >= 600:
            return 12.0   # Poor credit
        elif credit_score >= 550:
            return 14.0   # Very poor credit
        else:
            return 16.0   # Bad credit - highest interest rate
            
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
        current_score = account.get('credit_score', 600)
        new_score = max(300, min(850, current_score + change))
        
        # Create credit history event
        timestamp = datetime.datetime.now(datetime.UTC)
        credit_event = {
            'date': timestamp,
            'action': action,
            'change': change,
            'reason': reason,
            'old_score': current_score,
            'new_score': new_score
        }
        
        # Update account with new credit score and add to history
        filter_query = {'user_id': user_id}
        update_query = {
            '$set': {'credit_score': new_score},
            '$push': {'credit_history': credit_event}
        }
        
        try:
            result = await self.db.accounts.update_one(filter_query, update_query)
            
            if result.modified_count == 0:
                raise CreditScoreError(f"Failed to update credit score for user {user_id}")
                
            return {
                'user_id': user_id,
                'old_score': current_score,
                'new_score': new_score,
                'change': change,
                'action': action,
                'timestamp': timestamp
            }
            
        except Exception as e:
            self.logger.error({
                'event': 'Error updating credit score',
                'error': str(e),
                'user_id': user_id,
                'level': 'error'
            })
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
        credit_score = account.get('credit_score', 600)
        credit_history = account.get('credit_history', [])
        
        # Calculate account age in days
        created_at = account.get('created_at', datetime.datetime.now(datetime.UTC))
        account_age_days = (datetime.datetime.now(datetime.UTC) - created_at).days
        
        # Get recent transactions (last 30 days)
        thirty_days_ago = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=30)
        
        transactions_query = {
            'user_id': user_id,
            'timestamp': {'$gte': thirty_days_ago}
        }
        
        try:
            recent_transactions = []
            async for transaction in self.db.transactions.find(transactions_query).sort('timestamp', -1):
                recent_transactions.append(transaction)
                
            transaction_count_30d = len(recent_transactions)
            
            # Calculate average balance from recent transactions
            if transaction_count_30d > 0:
                average_balance = account.get('balance', 0)
            else:
                average_balance = account.get('balance', 0)
                
            # Check if user has an active loan
            loan = await self.get_active_loan(user_id)
            has_active_loan = loan is not None
            
            loan_repayment_status = "N/A"
            if has_active_loan:
                if loan.get('overdue_days', 0) > 0:
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
                sorted_history = sorted(credit_history, key=lambda x: x.get('date', datetime.datetime.min), reverse=True)
                recent_credit_events = sorted_history[:10]
                
            # Build and return the credit report
            credit_report = {
                'user_id': user_id,
                'credit_score': credit_score,
                'credit_rating': credit_rating,
                'account_age_days': account_age_days,
                'transaction_count_30d': transaction_count_30d,
                'average_balance': average_balance,
                'has_active_loan': has_active_loan,
                'loan_repayment_status': loan_repayment_status,
                'credit_limit_multiplier': credit_limit_multiplier,
                'loan_interest_rate': loan_interest_rate,
                'recent_credit_events': recent_credit_events
            }
            
            return credit_report
            
        except Exception as e:
            self.logger.error({
                'event': 'Error generating credit report',
                'error': str(e),
                'user_id': user_id,
                'level': 'error'
            })
            raise CreditScoreError(f"Error generating credit report: {str(e)}")

    @measure_performance("get_all_accounts")
    async def get_all_accounts(self) -> List[Dict[str, Any]]:
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
            self.logger.error({
                'event': 'Failed to get all accounts',
                'error': str(e),
                'level': 'error'
            })
            return []

    @measure_performance("get_accounts_with_active_loans")
    async def get_accounts_with_active_loans(self) -> List[Dict[str, Any]]:
        """Get all accounts with active loans"""
        try:
            # Check if db is available
            if self.db is None:
                return []
            
            # Use a simple query to find accounts with active loans
            # This query is more efficient than getting all accounts and filtering in Python
            async def _fetch_accounts_with_loans():
                return await self.db.accounts.find({
                    "loan.status": "active"
                }).to_list(None)
            
            return await self._execute_with_retry("get_accounts_with_active_loans", _fetch_accounts_with_loans)
        except Exception as e:
            self.logger.error({
                'event': 'Failed to get accounts with active loans',
                'error': str(e),
                'level': 'error'
            })
            return []

    @measure_performance("get_recent_transactions")
    async def get_recent_transactions(self, user_id: str, days: int = 30) -> List[Dict[str, Any]]:
        """Get recent transactions for a user within specified number of days"""
        try:
            if not self._validate_id(user_id):
                raise ValidationError("Invalid Discord ID format")
                
            # Calculate cutoff date
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            transactions = []
            cursor = self.db.transactions.find(
                {
                    "user_id": user_id,
                    "timestamp": {"$gte": cutoff_date}
                }
            ).sort("timestamp", -1)
            
            async for transaction in cursor:
                transactions.append(transaction)
                
            return transactions
        except Exception as e:
            self.logger.error({
                'event': 'Failed to get recent transactions',
                'error': str(e),
                'user_id': user_id,
                'level': 'error'
            })
            raise DatabaseError(f"Failed to get recent transactions: {str(e)}")

    @measure_performance("get_active_loan")
    async def get_active_loan(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get active loan for a user"""
        try:
            account = await self.get_account(user_id)
            if not account:
                return None
                
            loan = account.get('loan')
            if not loan or loan.get('status') != 'active':
                return None
                
            return loan
        except Exception as e:
            self.logger.error({
                'event': 'Failed to get active loan',
                'error': str(e),
                'user_id': user_id,
                'level': 'error'
            })
            return None

    def _log_mongo_connection_details(self, db_name=None):
        """Log MongoDB connection details without exposing credentials"""
        try:
            # Extract and sanitize connection information
            if self.mongo_uri:
                # Parse the connection string to extract the host
                host_part = None
                
                if self.mongo_uri.startswith('mongodb+srv://'):
                    # Parse for mongodb+srv:// format
                    if '@' in self.mongo_uri:
                        # Format: mongodb+srv://username:password@host/database
                        host_part = self.mongo_uri.split('@')[1].split('/')[0]
                    else:
                        # Format: mongodb+srv://host/database
                        host_part = self.mongo_uri.split('://')[1].split('/')[0]
                else:
                    # Parse for standard mongodb:// format
                    if '@' in self.mongo_uri:
                        # Format: mongodb://username:password@host:port/database
                        host_part = self.mongo_uri.split('@')[1].split('/')[0]
                    else:
                        # Format: mongodb://host:port/database
                        host_part = self.mongo_uri.split('://')[1].split('/')[0]
                    
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
                if 'expireAfterSeconds' in index_info:
                    ttl_index_exists = True
                    self.logger.info(f"TTL index already exists with name: {index_name}")
                    break
                
            if not ttl_index_exists:
                try:
                    # Create TTL index on timestamp field
                    result = await self.db.transactions.create_index(
                        [("timestamp", ASCENDING)],
                        expireAfterSeconds=60 * 60 * 24 * 30,  # 30 days
                        name="transaction_expiry_ttl"
                    )
                    self.logger.info(f"Created TTL index on transactions collection: {result}")
                except OperationFailure as e:
                    # Handle permission denied errors gracefully
                    if 'not allowed to do action [createIndex]' in str(e):
                        self.logger.warning("Skipping TTL index creation - insufficient permissions on Atlas")
                        # Consider the operation successful anyway
                        return True
                    else:
                        raise
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to create TTL index: {str(e)}")
            return False