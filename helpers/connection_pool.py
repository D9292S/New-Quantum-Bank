import asyncio
import logging
import time
from typing import Any
from urllib.parse import quote_plus

import aiohttp
import motor.motor_asyncio

logger = logging.getLogger("bot")


class ConnectionPoolManager:
    """
    Manages connection pools for MongoDB and HTTP connections
    with automatic retry, connection limiting, and circuit breaking
    """

    def __init__(
        self,
        mongo_uri: str | None = None,
        max_mongo_pool_size: int = 100,
        max_http_connections: int = 100,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_timeout: int = 30,
    ):
        # MongoDB connection
        self._mongo_uri = mongo_uri
        self._mongo_pool_size = max_mongo_pool_size
        self._mongo_client = None
        self._mongo_db = None

        # HTTP connection
        self._http_session = None
        self._max_http_connections = max_http_connections

        # Circuit breaker pattern implementation
        self._circuit_state = "CLOSED"  # CLOSED (normal), OPEN (failing), HALF-OPEN (testing)
        self._failure_count = 0
        self._circuit_threshold = circuit_breaker_threshold
        self._circuit_timeout = circuit_breaker_timeout
        self._last_failure_time = 0

        # Connection metrics
        self._mongo_connection_attempts = 0
        self._mongo_connection_failures = 0
        self._http_requests_total = 0
        self._http_request_failures = 0

        # Locks to prevent connection race conditions
        self._mongo_lock = asyncio.Lock()
        self._http_lock = asyncio.Lock()

    async def get_mongo_client(self) -> motor.motor_asyncio.AsyncIOMotorClient | None:
        """Get or create MongoDB client with connection pooling"""
        if not self._mongo_uri:
            return None

        # Check if we need to initialize the client
        if self._mongo_client is None:
            async with self._mongo_lock:
                # Check again in case another request initialized it
                if self._mongo_client is None:
                    try:
                        # Circuit breaker pattern
                        if self._circuit_state == "OPEN":
                            # Check if enough time has passed to retry
                            if time.time() - self._last_failure_time >= self._circuit_timeout:
                                self._circuit_state = "HALF-OPEN"
                                logger.info("Circuit breaker entering HALF-OPEN state")
                            else:
                                logger.warning("Circuit breaker is OPEN, skipping connection attempt")
                                return None

                        self._mongo_connection_attempts += 1

                        # Create MongoDB client with connection pooling
                        # Make sure we have a running event loop
                        try:
                            loop = asyncio.get_running_loop()
                        except RuntimeError:
                            # No running event loop, create one
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)

                        self._mongo_client = motor.motor_asyncio.AsyncIOMotorClient(
                            self._mongo_uri,
                            maxPoolSize=self._mongo_pool_size,
                            connectTimeoutMS=5000,
                            socketTimeoutMS=10000,
                            serverSelectionTimeoutMS=5000,
                            retryWrites=True,
                            w="majority",
                            io_loop=loop,
                        )

                        # Test connection
                        await self._mongo_client.admin.command("ping")

                        # Success handling
                        if self._circuit_state == "HALF-OPEN":
                            self._circuit_state = "CLOSED"
                            self._failure_count = 0
                            logger.info("Circuit breaker reset to CLOSED state")

                        logger.info(f"MongoDB connection pool established with max size {self._mongo_pool_size}")
                    except Exception as e:
                        self._mongo_connection_failures += 1
                        self._failure_count += 1
                        self._last_failure_time = time.time()

                        # Update circuit breaker state
                        if self._failure_count >= self._circuit_threshold:
                            self._circuit_state = "OPEN"
                            logger.error(f"Circuit breaker opened after {self._failure_count} failures")

                        logger.error(f"Failed to establish MongoDB connection pool: {str(e)}")
                        self._mongo_client = None
                        return None

        return self._mongo_client

    async def get_database(self, db_name: str) -> motor.motor_asyncio.AsyncIOMotorDatabase | None:
        """Get MongoDB database from the connection pool"""
        client = await self.get_mongo_client()
        if client:
            return client[db_name]
        return None

    async def get_http_session(self) -> aiohttp.ClientSession | None:
        """Get or create HTTP session with connection pooling"""
        if self._http_session is None or self._http_session.closed:
            async with self._http_lock:
                if self._http_session is None or self._http_session.closed:
                    try:
                        # Make sure we have a running event loop
                        try:
                            loop = asyncio.get_running_loop()
                        except RuntimeError:
                            # No running event loop, create one
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)

                        # Create HTTP session with optimized settings
                        self._http_session = aiohttp.ClientSession(
                            timeout=aiohttp.ClientTimeout(total=30),
                            connector=aiohttp.TCPConnector(
                                limit=self._max_http_connections,
                                ttl_dns_cache=300,  # DNS cache TTL in seconds
                                enable_cleanup_closed=True,  # Clean up closed connections
                                force_close=False,  # Keep connections open
                                keepalive_timeout=60,  # Keepalive timeout
                            ),
                            headers={"User-Agent": "QuantumBank Discord Bot/1.0.0"},
                            loop=loop,
                        )
                        logger.info(f"HTTP connection pool established with max size {self._max_http_connections}")
                    except Exception as e:
                        logger.error(f"Failed to establish HTTP connection pool: {str(e)}")
                        return None

        return self._http_session

    async def close(self):
        """Close all connections"""
        # Close MongoDB connection
        if self._mongo_client:
            try:
                self._mongo_client.close()
                self._mongo_client = None
                logger.info("MongoDB connection closed")
            except Exception as e:
                logger.error(f"Error closing MongoDB connection: {str(e)}")

        # Close HTTP session
        if self._http_session and not self._http_session.closed:
            try:
                await self._http_session.close()
                self._http_session = None
                logger.info("HTTP session closed")
            except Exception as e:
                logger.error(f"Error closing HTTP session: {str(e)}")

    def get_stats(self) -> dict[str, Any]:
        """Get connection pool statistics"""
        return {
            "mongo": {
                "connection_attempts": self._mongo_connection_attempts,
                "connection_failures": self._mongo_connection_failures,
                "circuit_state": self._circuit_state,
                "failure_count": self._failure_count,
            },
            "http": {
                "requests_total": self._http_requests_total,
                "request_failures": self._http_request_failures,
            },
        }

    @staticmethod
    def build_mongo_uri(
        host: str,
        port: int,
        username: str | None = None,
        password: str | None = None,
        auth_db: str = "admin",
        ssl: bool = False,
    ) -> str:
        """Build MongoDB URI from components"""
        scheme = "mongodb" if not ssl else "mongodb+srv"
        auth = ""

        if username and password:
            auth = f"{quote_plus(username)}:{quote_plus(password)}@"

        port_str = "" if ssl else f":{port}"

        return f"{scheme}://{auth}{host}{port_str}/{auth_db}"
