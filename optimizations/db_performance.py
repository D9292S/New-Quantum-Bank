"""
Database Performance Optimizations for Quantum Bank Bot

This module provides tools for:
1. Query optimization and profiling
2. Connection pooling enhancements
3. Result caching for repeated queries
4. Intelligent retry mechanisms
5. Transaction batching for write operations
"""

import asyncio
import functools
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, TypeVar, Union, cast

# Setup logger
logger = logging.getLogger("performance")

# Type for decorated functions
F = TypeVar("F", bound=Callable[..., Any])

# Global query statistics
query_stats = {
    "total_queries": 0,
    "slow_queries": 0,
    "cached_hits": 0,
    "total_query_time": 0.0,
    "slowest_query": {"query": None, "time": 0.0},
    "query_types": defaultdict(int),
    "collection_stats": defaultdict(lambda: {"count": 0, "time": 0.0}),
}

# Configuration
SLOW_QUERY_THRESHOLD = 0.5  # seconds
MAX_CACHE_SIZE = 1000
MAX_CACHE_AGE = 300  # seconds


class QueryCache:
    """Cache for query results to reduce database load"""
    
    def __init__(self, max_size: int = MAX_CACHE_SIZE, max_age: int = MAX_CACHE_AGE):
        self.max_size = max_size
        self.max_age = max_age
        self.cache: Dict[str, Tuple[Any, float]] = {}  # Map of cache key to (result, timestamp)
        self.hits = 0
        self.misses = 0
        self.last_cleanup = time.time()
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache if it exists and is not expired"""
        if key in self.cache:
            result, timestamp = self.cache[key]
            now = time.time()
            
            # Check if entry is expired
            if now - timestamp > self.max_age:
                del self.cache[key]
                self.misses += 1
                return None
                
            self.hits += 1
            return result
            
        self.misses += 1
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Store a value in the cache
        
        Args:
            key: Cache key
            value: Value to store
            ttl: Optional time-to-live in seconds (overrides default max_age)
        """
        now = time.time()
        
        # Clean up if needed
        if now - self.last_cleanup > 60:  # Clean up once per minute at most
            self.cleanup()
            
        # Check if we need to make room
        if len(self.cache) >= self.max_size:
            self.evict_oldest()
            
        # Store the value with timestamp
        self.cache[key] = (value, now)
    
    def cleanup(self) -> int:
        """Remove expired entries from the cache"""
        now = time.time()
        expired_keys = [
            key for key, (_, timestamp) in self.cache.items()
            if now - timestamp > self.max_age
        ]
        
        for key in expired_keys:
            del self.cache[key]
            
        self.last_cleanup = now
        return len(expired_keys)
    
    def evict_oldest(self) -> None:
        """Remove the oldest entry from the cache"""
        if not self.cache:
            return
            
        oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k][1])
        del self.cache[oldest_key]
    
    def clear(self) -> None:
        """Clear all entries from the cache"""
        self.cache.clear()
        
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio": self.hits / (self.hits + self.misses) if (self.hits + self.misses) > 0 else 0,
        }


# Global query cache
_query_cache = QueryCache()


def get_query_cache() -> QueryCache:
    """Get the global query cache"""
    global _query_cache
    return _query_cache


class QueryProfiler:
    """Utility class for profiling database queries"""
    
    @staticmethod
    def record_query(
        collection: str,
        operation: str,
        query: Dict[str, Any],
        duration: float,
        success: bool,
        result_size: int = 0,
    ) -> None:
        """Record information about a database query"""
        global query_stats
        
        query_stats["total_queries"] += 1
        query_stats["total_query_time"] += duration
        query_stats["query_types"][operation] += 1
        
        # Update collection stats
        coll_stats = query_stats["collection_stats"][collection]
        coll_stats["count"] += 1
        coll_stats["time"] += duration
        
        # Check for slow query
        if duration > SLOW_QUERY_THRESHOLD:
            query_stats["slow_queries"] += 1
            
            # Log slow queries
            query_str = str(query)
            if len(query_str) > 100:
                query_str = query_str[:97] + "..."
                
            logger.warning(
                f"Slow query ({duration:.3f}s) on {collection}.{operation}: {query_str}"
            )
            
            # Update slowest query if this one is slower
            if duration > query_stats["slowest_query"]["time"]:
                query_stats["slowest_query"] = {
                    "query": f"{collection}.{operation}: {query_str}",
                    "time": duration,
                }
        
        # Detailed logging for debugging
        log_level = logging.DEBUG
        if not success:
            log_level = logging.ERROR
        elif duration > SLOW_QUERY_THRESHOLD:
            log_level = logging.WARNING
            
        if logger.isEnabledFor(log_level):
            logger.log(
                log_level,
                f"DB {operation} on {collection}: {duration:.3f}s, "
                f"success={success}, size={result_size}"
            )
    
    @staticmethod
    def get_stats() -> Dict[str, Any]:
        """Get current query statistics"""
        global query_stats
        
        stats = dict(query_stats)
        
        # Calculate average query time
        if stats["total_queries"] > 0:
            stats["avg_query_time"] = stats["total_query_time"] / stats["total_queries"]
        else:
            stats["avg_query_time"] = 0.0
            
        # Add cache stats
        stats["cache"] = get_query_cache().stats()
        
        return stats
    
    @staticmethod
    def reset_stats() -> None:
        """Reset all query statistics"""
        global query_stats
        
        query_stats = {
            "total_queries": 0,
            "slow_queries": 0,
            "cached_hits": 0,
            "total_query_time": 0.0,
            "slowest_query": {"query": None, "time": 0.0},
            "query_types": defaultdict(int),
            "collection_stats": defaultdict(lambda: {"count": 0, "time": 0.0}),
        }


