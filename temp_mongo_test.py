import asyncio
import os
import logging
import traceback
import time
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure, ConnectionFailure
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('mongodb_test')

class DatabaseTester:
    def __init__(self, mongo_uri):
        self.mongo_uri = mongo_uri
        self.client = None
        self.db = None
        self.connected = False
        self.max_retries = 5
        self.retry_delay = 2
        
    async def initialize_client(self):
        """Initialize the MongoDB client like the bot does"""
        print("Initializing MongoDB client...")
        
        try:
            # Create client with bot-like settings
            self.client = AsyncIOMotorClient(
                self.mongo_uri,
                maxPoolSize=10,
                minPoolSize=2,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                socketTimeoutMS=20000,
                retryWrites=True,
                retryReads=True,
                w="majority"
            )
            
            # Get database name from URI or use default
            db_name = 'banking_bot'
            
            # Initialize the db with get_database
            self.db = self.client.get_database(db_name)
            
            print(f"MongoDB client initialized with database: {db_name}")
            return True
        except Exception as e:
            print(f"Failed to initialize MongoDB client: {str(e)}")
            self.client = None
            self.db = None
            return False
    
    async def test_connection(self):
        """Test the MongoDB connection exactly like the bot does"""
        retry_count = 0
        max_retries = self.max_retries
        delay = self.retry_delay
        
        # Print URI details for debugging (without exposing credentials)
        uri_parts = self.mongo_uri.split('@')
        safe_uri = uri_parts[-1] if len(uri_parts) > 1 else self.mongo_uri.split('://')[-1]
        print(f"Testing connection to MongoDB at {safe_uri}")
        
        while retry_count <= max_retries:
            try:
                start_time = time.time()
                # Try to ping the database
                print(f"Connection attempt {retry_count+1}/{max_retries+1} to MongoDB")
                
                # Simplest possible check - just ping
                await self.client.admin.command('ping')
                self.connected = True
                print(f"Successfully connected to MongoDB in {(time.time() - start_time)*1000:.2f}ms")
                
                # Get and print server info for debugging
                server_info = await self.client.admin.command("serverStatus")
                version = server_info.get("version", "unknown")
                uptime_hours = round(server_info.get("uptime", 0) / 3600, 1)
                connections = server_info.get("connections", {})
                current_connections = connections.get("current", 0)
                available_connections = connections.get("available", 0)
                
                print(f"MongoDB version {version} (uptime: {uptime_hours} hours)")
                print(f"MongoDB connections: {current_connections} active, {available_connections} available")
                
                # List databases for further debugging
                print("Available databases:")
                dbs = await self.client.list_database_names()
                for db in dbs:
                    print(f"  - {db}")
                
                return True
            except Exception as e:
                retry_count += 1
                
                # Log detailed error info
                print(f"MongoDB Error: {str(e)}")
                print(f"Error type: {type(e).__name__}")
                print(f"Stack trace: {traceback.format_exc()}")
                
                # Try to get more server details if possible
                try:
                    client_proxy = AsyncIOMotorClient(
                        self.mongo_uri, 
                        serverSelectionTimeoutMS=2000
                    )
                    info = await client_proxy.admin.command('isMaster')
                    print(f"isMaster info: {info}")
                except Exception as inner_e:
                    print(f"Failed to get isMaster info: {str(inner_e)}")
                
                if retry_count <= max_retries:
                    wait_time = delay * retry_count
                    print(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"Failed to connect to MongoDB after {max_retries} attempts")
                    break
        
        # Set connected to false
        self.connected = False
        return False

    async def check_collections(self):
        """Check existence of collections"""
        if not self.connected or self.db is None:
            print("Not connected to database, cannot check collections")
            return False
            
        try:
            # Define required collections
            required_collections = [
                'accounts', 'transactions', 'settings', 'performance_metrics',
                'credit_scores', 'loans', 'kyc_records', 'admin'
            ]
            
            # List existing collections
            existing = await self.db.list_collection_names()
            print(f"Existing collections: {existing}")
            
            # Check each required collection
            for collection in required_collections:
                if collection not in existing:
                    print(f"Creating collection: {collection}")
                    await self.db.create_collection(collection)
                else:
                    print(f"Collection exists: {collection}")
                    
            return True
        except Exception as e:
            print(f"Error checking/creating collections: {str(e)}")
            return False

    async def test_writes(self):
        """Test if we can write to collections"""
        if not self.connected or self.db is None:
            print("Not connected to database, cannot test writes")
            return False
        
        collections_to_test = ['performance_metrics', 'settings']
        success_count = 0
        
        for collection_name in collections_to_test:
            try:
                print(f"Testing write to {collection_name}...")
                test_doc = {
                    'test_id': f'test_{int(time.time())}',
                    'timestamp': time.time(),
                    'test': True
                }
                
                result = await self.db[collection_name].insert_one(test_doc)
                print(f"Successfully wrote to {collection_name}, inserted id: {result.inserted_id}")
                
                # Try to delete the test document
                delete_result = await self.db[collection_name].delete_one({'_id': result.inserted_id})
                print(f"Deleted test document: {delete_result.deleted_count} document(s)")
                
                success_count += 1
            except Exception as e:
                print(f"Error writing to {collection_name}: {str(e)}")
                print(f"Error type: {type(e).__name__}")
        
        return success_count == len(collections_to_test)

async def test_mongodb_connection():
    # Load environment variables
    load_dotenv()
    
    # Get MongoDB URI
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        print("MONGO_URI environment variable not found")
        return
    
    print("Starting comprehensive MongoDB connection test...")
    
    # Create tester object
    tester = DatabaseTester(mongo_uri)
    
    # Initialize the client
    client_init_success = await tester.initialize_client()
    if not client_init_success:
        print("Failed to initialize MongoDB client")
        return
        
    # Test connection with bot-like method
    connection_success = await tester.test_connection()
    if not connection_success:
        print("MongoDB connection test failed")
        return
        
    # Check collections
    collections_result = await tester.check_collections()
    if collections_result:
        print("Collections check passed!")
    else:
        print("Collections check failed!")
    
    # Test writes
    writes_result = await tester.test_writes()
    if writes_result:
        print("Write test passed!")
    else:
        print("Write test failed!")
    
    print("Test completed successfully!")

if __name__ == "__main__":
    print("Starting MongoDB connection test")
    asyncio.run(test_mongodb_connection())
    print("Test completed") 