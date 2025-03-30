"""Unit tests for the accounts cog functionality."""

import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from cogs.accounts import BankAccounts


@pytest.mark.unit
@pytest.mark.accounts
class TestAccountsCog(unittest.TestCase):
    """Test cases for accounts cog functionality."""

    def setUp(self):
        """Set up test environment."""
        # Create a mock bot
        self.bot = MagicMock()
        self.bot.user = MagicMock()
        self.bot.user.id = 123456789
        self.bot.user.name = "TestBot"
        
        # Mock a database cog
        self.mock_db = MagicMock()
        self.bot.get_cog.return_value = self.mock_db
        
        # Create the cog with mocked dependencies
        with patch("cogs.accounts.BankAccounts._connect_to_mongodb", return_value=None):
            self.cog = BankAccounts(self.bot)
            self.cog.db = self.mock_db
            self.cog.connected = True
        
        # Set up test data
        self.test_user_id = "123456789"
        self.test_guild_id = "987654321"
        self.test_username = "TestUser"
        self.test_guild_name = "Test Guild"

    def test_init(self):
        """Test initialization of the accounts cog."""
        # Check that logger is set up
        self.assertTrue(hasattr(self.cog, "logger"))
        
        # Verify bot reference is correct
        self.assertEqual(self.cog.bot, self.bot)
        
        # Verify default values
        self.assertIsNotNone(self.cog.transaction_lock)


