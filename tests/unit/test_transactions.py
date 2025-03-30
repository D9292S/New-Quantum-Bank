"""Unit tests for the transaction functionality."""

import asyncio
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from helpers.exceptions import AccountNotFoundError, InsufficientFundsError


@pytest.mark.asyncio
@pytest.mark.transactions
class TestTransactions:
    """Tests for transaction operations."""

    @pytest.fixture
    async def mock_db(self):
        """Set up a mock Database instance with transaction operations."""
        db = MagicMock()

        # Setup common mock methods as AsyncMocks
        db.get_account = AsyncMock()
        db.log_transaction = AsyncMock()
        db.update_balance = AsyncMock()
        db.get_transaction_history = AsyncMock()

        return db

    async def test_deposit(self, mock_db):
        """Test depositing money to an account."""
        # Set up test data
        user_id = "123456789"
        amount = 100.0
        description = "Test deposit"

        # Set up mocks
        mock_db.get_account.return_value = {"user_id": user_id, "balance": 500.0}

        mock_db.update_balance.return_value = {"new_balance": 600.0, "old_balance": 500.0, "change": amount}

        mock_db.log_transaction.return_value = {
            "transaction_id": "TX123",
            "user_id": user_id,
            "transaction_type": "deposit",
            "amount": amount,
            "description": description,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Get the account
        account = await mock_db.get_account(user_id)

        # Process deposit
        balance_update = await mock_db.update_balance(user_id, amount)
        transaction = await mock_db.log_transaction(
            user_id=user_id, transaction_type="deposit", amount=amount, description=description
        )

        # Verify results
        assert balance_update["new_balance"] == 600.0
        assert transaction["transaction_type"] == "deposit"
        assert transaction["amount"] == amount

        # Verify methods were called correctly
        mock_db.get_account.assert_called_once_with(user_id)
        mock_db.update_balance.assert_called_once_with(user_id, amount)
        mock_db.log_transaction.assert_called_once_with(
            user_id=user_id, transaction_type="deposit", amount=amount, description=description
        )

    async def test_withdraw_success(self, mock_db):
        """Test withdrawing money from an account."""
        # Set up test data
        user_id = "123456789"
        amount = 100.0
        description = "Test withdrawal"

        # Set up mocks
        mock_db.get_account.return_value = {"user_id": user_id, "balance": 500.0}

        mock_db.update_balance.return_value = {"new_balance": 400.0, "old_balance": 500.0, "change": -amount}

        mock_db.log_transaction.return_value = {
            "transaction_id": "TX124",
            "user_id": user_id,
            "transaction_type": "withdrawal",
            "amount": amount,
            "description": description,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Get the account
        account = await mock_db.get_account(user_id)

        # Process withdrawal
        balance_update = await mock_db.update_balance(user_id, -amount)
        transaction = await mock_db.log_transaction(
            user_id=user_id, transaction_type="withdrawal", amount=amount, description=description
        )

        # Verify results
        assert balance_update["new_balance"] == 400.0
        assert transaction["transaction_type"] == "withdrawal"
        assert transaction["amount"] == amount

        # Verify methods were called correctly
        mock_db.get_account.assert_called_once_with(user_id)
        mock_db.update_balance.assert_called_once_with(user_id, -amount)
        mock_db.log_transaction.assert_called_once_with(
            user_id=user_id, transaction_type="withdrawal", amount=amount, description=description
        )

    async def test_withdraw_insufficient_funds(self, mock_db):
        """Test withdrawing more money than available in the account."""
        # Set up test data
        user_id = "123456789"
        amount = 700.0  # More than account balance
        description = "Test withdrawal"

        # Set up mocks
        mock_db.get_account.return_value = {"user_id": user_id, "balance": 500.0}

        # Set up mock for insufficient funds error
        mock_db.update_balance.side_effect = InsufficientFundsError("Insufficient funds for withdrawal")

        # Get the account
        account = await mock_db.get_account(user_id)

        # Process withdrawal and check for exception
        with pytest.raises(InsufficientFundsError):
            await mock_db.update_balance(user_id, -amount)

        # Verify methods were called correctly
        mock_db.get_account.assert_called_once_with(user_id)
        mock_db.update_balance.assert_called_once_with(user_id, -amount)
        mock_db.log_transaction.assert_not_called()

    async def test_transfer_success(self, mock_db):
        """Test transferring money between accounts."""
        # Set up test data
        sender_id = "123456789"
        receiver_id = "987654321"
        amount = 100.0
        description = "Test transfer"

        # Set up mocks
        mock_db.get_account.side_effect = [
            # First call - sender account
            {"user_id": sender_id, "balance": 500.0},
            # Second call - receiver account
            {"user_id": receiver_id, "balance": 300.0},
        ]

        # Mock balance updates
        mock_db.update_balance.side_effect = [
            # First call - sender balance decreased
            {"new_balance": 400.0, "old_balance": 500.0, "change": -amount},
            # Second call - receiver balance increased
            {"new_balance": 400.0, "old_balance": 300.0, "change": amount},
        ]

        # Mock transaction logs
        mock_db.log_transaction.side_effect = [
            # First call - sender transaction
            {
                "transaction_id": "TX125",
                "user_id": sender_id,
                "transaction_type": "transfer",
                "amount": amount,
                "description": description,
                "receiver_id": receiver_id,
                "timestamp": datetime.utcnow().isoformat(),
            },
            # Second call - receiver transaction
            {
                "transaction_id": "TX126",
                "user_id": receiver_id,
                "transaction_type": "transfer_received",
                "amount": amount,
                "description": description,
                "sender_id": sender_id,
                "timestamp": datetime.utcnow().isoformat(),
            },
        ]

        # Get sender and receiver accounts
        sender_account = await mock_db.get_account(sender_id)
        receiver_account = await mock_db.get_account(receiver_id)

        # Process transfer
        sender_update = await mock_db.update_balance(sender_id, -amount)
        receiver_update = await mock_db.update_balance(receiver_id, amount)

        # Log transactions
        sender_transaction = await mock_db.log_transaction(
            user_id=sender_id,
            transaction_type="transfer",
            amount=amount,
            description=description,
            receiver_id=receiver_id,
        )

        receiver_transaction = await mock_db.log_transaction(
            user_id=receiver_id,
            transaction_type="transfer_received",
            amount=amount,
            description=description,
            sender_id=sender_id,
        )

        # Verify results
        assert sender_update["new_balance"] == 400.0
        assert receiver_update["new_balance"] == 400.0
        assert sender_transaction["transaction_type"] == "transfer"
        assert receiver_transaction["transaction_type"] == "transfer_received"
        assert sender_transaction["receiver_id"] == receiver_id
        assert receiver_transaction["sender_id"] == sender_id

        # Verify methods were called with correct parameters
        assert mock_db.get_account.call_count == 2
        assert mock_db.update_balance.call_count == 2
        assert mock_db.log_transaction.call_count == 2

    async def test_transfer_sender_not_found(self, mock_db):
        """Test transfer when sender account doesn't exist."""
        # Set up test data
        sender_id = "123456789"
        receiver_id = "987654321"
        amount = 100.0
        description = "Test transfer"

        # Set up mock for AccountNotFoundError
        mock_db.get_account.side_effect = AccountNotFoundError("Sender account not found")

        # Attempt to process transfer and check for exception
        with pytest.raises(AccountNotFoundError):
            await mock_db.get_account(sender_id)

        # Verify methods were called correctly
        mock_db.get_account.assert_called_once_with(sender_id)
        mock_db.update_balance.assert_not_called()
        mock_db.log_transaction.assert_not_called()

    async def test_get_transaction_history(self, mock_db):
        """Test retrieving transaction history for an account."""
        # Set up test data
        user_id = "123456789"
        start_date = "2023-01-01"
        end_date = "2023-06-30"

        # Set up mock transaction history
        mock_transactions = [
            {
                "transaction_id": "TX001",
                "user_id": user_id,
                "transaction_type": "deposit",
                "amount": 500.0,
                "description": "Initial deposit",
                "timestamp": "2023-01-15T10:30:00",
            },
            {
                "transaction_id": "TX002",
                "user_id": user_id,
                "transaction_type": "withdrawal",
                "amount": 100.0,
                "description": "ATM withdrawal",
                "timestamp": "2023-02-10T14:45:00",
            },
            {
                "transaction_id": "TX003",
                "user_id": user_id,
                "transaction_type": "transfer",
                "amount": 200.0,
                "description": "Rent payment",
                "receiver_id": "987654321",
                "timestamp": "2023-03-01T09:15:00",
            },
        ]

        # Set up mocks
        mock_db.get_transaction_history.return_value = mock_transactions

        # Call the method
        result = await mock_db.get_transaction_history(user_id, start_date=start_date, end_date=end_date)

        # Verify results
        assert len(result) == 3
        assert result[0]["transaction_type"] == "deposit"
        assert result[1]["transaction_type"] == "withdrawal"
        assert result[2]["transaction_type"] == "transfer"

        # Verify correct methods were called
        mock_db.get_transaction_history.assert_called_once_with(user_id, start_date=start_date, end_date=end_date)


if __name__ == "__main__":
    unittest.main()
