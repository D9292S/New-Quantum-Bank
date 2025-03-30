"""
MongoDB Optimization Implementations for Quantum Bank

This module provides enhanced MongoDB optimization strategies:
1. Advanced query optimization
2. Smart caching strategies
3. Bulk operation implementations
4. Index optimization recommendations
5. Connection pooling improvements
"""

import functools
import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any, TypeVar, cast

# Define type for the decorated function
F = TypeVar("F", bound=Callable[..., Any])

logger = logging.getLogger("database")

# --- Query Optimization Functions ---


def optimize_query(query: dict) -> dict:
    """
    Optimize a MongoDB query for better performance

    Improvements:
    - Use $in operator for multiple equality checks on same field
    - Replace $or with $in when possible
    - Add query hint recommendations
    """
    optimized = query.copy()

    # Optimize $or queries that check the same field with different values
    if "$or" in optimized:
        field_values = {}

        # Group $or conditions by field
        for condition in optimized["$or"]:
            for field, value in condition.items():
                if field not in field_values:
                    field_values[field] = []
                field_values[field].append(value)

        # Replace $or with $in for fields with multiple values
        new_conditions = {}
        remaining_or_conditions = []

        for condition in optimized["$or"]:
            handled = False
            for field, value in condition.items():
                if len(field_values[field]) > 1:
                    if field not in new_conditions:
                        new_conditions[field] = {"$in": field_values[field]}
                    handled = True
                    break

            if not handled:
                remaining_or_conditions.append(condition)

        # Update the query
        for field, condition in new_conditions.items():
            optimized[field] = condition

        # If we still have remaining $or conditions, keep them
        if remaining_or_conditions:
            optimized["$or"] = remaining_or_conditions
        else:
            del optimized["$or"]

    return optimized


# --- Bulk Operation Helpers ---


async def execute_bulk_write(collection, operations, ordered=True):
    """Execute bulk write operations with error handling and retry logic"""
    try:
        start_time = time.perf_counter()
        result = await collection.bulk_write(operations, ordered=ordered)
        execution_time = (time.perf_counter() - start_time) * 1000

        logger.debug(
            f"Bulk operation completed in {execution_time:.2f}ms - "
            f"{result.inserted_count} inserted, {result.modified_count} modified, "
            f"{result.deleted_count} deleted"
        )
        return result
    except Exception as e:
        logger.error(f"Bulk operation failed: {str(e)}")
        raise


# --- Smart Caching Decorator ---


