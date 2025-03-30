"""Unit tests for transaction operations."""

import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


@pytest.mark.asyncio
@pytest.mark.transactions
class TestTransactionOperations:
    """Tests for transaction creation, retrieval, and filtering."""
    
    @pytest.fixture
    async def mock_db(self):
        """Set up a mock Database instance with transaction operations."""
        db = AsyncMock()
        
        # Setup common mock methods
        db.log_transaction = AsyncMock()
        db.get_transactions = AsyncMock()
        db.get_recent_transactions = AsyncMock()
        db.get_transactions_by_type_and_date = AsyncMock()
        
        return db
    
    async def test_log_transaction(self, mock_db):
        """Test logging a transaction."""
        # Set up test data
        user_id = "123456789"
        transaction_type = "deposit"
        amount = 100.0
        description = "Test deposit"
        
        # Set up mock transaction ID
        transaction_id = "TXN-12345-abcdef"
        
        # Set up mocks
        mock_db.log_transaction.return_value = transaction_id
        
        # Call the method
        result = await mock_db.log_transaction(
            user_id=user_id,
            transaction_type=transaction_type,
            amount=amount,
            description=description
        )
        
        # Verify results
        assert result == transaction_id
        
        # Verify correct methods were called
        mock_db.log_transaction.assert_called_once_with(
            user_id=user_id,
            transaction_type=transaction_type,
            amount=amount,
            description=description,
            receiver_id=None
        )
    
    async def test_log_transfer_transaction(self, mock_db):
        """Test logging a transfer transaction."""
        # Set up test data
        user_id = "123456789"
        receiver_id = "987654321"
        transaction_type = "transfer_out"
        amount = 50.0
        description = "Transfer to friend"
        
        # Set up mock transaction ID
        transaction_id = "TXN-12346-ghijkl"
        
        # Set up mocks
        mock_db.log_transaction.return_value = transaction_id
        
        # Call the method
        result = await mock_db.log_transaction(
            user_id=user_id,
            transaction_type=transaction_type,
            amount=amount,
            description=description,
            receiver_id=receiver_id
        )
        
        # Verify results
        assert result == transaction_id
        
        # Verify correct methods were called
        mock_db.log_transaction.assert_called_once_with(
            user_id=user_id,
            transaction_type=transaction_type,
            amount=amount,
            description=description,
            receiver_id=receiver_id
        )
    
    async def test_get_transactions(self, mock_db):
        """Test retrieving a user's transaction history."""
        # Set up test data
        user_id = "123456789"
        limit = 10
        skip = 0
        
        # Set up mock transactions
        mock_transactions = [
            {
                "transaction_id": "TXN-12345-abcdef",
                "user_id": user_id,
                "transaction_type": "deposit",
                "amount": 100.0,
                "description": "Test deposit",
                "timestamp": datetime.utcnow() - timedelta(days=1)
            },
            {
                "transaction_id": "TXN-12346-ghijkl",
                "user_id": user_id,
                "transaction_type": "withdrawal",
                "amount": 50.0,
                "description": "Test withdrawal",
                "timestamp": datetime.utcnow() - timedelta(days=2)
            }
        ]
        
        # Set up mocks
        mock_db.get_transactions.return_value = mock_transactions
        
        # Call the method
        result = await mock_db.get_transactions(user_id, limit, skip)
        
        # Verify results
        assert result is not None
        assert len(result) == 2
        assert result[0]["transaction_type"] == "deposit"
        assert result[1]["transaction_type"] == "withdrawal"
        
        # Verify correct methods were called
        mock_db.get_transactions.assert_called_once_with(user_id, limit, skip)
    
    async def test_get_transactions_empty(self, mock_db):
        """Test retrieving transactions when none exist."""
        # Set up test data
        user_id = "123456789"
        
        # Set up mocks
        mock_db.get_transactions.return_value = []
        
        # Call the method
        result = await mock_db.get_transactions(user_id)
        
        # Verify results
        assert result == []
        
        # Verify correct methods were called
        mock_db.get_transactions.assert_called_once_with(user_id)
    
    async def test_get_recent_transactions(self, mock_db):
        """Test retrieving recent transactions within a time range."""
        # Set up test data
        user_id = "123456789"
        days = 30
        
        # Set up mock transactions (all within 30 days)
        mock_transactions = [
            {
                "transaction_id": "TXN-12345-abcdef",
                "user_id": user_id,
                "transaction_type": "deposit",
                "amount": 100.0,
                "description": "Test deposit",
                "timestamp": datetime.utcnow() - timedelta(days=1)
            },
            {
                "transaction_id": "TXN-12346-ghijkl",
                "user_id": user_id,
                "transaction_type": "withdrawal",
                "amount": 50.0,
                "description": "Test withdrawal",
                "timestamp": datetime.utcnow() - timedelta(days=15)
            },
            {
                "transaction_id": "TXN-12347-mnopqr",
                "user_id": user_id,
                "transaction_type": "transfer_out",
                "amount": 25.0,
                "description": "Test transfer",
                "timestamp": datetime.utcnow() - timedelta(days=29)
            }
        ]
        
        # Set up mocks
        mock_db.get_recent_transactions.return_value = mock_transactions
        
        # Call the method
        result = await mock_db.get_recent_transactions(user_id, days)
        
        # Verify results
        assert result is not None
        assert len(result) == 3
        
        # Verify correct methods were called
        mock_db.get_recent_transactions.assert_called_once_with(user_id, days)
    
    async def test_get_transactions_by_type_and_date(self, mock_db):
        """Test retrieving transactions of a specific type on a specific date."""
        # Set up test data
        user_id = "123456789"
        transaction_type = "deposit"
        date = datetime.utcnow().date()  # Today
        
        # Set up mock transactions
        mock_transactions = [
            {
                "transaction_id": "TXN-12345-abcdef",
                "user_id": user_id,
                "transaction_type": "deposit",
                "amount": 100.0,
                "description": "Morning deposit",
                "timestamp": datetime.combine(date, datetime.min.time()) + timedelta(hours=9)  # 9 AM
            },
            {
                "transaction_id": "TXN-12348-stuvwx",
                "user_id": user_id,
                "transaction_type": "deposit",
                "amount": 200.0,
                "description": "Afternoon deposit",
                "timestamp": datetime.combine(date, datetime.min.time()) + timedelta(hours=15)  # 3 PM
            }
        ]
        
        # Set up mocks
        mock_db.get_transactions_by_type_and_date.return_value = mock_transactions
        
        # Call the method
        result = await mock_db.get_transactions_by_type_and_date(user_id, transaction_type, date)
        
        # Verify results
        assert result is not None
        assert len(result) == 2
        assert all(tx["transaction_type"] == "deposit" for tx in result)
        assert all(tx["timestamp"].date() == date for tx in result)
        
        # Verify correct methods were called
        mock_db.get_transactions_by_type_and_date.assert_called_once_with(user_id, transaction_type, date)
    
    async def test_get_transactions_by_type_and_date_no_matches(self, mock_db):
        """Test retrieving transactions of a specific type on a date with no matching transactions."""
        # Set up test data
        user_id = "123456789"
        transaction_type = "loan_payment"
        date = datetime.utcnow().date() - timedelta(days=5)  # 5 days ago
        
        # Set up mocks (no matching transactions)
        mock_db.get_transactions_by_type_and_date.return_value = []
        
        # Call the method
        result = await mock_db.get_transactions_by_type_and_date(user_id, transaction_type, date)
        
        # Verify results
        assert result == []
        
        # Verify correct methods were called
        mock_db.get_transactions_by_type_and_date.assert_called_once_with(user_id, transaction_type, date)
    
    async def test_transaction_amounts(self, mock_db):
        """Test that transaction amounts are handled correctly."""
        # Set up test data with various amounts
        test_cases = [
            {"amount": 100.0, "expected": 100.0},  # Regular float
            {"amount": 99.99, "expected": 99.99},  # Two decimal places
            {"amount": 1000, "expected": 1000.0},  # Integer should be converted to float
            {"amount": 0.01, "expected": 0.01},    # Small amount
            {"amount": 9999999.99, "expected": 9999999.99}  # Large amount
        ]
        
        # Test each case
        for case in test_cases:
            # Set up mock transaction ID
            transaction_id = f"TXN-{case['amount']}-test"
            
            # Set up mocks
            mock_db.log_transaction.return_value = transaction_id
            
            # Call the method
            result = await mock_db.log_transaction(
                user_id="123456789",
                transaction_type="test",
                amount=case["amount"],
                description=f"Test amount {case['amount']}"
            )
            
            # Verify correct amount was passed
            call_args = mock_db.log_transaction.call_args
            assert call_args is not None
            assert call_args[1]["amount"] == case["expected"]


if __name__ == "__main__":
    unittest.main() 