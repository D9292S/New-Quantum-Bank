import time
import asyncio
import logging
from typing import Dict, Any, Optional, Callable, TypeVar, List, Set, Union, Tuple
from functools import wraps
import pickle
import zlib
import hashlib
import json

T = TypeVar('T')
logger = logging.getLogger('bot')

class CacheManager:
    """
    High-performance in-memory cache with tiered storage options:
    - Memory (fastest): for frequently accessed small data
    - Distributed (MongoDB): for shared data across shards/clusters
    """
    
    def __init__(self, ttl_seconds: int = 300, max_size: int = 1000, 
                 enable_stats: bool = True, mongodb=None):
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._default_ttl = ttl_seconds
        self._max_size = max_size
        self._enable_stats = enable_stats
        self._mongodb = mongodb
        self._last_cleanup = time.time()
        
        # Statistics tracking
        self._hits = 0
        self._misses = 0
        self._sets = 0
        self._evictions = 0
        
        # Namespace support for organization
        self._namespaces: Set[str] = set()
        
        # Cache hierarchies
        self._hierarchy: Dict[str, List[str]] = {}
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
        
        # Start cleanup task
        self._cleanup_task = None
    
    def start_cleanup_task(self, interval: int = 60):
        """Start background cleanup task"""
        if self._cleanup_task is None:
            # Create a coroutine but don't create a task immediately
            # This will be properly started when the event loop is running
            self._cleanup_coroutine = self._cleanup_expired(interval)
            logger.debug("Prepared cache cleanup coroutine")
    
    async def start_cleanup_task_async(self, interval: int = 60):
        """Async version to start the cleanup task when the event loop is running"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_expired(interval))
            logger.debug("Started cache cleanup task")
            
    async def _cleanup_expired(self, interval: int):
        """Periodically remove expired cache entries"""
        try:
            while True:
                await asyncio.sleep(interval)
                await self.cleanup()
        except asyncio.CancelledError:
            logger.info("Cache cleanup task cancelled")
        except Exception as e:
            logger.error(f"Error in cache cleanup task: {e}")
    
    async def cleanup(self):
        """Remove expired cache entries"""
        now = time.time()
        async with self._lock:
            # Skip if cleaned recently
            if now - self._last_cleanup < 10:  # Don't clean more often than every 10 seconds
                return
                
            self._last_cleanup = now
            
            # Check each namespace
            for namespace in list(self._memory_cache.keys()):
                evicted = 0
                data = self._memory_cache[namespace]
                
                # Find expired keys
                expired_keys = [
                    key for key, item in data.items()
                    if item.get('expires_at', 0) < now
                ]
                
                # Remove expired keys
                for key in expired_keys:
                    data.pop(key, None)
                    evicted += 1
                
                # Handle oversized caches
                if len(data) > self._max_size:
                    # Sort by least recently used first
                    sorted_items = sorted(
                        data.items(),
                        key=lambda x: x[1].get('last_access', 0)
                    )
                    
                    # Remove oldest items until under size limit
                    to_remove = len(data) - self._max_size
                    for key, _ in sorted_items[:to_remove]:
                        data.pop(key, None)
                        evicted += 1
                
                # Update stats
                self._evictions += evicted
                
                # Remove empty namespaces
                if not data:
                    self._memory_cache.pop(namespace, None)
                    self._namespaces.discard(namespace)
    
    async def get(self, key: str, namespace: str = 'default') -> Optional[Any]:
        """Get a value from the cache"""
        now = time.time()
        
        # Check memory cache first (fastest)
        if namespace in self._memory_cache and key in self._memory_cache[namespace]:
            item = self._memory_cache[namespace][key]
            
            # Check if expired
            if item.get('expires_at', 0) < now:
                self._memory_cache[namespace].pop(key, None)
                if self._enable_stats:
                    self._misses += 1
                return None
            
            # Update access time
            item['last_access'] = now
            
            if self._enable_stats:
                self._hits += 1
                
            return item['value']
        
        # Check MongoDB cache if enabled and available
        if self._mongodb is not None:
            try:
                # Try to get from MongoDB cache
                cache_data = await self._mongodb.cache.find_one({
                    "namespace": namespace,
                    "key": key,
                    "expires_at": {"$gt": now}
                })
                
                if cache_data:
                    value = cache_data["value"]
                    
                    # If compressed, decompress
                    if isinstance(value, bytes):
                        try:
                            value = pickle.loads(zlib.decompress(value))
                        except Exception as e:
                            logger.error(f"Error decompressing cache data: {e}")
                            value = None
                    
                    # Store in memory cache for faster future access
                    await self.set(key, value, namespace=namespace)
                    
                    if self._enable_stats:
                        self._hits += 1
                        
                    return value
            except Exception as e:
                logger.error(f"Error getting from MongoDB cache: {e}")
        
        if self._enable_stats:
            self._misses += 1
            
        return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None, 
                 namespace: str = 'default', store_distributed: bool = False,
                 compress: bool = False) -> None:
        """Set a value in the cache"""
        if ttl is None:
            ttl = self._default_ttl
            
        now = time.time()
        expires_at = now + ttl
        
        # Add to memory cache
        async with self._lock:
            # Create namespace if it doesn't exist
            if namespace not in self._memory_cache:
                self._memory_cache[namespace] = {}
                self._namespaces.add(namespace)
            
            # Store in memory
            self._memory_cache[namespace][key] = {
                'value': value,
                'created_at': now,
                'last_access': now,
                'expires_at': expires_at
            }
            
            if self._enable_stats:
                self._sets += 1
        
        # Store in MongoDB if enabled
        if store_distributed and self._mongodb is not None:
            try:
                mongo_value = value
                
                # Compress larger values
                if compress:
                    try:
                        mongo_value = zlib.compress(pickle.dumps(value))
                    except Exception as e:
                        logger.error(f"Error compressing cache data: {e}")
                
                # Store in MongoDB
                await self._mongodb.cache.update_one(
                    {"namespace": namespace, "key": key},
                    {
                        "$set": {
                            "namespace": namespace,
                            "key": key,
                            "value": mongo_value,
                            "created_at": now,
                            "expires_at": expires_at
                        }
                    },
                    upsert=True
                )
            except Exception as e:
                logger.error(f"Error setting distributed cache: {e}")
    
    async def delete(self, key: str, namespace: str = 'default') -> None:
        """Delete a key from the cache"""
        # Delete from memory cache
        async with self._lock:
            if namespace in self._memory_cache and key in self._memory_cache[namespace]:
                self._memory_cache[namespace].pop(key, None)
        
        # Delete from MongoDB cache if enabled
        if self._mongodb is not None:
            try:
                await self._mongodb.cache.delete_one({
                    "namespace": namespace,
                    "key": key
                })
            except Exception as e:
                logger.error(f"Error deleting from MongoDB cache: {e}")
    
    async def invalidate_namespace(self, namespace: str) -> None:
        """Invalidate all keys in a namespace"""
        # Delete from memory cache
        async with self._lock:
            self._memory_cache.pop(namespace, None)
            self._namespaces.discard(namespace)
            
            # Handle hierarchical namespaces
            if namespace in self._hierarchy:
                for child in self._hierarchy[namespace]:
                    await self.invalidate_namespace(child)
        
        # Delete from MongoDB cache if enabled
        if self._mongodb is not None:
            try:
                await self._mongodb.cache.delete_many({
                    "namespace": namespace
                })
            except Exception as e:
                logger.error(f"Error invalidating namespace in MongoDB cache: {e}")
    
    async def clear(self) -> None:
        """Clear all cache data"""
        async with self._lock:
            self._memory_cache.clear()
            self._namespaces.clear()
            self._hierarchy.clear()
        
        # Clear MongoDB cache if enabled
        if self._mongodb is not None:
            try:
                await self._mongodb.cache.delete_many({})
            except Exception as e:
                logger.error(f"Error clearing MongoDB cache: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_items = sum(len(items) for items in self._memory_cache.values())
        memory_usage = sum(
            len(pickle.dumps(item)) 
            for namespace in self._memory_cache.values() 
            for item in namespace.values()
        )
        
        return {
            "hits": self._hits,
            "misses": self._misses,
            "sets": self._sets,
            "evictions": self._evictions,
            "hit_rate": (self._hits / (self._hits + self._misses)) if (self._hits + self._misses) > 0 else 0,
            "namespaces": len(self._namespaces),
            "total_items": total_items,
            "memory_usage_bytes": memory_usage
        }
    
    # Helper methods for more advanced usage
    def register_namespace_hierarchy(self, parent: str, children: List[str]) -> None:
        """Register parent-child relationships between namespaces"""
        self._hierarchy[parent] = children
    
    async def get_keys(self, namespace: str = 'default') -> List[str]:
        """Get all keys in a namespace"""
        if namespace in self._memory_cache:
            return list(self._memory_cache[namespace].keys())
        return []


# Decorator for caching function results
def cached(ttl: int = 300, namespace: Optional[str] = None, 
          key_builder: Optional[Callable] = None, 
          store_distributed: bool = False):
    """
    Decorator to cache function results
    
    Args:
        ttl: Cache TTL in seconds
        namespace: Cache namespace (default: function name)
        key_builder: Function to build cache key from args/kwargs
        store_distributed: Whether to store in distributed cache
        
    Example:
        @cached(ttl=60)
        async def get_user_data(user_id: int):
            # Expensive database operation
            return await db.users.find_one({"id": user_id})
    """
    def decorator(func):
        # Use function name as default namespace
        _namespace = namespace or func.__name__
        
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Get cache manager from bot
            if not hasattr(self.bot, 'cache_manager'):
                # Fall back to calling the original function
                return await func(self, *args, **kwargs)
            
            cache_manager = self.bot.cache_manager
            
            # Build cache key
            if key_builder is not None:
                cache_key = key_builder(*args, **kwargs)
            else:
                # Default key builder: combine positional and keyword arguments
                arg_items = []
                
                for arg in args:
                    try:
                        arg_items.append(str(arg))
                    except:
                        arg_items.append(hash(str(type(arg))))
                
                kwarg_items = [f"{k}={v}" for k, v in sorted(kwargs.items())]
                
                # Create a unique key
                key_parts = arg_items + kwarg_items
                cache_key = hashlib.md5(json.dumps(key_parts).encode()).hexdigest()
            
            # Try to get from cache
            cached_result = await cache_manager.get(cache_key, namespace=_namespace)
            if cached_result is not None:
                return cached_result
            
            # Not in cache, call the function
            result = await func(self, *args, **kwargs)
            
            # Store result in cache
            await cache_manager.set(
                cache_key, 
                result, 
                ttl=ttl, 
                namespace=_namespace,
                store_distributed=store_distributed
            )
            
            return result
            
        return wrapper
    
    return decorator 