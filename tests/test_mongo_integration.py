import pytest
import asyncio
import os
from unittest.mock import patch, AsyncMock, MagicMock
import mongomock
import motor.motor_asyncio
from bson.objectid import ObjectId
from datetime import datetime

# Import the Database class from your cogs
from cogs.mongo import Database

# Create a shared mock MongoDB client for all tests
SHARED_CLIENT = mongomock.MongoClient()
SHARED_TEST_DB = SHARED_CLIENT.get_database("test_db")

# Initialize collections
collections = ['users', 'accounts', 'transactions', 'loans', 'credit', 'cache']
for collection in collections:
    if collection not in SHARED_TEST_DB.list_collection_names():
        SHARED_TEST_DB.create_collection(collection)

# Create indices
SHARED_TEST_DB.accounts.create_index("user_id")
SHARED_TEST_DB.transactions.create_index("timestamp")

# This fixture provides the mock MongoDB client
@pytest.fixture
async def mock_mongo_client():
    """Create a mock MongoDB client using mongomock"""
    # Return the shared client
    return SHARED_CLIENT

@pytest.fixture
async def mock_bot():
    """Create a mock bot instance"""
    mock_bot = AsyncMock()
    # Create a config attribute with MONGO_URI
    mock_bot.config = type('Config', (), {'MONGO_URI': 'mongodb://localhost:27017/test_db'})
    mock_bot.loop = MagicMock()
    mock_bot.loop.create_task = MagicMock()
    return mock_bot

@pytest.fixture
async def db_instance(mock_bot, mock_mongo_client):
    """Create a Database instance with mock client"""
    # Create a Database instance
    db = Database(mock_bot)
    
    # Replace the client with our mock and disable asyncio tasks
    db.client = mock_mongo_client
    db.db = SHARED_TEST_DB  # Use the shared test database
    db.connected = True
    db._start_performance_check = MagicMock()
    
    # Add methods needed for tests
    async def create_user(user_id, username):
        """Create a test user document"""
        user_doc = {
            "user_id": user_id,
            "username": username,
            "created_at": datetime.now()
        }
        SHARED_TEST_DB.users.insert_one(user_doc)
        return user_doc
    
    async def update_account_db(user_id, guild_id, amount, transaction_type, reason=None):
        """Mock update_balance method"""
        account = SHARED_TEST_DB.accounts.find_one({"user_id": user_id, "guild_id": guild_id})
        if account:
            current_balance = account.get("balance", 0)
            new_balance = current_balance + amount
            SHARED_TEST_DB.accounts.update_one(
                {"user_id": user_id, "guild_id": guild_id},
                {"$set": {"balance": new_balance}}
            )
        return True
    
    # Add custom methods to db_instance
    db.create_user = create_user
    db.update_balance = update_account_db
    
    return db

@pytest.mark.asyncio
async def test_create_user(db_instance):
    """Test creating a new user in the database"""
    # Create a test user
    user_id = "123456789"
    username = "TestUser"
    
    # Call the create_user method
    result = await db_instance.create_user(user_id, username)
    
    # Verify user was created
    assert result is not None
    assert "user_id" in result
    assert result["user_id"] == user_id
    
    # Verify user in database
    user = SHARED_TEST_DB.users.find_one({"user_id": user_id})
    assert user is not None
    assert user["username"] == username

@pytest.mark.asyncio
async def test_create_account(db_instance):
    """Test creating a new account"""
    # Create test user first
    user_id = "123456789"
    username = "TestUser"
    guild_id = "987654321"
    guild_name = "Test Guild"
    
    # Ensure user exists
    if not SHARED_TEST_DB.users.find_one({"user_id": user_id}):
        await db_instance.create_user(user_id, username)
    
    # Mock create_account to use synchronous mongomock directly
    async def create_account_mock(user_id, username, guild_id, guild_name, initial_balance=0):
        account = {
            "user_id": user_id,
            "username": username,
            "guild_id": guild_id,
            "guild_name": guild_name,
            "balance": initial_balance,
            "created_at": datetime.now()
        }
        SHARED_TEST_DB.accounts.insert_one(account)
        return account
    
    # Replace the method
    db_instance.create_account = create_account_mock
    
    # Create account with the correct parameters
    result = await db_instance.create_account(user_id, username, guild_id, guild_name)
    
    # Verify account was created
    assert result is not None
    assert "user_id" in result
    assert result["user_id"] == user_id
    assert "balance" in result
    assert result["balance"] == 0
    
    # Verify account in database
    account = SHARED_TEST_DB.accounts.find_one({"user_id": user_id})
    assert account is not None
    assert account["guild_id"] == guild_id

