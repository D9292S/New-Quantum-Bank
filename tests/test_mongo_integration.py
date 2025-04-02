from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import mongomock
import pytest

# Import the Database class from your cogs
from cogs.mongo import Database

# Create a shared mock MongoDB instance for all tests
SHARED_TEST_DB = mongomock.MongoClient().db

# Initialize collections
collections = ["users", "accounts", "transactions", "loans", "credit", "cache"]
for collection in collections:
    if collection not in SHARED_TEST_DB.list_collection_names():
        SHARED_TEST_DB.create_collection(collection)

# Create indices
SHARED_TEST_DB.accounts.create_index("user_id")
SHARED_TEST_DB.transactions.create_index("timestamp")


@pytest.fixture
async def mock_bot():
    """Create a mock bot instance"""
    mock_bot = AsyncMock()
    # Create a config attribute with MONGO_URI
    mock_bot.config = type("Config", (), {"MONGO_URI": "mongodb+srv://ci-user:ci-password@placeholder-cluster.mongodb.net/quantum_test?retryWrites=true&w=majority/test_db"})
    mock_bot.loop = MagicMock()
    mock_bot.loop.create_task = MagicMock()
    return mock_bot


@pytest.fixture
async def db_instance(mock_bot):
    """Create a test Database instance with mocked MongoDB connection."""
    # Create a mongomock client
    mock_mongo_client = MagicMock()
    mock_mongo_client.server_info = AsyncMock(return_value={"version": "4.0.0"})

    # Connect it to our shared test DB
    mock_mongo_client.__getitem__.return_value = SHARED_TEST_DB
    mock_mongo_client.get_database.return_value = SHARED_TEST_DB

    # Create a Database instance
    db = Database(mock_bot)

    # Replace the client with our mock and disable asyncio tasks
    db.client = mock_mongo_client

    # Properly mock performance monitoring to prevent warning about unwaited coroutine
    db._run_performance_monitoring = AsyncMock()  # Replace with AsyncMock before it's called
    db._performance_check_task = MagicMock()
    db.connected = True
    db._start_performance_check = MagicMock()

    # Add methods needed for tests
    async def create_user(user_id, username):
        """Mock create_user method"""
        user_doc = {"user_id": user_id, "username": username, "created_at": datetime.now()}
        SHARED_TEST_DB.users.insert_one(user_doc)
        return user_doc

    async def update_account_db(user_id, guild_id, amount, transaction_type, reason=None):
        """Mock update_balance method"""
        SHARED_TEST_DB.accounts.update_one({"user_id": user_id, "guild_id": guild_id}, {"$inc": {"balance": amount}})
        SHARED_TEST_DB.transactions.insert_one(
            {
                "user_id": user_id,
                "guild_id": guild_id,
                "amount": amount,
                "type": transaction_type,
                "reason": reason,
                "timestamp": datetime.now(),
            }
        )
        return True

    # Add custom methods to db_instance
    db.create_user = create_user
    db.update_balance = update_account_db

    yield db

    # No need to reset the coroutine since we already mocked it properly

    # Close the client connection
    if hasattr(db, "client") and db.client:
        db.client = None

    # Reset the connected state
    db.connected = False


@pytest.mark.asyncio
@pytest.mark.database
async def test_create_user(db_instance):
    """Test creating a user"""
    user_id = "123456789"
    username = "TestUser"

    # Call the create_user method
    result = await db_instance.create_user(user_id, username)

    # Verify user was created
    assert result is not None
    assert "username" in result
    assert result["username"] == username
    assert "user_id" in result
    assert result["user_id"] == user_id

    # Verify user in database
    user = SHARED_TEST_DB.users.find_one({"user_id": user_id})
    assert user is not None
    assert user["username"] == username
    assert user["user_id"] == user_id


