"""
Memory Management Optimizations for Quantum Bank Bot

This module provides tools to optimize memory usage and prevent memory leaks:
1. Memory profiling to identify usage patterns
2. Resource limits and garbage collection triggers
3. Weak references for large objects
4. Proactive cleanup of unused resources
"""

import gc
import logging
import os
import sys
import time
import weakref
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, TypeVar

# Setup logger
logger = logging.getLogger("performance")

# Type for decorated functions
F = TypeVar("F", bound=Callable[..., Any])


class MemoryManager:
    """Memory manager for optimizing and monitoring memory usage"""

    def __init__(
        self,
        gc_threshold: int = 50000,  # Object count threshold to trigger GC
        memory_limit_mb: int = 500,  # Memory limit in MB before taking action
        log_interval: int = 300,  # Log memory usage every 5 minutes
        auto_optimize: bool = True,  # Automatically try to optimize memory
    ):
        self.gc_threshold = gc_threshold
        self.memory_limit_mb = memory_limit_mb
        self.log_interval = log_interval
        self.auto_optimize = auto_optimize
        
        # Memory usage tracking
        self.last_log_time = time.time()
        self.last_collection_time = time.time()
        self.peak_memory = 0
        self.collections_triggered = 0
        
        # Weak reference registry for large objects we want to track
        self.tracked_objects: Dict[str, weakref.ref] = {}
        
        # Memory usage statistics
        self.memory_samples: List[Tuple[float, float]] = []
        
        # Reference to psutil.Process instance if available
        self.process = None
        try:
            import psutil
            self.process = psutil.Process()
            logger.info("Memory manager initialized with psutil support")
        except ImportError:
            logger.warning("psutil not available, memory management will be limited")

        # Enable garbage collection
        gc.enable()
        
        # Configure GC thresholds for better performance
        old_thresholds = gc.get_threshold()
        # More aggressive for generation 0 (new objects)
        # More conservative for generations 1 and 2 (older objects)
        gc.set_threshold(old_thresholds[0], old_thresholds[1] * 5, old_thresholds[2] * 10)
        
        logger.info(f"Memory manager initialized with {memory_limit_mb}MB limit and monitoring enabled")

    def get_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        if self.process:
            try:
                return self.process.memory_info().rss / (1024 * 1024)
            except Exception as e:
                logger.error(f"Error getting memory usage: {e}")

        # Fallback method if psutil isn't available
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

    def check_memory(self, force_log: bool = False) -> Dict[str, Any]:
        """
        Check current memory usage and take action if needed
        Returns dict with memory stats
        """
        now = time.time()
        memory_mb = self.get_memory_usage()
        self.peak_memory = max(self.peak_memory, memory_mb)
        
        # Store sample
        self.memory_samples.append((now, memory_mb))
        # Keep only last day of samples
        day_ago = now - 86400
        self.memory_samples = [(t, m) for t, m in self.memory_samples if t >= day_ago]
        
        # Check if we should log memory usage
        should_log = force_log or (now - self.last_log_time >= self.log_interval)
        
        # Get object counts
        counts = gc.get_count()
        
        # Build report
        report = {
            "memory_mb": memory_mb,
            "peak_memory_mb": self.peak_memory,
            "gen0_objects": counts[0],
            "gen1_objects": counts[1],
            "gen2_objects": counts[2],
            "tracked_objects": len(self.tracked_objects),
            "collections_triggered": self.collections_triggered,
            "threshold_pct": (memory_mb / self.memory_limit_mb) * 100 if self.memory_limit_mb else 0,
        }
        
        # Determine if we need to take action
        need_collection = False
        
        # Check generation 0 object count
        if counts[0] > self.gc_threshold:
            need_collection = True
            logger.debug(f"Generation 0 object count ({counts[0]}) exceeded threshold ({self.gc_threshold})")
        
        # Check memory usage vs limit
        if self.memory_limit_mb and memory_mb > self.memory_limit_mb:
            need_collection = True
            logger.warning(f"Memory usage ({memory_mb:.1f}MB) exceeded limit ({self.memory_limit_mb}MB)")
        
        # Log memory usage periodically
        if should_log:
            log_level = logging.WARNING if memory_mb > self.memory_limit_mb else logging.INFO
            logger.log(
                log_level,
                f"Memory usage: {memory_mb:.1f}MB (peak: {self.peak_memory:.1f}MB), "
                f"Objects: gen0={counts[0]}, gen1={counts[1]}, gen2={counts[2]}"
            )
            self.last_log_time = now
            
            # Log tracked objects that still exist
            self.check_tracked_objects()
        
        # Perform garbage collection if needed
        if need_collection and self.auto_optimize and now - self.last_collection_time >= 60:  # Max once per minute
            self.force_collection()
            self.last_collection_time = now
            report["collection_performed"] = True
        else:
            report["collection_performed"] = False
            
        return report
    
    def force_collection(self) -> int:
        """Force garbage collection and return number of objects collected"""
        logger.info("Forcing garbage collection")
        
        # Disable automatic garbage collection during manual collection
        was_enabled = gc.isenabled()
        if was_enabled:
            gc.disable()
        
        # Perform full collection
        gc.collect(2)  # Collect all generations
        collected = sum(gc.get_count())
        
        # Re-enable if it was enabled before
        if was_enabled:
            gc.enable()
            
        self.collections_triggered += 1
        logger.info(f"Garbage collection complete, collected objects: {collected}")
        return collected
    
    def track_object(self, obj: Any, name: str) -> None:
        """
        Track a large object with a weak reference to detect memory leaks
        """
        self.tracked_objects[name] = weakref.ref(obj)
        logger.debug(f"Tracking object: {name}")
    
    def check_tracked_objects(self) -> Dict[str, bool]:
        """
        Check if tracked objects still exist
        Returns dict mapping object names to existence status
        """
        result = {}
        to_remove = []
        
        for name, ref in self.tracked_objects.items():
            obj = ref()
            exists = obj is not None
            result[name] = exists
            
            if not exists:
                to_remove.append(name)
                logger.debug(f"Tracked object no longer exists: {name}")
        
        # Clean up references to non-existent objects
        for name in to_remove:
            del self.tracked_objects[name]
            
        return result
    
    def get_memory_trend(self, hours: int = 1) -> Dict[str, Any]:
        """
        Calculate memory usage trend over the specified time period
        Returns dict with trend analysis
        """
        now = time.time()
        period_start = now - (hours * 3600)
        
        # Filter samples to the requested time period
        period_samples = [(t, m) for t, m in self.memory_samples if t >= period_start]
        
        if len(period_samples) < 2:
            return {"trend": "unknown", "change_rate": 0, "samples": len(period_samples)}
            
        # Get first and last samples
        first_time, first_mem = period_samples[0]
        last_time, last_mem = period_samples[-1]
        
        # Calculate change rate (MB per hour)
        time_diff = (last_time - first_time) / 3600  # Convert to hours
        if time_diff > 0:
            mem_diff = last_mem - first_mem
            change_rate = mem_diff / time_diff
            
            # Determine trend
            if change_rate > 1.0:  # More than 1MB/hour increase
                trend = "increasing"
            elif change_rate < -1.0:  # More than 1MB/hour decrease
                trend = "decreasing"
            else:
                trend = "stable"
                
            return {
                "trend": trend,
                "change_rate": change_rate,
                "samples": len(period_samples),
                "start_memory_mb": first_mem,
                "end_memory_mb": last_mem,
                "period_hours": time_diff,
            }
        
        return {"trend": "unknown", "change_rate": 0, "samples": len(period_samples)}


