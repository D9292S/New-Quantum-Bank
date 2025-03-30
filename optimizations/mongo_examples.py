"""
Example implementations of MongoDB optimizations for Quantum Bank.

This module demonstrates how to apply the optimizations to existing methods.
"""

import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Optional

from optimizations.mongodb_improvements import BulkOperations, optimize_query, smart_cache

logger = logging.getLogger("database")

# --- Smart Caching Example ---


class OptimizedDatabase:
    """Examples of optimized database methods"""

    @smart_cache(ttl=300)  # 5 minutes cache
    async def get_account_optimized(self, user_id: str, guild_id: str) -> dict[str, Any] | None:
        """
        Get account information with smart caching.

        This implementation will cache results for 5 minutes, reducing database load
        for frequently accessed accounts.
        """
        query = {"user_id": user_id, "guild_id": guild_id}
        return await self.db.accounts.find_one(query)

    @smart_cache(ttl=600)  # 10 minutes cache
    async def get_leaderboard_optimized(self, branch_name: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        Get branch leaderboard with optimized query and caching.
        """
        # Smart query with projection to limit fields returned
        projection = {"user_id": 1, "username": 1, "balance": 1, "branch_name": 1, "_id": 1}

        # Only return users from the specified branch with positive balances
        query = {"branch_name": branch_name, "balance": {"$gt": 0}}

        # Use optimized cursor with hint
        cursor = self.db.accounts.find(query, projection)
        cursor.sort("balance", -1).limit(limit)

        # Use index hint if available
        try:
            cursor.hint("balance_-1")
        except Exception:
            # If index doesn't exist, still work without the hint
            logger.warning("No balance_-1 index available for leaderboard query")

        return await cursor.to_list(length=limit)

    # --- Bulk Operations Example ---

    async def process_payroll_optimized(self, payments: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Process payroll payments in bulk instead of individually.

        Args:
            payments: List of payment dictionaries with user_id and amount

        Returns:
            Dict with results summary
        """
        if not payments:
            return {"success": False, "error": "No payments to process"}

        # Group payments by user
        user_payments = {}
        for payment in payments:
            user_id = payment["user_id"]
            if user_id not in user_payments:
                user_payments[user_id] = 0
            user_payments[user_id] += payment["amount"]

        # Prepare bulk operations
        update_ops = []
        transaction_ops = []

        timestamp = datetime.utcnow()

        # Create operations for each user
        for user_id, amount in user_payments.items():
            # Update account balance
            update_ops.append(
                {
                    "update_one": {
                        "filter": {"user_id": user_id},
                        "update": {"$inc": {"balance": amount}, "$set": {"updated_at": timestamp}},
                    }
                }
            )

            # Record transaction
            transaction_ops.append(
                {
                    "insert_one": {
                        "document": {
                            "user_id": user_id,
                            "transaction_type": "payroll",
                            "amount": amount,
                            "description": "Scheduled payroll payment",
                            "timestamp": timestamp,
                        }
                    }
                }
            )

        # Execute bulk operations
        results = {"accounts_updated": 0, "transactions_recorded": 0, "errors": []}

        try:
            if update_ops:
                update_result = await BulkOperations.execute_bulk_write(self.db.accounts, update_ops)
                results["accounts_updated"] = update_result.modified_count

            if transaction_ops:
                tx_result = await BulkOperations.execute_bulk_write(self.db.transactions, transaction_ops)
                results["transactions_recorded"] = tx_result.inserted_count

            results["success"] = True
        except Exception as e:
            logger.error(f"Error in bulk payroll processing: {str(e)}")
            results["success"] = False
            results["errors"].append(str(e))

        return results

    # --- Query Optimization Example ---

    async def search_accounts_optimized(self, criteria: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Search accounts with optimized query structure.

        This method optimizes the query for better performance.
        """
        # Apply query optimization to improve performance
        optimized_criteria = optimize_query(criteria)

        # Use projection to limit returned fields
        projection = {
            "user_id": 1,
            "username": 1,
            "balance": 1,
            "guild_id": 1,
            "branch_name": 1,
            "account_type": 1,
            "_id": 1,
        }

        # Execute optimized query
        return await self.db.accounts.find(optimized_criteria, projection).to_list(length=None)
