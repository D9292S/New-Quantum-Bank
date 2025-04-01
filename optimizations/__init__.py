"""
This package contains various performance optimizations for the Quantum Bank project.

Version: 0.1.0
"""

__version__ = "0.1.0"

# Import and expose key modules and functions
try:
    from .memory_management import (
        get_memory_manager, 
        optimize_memory_usage, 
        memory_intensive,
        MemoryManager
    )
    
    from .db_performance import (
        get_query_cache,
        QueryProfiler,
        get_index_recommender,
        BatchProcessor,
        query_timing,
        cacheable_query,
        db_retry,
        IndexRecommender,
        QueryCache
    )
    
    from .mongodb_improvements import (
        optimize_query,
        smart_cache, 
        execute_bulk_write,
        BulkOperations
    )
    
    # Flag that optimizations are available
    OPTIMIZATIONS_AVAILABLE = True
except ImportError as e:
    # Flag that optimizations failed to load
    OPTIMIZATIONS_AVAILABLE = False
    
    # Define a function to report the error
    def get_import_error():
        return str(e)