def cacheable_query(
    ttl: int = MAX_CACHE_AGE,
    key_prefix: str = "",
    cache_errors: bool = False,
) -> Callable[[F], F]:
    """
    Decorator for caching database query results
    
    Parameters:
        ttl: Cache time-to-live in seconds
        key_prefix: Prefix for cache keys
        cache_errors: Whether to cache error results
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Create a cache key based on function name, args, and kwargs
            cache_key = f"{key_prefix}:{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Check if result is in cache
            cache = get_query_cache()
            cached_result = cache.get(cache_key)
            
            if cached_result is not None:
                # Update stats
                global query_stats
                query_stats["cached_hits"] += 1
                
                return cached_result
                
            # Execute the query
            try:
                result = await func(*args, **kwargs)
                # Cache the successful result
                cache.set(cache_key, result)
                return result
            except Exception as e:
                if cache_errors:
                    # Cache the error if configured to do so
                    cache.set(cache_key, e)
                raise
                
        return cast(F, wrapper)
    
    return decorator


def db_retry(
    max_attempts: int = 3,
    retry_delay: float = 0.5,
    backoff_factor: float = 2.0,
    exceptions: Tuple[Exception, ...] = (Exception,),
) -> Callable[[F], F]:
    """
    Decorator for retrying database operations with exponential backoff
    
    Parameters:
        max_attempts: Maximum number of retry attempts
        retry_delay: Initial delay between retries in seconds
        backoff_factor: Factor to increase delay with each retry
        exceptions: Tuple of exceptions to catch and retry
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            delay = retry_delay
            
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    # Log the error
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"Database operation failed (attempt {attempt+1}/{max_attempts}): {str(e)}"
                            f" - Retrying in {delay:.2f}s"
                        )
                        
                        # Wait before retrying
                        await asyncio.sleep(delay)
                        
                        # Increase delay for next attempt
                        delay *= backoff_factor
                    else:
                        logger.error(
                            f"Database operation failed after {max_attempts} attempts: {str(e)}"
                        )
            
            # If we get here, all attempts failed
            raise last_exception
                
        return cast(F, wrapper)
    
    return decorator


class BatchProcessor:
    """
    Utility for batching database write operations
    This helps reduce the number of database round-trips for frequent writes
    """
    
    def __init__(
        self,
        batch_size: int = 100,
        max_delay: float = 1.0,
        processor_func: Optional[Callable[[List[Dict[str, Any]]], Any]] = None,
    ):
        self.batch_size = batch_size
        self.max_delay = max_delay
        self.processor_func = processor_func
        self.batch: List[Dict[str, Any]] = []
        self.last_flush: float = time.time()
        self.lock = asyncio.Lock()
        self.flush_task = None
    
    async def add(self, item: Dict[str, Any]) -> None:
        """Add an item to the batch"""
        async with self.lock:
            self.batch.append(item)
            
            # Check if we need to flush
            if len(self.batch) >= self.batch_size:
                await self.flush()
            elif self.flush_task is None:
                # Schedule a delayed flush
                self.flush_task = asyncio.create_task(self._delayed_flush())
    
    async def _delayed_flush(self) -> None:
        """Flush the batch after a delay"""
        await asyncio.sleep(self.max_delay)
        await self.flush()
    
    async def flush(self) -> None:
        """Flush the current batch to the database"""
        async with self.lock:
            if not self.batch:
                return
                
            items_to_process = self.batch.copy()
            self.batch = []
            self.last_flush = time.time()
            
            # Cancel any scheduled flush
            if self.flush_task is not None:
                self.flush_task.cancel()
                self.flush_task = None
                
        # Process the batch
        if self.processor_func:
            try:
                await self.processor_func(items_to_process)
                logger.debug(f"Processed batch of {len(items_to_process)} items")
            except Exception as e:
                logger.error(f"Error processing batch: {str(e)}")
                # You might want to implement retries or recovery here
    
    def stats(self) -> Dict[str, Any]:
        """Get statistics about the batch processor"""
        return {
            "current_batch_size": len(self.batch),
            "max_batch_size": self.batch_size,
            "time_since_last_flush": time.time() - self.last_flush,
        }


