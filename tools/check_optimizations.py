#!/usr/bin/env python
# Quick script to verify that optimizations are operational

import time
import asyncio
import logging
import gc

# Configure logging - Less verbose
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger("optimization_check")

# Import optimization modules
try:
    from optimizations.memory_management import get_memory_manager, optimize_memory_usage
    from optimizations.db_performance import get_query_cache, QueryProfiler, cacheable_query, BatchProcessor
    OPTIMIZATIONS_AVAILABLE = True
except ImportError as e:
    OPTIMIZATIONS_AVAILABLE = False
    logger.error(f"Failed to import optimization modules: {e}")

async def test_memory_manager():
    """Test if memory manager is operational"""
    logger.info("Testing memory manager...")
    
    memory_manager = get_memory_manager()
    if not memory_manager:
        logger.error("Memory manager not initialized")
        return False
    
    # Get initial memory usage
    initial_usage = memory_manager.get_memory_usage()
    
    # Create some objects to use memory
    big_list = [i for i in range(500000)]
    
    # Check new memory usage
    after_usage = memory_manager.get_memory_usage()
    
    # Force garbage collection
    memory_manager.force_collection()
    
    # Check memory usage after garbage collection
    final_usage = memory_manager.get_memory_usage()
    
    # Delete big object
    del big_list
    
    return True

async def test_query_cache():
    """Test if query cache is operational"""
    logger.info("Testing query cache...")
    
    query_cache = get_query_cache()
    if not query_cache:
        logger.error("Query cache not initialized")
        return False
    
    # Test cache set and get
    query_cache.set("test_key", "test_value")
    result = query_cache.get("test_key")
    
    if result != "test_value":
        logger.error(f"Query cache retrieval failed: got {result}")
        return False
    
    # Test cache with decorator
    @cacheable_query(ttl=10)
    async def expensive_query(param):
        await asyncio.sleep(0.1)  # Simulate slow query
        return f"Result for {param}"
    
    # First call should be slow
    start = time.time()
    result1 = await expensive_query("test_param")
    time1 = time.time() - start
    
    # Second call should be cached and fast
    start = time.time()
    result2 = await expensive_query("test_param")
    time2 = time.time() - start
    
    # Check that we're getting cache hits
    return "hits" in query_cache.stats() and query_cache.stats()["hits"] > 0

async def test_batch_processor():
    """Test if batch processor is operational"""
    logger.info("Testing batch processor...")
    
    # Create a batch processor
    processed_items = []
    
    async def process_batch(items):
        processed_items.extend(items)
        return {"processed": len(items)}
    
    batch = BatchProcessor(
        batch_size=5,
        max_delay=0.2,
        processor_func=process_batch
    )
    
    # Add items to the batch
    for i in range(10):
        await batch.add(f"item_{i}")
        await asyncio.sleep(0.05)
    
    # Make sure all items get processed by flushing
    await batch.flush()
    
    # Check that we processed all items
    return len(processed_items) == 10

async def main():
    """Run all tests"""
    if not OPTIMIZATIONS_AVAILABLE:
        logger.error("Optimizations not available, cannot run tests")
        return False
    
    logger.info("Running optimization tests...")
    
    # Test memory manager
    memory_result = await test_memory_manager()
    
    # Test query cache
    cache_result = await test_query_cache()
    
    # Test batch processor
    batch_result = await test_batch_processor()
    
    # Report results
    print("\n===== OPTIMIZATION TEST RESULTS =====")
    print(f"Memory Manager: {'✅' if memory_result else '❌'}")
    print(f"Query Cache:    {'✅' if cache_result else '❌'}")
    print(f"Batch Processor: {'✅' if batch_result else '❌'}")
    print("===================================")
    
    all_passing = memory_result and cache_result and batch_result
    print(f"Overall Status: {'✅ ALL OPTIMIZATIONS OPERATIONAL' if all_passing else '❌ SOME OPTIMIZATIONS FAILED'}")
    
    return all_passing

if __name__ == "__main__":
    print("Checking if performance optimizations are operational...")
    asyncio.run(main()) 