@pytest.mark.asyncio
@pytest.mark.accounts
class TestAccountsAsync:
    """Asynchronous tests for accounts cog."""
    
    @pytest.fixture
    async def test_cog(self):
        """Set up the accounts cog for testing."""
        bot = MagicMock()
        bot.user = MagicMock()
        bot.user.id = 123456789
        bot.user.name = "TestBot"
        
        # Create a mock database
        mock_db = AsyncMock()
        
        # Set up mock for get_cog to return our mock db
        bot.get_cog.return_value = mock_db
        
        # Override the connect method for testing
        with patch("cogs.accounts.BankAccounts._connect_to_mongodb", return_value=None):
            cog = BankAccounts(bot)
            cog.db = mock_db
            cog.connected = True
            
            # Setup common mock responses
            mock_db.get_account = AsyncMock()
            mock_db.create_account = AsyncMock()
            mock_db.update_balance = AsyncMock()
            mock_db.log_transaction = AsyncMock()
            
            return cog
    
    async def test_create_account(self, test_cog):
        """Test account creation."""
        # Set up test data
        user_id = "123456789"
        username = "TestUser"
        guild_id = "987654321"
        guild_name = "Test Guild"
        
        # Mock database response
        test_cog.db.get_account.return_value = None  # Account doesn't exist yet
        test_cog.db.create_account.return_value = {
            "user_id": user_id,
            "username": username,
            "guild_id": guild_id,
            "guild_name": guild_name,
            "balance": 0,
            "created_at": datetime.utcnow()
        }
        
        # Call the method
        account = await test_cog.create_account(user_id, username, guild_id, guild_name)
        
        # Verify results
        assert account is not None
        assert account["user_id"] == user_id
        assert account["username"] == username
        
        # Verify DB was called with correct parameters
        test_cog.db.get_account.assert_called_once_with(user_id, guild_id)
        test_cog.db.create_account.assert_called_once_with(
            user_id, username, guild_id, guild_name, initial_balance=0
        )
    
    async def test_get_account(self, test_cog):
        """Test retrieving an account."""
        # Set up test data
        user_id = "123456789"
        guild_id = "987654321"
        
        # Mock database response for existing account
        mock_account = {
            "user_id": user_id,
            "username": "TestUser",
            "guild_id": guild_id,
            "guild_name": "Test Guild",
            "balance": 100.0,
            "created_at": datetime.utcnow()
        }
        test_cog.db.get_account.return_value = mock_account
        
        # Call the method
        account = await test_cog.get_account(user_id, guild_id)
        
        # Verify results
        assert account is not None
        assert account["user_id"] == user_id
        assert account["balance"] == 100.0
        
        # Verify DB was called correctly
        test_cog.db.get_account.assert_called_once_with(user_id, guild_id)
    
    async def test_get_account_not_found(self, test_cog):
        """Test retrieving a non-existent account."""
        # Set up test data
        user_id = "123456789"
        guild_id = "987654321"
        
        # Mock database response for non-existent account
        test_cog.db.get_account.return_value = None
        
        # Call the method
        account = await test_cog.get_account(user_id, guild_id)
        
        # Verify results
        assert account is None
        
        # Verify DB was called correctly
        test_cog.db.get_account.assert_called_once_with(user_id, guild_id)
    
    async def test_deposit(self, test_cog):
        """Test depositing money into an account."""
        # Set up test data
        user_id = "123456789"
        guild_id = "987654321"
        amount = 50.0
        
        # Mock account existence
        mock_account = {
            "user_id": user_id,
            "username": "TestUser",
            "guild_id": guild_id,
            "guild_name": "Test Guild",
            "balance": 100.0,
            "created_at": datetime.utcnow()
        }
        test_cog.db.get_account.return_value = mock_account
        test_cog.db.update_balance.return_value = True
        
        # Call the method
        result = await test_cog.deposit(user_id, guild_id, amount)
        
        # Verify results
        assert result is True
        
        # Verify DB calls
        test_cog.db.get_account.assert_called_once_with(user_id, guild_id)
        test_cog.db.update_balance.assert_called_once_with(
            user_id, guild_id, amount, "deposit", reason="User deposit"
        )
    
    async def test_withdraw_sufficient_funds(self, test_cog):
        """Test withdrawing money with sufficient funds."""
        # Set up test data
        user_id = "123456789"
        guild_id = "987654321"
        amount = 50.0
        
        # Mock account with sufficient balance
        mock_account = {
            "user_id": user_id,
            "username": "TestUser",
            "guild_id": guild_id,
            "guild_name": "Test Guild",
            "balance": 100.0,
            "created_at": datetime.utcnow()
        }
        test_cog.db.get_account.return_value = mock_account
        test_cog.db.update_balance.return_value = True
        
        # Call the method
        result = await test_cog.withdraw(user_id, guild_id, amount)
        
        # Verify results
        assert result is True
        
        # Verify DB calls
        test_cog.db.get_account.assert_called_once_with(user_id, guild_id)
        test_cog.db.update_balance.assert_called_once_with(
            user_id, guild_id, -amount, "withdrawal", reason="User withdrawal"
        )
    
    async def test_withdraw_insufficient_funds(self, test_cog):
        """Test withdrawing money with insufficient funds."""
        # Set up test data
        user_id = "123456789"
        guild_id = "987654321"
        amount = 150.0  # More than balance
        
        # Mock account with insufficient balance
        mock_account = {
            "user_id": user_id,
            "username": "TestUser",
            "guild_id": guild_id,
            "guild_name": "Test Guild",
            "balance": 100.0,
            "created_at": datetime.utcnow()
        }
        test_cog.db.get_account.return_value = mock_account
        
        # Call the method
        result = await test_cog.withdraw(user_id, guild_id, amount)
        
        # Verify results
        assert result is False
        
        # Verify DB calls
        test_cog.db.get_account.assert_called_once_with(user_id, guild_id)
        # update_balance should not be called
        test_cog.db.update_balance.assert_not_called()
    
    async def test_transfer_successful(self, test_cog):
        """Test transferring money between accounts successfully."""
        # Set up test data
        sender_id = "123456789"
        receiver_id = "987654321"
        guild_id = "111222333"
        amount = 50.0
        
        # Mock sender account with sufficient balance
        sender_account = {
            "user_id": sender_id,
            "username": "SenderUser",
            "guild_id": guild_id,
            "guild_name": "Test Guild",
            "balance": 100.0,
            "created_at": datetime.utcnow()
        }
        
        # Mock receiver account
        receiver_account = {
            "user_id": receiver_id,
            "username": "ReceiverUser",
            "guild_id": guild_id,
            "guild_name": "Test Guild",
            "balance": 50.0,
            "created_at": datetime.utcnow()
        }
        
        # Setup mocks
        async def get_account_mock(user_id, guild_id):
            if user_id == sender_id:
                return sender_account
            elif user_id == receiver_id:
                return receiver_account
            return None
        
        test_cog.db.get_account = AsyncMock(side_effect=get_account_mock)
        test_cog.db.update_balance.return_value = True
        
        # Call the method
        result = await test_cog.transfer(sender_id, receiver_id, guild_id, amount)
        
        # Verify results
        assert result is True
        
        # Verify DB calls - should be called twice for sender and receiver
        assert test_cog.db.get_account.call_count == 2
        
        # Check that update_balance was called correctly for both accounts
        assert test_cog.db.update_balance.call_count == 2
        
        # First call should be withdrawal from sender
        withdrawal_call = test_cog.db.update_balance.call_args_list[0]
        assert withdrawal_call[0][0] == sender_id
        assert withdrawal_call[0][1] == guild_id
        assert withdrawal_call[0][2] == -amount
        assert withdrawal_call[0][3] == "transfer_out"
        
        # Second call should be deposit to receiver
        deposit_call = test_cog.db.update_balance.call_args_list[1]
        assert deposit_call[0][0] == receiver_id
        assert deposit_call[0][1] == guild_id
        assert deposit_call[0][2] == amount
        assert deposit_call[0][3] == "transfer_in"

    async def test_transfer_insufficient_funds(self, test_cog):
        """Test transferring money with insufficient funds."""
        # Set up test data
        sender_id = "123456789"
        receiver_id = "987654321"
        guild_id = "111222333"
        amount = 150.0  # More than sender's balance
        
        # Mock sender account with insufficient balance
        sender_account = {
            "user_id": sender_id,
            "username": "SenderUser",
            "guild_id": guild_id,
            "guild_name": "Test Guild",
            "balance": 100.0,
            "created_at": datetime.utcnow()
        }
        
        # Mock receiver account
        receiver_account = {
            "user_id": receiver_id,
            "username": "ReceiverUser",
            "guild_id": guild_id,
            "guild_name": "Test Guild",
            "balance": 50.0,
            "created_at": datetime.utcnow()
        }
        
        # Setup mocks
        async def get_account_mock(user_id, guild_id):
            if user_id == sender_id:
                return sender_account
            elif user_id == receiver_id:
                return receiver_account
            return None
        
        test_cog.db.get_account = AsyncMock(side_effect=get_account_mock)
        
        # Call the method
        result = await test_cog.transfer(sender_id, receiver_id, guild_id, amount)
        
        # Verify results
        assert result is False
        
        # Verify DB calls - should check sender's account
        test_cog.db.get_account.assert_called_once_with(sender_id, guild_id)
        
        # update_balance should not be called at all
        test_cog.db.update_balance.assert_not_called()


if __name__ == "__main__":
    unittest.main() 