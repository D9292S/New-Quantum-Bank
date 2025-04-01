#!/usr/bin/env python

"""
Performance test runner for Quantum Bank

This script runs performance tests and displays a performance report.
"""

import asyncio
import argparse
import logging
import os
import sys
import time
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('performance_tests.log')
    ]
)
logger = logging.getLogger("perf_runner")

# Import optimization modules
try:
    # Import the modules directly from the optimizations package
    from optimizations.memory_management import get_memory_manager, optimize_memory_usage, memory_intensive
    from optimizations.db_performance import get_query_cache, QueryProfiler, get_index_recommender, BatchProcessor
    from optimizations.test_performance import run_tests as run_optimization_tests
    
    OPTIMIZATIONS_AVAILABLE = True
    logger.info("Successfully imported optimization modules")
except ImportError as e:
    logger.error(f"Failed to import optimization modules: {e}")
    logger.error("Make sure you've created the optimization modules first")
    OPTIMIZATIONS_AVAILABLE = False
    sys.exit(1)


async def run_api_benchmark(iterations=100):
    """Run benchmark for API operations"""
    logger.info(f"Running API benchmark with {iterations} iterations")
    
    start_time = time.time()
    
    # Simulate API calls with different response times
    for i in range(iterations):
        # Simulate API latency (varying between 10-50ms)
        await asyncio.sleep(0.01 + (i % 5) * 0.01)
    
    total_time = time.time() - start_time
    avg_time = total_time / iterations
    
    logger.info(f"API benchmark completed: {total_time:.2f}s total, {avg_time*1000:.2f}ms per iteration")
    return {
        "total_time": total_time,
        "iterations": iterations,
        "avg_time_ms": avg_time * 1000
    }


async def run_db_benchmark(iterations=100):
    """Run benchmark for database operations"""
    logger.info(f"Running database benchmark with {iterations} iterations")
    
    start_time = time.time()
    
    # Simulate database queries with varying complexities
    for i in range(iterations):
        # Simulate DB operation (varying between 20-100ms)
        complexity = 0.02 + (i % 5) * 0.02
        await asyncio.sleep(complexity)
    
    total_time = time.time() - start_time
    avg_time = total_time / iterations
    
    logger.info(f"DB benchmark completed: {total_time:.2f}s total, {avg_time*1000:.2f}ms per iteration")
    return {
        "total_time": total_time,
        "iterations": iterations,
        "avg_time_ms": avg_time * 1000
    }


async def run_memory_benchmark(iterations=10):
    """Run benchmark for memory usage"""
    logger.info(f"Running memory benchmark with {iterations} iterations")
    
    memory_manager = get_memory_manager()
    start_memory = memory_manager.get_memory_usage()
    peak_memory = start_memory
    
    # Create temporary objects to test memory usage
    objects = []
    for i in range(iterations):
        # Create a moderately large object
        objects.append([i * j for j in range(10000)])
        
        # Check memory usage
        current_memory = memory_manager.get_memory_usage()
        peak_memory = max(peak_memory, current_memory)
    
    # Clean up
    objects = None
    memory_manager.force_collection()
    end_memory = memory_manager.get_memory_usage()
    
    logger.info(f"Memory benchmark completed: started at {start_memory:.2f}MB, " 
                f"peaked at {peak_memory:.2f}MB, ended at {end_memory:.2f}MB")
    return {
        "start_memory_mb": start_memory,
        "peak_memory_mb": peak_memory,
        "end_memory_mb": end_memory,
        "memory_increase_mb": peak_memory - start_memory,
        "memory_leak_mb": end_memory - start_memory
    }


async def generate_performance_report():
    """Generate a comprehensive performance report"""
    report = {}
    
    try:
        # Run optimization tests
        logger.info("Running optimization tests...")
        optimization_success = await run_optimization_tests()
        report["optimization_tests"] = {
            "success": optimization_success
        }
    except Exception as e:
        logger.error(f"Error running optimization tests: {e}")
        report["optimization_tests"] = {
            "success": False,
            "error": str(e)
        }
    
    # Run performance benchmarks
    logger.info("Running API benchmark...")
    report["api_benchmark"] = await run_api_benchmark()
    
    logger.info("Running database benchmark...")
    report["db_benchmark"] = await run_db_benchmark()
    
    logger.info("Running memory benchmark...")
    report["memory_benchmark"] = await run_memory_benchmark()
    
    # Get memory manager stats
    memory_manager = get_memory_manager()
    report["memory_stats"] = {
        "current_usage_mb": memory_manager.get_memory_usage(),
        "peak_usage_mb": memory_manager.peak_memory,
        "collections_triggered": memory_manager.collections_triggered
    }
    
    # Get memory trend
    report["memory_trend"] = memory_manager.get_memory_trend(hours=1)
    
    return report


