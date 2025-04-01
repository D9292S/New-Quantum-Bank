# Performance Optimizations for Quantum Bank

This directory contains various performance optimizations for the Quantum Bank project, designed to improve memory usage, database operations, and overall application performance.

## Key Optimizations

### Memory Management (`memory_management.py`)

- **Memory Usage Tracking**: Monitors memory usage and reports trends over time
- **Garbage Collection Management**: Provides intelligent garbage collection triggering
- **Memory Leak Detection**: Tracks objects with weak references to detect potential leaks
- **Memory-Intensive Function Decorator**: Special handling for functions that use a lot of memory

### Database Performance (`db_performance.py`)

- **Query Caching**: Caches frequently used query results to reduce database load
- **Query Profiling**: Tracks query performance and identifies slow queries
- **Retry Mechanisms**: Automatically retries failed database operations with exponential backoff
- **Batch Processing**: Groups database write operations to reduce overhead
- **Index Recommendations**: Analyzes query patterns and recommends optimal database indexes

### MongoDB Improvements (`mongodb_improvements.py`)

- **Query Optimization**: Rewrites queries to use more efficient operators
- **Smart Caching**: Context-aware caching for frequently accessed data
- **Bulk Operations**: Helpers for performing efficient batch operations
- **Connection Pooling**: Optimized connection pooling settings

## Implementation and Integration

These optimizations have been integrated in:

- `launcher.py`: Initializes and configures optimization systems at startup
- `database.py`: Utilizes database optimizations for queries and transactions
- Performance monitoring systems: Track and report on optimization effectiveness

## Testing

The optimizations include testing utilities:

- `test_performance.py`: Unit tests for the optimization modules
- `run_performance_tests.py`: Comprehensive performance testing and benchmarking

To run the tests:

```bash
# Run the simple test to verify optimizations are working
python run_test.py

# Run comprehensive performance tests (may take several minutes)
python run_performance_tests.py

# Run a quick performance test
python run_performance_tests.py --quick

# Run tests and save results to a file
python run_performance_tests.py --save
```

## Performance Improvements

The optimizations provide significant performance improvements:

1. **Memory Usage**: Reduced peak memory usage by controlling garbage collection and proactively cleaning up unused resources
2. **Database Performance**: 
   - Decreased query latency through caching (up to 90% reduction for repeated queries)
   - Reduced database load through batched operations
   - Improved reliability with automatic retry mechanisms
3. **Startup Time**: Optimized initialization sequence reduces bot startup time
4. **Overall Responsiveness**: The combined optimizations improve the bot's response time to user commands

## Monitoring Dashboard

The performance monitoring system provides real-time insights into:

1. Memory usage and trends
2. Database query performance
3. Cache hit rates
4. Slow query detection

## Adding New Optimizations

When adding new optimizations:

1. Add the optimization code to the appropriate module
2. Update the `__init__.py` file to expose any new public functions or classes
3. Add tests to verify the optimization works correctly
4. Document the optimization in this README

## Requirements

The optimizations use the following packages:

- `psutil`: For memory usage monitoring
- `weakref`: For tracking objects and detecting memory leaks

Optional but recommended:
- `orjson`: For faster JSON serialization/deserialization
- `uvloop`: For improved event loop performance (non-Windows platforms only) 