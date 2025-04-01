# Performance Optimization Guide

This document provides detailed information about the performance optimization features in Quantum Bank Bot and how to use them effectively.

## Overview

Quantum Bank includes several performance optimization modules designed to:

- Reduce memory usage and prevent memory leaks
- Optimize database operations through intelligent caching
- Improve overall responsiveness and reduce latency
- Monitor and report on performance metrics

These optimizations are designed to work together to provide a smooth, efficient experience even under heavy load or with limited resources.

## Memory Management

The memory management system (`optimizations/memory_management.py`) provides tools for monitoring and optimizing memory usage.

### Key Features

- **Memory Usage Tracking**: Real-time monitoring of memory consumption
- **Garbage Collection Control**: Intelligent triggering of Python's garbage collector
- **Object Tracking**: Detection of potential memory leaks using weak references
- **Memory-Intensive Operation Handling**: Special decorator for memory-heavy functions

### Using Memory Management

```python
# Import the memory manager
from optimizations.memory_management import get_memory_manager, optimize_memory_usage

# Get the global memory manager instance
memory_manager = get_memory_manager()

# Check current memory usage
current_mb = memory_manager.get_memory_usage()
print(f"Current memory usage: {current_mb}MB")

# Force garbage collection if needed
collected = memory_manager.force_collection()
print(f"Collected {collected} objects")

# Track an object for potential memory leaks
big_object = [1] * 1000000
memory_manager.track_object(big_object, "large_list")

# Apply memory optimization with a custom threshold
optimize_memory_usage(threshold_mb=200)
```

## Database Performance

The database performance module (`optimizations/db_performance.py`) provides tools for optimizing database operations.

### Key Features

- **Query Caching**: Eliminates redundant queries by caching frequently accessed data
- **Query Profiling**: Identifies slow queries and provides performance metrics
- **Batch Processing**: Reduces database load by grouping write operations
- **Intelligent Retry Logic**: Handles transient database errors with exponential backoff

### Using Query Caching

```python
# Import the query cache
from optimizations.db_performance import get_query_cache, cacheable_query

# Get the global query cache
cache = get_query_cache()

# Use the cache directly
cache.set("user:123:profile", user_data, ttl=300)  # Cache for 5 minutes
result = cache.get("user:123:profile")

# Use the decorator for automatic caching of async functions
@cacheable_query(ttl=300)
async def get_user_profile(user_id):
    # This query will only hit the database if not in cache
    return await db.users.find_one({"user_id": user_id})

# Check cache statistics
stats = cache.stats()
print(f"Cache hit ratio: {stats['hit_ratio']:.2f}")
```

### Using Query Profiling

```python
from optimizations.db_performance import QueryProfiler

# Record a database query
QueryProfiler.record_query(
    collection="users",
    operation="find_one",
    query={"user_id": "123456789"},
    duration=0.045,  # 45ms
    success=True,
    result_size=1
)

# Get profiling statistics
stats = QueryProfiler.get_stats()
print(f"Total queries: {stats['total_queries']}")
print(f"Slow queries: {stats['slow_queries']}")
print(f"Average query time: {stats['avg_query_time']:.3f}s")
```

### Using Batch Processing

```python
from optimizations.db_performance import BatchProcessor

# Create a batch processor for user updates
async def process_user_updates(updates):
    await db.users.bulk_write(updates)
    return {"processed": len(updates)}

batch = BatchProcessor(
    batch_size=50,      # Process in batches of 50
    max_delay=1.0,      # Process at least every second
    processor_func=process_user_updates
)

# Add operations to the batch
for user_id, new_balance in updates:
    operation = {
        "update_one": {
            "filter": {"user_id": user_id},
            "update": {"$set": {"balance": new_balance}}
        }
    }
    await batch.add(operation)

# Force processing of any remaining items
await batch.flush()
```

## MongoDB-Specific Optimizations

The MongoDB improvements module (`optimizations/mongodb_improvements.py`) provides optimizations specific to MongoDB.

### Key Features

- **Query Optimization**: Automatically rewrites queries for better performance
- **Bulk Operation Helpers**: Utilities for efficient batch operations
- **Smart Caching Strategies**: MongoDB-aware caching that respects document schemas
- **Index Recommendations**: Analyzes queries to suggest optimal indexes

