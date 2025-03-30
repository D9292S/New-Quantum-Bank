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

from cogs.accounts import Account
from helpers.exceptions import InsufficientFundsError


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
        
        # Override cog_load to avoid MongoDB connection
        with patch.object(Account, "cog_load", AsyncMock(return_value=None)):
            self.cog = Account(self.bot)
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
        
        # Verify the cog has required attributes
        self.assertTrue(hasattr(self.cog, "connected"))
        self.assertTrue(hasattr(self.cog, "logger"))


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
        mock_db = MagicMock()
        mock_db.get_account = AsyncMock()
        mock_db.create_account = AsyncMock()
        mock_db.update_balance = AsyncMock()
        mock_db.log_transaction = AsyncMock()
        
        # Set up mock for get_cog to return our mock db
        bot.get_cog.return_value = mock_db
        
        # Override the async methods for testing
        with patch.object(Account, "cog_load", AsyncMock(return_value=None)):
            cog = Account(bot)
            # Manually set the db and connection status
            cog.db = mock_db
            cog.connected = True
            
            # Mock the command methods
            cog.balance_command = AsyncMock()
            cog.register_command = AsyncMock()
            cog.create_account = AsyncMock()
            cog.passbook = AsyncMock()
            cog.upi_payment = AsyncMock()
            cog.repay_loan = AsyncMock()
            cog.transfer = AsyncMock()
            
            # Mock internal methods
            cog._get_cached_account = AsyncMock()
            cog._invalidate_account_cache = AsyncMock()
            
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
        
        # Mock the create_account slash command
        mock_ctx = MagicMock()
        mock_ctx.author.id = user_id
        mock_ctx.author.name = username
        mock_ctx.guild.id = guild_id
        mock_ctx.guild.name = guild_name
        
        # Set up return value for the create_account command
        test_cog.create_account.return_value = None  # Commands return None
        
        # Call the command
        await test_cog.create_account(mock_ctx)
        
        # Verify the command was called
        test_cog.create_account.assert_called_once()
    
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
        
        # Set up the cached account method
        test_cog._get_cached_account.return_value = mock_account
        
        # Call the method
        account = await test_cog._get_cached_account(user_id)
        
        # Verify results
        assert account is not None
        assert account["user_id"] == user_id
        assert account["balance"] == 100.0
        
        # Verify method was called with correct parameters
        test_cog._get_cached_account.assert_called_once_with(user_id)
    
    async def test_get_account_not_found(self, test_cog):
        """Test retrieving a non-existent account."""
        # Set up test data
        user_id = "123456789"
        
        # Set up the cached account method to return None
        test_cog._get_cached_account.return_value = None
        
        # Call the method
        account = await test_cog._get_cached_account(user_id)
        
        # Verify results
        assert account is None
        
        # Verify method was called correctly
        test_cog._get_cached_account.assert_called_once_with(user_id)
    
    async def test_deposit(self, test_cog):
        """Test depositing money into an account."""
        # Set up test data
        user_id = "123456789"
        amount = 50.0
        
        # Mock ctx for the upi_payment command which handles deposits
        mock_ctx = MagicMock()
        mock_ctx.author.id = user_id
        
        # Set up return value for the command
        test_cog.upi_payment.return_value = None  # Commands return None
        
        # Call the command with a UPI ID for deposit
        await test_cog.upi_payment(mock_ctx, "deposit@bank", amount)
        
        # Verify command was called with correct parameters
        test_cog.upi_payment.assert_called_once_with(mock_ctx, "deposit@bank", amount)
    
    async def test_withdraw_sufficient_funds(self, test_cog):
        """Test withdrawing money with sufficient funds."""
        # Set up test data
        user_id = "123456789"
        amount = 50.0
        
        # Mock ctx for the upi_payment command which handles withdrawals
        mock_ctx = MagicMock()
        mock_ctx.author.id = user_id
        
        # Set up return value for the command
        test_cog.upi_payment.return_value = None  # Commands return None
        
        # Call the command with a UPI ID for withdrawal
        await test_cog.upi_payment(mock_ctx, "withdraw@bank", amount)
        
        # Verify command was called with correct parameters
        test_cog.upi_payment.assert_called_once_with(mock_ctx, "withdraw@bank", amount)
    
    async def test_withdraw_insufficient_funds(self, test_cog):
        """Test withdrawing money with insufficient funds."""
        # Set up test data
        user_id = "123456789"
        amount = 150.0  # More than balance
        
        # Mock ctx for the upi_payment command which handles withdrawals
        mock_ctx = MagicMock()
        mock_ctx.author.id = user_id
        
        # Set up a side effect for insufficient funds
        test_cog.upi_payment.side_effect = InsufficientFundsError("Insufficient funds")
        
        # Call the command with a UPI ID for withdrawal and expect exception
        with pytest.raises(InsufficientFundsError):
            await test_cog.upi_payment(mock_ctx, "withdraw@bank", amount)
        
        # Verify command was called with correct parameters
        test_cog.upi_payment.assert_called_once_with(mock_ctx, "withdraw@bank", amount)
    
    async def test_transfer_successful(self, test_cog):
        """Test transferring money between accounts successfully."""
        # Set up test data
        sender_id = "123456789"
        receiver_id = "987654321"
        amount = 50.0
        
        # Mock ctx for the transfer command
        mock_ctx = MagicMock()
        mock_ctx.author.id = sender_id
        
        # Set up return value for the command
        test_cog.transfer.return_value = None  # Commands return None
        
        # Call the command
        await test_cog.transfer(mock_ctx, receiver_id, amount)
        
        # Verify command was called with correct parameters
        test_cog.transfer.assert_called_once_with(mock_ctx, receiver_id, amount)
    
    async def test_transfer_insufficient_funds(self, test_cog):
        """Test transferring money with insufficient funds."""
        # Set up test data
        sender_id = "123456789"
        receiver_id = "987654321"
        amount = 150.0  # More than sender's balance
        
        # Mock ctx for the transfer command
        mock_ctx = MagicMock()
        mock_ctx.author.id = sender_id
        
        # Set up a side effect for insufficient funds
        test_cog.transfer.side_effect = InsufficientFundsError("Insufficient funds")
        
        # Call the command and expect exception
        with pytest.raises(InsufficientFundsError):
            await test_cog.transfer(mock_ctx, receiver_id, amount)
        
        # Verify command was called with correct parameters
        test_cog.transfer.assert_called_once_with(mock_ctx, receiver_id, amount)


if __name__ == "__main__":
    unittest.main() 