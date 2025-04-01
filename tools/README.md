# Quantum Bank Diagnostic Tools

This directory contains diagnostic and testing tools for the Quantum Bank bot.

## Available Tools

### check_optimizations.py

A lightweight verification tool that checks if all performance optimizations are correctly functioning. This tool:

- Tests the memory manager
- Verifies query cache functionality
- Validates batch processing operations

**Usage:**
```
python tools/check_optimizations.py
```

### run_performance_tests.py

A comprehensive benchmarking tool that generates detailed performance reports. This tool:

- Runs extensive tests on all optimization components
- Benchmarks database query performance
- Measures memory usage patterns
- Generates formatted performance reports

**Usage:**
```
# Run full benchmark
python tools/run_performance_tests.py

# Run quicker benchmark with fewer iterations
python tools/run_performance_tests.py --quick

# Save benchmark results to a file
python tools/run_performance_tests.py --save
```

## When to Use These Tools

- After making code changes to verify performance hasn't degraded
- When troubleshooting performance issues
- To evaluate the impact of optimization changes
- During deployment to verify proper system configuration 