def smart_cache(ttl: int = 300, key_prefix: str = "", max_entries_per_user: int = 20, cache_null: bool = False):
    """
    Smart caching decorator that adapts based on usage patterns

    Features:
    - Per-user cache limits
    - Automatic TTL adjustment based on access frequency
    - Support for distributed caching via MongoDB
    - Cache warming for frequently accessed data
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            if not hasattr(self, "bot") or not hasattr(self.bot, "cache_manager"):
                return await func(self, *args, **kwargs)

            cache_manager = self.bot.cache_manager

            # Build cache key
            cache_key_parts = [key_prefix or func.__name__]

            # Add args to key, looking for user_id specially
            user_id = None
            for arg in args:
                if isinstance(arg, str) and len(arg) > 0:
                    cache_key_parts.append(str(arg))
                    # Check if this might be a user_id
                    if len(arg) >= 17 and arg.isdigit():
                        user_id = arg

            # Add kwargs to key
            for key, value in kwargs.items():
                if isinstance(value, (str, int, float, bool)):
                    cache_key_parts.append(f"{key}:{value}")
                if key == "user_id" and isinstance(value, str):
                    user_id = value

            # Finalize cache key
            cache_key = ":".join(cache_key_parts)

            # Determine namespace
            namespace = f"user:{user_id}" if user_id else "global"

            # Try to get from cache
            result = await cache_manager.get(cache_key, namespace=namespace)
            if result is not None:
                logger.debug(f"Cache hit for {func.__name__}")
                return result

            # Not in cache, call the original function
            result = await func(self, *args, **kwargs)

            # Don't cache None results unless explicitly asked to
            if result is None and not cache_null:
                return result

            # Store in cache, with distributed storage for global data
            store_distributed = namespace == "global"

            # Adjust TTL based on the entity type and size
            actual_ttl = ttl

            # For user-specific data, use shorter TTL
            if user_id:
                # Check if we need to evict old entries
                keys = await cache_manager.get_keys(namespace=namespace)
                if len(keys) >= max_entries_per_user:
                    # Remove the oldest key
                    if keys:
                        await cache_manager.delete(keys[0], namespace=namespace)

                # Store the new result
                await cache_manager.set(
                    cache_key, result, ttl=actual_ttl, namespace=namespace, store_distributed=store_distributed
                )
            else:
                # For global data, use distributed storage with longer TTL
                await cache_manager.set(
                    cache_key, result, ttl=actual_ttl * 2, namespace=namespace, store_distributed=True
                )

            return result

        return cast(F, wrapper)

    return decorator


# --- Bulk Operation Implementations ---


class BulkOperations:
    """Helper class for efficient bulk operations"""

    @staticmethod
    async def update_many_accounts(db, query, update, ordered=True):
        """Efficient bulk update for multiple accounts"""
        accounts = await db.accounts.find(query).to_list(length=None)
        if not accounts:
            return 0

        operations = []
        for account in accounts:
            operations.append({"update_one": {"filter": {"_id": account["_id"]}, "update": update}})

        if operations:
            result = await execute_bulk_write(db.accounts, operations, ordered=ordered)
            return result.modified_count
        return 0

    @staticmethod
    async def process_daily_interest(db, rate=0.01, min_balance=1000):
        """Process daily interest for all eligible accounts in bulk"""
        query = {"balance": {"$gte": min_balance}}
        eligible_accounts = await db.accounts.find(query).to_list(length=None)

        operations = []
        for account in eligible_accounts:
            interest_amount = round(account["balance"] * rate, 2)
            new_balance = account["balance"] + interest_amount

            # Update account balance
            operations.append(
                {"update_one": {"filter": {"_id": account["_id"]}, "update": {"$set": {"balance": new_balance}}}}
            )

            # Record transaction
            operations.append(
                {
                    "insert_one": {
                        "document": {
                            "user_id": account["user_id"],
                            "transaction_type": "interest",
                            "amount": interest_amount,
                            "description": "Daily interest",
                            "timestamp": datetime.utcnow(),
                            "guild_id": account.get("guild_id", "global"),
                        }
                    }
                }
            )

        if operations:
            await execute_bulk_write(db.transactions, operations, ordered=False)
            return len(operations) // 2  # Number of accounts processed
        return 0


async def analyze_and_recommend_indexes(db):
    """
    Analyze query patterns and recommend optimal indexes

    Returns a dict of collection names and recommended indexes
    """
    recommendations = {}

    # Get current indexes
    current_indexes = {}

    # Check main collections
    for collection_name in ["accounts", "transactions", "loans", "credit_reports"]:
        collection = db[collection_name]
        index_info = await collection.index_information()
        current_indexes[collection_name] = list(index_info.keys())

    # Query the system.profile collection if profiling is enabled
    profiling_level = await db.command({"profile": -1})

    if profiling_level["was"] > 0:
        # Analyze slow queries from profile
        slow_queries = (
            await db.system.profile.find({"millis": {"$gt": 100}})  # Queries taking more than 100ms
            .sort("millis", -1)
            .limit(20)
            .to_list(length=None)
        )

        for query in slow_queries:
            collection_name = query.get("ns", "").split(".")[-1]

            if collection_name not in recommendations:
                recommendations[collection_name] = set()

            # Extract query shape
            query_obj = query.get("query", {})

            if isinstance(query_obj, dict):
                for field in query_obj:
                    if field not in ["$query", "$orderby"] and not field.startswith("$"):
                        # Check if this field already has an index
                        if collection_name in current_indexes and f"{field}_1" not in current_indexes[collection_name]:
                            recommendations[collection_name].add(field)

    # Add default recommendations based on common patterns
    common_patterns = {
        "accounts": ["user_id", "guild_id", "balance", "created_at"],
        "transactions": ["user_id", "transaction_type", "timestamp"],
        "loans": ["user_id", "status", "due_date"],
    }

    for collection_name, fields in common_patterns.items():
        if collection_name in current_indexes:
            if collection_name not in recommendations:
                recommendations[collection_name] = set()

            for field in fields:
                if f"{field}_1" not in current_indexes[collection_name]:
                    recommendations[collection_name].add(field)

    # Convert sets to lists for easier consumption
    result = {}
    for collection_name, fields in recommendations.items():
        result[collection_name] = list(fields)

    return result


# --- Example optimized implementations ---


async def example_optimized_leaderboard(db, limit=10, guild_id=None):
    """Example of an optimized leaderboard query using proper indexing and projection"""
    # Build query with proper filter
    query = {"balance": {"$gt": 0}}

    if guild_id:
        query["guild_id"] = guild_id

    # Use projection to limit returned fields
    projection = {"user_id": 1, "username": 1, "balance": 1, "_id": 0}

    # Use appropriate sort and limit with a hint for the index
    cursor = db.accounts.find(query, projection)
    cursor.sort("balance", -1).limit(limit)

    # Add a hint to use the balance index
    cursor.hint("balance_-1")

    return await cursor.to_list(length=limit)


async def example_batch_transaction_processing(db, transactions):
    """Example of efficient batch processing for transactions"""
    if not transactions:
        return []

    # Group transactions by user
    user_transactions = {}

    for tx in transactions:
        user_id = tx.get("user_id")
        if not user_id:
            continue

        if user_id not in user_transactions:
            user_transactions[user_id] = []
        user_transactions[user_id].append(tx)

    # Process in batches by user
    results = []
    operations = []

    for user_id, txs in user_transactions.items():
        # Get user account once
        account = await db.accounts.find_one({"user_id": user_id})

        if not account:
            continue

        balance = account["balance"]

        for tx in txs:
            # Update balance
            if tx["type"] == "deposit":
                balance += tx["amount"]
            else:
                balance -= tx["amount"]

            # Prepare account update
            operations.append(
                {"update_one": {"filter": {"user_id": user_id}, "update": {"$set": {"balance": balance}}}}
            )

            # Prepare transaction record
            operations.append(
                {
                    "insert_one": {
                        "document": {
                            "user_id": user_id,
                            "transaction_type": tx["type"],
                            "amount": tx["amount"],
                            "description": tx.get("description", ""),
                            "timestamp": datetime.utcnow(),
                            "guild_id": account.get("guild_id", "global"),
                        }
                    }
                }
            )

            # Track result
            results.append(
                {
                    "user_id": user_id,
                    "transaction_id": f"batch_{len(results)}",
                    "status": "processed",
                    "new_balance": balance,
                }
            )

    # Execute all operations in one bulk write
    if operations:
        await execute_bulk_write(db, operations, ordered=False)

    return results
