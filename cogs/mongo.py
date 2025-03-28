import os
from datetime import datetime
import string
import random
from motor.motor_asyncio import AsyncIOMotorClient
import discord
from discord.ext import commands

COG_METADATA = {
    "name": "database",
    "enabled": True,
    "version": "1.0",
    "description": "Handles MongoDB operations for the banking bot"
}

async def setup(bot):
    bot.add_cog(Database(bot))

class Database(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        mongo_uri = self.bot.config.MONGO_URI
        if not mongo_uri:
            raise ValueError("MONGO_URI is not set in config")
        if not (mongo_uri.startswith('mongodb://') or mongo_uri.startswith('mongodb+srv://')):
            raise ValueError(f"Invalid MONGO_URI format: {mongo_uri[:10]}...")
        self.client = AsyncIOMotorClient(mongo_uri)
        self.db = self.client.get_database('banking_bot')

    async def cog_unload(self):
        await self.client.close()
        self.bot.log.info("Closed MongoDB connection for Database cog")

    async def create_account(self, user_id: str, guild_id: str, username: str, guild_name: str):
        accounts_collection = self.db["accounts"]
        existing_account = await accounts_collection.find_one({"user_id": user_id})
        if existing_account:
            return False
        await accounts_collection.insert_one({
            "user_id": user_id,
            "username": username,
            "branch_id": guild_id,
            "branch_name": guild_name,
            "balance": 0,
            "created_at": datetime.now()
        })
        return True

    async def get_account(self, user_id: str):
        accounts_collection = self.db["accounts"]
        return await accounts_collection.find_one({"user_id": user_id})

    async def update_balance(self, user_id: str, new_balance: int):
        accounts_collection = self.db["accounts"]
        await accounts_collection.update_one({"user_id": user_id}, {"$set": {"balance": new_balance}})

    async def log_failed_kyc_attempt(self, user_id: str, provided_user_id: str, guild_id: str, provided_guild_id: str, reason: str):
        failed_kyc_collection = self.db["failed_kyc_attempts"]
        await failed_kyc_collection.insert_one({
            "User_Id": user_id,
            "Provided_User_Id": provided_user_id,
            "Branch_Id": guild_id,
            "Provided_Branch_Id": provided_guild_id,
            "reason": reason,
            "timestamp": datetime.now()
        })

    async def log_transaction(self, user_id: str, txn_type: str, amount: int, receiver_id: str = None):
        transactions_collection = self.db["transactions"]
        transaction = {
            "user_id": user_id,
            "type": txn_type,
            "amount": amount,
            "receiver_id": receiver_id,
            "timestamp": datetime.utcnow()
        }
        await transactions_collection.insert_one(transaction)

    async def get_transactions(self, user_id: str):
        transactions_collection = self.db["transactions"]
        cursor = transactions_collection.find({"user_id": user_id}).sort("timestamp", -1).limit(10)
        return [doc async for doc in cursor]

    def generate_upi_id(self, user_id: str):
        bank_name = "quantumbank"
        random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
        return f"{user_id}@{bank_name}.{random_suffix}"

    async def set_upi_id(self, user_id: str):
        upi_id = self.generate_upi_id(user_id)
        accounts_collection = self.db["accounts"]
        await accounts_collection.update_one({"user_id": user_id}, {"$set": {"upi_id": upi_id}})
        return upi_id

    async def get_leaderboard(self, branch_name: str):
        cursor = self.db.accounts.find({"branch_name": branch_name}).sort("balance", -1).limit(10)
        return [doc async for doc in cursor]

    async def update_user_branch(self, user_id: str, branch_id: str, branch_name: str):
        result = await self.db.accounts.update_one(
            {"user_id": user_id},
            {"$set": {"branch_id": branch_id, "branch_name": branch_name}}
        )
        return result.modified_count > 0

    async def toggle_command(self, guild_id: str, command_name: str, status: bool):
        await self.db["guild_commands"].update_one(
            {"guild_id": guild_id},
            {"$set": {command_name: status}},
            upsert=True
        )

    async def get_command_status(self, guild_id: str, command_name: str):
        guild_commands = await self.db["guild_commands"].find_one({"guild_id": guild_id})
        return guild_commands.get(command_name, True) if guild_commands else True

    async def ping_db(self):
        try:
            await self.client.admin.command('ping')
            return True
        except Exception as e:
            self.bot.log.error(f"Database connection error: {e}")
            return False