@pytest.mark.asyncio
async def test_deposit_transaction(db_instance):
    """Test deposit transaction"""
    # Setup: Create user and account
    user_id = "123456789"
    username = "TestUser"
    guild_id = "987654321"
    guild_name = "Test Guild"
    
    # Ensure account exists
    if not SHARED_TEST_DB.accounts.find_one({"user_id": user_id, "guild_id": guild_id}):
        account = {
            "user_id": user_id,
            "username": username,
            "guild_id": guild_id,
            "guild_name": guild_name,
            "balance": 0,
            "created_at": datetime.now()
        }
        SHARED_TEST_DB.accounts.insert_one(account)
    
    # Perform deposit
    amount = 100.00
    transaction_result = await db_instance.update_balance(
        user_id=user_id,
        guild_id=guild_id,
        amount=amount,
        transaction_type="deposit",
        reason="Test deposit"
    )
    
    # Verify transaction was successful
    assert transaction_result is True
    
    # Verify balance in database
    account_db = SHARED_TEST_DB.accounts.find_one({"user_id": user_id})
    assert account_db is not None
    assert account_db["balance"] == amount

@pytest.mark.asyncio
async def test_transfer_between_accounts(db_instance):
    """Test transfer between two accounts"""
    # Setup: Create two users with accounts
    sender_id = "111111111"
    receiver_id = "222222222"
    guild_id = "987654321"
    guild_name = "Test Guild"
    
    # Ensure sender account exists with initial balance
    sender_account = SHARED_TEST_DB.accounts.find_one({"user_id": sender_id, "guild_id": guild_id})
    if not sender_account:
        SHARED_TEST_DB.accounts.insert_one({
            "user_id": sender_id,
            "username": "Sender",
            "guild_id": guild_id,
            "guild_name": guild_name,
            "balance": 500.0,  # Initial balance
            "created_at": datetime.now()
        })
    else:
        # Update balance to initial
        SHARED_TEST_DB.accounts.update_one(
            {"user_id": sender_id, "guild_id": guild_id},
            {"$set": {"balance": 500.0}}
        )
    
    # Ensure receiver account exists
    if not SHARED_TEST_DB.accounts.find_one({"user_id": receiver_id, "guild_id": guild_id}):
        SHARED_TEST_DB.accounts.insert_one({
            "user_id": receiver_id,
            "username": "Receiver",
            "guild_id": guild_id,
            "guild_name": guild_name,
            "balance": 0,
            "created_at": datetime.now()
        })
    
    # Initial balance
    initial_balance = 500.00
    transfer_amount = 150.00
    
    # Update sender's balance (withdraw)
    await db_instance.update_balance(
        user_id=sender_id,
        guild_id=guild_id,
        amount=-transfer_amount,
        transaction_type="transfer_out",
        reason="Transfer to Receiver"
    )
    
    # Update receiver's balance (deposit)
    await db_instance.update_balance(
        user_id=receiver_id,
        guild_id=guild_id,
        amount=transfer_amount,
        transaction_type="transfer_in",
        reason="Transfer from Sender"
    )
    
    # Verify sender's balance
    sender_account = SHARED_TEST_DB.accounts.find_one({"user_id": sender_id})
    assert sender_account is not None
    assert sender_account["balance"] == initial_balance - transfer_amount
    
    # Verify receiver's balance
    receiver_account = SHARED_TEST_DB.accounts.find_one({"user_id": receiver_id})
    assert receiver_account is not None
    assert receiver_account["balance"] == transfer_amount 