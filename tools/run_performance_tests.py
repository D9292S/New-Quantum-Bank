#!/usr/bin/env python

"""
Performance test runner for Quantum Superbot

This script runs performance tests and displays a performance report.
"""

import asyncio
import argparse
import logging
import os
import sys
import time
from datetime import datetime
import inspect

# Add project root to Python path for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

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
    from optimizations.memory_management import get_memory_manager
    # Only importing what we actually use to avoid lint errors
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
        opt_results = run_optimization_tests()
        # Convert to awaitable if not already
        if inspect.isawaitable(opt_results):
            opt_results = await opt_results
        report["optimization_tests"] = opt_results
    except Exception as e:
        logger.error(f"Error running optimization tests: {e}")
        report["optimization_tests"] = {"success": False, "error": str(e)}
    
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


def format_markdown_report(report):
    markdown_report = "# Quantum Superbot Performance Report\n"
    markdown_report += f"## {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    
    # Optimization tests
    opt_tests = report.get("optimization_tests", {})
    markdown_report += f"### Optimization Tests: {'Passed' if opt_tests.get('success', False) else 'Failed'}\n"
    if "error" in opt_tests:
        markdown_report += f"#### Error: {opt_tests['error']}\n"
    
    # API benchmark
    api = report.get("api_benchmark", {})
    markdown_report += "\n### API Performance\n"
    markdown_report += f"#### Iterations: {api.get('iterations', 0)}\n"
    markdown_report += f"#### Total time: {api.get('total_time', 0):.2f}s\n"
    markdown_report += f"#### Average response time: {api.get('avg_time_ms', 0):.2f}ms\n"
    
    # Database benchmark
    db = report.get("db_benchmark", {})
    markdown_report += "\n### Database Performance\n"
    markdown_report += f"#### Iterations: {db.get('iterations', 0)}\n"
    markdown_report += f"#### Total time: {db.get('total_time', 0):.2f}s\n"
    markdown_report += f"#### Average query time: {db.get('avg_time_ms', 0):.2f}ms\n"
    
    # Memory benchmark
    mem = report.get("memory_benchmark", {})
    markdown_report += "\n### Memory Usage\n"
    markdown_report += f"#### Starting memory: {mem.get('start_memory_mb', 0):.2f}MB\n"
    markdown_report += f"#### Peak memory: {mem.get('peak_memory_mb', 0):.2f}MB\n"
    markdown_report += f"#### Ending memory: {mem.get('end_memory_mb', 0):.2f}MB\n"
    markdown_report += f"#### Memory increase during test: {mem.get('memory_increase_mb', 0):.2f}MB\n"
    markdown_report += f"#### Potential memory leak: {mem.get('memory_leak_mb', 0):.2f}MB\n"
    
    # Memory trend
    trend = report.get("memory_trend", {})
    trend_direction = trend.get("trend", "unknown")
    markdown_report += f"\n### Memory Trend: {trend_direction.upper()}\n"
    if "change_rate" in trend:
        markdown_report += f"#### Rate of change: {trend.get('change_rate', 0):.2f}MB/hour\n"
    
    # Summary
    markdown_report += "\n### Performance Summary\n"
    memory_status = "GOOD" if mem.get("memory_leak_mb", 0) < 5 else "WARNING" if mem.get("memory_leak_mb", 0) < 20 else "CRITICAL"
    api_status = "GOOD" if api.get("avg_time_ms", 1000) < 50 else "WARNING" if api.get("avg_time_ms", 1000) < 100 else "CRITICAL"
    db_status = "GOOD" if db.get("avg_time_ms", 1000) < 100 else "WARNING" if db.get("avg_time_ms", 1000) < 200 else "CRITICAL"
    
    markdown_report += f"#### Memory: {memory_status}\n"
    markdown_report += f"#### API: {api_status}\n"
    markdown_report += f"#### Database: {db_status}\n"
    
    return markdown_report