# Function to create global memory manager
_memory_manager = None


def get_memory_manager() -> MemoryManager:
    """Get or create the global memory manager"""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager


def optimize_memory_usage(threshold_mb: int = 200) -> None:
    """
    Perform memory optimization when memory usage exceeds threshold
    This is a utility function that can be called periodically
    """
    manager = get_memory_manager()
    memory_mb = manager.get_memory_usage()
    
    if memory_mb > threshold_mb:
        logger.info(f"Memory usage ({memory_mb:.1f}MB) exceeds threshold ({threshold_mb}MB), optimizing...")
        
        # Force garbage collection
        manager.force_collection()
        
        # Get new memory usage after collection
        new_memory_mb = manager.get_memory_usage()
        savings = memory_mb - new_memory_mb
        
        if savings > 0:
            logger.info(f"Memory optimization freed {savings:.1f}MB")
        else:
            logger.warning("Memory optimization did not free any memory, possible memory leak")


def memory_intensive(func: F) -> F:
    """
    Decorator for memory-intensive functions
    Performs garbage collection before and after execution
    """
    from functools import wraps
    
    @wraps(func)
    async def wrapper(*args, **kwargs):
        manager = get_memory_manager()
        
        # Log memory usage before execution
        before_mem = manager.get_memory_usage()
        logger.debug(f"Executing memory-intensive function '{func.__name__}', memory before: {before_mem:.1f}MB")
        
        # Run garbage collection before execution
        gc.collect()
        
        # Execute function
        try:
            result = await func(*args, **kwargs)
        finally:
            # Run garbage collection after execution
            gc.collect()
            
            # Log memory usage after execution
            after_mem = manager.get_memory_usage()
            diff = after_mem - before_mem
            if diff > 5:  # Only log if difference is significant (>5MB)
                logger.warning(
                    f"Memory-intensive function '{func.__name__}' used {diff:.1f}MB of memory, "
                    f"current usage: {after_mem:.1f}MB"
                )
            else:
                logger.debug(
                    f"Memory-intensive function '{func.__name__}' completed, "
                    f"memory after: {after_mem:.1f}MB (diff: {diff:.1f}MB)"
                )
        
        return result
    
    return wrapper 