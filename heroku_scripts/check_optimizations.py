#!/usr/bin/env python
"""
Quick script to verify that optimizations are working on Heroku
"""

import os
import sys
import time
import asyncio
import logging
import importlib.util

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger("heroku_check")

# Check if we're running on Heroku
on_heroku = "DYNO" in os.environ

def check_module_available(module_name):
    """Check if a module is available for import"""
    try:
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            logger.error(f"✗ Module {module_name} not found")
            return False
        logger.info(f"✓ Module {module_name} is available")
        return True
    except ImportError:
        logger.error(f"✗ Module {module_name} not importable")
        return False

async def check_memory_management():
    """Check if memory management is working"""
    try:
        from optimizations.memory_management import get_memory_manager
        memory_manager = get_memory_manager()
        
        if memory_manager:
            memory_mb = memory_manager.get_memory_usage()
            logger.info(f"✓ Memory manager working - Current usage: {memory_mb:.2f}MB")
            
            # Try forcing collection
            collected = memory_manager.force_collection()
            logger.info(f"✓ Garbage collection working - Collected {collected} objects")
            return True
        else:
            logger.error("✗ Memory manager not initialized properly")
            return False
    except Exception as e:
        logger.error(f"✗ Memory management error: {e}")
        return False

async def check_query_cache():
    """Check if query cache is working"""
    try:
        from optimizations.db_performance import get_query_cache
        query_cache = get_query_cache()
        
        if query_cache:
            # Test basic operations
            query_cache.set("test_key", "test_value")
            value = query_cache.get("test_key")
            
            if value == "test_value":
                logger.info("✓ Query cache working correctly")
                stats = query_cache.stats()
                logger.info(f"✓ Cache stats: Size={stats['size']}, Hits={stats['hits']}")
                return True
            else:
                logger.error(f"✗ Query cache retrieval failed: got {value}")
                return False
        else:
            logger.error("✗ Query cache not initialized properly")
            return False
    except Exception as e:
        logger.error(f"✗ Query cache error: {e}")
        return False

async def main():
    logger.info(f"Running optimization checks on {'Heroku' if on_heroku else 'local environment'}")
    
    # Check for optimization modules
    modules_ok = all([
        check_module_available("optimizations.memory_management"),
        check_module_available("optimizations.db_performance"),
        check_module_available("optimizations.mongodb_improvements")
    ])
    
    if not modules_ok:
        logger.error("✗ Some optimization modules are missing")
        return False
    
    # Check memory management
    memory_ok = await check_memory_management()
    
    # Check query cache
    cache_ok = await check_query_cache()
    
    # Print summary
    print("\n===== OPTIMIZATION STATUS =====")
    print(f"Modules available: {'✅' if modules_ok else '❌'}")
    print(f"Memory management: {'✅' if memory_ok else '❌'}")
    print(f"Query cache:       {'✅' if cache_ok else '❌'}")
    print("=============================")
    
    all_ok = modules_ok and memory_ok and cache_ok
    print(f"Overall status: {'✅ ALL OPTIMIZATIONS WORKING' if all_ok else '❌ SOME OPTIMIZATIONS FAILED'}")
    
    return all_ok

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 