### Using MongoDB Optimizations

```python
from optimizations.mongodb_improvements import optimize_query, BulkOperations

# Optimize a complex query
original_query = {
    "$or": [
        {"user_id": "123"},
        {"user_id": "456"},
        {"user_id": "789"}
    ],
    "active": True
}
optimized_query = optimize_query(original_query)
# Transforms to: {"user_id": {"$in": ["123", "456", "789"]}, "active": True}

# Use bulk operations
await BulkOperations.update_many_accounts(
    db,
    {"guild_id": "guild123", "balance": {"$lt": 1000}},
    {"$set": {"low_balance_warning": True}}
)

# Process daily interest in bulk
count = await BulkOperations.process_daily_interest(db, rate=0.01, min_balance=1000)
print(f"Processed interest for {count} accounts")
```

## Configuration Options

The performance optimization systems can be configured through environment variables or command-line arguments:

| Option | Environment Variable | Command-Line Arg | Description |
|--------|---------------------|------------------|-------------|
| Performance Mode | `PERFORMANCE_MODE` | `--performance` | Sets overall performance mode (low/medium/high) |
| Memory Limit | `MEMORY_LIMIT_MB` | N/A | Memory limit in MB before aggressive optimization |
| Query Cache Size | `QUERY_CACHE_SIZE` | N/A | Maximum number of items in query cache |
| Query Cache TTL | `QUERY_CACHE_TTL` | N/A | Default time-to-live for cached queries in seconds |

Example `.env` configuration:
```
PERFORMANCE_MODE=high
MEMORY_LIMIT_MB=500
QUERY_CACHE_SIZE=2000
QUERY_CACHE_TTL=600
```

## Performance Testing

The `tools/` directory contains scripts for testing and benchmarking performance:

### check_optimizations.py

Verifies that all optimization systems are functioning correctly:

```bash
python tools/check_optimizations.py
```

Output example:
```
===== OPTIMIZATION STATUS =====
Modules available: ✅
Memory management: ✅
Query cache:       ✅
=============================
Overall status: ✅ ALL OPTIMIZATIONS WORKING
```

### run_performance_tests.py

Runs comprehensive performance benchmarks and generates reports:

```bash
# Run quick benchmarks
python tools/run_performance_tests.py --quick

# Run full benchmarks and save results
python tools/run_performance_tests.py --save
```

The script will generate detailed performance reports in the `performance_reports/` directory, including:
- Memory usage statistics
- Query performance metrics
- System resource utilization
- Optimization effectiveness measurements

## Best Practices

For optimal performance, follow these guidelines:

1. **Memory Management**:
   - Avoid storing large objects in memory indefinitely
   - Use `track_object()` for large temporary objects
   - Consider using generators for processing large datasets

2. **Database Operations**:
   - Use the `@cacheable_query` decorator for frequently accessed data
   - Group related write operations using `BatchProcessor`
   - Keep database connections open for reuse rather than reconnecting

3. **General Performance**:
   - Profile code regularly using the performance test tools
   - Monitor cache hit ratios and adjust TTLs accordingly
   - Increase `MEMORY_LIMIT_MB` for high-traffic servers

4. **CI/CD Integration**:
   - Run performance tests as part of CI/CD pipelines
   - Monitor performance trends over time
   - Set performance budgets for critical operations

## Troubleshooting

### Common Issues

1. **High Memory Usage**:
   - Check for memory leaks using `memory_manager.check_tracked_objects()`
   - Reduce cache sizes with `cache.max_size = smaller_value`
   - Force garbage collection periodically during heavy operations

2. **Slow Database Operations**:
   - Examine the slow queries report with `QueryProfiler.get_slow_queries()`
   - Verify correct index usage
   - Increase cache TTLs for frequently accessed data

3. **Cache Not Working**:
   - Ensure cache keys are consistently generated
   - Check if TTLs are appropriate for the data
   - Verify cache size is sufficient for your workload

For more serious performance issues, run a full benchmark with `run_performance_tests.py` and analyze the detailed report. 