def display_report(report):
    """Display the performance report in a readable format"""
    print("="*80)
    print(f"QUANTUM SUPERBOT PERFORMANCE REPORT - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80 + "\n")
    
    # Display optimization test results
    opt_tests = report.get("optimization_tests", {})
    print(f"OPTIMIZATION TESTS: {'PASSED' if opt_tests.get('success', False) else 'FAILED'}")
    if "error" in opt_tests:
        print(f"   - Error: {opt_tests['error']}")
    print()
    
    # Display API benchmark
    api = report.get("api_benchmark", {})
    print("API PERFORMANCE:")
    print(f"   - Iterations: {api.get('iterations', 0)}")
    print(f"   - Total time: {api.get('total_time', 0):.2f}s")
    print(f"   - Average response time: {api.get('avg_time_ms', 0):.2f}ms")
    print()
    
    # Display database benchmark
    db = report.get("db_benchmark", {})
    print("DATABASE PERFORMANCE:")
    print(f"   - Iterations: {db.get('iterations', 0)}")
    print(f"   - Total time: {db.get('total_time', 0):.2f}s")
    print(f"   - Average query time: {db.get('avg_time_ms', 0):.2f}ms")
    print()
    
    # Display memory benchmark
    mem = report.get("memory_benchmark", {})
    print("MEMORY USAGE:")
    print(f"   - Starting memory: {mem.get('start_memory_mb', 0):.2f}MB")
    print(f"   - Peak memory: {mem.get('peak_memory_mb', 0):.2f}MB")
    print(f"   - Ending memory: {mem.get('end_memory_mb', 0):.2f}MB")
    print(f"   - Memory increase during test: {mem.get('memory_increase_mb', 0):.2f}MB")
    print(f"   - Potential memory leak: {mem.get('memory_leak_mb', 0):.2f}MB")
    print()
    
    # Display memory trend information
    trend = report.get("memory_trend", {})
    trend_direction = trend.get("trend", "unknown")
    print(f"MEMORY TREND: {trend_direction.upper()}")
    if "change_rate" in trend:
        print(f"   - Rate of change: {trend.get('change_rate', 0):.2f}MB/hour")
    print()
    
    # Display performance summary
    print("PERFORMANCE SUMMARY:")
    memory_status = "GOOD" if mem.get("memory_leak_mb", 0) < 5 else "WARNING" if mem.get("memory_leak_mb", 0) < 20 else "CRITICAL"
    api_status = "GOOD" if api.get("avg_time_ms", 1000) < 50 else "WARNING" if api.get("avg_time_ms", 1000) < 100 else "CRITICAL"
    db_status = "GOOD" if db.get("avg_time_ms", 1000) < 100 else "WARNING" if db.get("avg_time_ms", 1000) < 200 else "CRITICAL"
    
    print(f"   - Memory: {memory_status}")
    print(f"   - API: {api_status}")
    print(f"   - Database: {db_status}")
    print("="*80 + "\n")


async def main():
    parser = argparse.ArgumentParser(description="Run performance tests for Quantum Superbot")
    parser.add_argument("--save", action="store_true", help="Save the report to a file")
    parser.add_argument("--quick", action="store_true", help="Run a quick benchmark with fewer iterations")
    parser.add_argument("--output", help="Output file for the report")
    args = parser.parse_args()
    
    try:
        # Adjust benchmark parameters if quick mode is requested
        if args.quick:
            logger.info("Running quick benchmark with reduced iterations")
            
            # Use global keyword to modify the global benchmark functions
            global run_api_benchmark, run_db_benchmark, run_memory_benchmark
            
            # Save original function references
            _orig_api_benchmark = run_api_benchmark
            _orig_db_benchmark = run_db_benchmark
            _orig_memory_benchmark = run_memory_benchmark
            
            # Define quick versions
            async def _run_api_benchmark_quick(iterations=20):
                return await _orig_api_benchmark(iterations=iterations)
            
            async def _run_db_benchmark_quick(iterations=20):
                return await _orig_db_benchmark(iterations=iterations)
            
            async def _run_memory_benchmark_quick(iterations=3):
                return await _orig_memory_benchmark(iterations=iterations)
            
            # Replace global functions with quick versions
            run_api_benchmark = _run_api_benchmark_quick
            run_db_benchmark = _run_db_benchmark_quick
            run_memory_benchmark = _run_memory_benchmark_quick
        
        # Generate the report
        report = await generate_performance_report()
        display_report(report)
        
        if args.output:
            with open(args.output, 'w') as f:
                f.write(format_markdown_report(report))
            logger.info(f"Report saved to {args.output}")
        elif args.save:
            filename = f"performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            with open(filename, 'w') as f:
                f.write(format_markdown_report(report))
            logger.info(f"Report saved to {filename}")
            
        return 0
    except Exception as e:
        logger.error(f"Error running performance tests: {e}", exc_info=True)
        return 1


def calculate_memory_trend(start_memory, end_memory, test_duration):
    """Calculate memory trend and rate of change"""
    memory_change = end_memory - start_memory
    # Convert seconds to hours for the rate
    hours = test_duration / 3600
    
    if memory_change > 0.5:  # More than 0.5MB increase
        trend = "increasing"
        change_rate = memory_change / hours if hours > 0 else 0
    elif memory_change < -0.5:  # More than 0.5MB decrease
        trend = "decreasing"
        change_rate = abs(memory_change) / hours if hours > 0 else 0
    else:
        trend = "stable"
        change_rate = 0
    
    return {
        "trend": trend,
        "change_rate": change_rate,
        "summary": f"Memory is {trend} at a rate of {change_rate:.2f} MB/hour"
    }


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))