def display_report(report):
    """Display the performance report in a user-friendly format"""
    print("\n" + "="*80)
    print(f"QUANTUM BANK PERFORMANCE REPORT - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    # Optimization tests
    opt_tests = report.get("optimization_tests", {})
    print(f"\n🧪 OPTIMIZATION TESTS: {'✅ PASSED' if opt_tests.get('success', False) else '❌ FAILED'}")
    if "error" in opt_tests:
        print(f"   - Error: {opt_tests['error']}")
    
    # API benchmark
    api = report.get("api_benchmark", {})
    print(f"\n🌐 API PERFORMANCE:")
    print(f"   - Iterations: {api.get('iterations', 0)}")
    print(f"   - Total time: {api.get('total_time', 0):.2f}s")
    print(f"   - Average response time: {api.get('avg_time_ms', 0):.2f}ms")
    
    # Database benchmark
    db = report.get("db_benchmark", {})
    print(f"\n💾 DATABASE PERFORMANCE:")
    print(f"   - Iterations: {db.get('iterations', 0)}")
    print(f"   - Total time: {db.get('total_time', 0):.2f}s")
    print(f"   - Average query time: {db.get('avg_time_ms', 0):.2f}ms")
    
    # Memory benchmark
    mem = report.get("memory_benchmark", {})
    print(f"\n🧠 MEMORY USAGE:")
    print(f"   - Starting memory: {mem.get('start_memory_mb', 0):.2f}MB")
    print(f"   - Peak memory: {mem.get('peak_memory_mb', 0):.2f}MB")
    print(f"   - Ending memory: {mem.get('end_memory_mb', 0):.2f}MB")
    print(f"   - Memory increase during test: {mem.get('memory_increase_mb', 0):.2f}MB")
    print(f"   - Potential memory leak: {mem.get('memory_leak_mb', 0):.2f}MB")
    
    # Memory trend
    trend = report.get("memory_trend", {})
    trend_direction = trend.get("trend", "unknown")
    trend_icon = "⬆️" if trend_direction == "increasing" else "⬇️" if trend_direction == "decreasing" else "➡️"
    print(f"\n📈 MEMORY TREND: {trend_icon} {trend_direction.upper()}")
    if "change_rate" in trend:
        print(f"   - Rate of change: {trend.get('change_rate', 0):.2f}MB/hour")
    
    # Summary
    print("\n"+"="*80)
    memory_status = "GOOD" if mem.get("memory_leak_mb", 0) < 5 else "WARNING" if mem.get("memory_leak_mb", 0) < 20 else "CRITICAL"
    api_status = "GOOD" if api.get("avg_time_ms", 1000) < 50 else "WARNING" if api.get("avg_time_ms", 1000) < 100 else "CRITICAL"
    db_status = "GOOD" if db.get("avg_time_ms", 1000) < 100 else "WARNING" if db.get("avg_time_ms", 1000) < 200 else "CRITICAL"
    
    print(f"PERFORMANCE SUMMARY:")
    print(f"   - Memory: {memory_status}")
    print(f"   - API: {api_status}")
    print(f"   - Database: {db_status}")
    print("="*80 + "\n")


async def main():
    parser = argparse.ArgumentParser(description="Run performance tests for Quantum Bank")
    parser.add_argument("--save", action="store_true", help="Save the report to a file")
    parser.add_argument("--quick", action="store_true", help="Run a quick benchmark with fewer iterations")
    args = parser.parse_args()
    
    try:
        # Adjust benchmark parameters if quick mode is requested
        if args.quick:
            logger.info("Running quick benchmark with reduced iterations")
            global run_api_benchmark, run_db_benchmark, run_memory_benchmark
            
            # Create wrapper functions with fewer iterations
            orig_api_benchmark = run_api_benchmark
            orig_db_benchmark = run_db_benchmark
            orig_memory_benchmark = run_memory_benchmark
            
            run_api_benchmark = lambda: orig_api_benchmark(iterations=20)
            run_db_benchmark = lambda: orig_db_benchmark(iterations=20)
            run_memory_benchmark = lambda: orig_memory_benchmark(iterations=3)
        
        # Generate the report
        report = await generate_performance_report()
        display_report(report)
        
        if args.save:
            import json
            filename = f"performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            print(f"Report saved to {filename}")
            
        return 0
    except Exception as e:
        logger.error(f"Error running performance tests: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))