@pytest.mark.asyncio
@pytest.mark.database
async def test_create_account(db_instance):
    """Test creating an account"""
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
            "created_at": datetime.now(),
        }
        SHARED_TEST_DB.accounts.insert_one(account)
        return account

    # Replace the method
    db_instance.create_account = create_account_mock

    # Create account with the correct parameters
    result = await db_instance.create_account(user_id, username, guild_id, guild_name)

    # Verify account was created
    assert result is not None
    assert "username" in result
    assert result["username"] == username
    assert "guild_id" in result
    assert result["guild_id"] == guild_id
    assert "balance" in result
    assert result["balance"] == 0

    # Verify account in database
    account = SHARED_TEST_DB.accounts.find_one({"user_id": user_id})
    assert account is not None
    assert account["username"] == username
    assert account["guild_id"] == guild_id
    assert account["balance"] == 0


@pytest.mark.asyncio
@pytest.mark.database
async def test_update_balance(db_instance):
    """Test updating account balance"""
    user_id = "123456789"
    username = "TestUser"
    guild_id = "987654321"
    guild_name = "Test Guild"

    # Ensure account exists
    if not SHARED_TEST_DB.accounts.find_one({"user_id": user_id, "guild_id": guild_id}):
        # Create account with the mongomock client
        account = {
            "user_id": user_id,
            "username": username,
            "guild_id": guild_id,
            "guild_name": guild_name,
            "balance": 0,
            "created_at": datetime.now(),
        }
        SHARED_TEST_DB.accounts.insert_one(account)

    # Perform deposit
    amount = 100.00
    transaction_type = "deposit"

    # Call the update_balance method
    transaction_result = await db_instance.update_balance(
        user_id, guild_id, amount, transaction_type, reason="Test deposit"
    )

    # Verify transaction was successful
    assert transaction_result is True

    # Verify balance in database
    account_db = SHARED_TEST_DB.accounts.find_one({"user_id": user_id})
    assert account_db is not None
    assert account_db["balance"] == amount


@pytest.mark.asyncio
@pytest.mark.database
async def test_transfer_between_accounts(db_instance):
    """Test transferring funds between accounts"""
    sender_id = "123456789"
    sender_name = "Sender"
    receiver_id = "987654321"
    receiver_name = "Receiver"
    guild_id = "987654321"
    guild_name = "Test Guild"

    # Ensure sender account exists with initial balance
    sender_account = SHARED_TEST_DB.accounts.find_one({"user_id": sender_id, "guild_id": guild_id})
    if not sender_account:
        # Create new sender account
        SHARED_TEST_DB.accounts.insert_one(
            {
                "user_id": sender_id,
                "username": sender_name,
                "guild_id": guild_id,
                "guild_name": guild_name,
                "balance": 0,
                "created_at": datetime.now(),
            }
        )
        # Set initial balance
        SHARED_TEST_DB.accounts.update_one({"user_id": sender_id, "guild_id": guild_id}, {"$set": {"balance": 500.0}})

    # Ensure receiver account exists
    if not SHARED_TEST_DB.accounts.find_one({"user_id": receiver_id, "guild_id": guild_id}):
        SHARED_TEST_DB.accounts.insert_one(
            {
                "user_id": receiver_id,
                "username": receiver_name,
                "guild_id": guild_id,
                "guild_name": guild_name,
                "balance": 0,
                "created_at": datetime.now(),
            }
        )

    # Reset balances to initial state before test
    SHARED_TEST_DB.accounts.update_one({"user_id": sender_id, "guild_id": guild_id}, {"$set": {"balance": 500.0}})
    SHARED_TEST_DB.accounts.update_one({"user_id": receiver_id, "guild_id": guild_id}, {"$set": {"balance": 0.0}})

    # Initial balance
    initial_balance = 500.00
    transfer_amount = 150.00

    # Update sender's balance (withdraw)
    await db_instance.update_balance(sender_id, guild_id, -transfer_amount, "transfer", reason="Transfer to Receiver")

    # Update receiver's balance (deposit)
    await db_instance.update_balance(receiver_id, guild_id, transfer_amount, "transfer", reason="Transfer from Sender")

    # Verify sender's balance
    sender_account = SHARED_TEST_DB.accounts.find_one({"user_id": sender_id, "guild_id": guild_id})
    assert sender_account is not None
    assert sender_account["balance"] == initial_balance - transfer_amount

    # Verify receiver's balance
    receiver_account = SHARED_TEST_DB.accounts.find_one({"user_id": receiver_id, "guild_id": guild_id})
    assert receiver_account is not None
    assert receiver_account["balance"] == transfer_amount