class IndexRecommender:
    """
    Analyzes query patterns and recommends indexes
    This helps optimize database performance by suggesting appropriate indices
    """
    
    def __init__(self):
        self.query_patterns: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.current_indexes: Set[str] = set()
        
    def record_query(self, collection: str, query: Dict[str, Any]) -> None:
        """Record a query for analysis"""
        # Extract fields being queried
        fields = self._extract_query_fields(query)
        
        # Create a pattern key from the fields
        if fields:
            pattern_key = ",".join(sorted(fields))
            self.query_patterns[collection][pattern_key] += 1
    
    def register_index(self, collection: str, fields: List[str]) -> None:
        """Register an existing index"""
        index_key = f"{collection}:{','.join(sorted(fields))}"
        self.current_indexes.add(index_key)
    
    def get_recommendations(self, min_occurrences: int = 10) -> Dict[str, List[str]]:
        """
        Get index recommendations based on query patterns
        
        Returns a dict where keys are collection names and values are lists of
        recommended index field combinations
        """
        recommendations = {}
        
        for collection, patterns in self.query_patterns.items():
            collection_recommendations = []
            
            for pattern, count in patterns.items():
                if count >= min_occurrences:
                    fields = pattern.split(",")
                    
                    # Check if this pattern or a superset is already indexed
                    index_key = f"{collection}:{pattern}"
                    if index_key in self.current_indexes:
                        continue
                        
                    # Check for subset or superset that would cover this
                    is_covered = False
                    for existing_index in self.current_indexes:
                        if existing_index.startswith(f"{collection}:"):
                            existing_fields = set(existing_index.split(":", 1)[1].split(","))
                            pattern_fields = set(fields)
                            
                            # If existing index is a superset of this pattern
                            if pattern_fields.issubset(existing_fields):
                                is_covered = True
                                break
                                
                    if not is_covered:
                        collection_recommendations.append({
                            "fields": fields,
                            "count": count,
                        })
            
            if collection_recommendations:
                # Sort by query count (descending)
                collection_recommendations.sort(key=lambda x: x["count"], reverse=True)
                recommendations[collection] = collection_recommendations
                
        return recommendations
    
    def _extract_query_fields(self, query: Dict[str, Any], prefix: str = "") -> Set[str]:
        """Extract field names from a query document"""
        fields = set()
        
        for key, value in query.items():
            if key.startswith("$"):
                # Handle operators like $and, $or
                if key in ("$and", "$or", "$nor") and isinstance(value, list):
                    for sub_query in value:
                        fields.update(self._extract_query_fields(sub_query, prefix))
            else:
                field_name = f"{prefix}{key}" if prefix else key
                
                # Add the field
                fields.add(field_name.split(".", 1)[0])  # Just the top-level field
                
                # Handle sub-documents
                if isinstance(value, dict):
                    # Check if it's a query operator
                    if all(k.startswith("$") for k in value.keys()):
                        continue
                        
                    # It's a sub-document, recurse
                    sub_fields = self._extract_query_fields(value, f"{field_name}.")
                    fields.update(sub_fields)
        
        return fields


# Global instance of IndexRecommender
_index_recommender = IndexRecommender()


def get_index_recommender() -> IndexRecommender:
    """Get the global index recommender"""
    global _index_recommender
    return _index_recommender


def query_timing(
    collection: str,
    operation: str = "query",
    record_for_index: bool = True,
) -> Callable[[F], F]:
    """
    Decorator for timing and recording database queries
    
    Parameters:
        collection: Name of the database collection being accessed
        operation: Type of operation (find, update, etc.)
        record_for_index: Whether to record the query for index recommendations
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            success = False
            result_size = 0
            
            try:
                # Execute the query
                result = await func(*args, **kwargs)
                success = True
                
                # Try to determine result size
                if hasattr(result, "__len__"):
                    result_size = len(result)
                    
                return result
            finally:
                # Calculate duration
                duration = time.time() - start_time
                
                # Record query statistics
                QueryProfiler.record_query(
                    collection=collection,
                    operation=operation,
                    query=kwargs.get("filter", kwargs.get("query", {})),
                    duration=duration,
                    success=success,
                    result_size=result_size,
                )
                
                # Record for index recommendations
                if record_for_index:
                    query = kwargs.get("filter", kwargs.get("query", {}))
                    get_index_recommender().record_query(collection, query)
                
        return cast(F, wrapper)
    
    return decorator 