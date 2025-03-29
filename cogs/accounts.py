import asyncio
import io
import logging
import random
from datetime import datetime, timedelta
from typing import Any, Optional

import discord
import requests
from discord.ext import commands, tasks
from PIL import Image, ImageDraw, ImageFont

from cogs.mongo import ConnectionError, DatabaseError, ValidationError
from helper.exceptions import (
    AccountAlreadyExistsError,
    AccountNotFoundError,
    AccountTypeError,
    CreditScoreError,
    InsufficientCreditScoreError,
    InsufficientFundsError,
    InvalidTransactionError,
    LoanAlreadyExistsError,
    LoanError,
    LoanLimitError,
    LoanRepaymentError,
    TransactionLimitError,
)

# Cache configuration
CACHE_TTL = 300  # 5 minutes cache TTL
MAX_CACHE_SIZE = 1000  # Maximum number of items to cache

class Cache:
    def __init__(self, db, ttl: int = CACHE_TTL, max_size: int = MAX_CACHE_SIZE):
        self.db = db
        self.ttl = ttl
        self.max_size = max_size
        self.logger = logging.getLogger('bot')

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache with TTL check"""
        try:
            cache_data = await self.db.cache.find_one({
                "key": key,
                "expires_at": {"$gt": datetime.utcnow()}
            })
            
            if cache_data:
                return cache_data["value"]
            return None
        except Exception as e:
            self.logger.error({
                'event': 'Cache get error',
                'error': str(e),
                'key': key,
                'level': 'error'
            })
            return None

    async def set(self, key: str, value: Any) -> None:
        """Set value in cache with TTL"""
        try:
            # Check cache size
            cache_count = await self.db.cache.count_documents({})
            if cache_count >= self.max_size:
                # Remove oldest entries
                await self.db.cache.delete_many({
                    "expires_at": {"$lt": datetime.utcnow()}
                })
                # If still too many, remove oldest
                if await self.db.cache.count_documents({}) >= self.max_size:
                    await self.db.cache.delete_one({
                        "created_at": {"$exists": True}
                    }, sort=[("created_at", 1)])

            # Set new cache entry
            await self.db.cache.update_one(
                {"key": key},
                {
                    "$set": {
                        "key": key,
                        "value": value,
                        "created_at": datetime.utcnow(),
                        "expires_at": datetime.utcnow() + timedelta(seconds=self.ttl)
                    }
                },
                upsert=True
            )
        except Exception as e:
            self.logger.error({
                'event': 'Cache set error',
                'error': str(e),
                'key': key,
                'level': 'error'
            })

    async def invalidate(self, key: str) -> None:
        """Invalidate cache entry"""
        try:
            await self.db.cache.delete_one({"key": key})
        except Exception as e:
            self.logger.error({
                'event': 'Cache invalidation error',
                'error': str(e),
                'key': key,
                'level': 'error'
            })

    async def clear(self) -> None:
        """Clear all cache entries"""
        try:
            await self.db.cache.delete_many({})
        except Exception as e:
            self.logger.error({
                'event': 'Cache clear error',
                'error': str(e),
                'level': 'error'
            })

class AccountError(Exception):
    """Base exception for account-related errors"""
    pass

class KYCError(AccountError):
    """Exception for KYC verification errors"""
    pass

class TransactionError(AccountError):
    """Exception for transaction-related errors"""
    pass

class PassbookError(AccountError):
    """Exception for passbook generation errors"""
    pass

COG_METADATA = {
    "name": "accounts",
    "enabled": True, 
    "version": "1.0",
    "description": "Handles Accounts and Transactions"
}

async def setup(bot):
    # Ensure Database cog is loaded first
    if 'Database' not in [cog.qualified_name for cog in bot.cogs.values()]:
        try:
            await bot.load_extension('cogs.mongo')
        except Exception as e:
            logging.getLogger('bot').error({
                'event': 'Failed to load Database cog',
                'error': str(e),
                'level': 'error'
            })
            return
    
    # Create and add the Account cog
    cog = Account(bot)
    bot.add_cog(cog)
    await cog.cog_load()

class Account(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger('commands')
        
        # Initialize cog setup
        self._init_daily_tasks()

    async def cog_load(self):
        """Called when the cog is loaded"""
        self.logger.info("Accounts cog loading...")
        
        # Wait for MongoDB cog to fully initialize (it may need more time)
        retries = 0
        max_retries = 5
        

        try:
            # Attempt direct connection to MongoDB
            await self._establish_direct_connection()
            self.logger.info("Direct database connection successful for accounts cog")
            return
        except Exception as e:
            self.logger.warning(f"Direct connection failed: {str(e)}, trying via Database cog...")
        
        while retries < max_retries:
            try:
                # Get MongoDB cog
                mongo_cog = self.bot.get_cog('Database')
                
                if mongo_cog and mongo_cog.connected:
                    self.logger.info("Successfully connected to MongoDB for accounts cog")
                    self.mongo_client = mongo_cog.client
                    self.db = mongo_cog.db
                    self.connected = True
                    self.logger.info("Accounts cog successfully initialized with database connection")
                    return
                
                # MongoDB cog exists but not connected
                if mongo_cog and not mongo_cog.connected:
                    self.logger.warning("MongoDB cog exists but not connected yet, waiting...")
                    
                # MongoDB cog doesn't exist yet
                if not mongo_cog:
                    self.logger.warning("MongoDB cog not found yet, waiting...")
                    
                retries += 1
                await asyncio.sleep(2)
                
            except Exception as e:
                self.logger.error(f"Error connecting to MongoDB in accounts cog: {str(e)}")
                retries += 1
                await asyncio.sleep(2)
        
        # If we get here, we couldn't connect after all retries
        self.logger.error("Failed to connect to database after maximum attempts, accounts cog will operate in limited mode")
        
        # Set up minimum functionality
        self.mongo_client = None
        self.db = None
        self.connected = False

    async def _establish_direct_connection(self):
        """Establish a direct connection to MongoDB"""
        import os

        from motor.motor_asyncio import AsyncIOMotorClient
        
        # Get the MongoDB URI from environment
        mongo_uri = os.getenv("MONGO_URI")
        if not mongo_uri:
            raise ValueError("MONGO_URI environment variable not found")
        
        # Create a simple client
        self.logger.info("Creating direct MongoDB client in accounts cog...")
        self.mongo_client = AsyncIOMotorClient(
            mongo_uri,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            socketTimeoutMS=20000
        )
        
        # Always use banking_bot database
        db_name = 'banking_bot'
        self.db = self.mongo_client[db_name]
        
        # Test connection with a ping
        self.logger.info("Testing direct MongoDB connection...")
        await self.mongo_client.admin.command('ping')
        
        # Log success
        self.connected = True
        self.logger.info(f"Successfully established direct MongoDB connection to {db_name}")
        
        return True

    def _init_daily_tasks(self):
        """Initialize daily scheduled tasks"""
        self.logger.info("Initializing daily account tasks")
        
        # Create task for updating credit scores
        self.bot.loop.create_task(self._schedule_credit_score_updates())
        
    async def _schedule_credit_score_updates(self):
        """Schedule the credit score update task to run daily"""
        try:
            # Wait for bot to be fully ready
            await self.bot.wait_until_ready()
            self.logger.info("Credit score update scheduler started")
            
            while not self.bot.is_closed():
                # Calculate time until next update (midnight UTC)
                now = datetime.utcnow()
                tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                seconds_until_midnight = (tomorrow - now).total_seconds()
                
                # Log when the next update will occur
                next_update = now + timedelta(seconds=seconds_until_midnight)
                self.logger.info(f"Next credit score update scheduled for {next_update.isoformat()}")
                
                # Wait until the scheduled time
                await asyncio.sleep(seconds_until_midnight)
                
                # Run the update
                try:
                    await self.update_credit_scores_task()
                except Exception as e:
                    self.logger.error(f"Error during credit score update: {str(e)}")
                
        except Exception as e:
            self.logger.error(f"Credit score scheduler failed: {str(e)}")

    async def update_credit_scores_task(self):
        """Daily task to update credit scores based on account activity"""
        try:
            self.logger.info("Starting daily credit score updates")
            
            # Check database connection
            if not hasattr(self.bot, 'db') or self.bot.db is None:
                self.logger.error("Cannot update credit scores: database not initialized")
                return
            
            if not hasattr(self.bot.db, 'connected') or not self.bot.db.connected:
                self.logger.error("Cannot update credit scores: database not connected")
                return
            
            # Get all accounts
            accounts = await self.bot.db.get_all_accounts()
            if not accounts:
                self.logger.warning("No accounts found for credit score update")
                return
            
            self.logger.info(f"Processing credit score updates for {len(accounts)} accounts")
            
            # Process each account
            update_count = 0
            for account in accounts:
                try:
                    user_id = account.get('user_id')
                    guild_id = account.get('guild_id')
                    
                    if not user_id or not guild_id:
                        continue
                    
                    # Add your credit score update logic here
                    # For example:
                    # - Check account activity
                    # - Check payment history
                    # - Update credit score based on activity
                    
                    # For now, just count the update
                    update_count += 1
                    
                except Exception as e:
                    self.logger.error(f"Error updating credit score for account {account.get('_id')}: {str(e)}")
            
            self.logger.info(f"Completed credit score updates: {update_count} accounts processed")
            
        except Exception as e:
            self.logger.error(f"Credit score update task failed: {str(e)}")

    @commands.slash_command(name="register", description="Register your bank account")
    async def register_command(self, ctx):
        """Register a new bank account"""
        try:
            # Check if database is available
            if not hasattr(self.bot, 'db') or self.bot.db is None:
                await ctx.respond("⚠️ Unable to register account: Database service unavailable", ephemeral=True)
                self.logger.error(f"Failed account registration for {ctx.author.name}: Database unavailable")
                return
            
            # Get user information
            user_id = str(ctx.author.id)
            username = ctx.author.name
            guild_id = str(ctx.guild.id)
            guild_name = ctx.guild.name
            
            # Check if account already exists
            account = await self.bot.db.get_account(user_id, guild_id)
            
            if account:
                await ctx.respond(f"You already have an account with balance of ${account['balance']}", ephemeral=True)
                return
            
            # Create the account
            new_account = await self.bot.db.create_account(user_id, username, guild_id, guild_name)
            
            if new_account:
                # Create embed for success response
                embed = discord.Embed(
                    title="🎉 Account Created Successfully!",
                    description=f"Welcome to Quantum Bank, {ctx.author.mention}!",
                    color=discord.Color.green()
                )
                embed.add_field(name="Account Holder", value=username, inline=True)
                embed.add_field(name="Initial Balance", value="$0", inline=True)
                embed.add_field(name="Created On", value=datetime.utcnow().strftime("%Y-%m-%d"), inline=True)
                embed.set_footer(text="Use /balance to check your balance anytime")
                
                await ctx.respond(embed=embed)
                self.logger.info(f"Account registered for {username} in {guild_name}")
            else:
                await ctx.respond("⚠️ Failed to create your account. Please try again later.", ephemeral=True)
                self.logger.error(f"Failed to register account for {username}")
        
        except Exception as e:
            await ctx.respond("⚠️ An error occurred while registering your account", ephemeral=True)
            self.logger.error(f"Error in register command: {str(e)}")

    async def _get_cached_account(self, user_id: str) -> dict:
        """Retrieve account from cache or database"""
        if not self.cache:
            # If cache is not initialized, get directly from db
            return await self.db.get_account(user_id)
            
        # Try to get from cache first
        cache_key = f"account:{user_id}"
        account = await self.cache.get(cache_key)
        
        # If not in cache, get from database and cache it
        if account is None:
            account = await self.db.get_account(user_id)
            if account:
                await self.cache.set(cache_key, account)
                
        return account
        
    async def _invalidate_account_cache(self, user_id: str) -> None:
        """Invalidate account cache for a user"""
        if self.cache:
            cache_key = f"account:{user_id}"
            await self.cache.invalidate(cache_key)

    @tasks.loop(hours=24)
    async def _calculate_interest_daily(self):
        """Calculate interest for savings accounts daily"""
        try:
            self.logger.info("Starting daily interest calculation...")
            
            # Skip if database not connected
            if not self.db or not hasattr(self.db, 'db') or self.db.db is None:
                self.logger.warning("Database not available for interest calculation - skipping")
                return
            
            try:
                # Get all savings accounts
                accounts = await self.db.db.accounts.find({"account_type": "savings"}).to_list(None)
            except Exception as e:
                self.logger.error({
                    'event': 'Failed to get savings accounts',
                    'error': str(e),
                    'level': 'error'
                })
                raise Exception(f"Failed to get savings accounts: {str(e)}")
            
            if not accounts:
                self.logger.info("No savings accounts found for interest calculation")
                return
            
            count = 0
            for account in accounts:
                user_id = account.get('user_id')
                
                if user_id:
                    try:
                        # Calculate interest for each user
                        result = await self.db.calculate_interest(user_id)
                        if result:
                            count += 1
                            await self._invalidate_account_cache(user_id)
                    except Exception as e:
                        self.logger.error({
                            'event': 'Error calculating interest',
                            'error': str(e),
                            'user_id': user_id,
                            'level': 'error'
                        })
            
            self.logger.info({
                'event': 'Interest calculation completed',
                'accounts_processed': count,
                'total_accounts': len(accounts),
                'level': 'info'
            })
        except Exception as e:
            self.logger.error(f"Error in daily interest calculation: {str(e)}")
            
    @_calculate_interest_daily.before_loop
    async def before_interest_calc(self):
        """Wait for the bot to be ready before starting the task"""
        await self.bot.wait_until_ready()
        # Wait a random amount of time to distribute tasks
        await asyncio.sleep(random.randint(1, 300))

    @tasks.loop(hours=24)
    async def _check_fd_maturity_daily(self):
        """Check for mature fixed deposits daily"""
        try:
            self.logger.info("Starting daily FD maturity check...")
            
            # Skip if database not connected
            if not self.db or not hasattr(self.db, 'db') or self.db.db is None:
                self.logger.warning("Database not available for FD maturity check - skipping")
                return
            
            try:
                # Get all accounts
                accounts = await self.db.get_all_accounts()
            except Exception as e:
                self.logger.error({
                    'event': 'Failed to get all accounts',
                    'error': str(e),
                    'level': 'error'
                })
                raise Exception(f"Failed to get all accounts: {str(e)}")
            
            for account in accounts:
                user_id = account.get('user_id')
                
                if user_id:
                    try:
                        # Check if this account has any mature FDs
                        matured = await self.db.check_fd_maturity(user_id)
                        
                        if matured:
                            self.logger.info({
                                'event': 'Fixed deposit matured',
                                'user_id': user_id,
                                'level': 'info'
                            })
                            
                            # Invalidate cache for this user
                            await self._invalidate_account_cache(user_id)
                            
                    except Exception as e:
                        self.logger.error({
                            'event': 'Error checking FD maturity',
                            'error': str(e),
                            'user_id': user_id,
                            'level': 'error'
                        })
        except Exception as e:
            self.logger.error(f"Error in daily FD maturity check: {str(e)}")
            
    @_check_fd_maturity_daily.before_loop
    async def before_fd_check(self):
        """Wait for the bot to be ready before starting the task"""
        await self.bot.wait_until_ready()
        # Wait a random amount of time to distribute tasks
        await asyncio.sleep(random.randint(5, 300))

    async def cog_unload(self):
        """Clean up database connections"""
        try:
            await self.client.close()
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_application_command_error(self, ctx, error):
        """Handle errors from slash commands in this cog"""
        if hasattr(ctx.command, 'on_error'):
            # Command has its own error handler
            return
            
        # Get the original error if it's wrapped in CommandInvokeError
        error = getattr(error, 'original', error)
        
        if isinstance(error, commands.CommandOnCooldown):
            # Format time remaining nicely
            retry_after = round(error.retry_after, 1)
            time_format = "second" if retry_after == 1 else "seconds"
            
            embed = discord.Embed(
                title="Rate Limit Reached",
                description=f"This command is on cooldown! Please try again in {retry_after} {time_format}.",
                color=discord.Color.red()
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return
            
        if isinstance(error, ConnectionError):
            embed = discord.Embed(
                title="Database Error",
                description="Unable to connect to the database. Please try again later.",
                color=discord.Color.red()
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return
            
        if isinstance(error, DatabaseError):
            embed = discord.Embed(
                title="Database Error",
                description=str(error),
                color=discord.Color.red()
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return
            
        if isinstance(error, ValidationError):
            embed = discord.Embed(
                title="Validation Error",
                description=str(error),
                color=discord.Color.red()
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return
            
        if isinstance(error, AccountError):
            embed = discord.Embed(
                title="Account Error",
                description=str(error),
                color=discord.Color.red()
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return
            
        if isinstance(error, AccountNotFoundError):
            embed = discord.Embed(
                title="Account Not Found",
                description=str(error),
                color=discord.Color.red()
            )
            embed.add_field(
                name="Need an account?",
                value="Use `/create_account` to open a new account.",
                inline=False
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return
            
        if isinstance(error, AccountTypeError):
            embed = discord.Embed(
                title="Account Type Error",
                description=str(error),
                color=discord.Color.red()
            )
            embed.add_field(
                name="Need to convert your account?",
                value="Use `/convert_to_savings` to convert your account to a savings account.",
                inline=False
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return
            
        if isinstance(error, AccountAlreadyExistsError):
            embed = discord.Embed(
                title="Account Already Exists",
                description=str(error),
                color=discord.Color.red()
            )
            embed.add_field(
                name="Existing account",
                value="You already have an account. Use `/check_balance` to view your balance.",
                inline=False
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return
            
        if isinstance(error, TransactionError):
            embed = discord.Embed(
                title="Transaction Error",
                description=str(error),
                color=discord.Color.red()
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return
            
        if isinstance(error, InsufficientFundsError):
            embed = discord.Embed(
                title="Insufficient Funds",
                description=str(error),
                color=discord.Color.red()
            )
            embed.add_field(
                name="Need a loan?",
                value="Consider using the `/loan` command to apply for a loan.",
                inline=False
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return
            
        if isinstance(error, TransactionLimitError):
            embed = discord.Embed(
                title="Transaction Limit Reached",
                description=str(error),
                color=discord.Color.red()
            )
            embed.add_field(
                name="Need to increase your limits?",
                value="Upgrade your account by maintaining a higher balance or contact support.",
                inline=False
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return
            
        if isinstance(error, InvalidTransactionError):
            embed = discord.Embed(
                title="Invalid Transaction",
                description=str(error),
                color=discord.Color.red()
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return
            
        if isinstance(error, asyncio.TimeoutError):
            embed = discord.Embed(
                title="Timeout Error",
                description="The operation took too long to complete. Please try again.",
                color=discord.Color.red()
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return
            
        if isinstance(error, PassbookError):
            embed = discord.Embed(
                title="Passbook Error",
                description=str(error),
                color=discord.Color.red()
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return
            
        if isinstance(error, KYCError):
            embed = discord.Embed(
                title="KYC Verification Error",
                description=str(error),
                color=discord.Color.red()
            )
            embed.add_field(
                name="Need Help?",
                value="If you're having trouble with KYC verification, please contact support.",
                inline=False
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return
            
        if isinstance(error, LoanError):
            embed = discord.Embed(
                title="Loan Error",
                description=str(error),
                color=discord.Color.red()
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return
            
        if isinstance(error, LoanLimitError):
            embed = discord.Embed(
                title="Loan Limit Error",
                description=str(error),
                color=discord.Color.red()
            )
            embed.add_field(
                name="Credit Score",
                value="Build your credit score by maintaining a higher balance and making regular transactions.",
                inline=False
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return
            
        if isinstance(error, LoanRepaymentError):
            embed = discord.Embed(
                title="Loan Repayment Error",
                description=str(error),
                color=discord.Color.red()
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return
            
        if isinstance(error, LoanAlreadyExistsError):
            embed = discord.Embed(
                title="Loan Already Exists",
                description=str(error),
                color=discord.Color.red()
            )
            embed.add_field(
                name="Check Loan Status",
                value="Use `/loan_status` to check your current loan details.",
                inline=False
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return
            
        if isinstance(error, CreditScoreError):
            embed = discord.Embed(
                title="Credit Score Error",
                description=str(error),
                color=discord.Color.red()
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return
            
        if isinstance(error, InsufficientCreditScoreError):
            embed = discord.Embed(
                title="Low Credit Score",
                description=str(error),
                color=discord.Color.red()
            )
            embed.add_field(
                name="Improve Your Score",
                value="Maintain a positive balance, make regular deposits, and pay loans on time to boost your credit score.",
                inline=False
            )
            embed.add_field(
                name="Credit Report",
                value="Use `/credit_report` to view your current credit score and history.",
                inline=False
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return
            
        # For any other errors, log them and send a generic error message
        self.logger.error(f"Command error in {ctx.command}: {error}", exc_info=error)
        
        embed = discord.Embed(
            title="Error",
            description="An unexpected error occurred. Please try again later.",
            color=discord.Color.red()
        )
        await ctx.respond(embed=embed, ephemeral=True)

    @discord.slash_command(description="Initiate KYC verification for account creation.")
    async def create_account(self, ctx):
        """Initiates KYC verification for account creation."""
        if not self.db:
            raise ConnectionError("Database connection not initialized")

        actual_user_id = str(ctx.author.id)
        actual_guild_id = str(ctx.guild.id)
        username = ctx.author.name
        guild_name = ctx.guild.name

        existing_account = await self.db.get_account(actual_user_id)
        if existing_account:
            embed = discord.Embed(
                title="Account Already Exists",
                description=f"You already have an account at the **'{existing_account['branch_name']}'** branch!",
                color=discord.Color.red()
            )
            await ctx.respond(embed=embed) 
            return

        welcome_embed = discord.Embed(
            title="Hi 👋 Welcome to the **QUANTUM BANK ⚛️**",
            description="To create an account, you need to verify your identity and residence.\n\n"
                        "Please check your DMs for further instructions.",
            color=discord.Color.gold()  
        )
        await ctx.respond(embed=welcome_embed)

        await asyncio.sleep(2)

        while True:
            try:
                dm_embed = discord.Embed(
                    title="KYC Verification Required",
                    description="Please provide your proof of identity (**Discord User ID**) and Proof of residence (**Guild ID**).\n\n"
                                "**Format**: '<Your Discord User ID> <Your Guild ID>'\n\n"
                                "**For Example**: `1234567890 1234567890`\n\n"
                                "If you don't know how to get your Discord User ID, click [here](https://support.discord.com/hc/en-us/articles/206346498-Where-can-I-find-my-User-Server-Message-ID-)\n\n"
                                "**NOTE**: You have 2 minutes to respond.",
                    color=discord.Color.gold()
                )
                await ctx.author.send(embed=dm_embed)

            except discord.Forbidden:
                raise KYCError("I couldn't send you a DM. Please enable DMs from server members and try again.")

            def check(msg):
                return msg.author == ctx.author and isinstance(msg.channel, discord.DMChannel)

            try:
                dm_response = await self.bot.wait_for('message', check=check, timeout=120)
                provided_data = dm_response.content.split()

                if len(provided_data) != 2:
                    invalid_format_embed = discord.Embed(
                        title="Invalid Format",
                        description="Please provide your Discord User ID and Guild ID in the correct format. For example: `1234567890 1234567890`",
                        color=discord.Color.red()
                    )
                    await ctx.author.send(embed=invalid_format_embed)
                    continue

                processing_embed = discord.Embed(
                    title="Processing Your KYC details in Central Database",
                    description="Please wait while we verify your KYC details.",
                    color=discord.Color.gold()
                )
                await ctx.author.send(embed=processing_embed)

                provided_user_id, provided_guild_id = provided_data

                await asyncio.sleep(10)

                if provided_user_id != actual_user_id or provided_guild_id != actual_guild_id:
                    await self.db.log_failed_kyc_attempt(
                        user_id=actual_user_id, 
                        provided_user_id=provided_user_id,
                        guild_id=actual_guild_id,
                        provided_guild_id=provided_guild_id,
                        reason="KYC details mismatch"
                    )

                    kyc_failed_embed = discord.Embed(
                        title="KYC Verification Failed",
                        description="The provided details do not match your actual Discord User ID and Guild ID. Please try again.",
                        color=discord.Color.red()
                    )
                    await ctx.author.send(embed=kyc_failed_embed) 
                    continue

                success = await self.db.create_account(actual_user_id, actual_guild_id, username, guild_name)

                if success:
                    success_embed = discord.Embed(
                        title="Account Created",
                        description=f"Your account has been successfully created at the **'{guild_name}'** branch!",
                        color=discord.Color.green()
                    )
                    await ctx.author.send(embed=success_embed)

                    account_details_embed = discord.Embed(
                        title="Your Account Details",
                        description=f"**Username**: {username}\n**User ID**: {actual_user_id}\n**Branch Name**: {guild_name}\n**Branch ID**: {actual_guild_id}\n**Balance**: 0\n**Account Created At**: {datetime.now()}",
                        color=discord.Color.blue()
                    )
                    account_details_embed.set_thumbnail(url=ctx.author.avatar.url)
                    account_details_embed.set_footer(text="Powered By Quantum Bank ⚛️")

                    await ctx.author.send(embed=account_details_embed)

                    public_success_embed = discord.Embed(
                        title="Account Created",
                        description=f"{ctx.author.name} has successfully created an account. Check your DMs for the details.",
                        color=discord.Color.green()
                    )
                    await ctx.respond(embed=public_success_embed)
                    break 

                raise AccountError("Failed to create account")

            except asyncio.TimeoutError:
                raise KYCError("You took too long to provide your KYC details. Please try again.")

    @discord.slash_command(description="Generate a UPI ID for your account.")
    async def generate_upi(self, ctx):
        """Generate a UPI ID for the user's account."""
        if not self.db:
            raise ConnectionError("Database connection not initialized")

        user_id = str(ctx.author.id)
        account = await self._get_cached_account(user_id)

        if not account:
            raise AccountError("You don't have an account! Use `/create_account` to open one.")

        if 'upi_id' in account and account['upi_id']:
            raise AccountError(f"You already have a UPI ID: `{account['upi_id']}`. You cannot generate another one.")

        # Generate a unique UPI ID
        upi_id = f"{user_id}@quantumbank.0zaq"
        
        # Update account with new UPI ID
        success = await self.db.update_account(user_id, {'upi_id': upi_id})
        if not success:
            raise DatabaseError("Failed to generate UPI ID")

        # Invalidate cache
        await self._invalidate_account_cache(user_id)

        embed = discord.Embed(
            title="UPI ID Generated",
            description=f"Your UPI ID has been generated successfully!\n"
                       f"UPI ID: `{upi_id}`\n\n"
                       f"**Important:**\n"
                       f"• Keep your UPI ID safe\n"
                       f"• Share it only with trusted users\n"
                       f"• You can use this ID to receive payments\n"
                       f"• Use `/upi_payment` to make payments",
            color=discord.Color.green()
        )
        await ctx.respond(embed=embed, ephemeral=True)

    def _validate_upi_id(self, upi_id: str) -> bool:
        """Validate UPI ID format"""
        if not upi_id:
            return False
        
        # Basic UPI ID format: username@bankname
        parts = upi_id.split('@')
        if len(parts) != 2:
            return False
            
        username, bankname = parts
        
        # Username should be alphanumeric and 3-30 characters
        if not (3 <= len(username) <= 30 and username.isalnum()):
            return False
            
        # Bankname should be alphanumeric and 3-20 characters
        if not (3 <= len(bankname) <= 20 and bankname.isalnum()):
            return False
            
        return True

    async def _check_daily_transaction_limit(self, user_id: str, amount: float) -> bool:
        """Check if user has exceeded daily transaction limit"""
        try:
            # Get today's transactions
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            transactions = await self.db.get_transactions(user_id, limit=100)  # Get last 100 transactions
            
            # Calculate total amount for today
            daily_total = sum(
                txn['amount'] for txn in transactions 
                if txn['timestamp'] >= today and txn['type'] == 'send_upi_payment'
            )
            
            # Check if new transaction would exceed limit
            DAILY_LIMIT = 100000  # $100,000 daily limit
            return (daily_total + amount) <= DAILY_LIMIT
            
        except Exception as e:
            self.logger.error({
                'event': 'Failed to check daily transaction limit',
                'error': str(e),
                'user_id': user_id,
                'level': 'error'
            })
            return False

    @commands.cooldown(rate=3, per=10, type=commands.BucketType.user)
    async def upi_payment(self, ctx, upi_id: str, amount: float):
        """Processes a payment using the user's UPI ID."""
        if not self.db:
            raise ConnectionError("Database connection not initialized")

        # Validate UPI ID format
        if not self._validate_upi_id(upi_id):
            raise ValidationError("Invalid UPI ID format. Use format: username@bankname")

        # Use the more robust validation method
        is_valid, error_message = self._validate_amount(amount)
        if not is_valid:
            raise ValidationError(error_message)

        sender_id = str(ctx.author.id)
        sender_account = await self._get_cached_account(sender_id)

        if not sender_account:
            raise AccountError("You don't have an account! Use `/create_account` to open one.")

        if amount > sender_account['balance']:
            raise TransactionError("You do not have enough balance to make this payment.")

        # Check daily transaction limit
        if not await self._check_daily_transaction_limit(sender_id, amount):
            raise TransactionError("You have exceeded your daily transaction limit of $100,000")

        receiver_account = await self._get_cached_account(upi_id.split('@')[0])

        if not receiver_account:
            raise AccountError(f"No account found for the provided UPI ID: {upi_id}.")

        confirm_button = discord.ui.Button(label="Confirm Payment", style=discord.ButtonStyle.green)
        decline_button = discord.ui.Button(label="Decline Payment", style=discord.ButtonStyle.red)

        async def confirm_callback(interaction):
            try:
                new_sender_balance = sender_account['balance'] - amount
                new_receiver_balance = receiver_account['balance'] + amount

                await self.db.log_transaction(sender_id, 'send_upi_payment', amount, receiver_account['user_id'])
                await self.db.log_transaction(receiver_account['user_id'], 'received_upi_payment', amount, sender_id)

                await self.db.update_balance(sender_id, new_sender_balance)
                await self.db.update_balance(receiver_account['user_id'], new_receiver_balance)

                # Invalidate caches after successful transaction
                await self._invalidate_account_cache(sender_id)
                await self._invalidate_account_cache(receiver_account['user_id'])
                await self._invalidate_transactions_cache(sender_id)
                await self._invalidate_transactions_cache(receiver_account['user_id'])

                embed = discord.Embed(
                    title="Payment Successful",
                    description=f"You have successfully paid ${amount:.2f} using your UPI ID `{upi_id}`.",
                    color=discord.Color.green()
                )

                await interaction.response.send_message(embed=embed, ephemeral=True)
            except Exception as e:
                self.logger.error(f"Error in payment confirmation: {e}", exc_info=True)
                await interaction.response.send_message(
                    "An error occurred while processing the payment. Please try again later.",
                    ephemeral=True
                )

        async def decline_callback(interaction):
            await interaction.response.send_message("Payment has been declined.", ephemeral=True)

        confirm_button.callback = confirm_callback
        decline_button.callback = decline_callback

        view = discord.ui.View()
        view.add_item(confirm_button)
        view.add_item(decline_button)

        await ctx.respond("Are you sure you want to make this payment?", view=view)

    @discord.slash_command(description="Check your account balance and view your passbook.")
    async def passbook(self, ctx):
        """Generates and displays a passbook for the user."""
        if not self.db:
            raise ConnectionError("Database connection not initialized")

        # Defer the response immediately
        await ctx.defer(ephemeral=True)
        
        user_id = str(ctx.author.id)
        account = await self._get_cached_account(user_id)

        if not account:
            raise AccountError("You don't have an account! Use `/create_account` to open one.")

        transactions = await self._get_cached_transactions(user_id)
        passbook_image = self.create_passbook_image(ctx.author.name, account, transactions, ctx.author.avatar.url)

        if passbook_image is None:
            raise PassbookError("Failed to generate your passbook. Please try again later.")

        # Create a temporary file
        with io.BytesIO() as image_binary:
            passbook_image.save(image_binary, 'PNG')
            image_binary.seek(0)
            
            # Use followup instead of respond
            await ctx.followup.send(
                content="Here's your passbook!",
                file=discord.File(fp=image_binary, filename='passbook.png'),
                ephemeral=True
            )

    @staticmethod
    def create_passbook_image(username, account, transactions, avatar_url):
        """Creates a decorative passbook-like image with account information and transaction history."""
        try:
            background_path = "images/Technology-for-more-than-technologys-sake-1024x614.jpg"
            background_image = Image.open(background_path)
            background_image = background_image.resize((600, 400))

            passbook = Image.new('RGB', (600, 400))
            passbook.paste(background_image)

            draw = ImageDraw.Draw(passbook)

            title_font_path = "fonts/arial.ttf"
            text_font_path = "fonts/arial.ttf"

            title_font = ImageFont.truetype(title_font_path, size=24)
            text_font = ImageFont.truetype(text_font_path, size=18)

            draw.text((20, 20), f"Passbook for {username}", fill='white', font=title_font)
            draw.text((20, 60), f"Branch Name: {account['branch_name']}", fill='white', font=text_font)
            draw.text((20, 90), f"Balance: ${account['balance']:.2f}", fill='white', font=text_font)

            avatar_image = Image.open(requests.get(avatar_url, stream=True).raw).convert("RGBA")
            avatar_image = avatar_image.resize((50, 50))
            passbook.paste(avatar_image, (500, 10), avatar_image)

            draw.text((20, 130), "Transaction History:", fill='white', font=text_font)

            y_offset = 160
            for txn in transactions[:5]:
                txn_info = f"{txn['type'].capitalize()} 💵: ${txn['amount']} on {txn['timestamp']}"
                draw.text((20, y_offset), txn_info, fill='white', font=text_font)
                y_offset += 25

            return passbook

        except Exception as e:
            raise PassbookError(f"Failed to create passbook image: {str(e)}")

    @discord.slash_command(description="View your transaction history.")
    async def view_transactions(self, ctx):
        """View your transaction history."""
        if not self.db:
            raise ConnectionError("Database connection not initialized")

        user_id = str(ctx.author.id)
        transactions = await self._get_cached_transactions(user_id)

        if not transactions:
            raise AccountError("You don't have any transactions!")

        transaction_list = "\n".join([f"{txn['type'].capitalize()} 💵: ${txn['amount']} on {txn['timestamp']}" for txn in transactions])

        embed = discord.Embed(
            title="Transaction History",
            description=f"```{transaction_list}```",
            color=discord.Color.blue()
        )
        await ctx.respond(embed=embed)

    @discord.slash_command(description="View your account details.")
    async def view_account_details(self, ctx):
        """View your account details."""
        if not self.db:
            raise ConnectionError("Database connection not initialized")

        user_id = str(ctx.author.id)
        account = await self._get_cached_account(user_id)

        if not account:
            raise AccountError("You don't have an account! Use `/create_account` to open one.")

        embed = discord.Embed(
            title="Account Details",
            description=f"**User ID**: {user_id}\n**Branch Name**: {account['branch_name']}\n**Balance**: ${account['balance']:.2f}",
            color=discord.Color.blue()
        )
        await ctx.respond(embed=embed)

    @discord.slash_command(description="Change your bank branch.")
    async def change_branch(self, ctx, new_branch: str):
        """Change your bank branch."""
        if not self.db:
            raise ConnectionError("Database connection not initialized")

        user_id = str(ctx.author.id)
        account = await self._get_cached_account(user_id)

        if not account:
            raise AccountError("You don't have an account! Use `/create_account` to open one.")

        success = await self.db.update_branch(user_id, new_branch)

        if not success:
            raise AccountError("Failed to change your bank branch")

        # Invalidate cache
        await self._invalidate_account_cache(user_id)

        embed = discord.Embed(
            title="Branch Changed",
            description=f"Your bank branch has been successfully changed to {new_branch}.",
            color=discord.Color.green()
        )
        await ctx.respond(embed=embed)

    def _validate_amount(self, amount: float) -> tuple[bool, str]:
        """Validate transaction amount with strong security checks"""
        if not isinstance(amount, (int, float)):
            return False, "Amount must be a number"
            
        # Amount should be positive
        if amount <= 0:
            return False, "Amount must be greater than 0"
            
        # Check for reasonable limits to prevent accidents
        if amount > 1000000:
            return False, "Amount exceeds maximum transaction limit of $1,000,000"
            
        # Check for precision - prevent micro-transaction exploits
        # Only allow 2 decimal places max
        if amount != round(amount, 2):
            return False, "Amount can only have up to 2 decimal places"
            
        # Check for extremely small amounts that might be used in attacks
        if amount < 0.01:
            return False, "Amount must be at least $0.01"
            
        return True, ""

    @discord.slash_command(description="Apply for a personal loan")
    @commands.cooldown(rate=1, per=600, type=commands.BucketType.user)  # 10 minute cooldown
    async def apply_loan(self, ctx, amount: discord.Option(float, "Amount to borrow", min_value=100),
                        term_months: discord.Option(int, "Loan term in months", choices=[3, 6, 12, 24, 36])):
        """Apply for a personal loan"""
        if not self.db:
            raise ConnectionError("Database connection not initialized")
            
        # Validate amount
        is_valid, error_message = self._validate_amount(amount)
        if not is_valid:
            raise ValidationError(error_message)
            
        # Get user account
        user_id = str(ctx.author.id)
        account = await self._get_cached_account(user_id)
        
        if not account:
            raise AccountNotFoundError("You don't have an account! Use `/create_account` to open one.")
            
        # Minimum account age for loans (7 days)
        account_age = (datetime.utcnow() - account.get('created_at', datetime.utcnow())).days
        if account_age < 7:
            raise LoanError(f"Your account must be at least 7 days old to apply for a loan. Your account is {account_age} days old.")
        
        # Send confirmation message with loan details
        interest_rate = 12.0  # Fixed rate for now
        total_interest = (amount * interest_rate * term_months) / (12 * 100)
        total_repayment = amount + total_interest
        monthly_payment = total_repayment / term_months
        
        embed = discord.Embed(
            title="Loan Application Confirmation",
            description="Please review your loan details before confirming:",
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name="Loan Amount",
            value=f"${amount:,.2f}",
            inline=True
        )
        
        embed.add_field(
            name="Term",
            value=f"{term_months} months",
            inline=True
        )
        
        embed.add_field(
            name="Interest Rate",
            value=f"{interest_rate}%",
            inline=True
        )
        
        embed.add_field(
            name="Monthly Payment",
            value=f"${monthly_payment:,.2f}",
            inline=True
        )
        
        embed.add_field(
            name="Total Interest",
            value=f"${total_interest:,.2f}",
            inline=True
        )
        
        embed.add_field(
            name="Total Repayment",
            value=f"${total_repayment:,.2f}",
            inline=True
        )
        
        # Create confirmation buttons
        confirm_button = discord.ui.Button(style=discord.ButtonStyle.green, label="Confirm Loan", custom_id="confirm_loan")
        cancel_button = discord.ui.Button(style=discord.ButtonStyle.red, label="Cancel", custom_id="cancel_loan")
        
        view = discord.ui.View()
        view.add_item(confirm_button)
        view.add_item(cancel_button)
        
        await ctx.respond(embed=embed, view=view)
        
        # Wait for button interaction
        try:
            interaction = await self.bot.wait_for(
                "interaction",
                check=lambda i: i.user.id == ctx.author.id and 
                              i.data.get("custom_id") in ["confirm_loan", "cancel_loan"],
                timeout=120.0
            )
            
            if interaction.data.get("custom_id") == "cancel_loan":
                cancel_embed = discord.Embed(
                    title="Loan Application Cancelled",
                    description="Your loan application has been cancelled.",
                    color=discord.Color.red()
                )
                await interaction.response.edit_message(embed=cancel_embed, view=None)
                return
                
            # Confirm loan processing
            await interaction.response.defer(ephemeral=False)
            
            # Process loan application
            success = await self.db.create_loan(user_id, amount, term_months)
            
            if success:
                # Invalidate cache
                await self._invalidate_account_cache(user_id)
                
                success_embed = discord.Embed(
                    title="Loan Approved",
                    description=f"Your loan of ${amount:,.2f} has been approved and added to your account!",
                    color=discord.Color.green()
                )
                
                success_embed.add_field(
                    name="Monthly Payment",
                    value=f"${monthly_payment:,.2f} due every 30 days",
                    inline=False
                )
                
                success_embed.add_field(
                    name="First Payment Due",
                    value=f"{(datetime.utcnow() + timedelta(days=30)).strftime('%Y-%m-%d')}",
                    inline=False
                )
                
                success_embed.add_field(
                    name="Payment Instructions",
                    value="Use `/repay_loan` to make payments toward your loan.",
                    inline=False
                )
                
                success_embed.set_footer(text="Thank you for choosing Quantum Bank!")
                
                await interaction.followup.send(embed=success_embed)
            else:
                fail_embed = discord.Embed(
                    title="Loan Application Failed",
                    description="We couldn't process your loan application at this time. Please try again later.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=fail_embed)
                
        except asyncio.TimeoutError:
            timeout_embed = discord.Embed(
                title="Loan Application Cancelled",
                description="Confirmation timed out. Your loan application has been cancelled.",
                color=discord.Color.red()
            )
            await ctx.edit(embed=timeout_embed, view=None)
            
    @discord.slash_command(description="Repay your active loan")
    @commands.cooldown(rate=3, per=60, type=commands.BucketType.user)
    async def repay_loan(self, ctx, amount: discord.Option(float, "Amount to repay (defaults to monthly payment)", required=False) = None):
        """Make a payment toward your loan"""
        if not self.db:
            raise ConnectionError("Database connection not initialized")
            
        # Get user account
        user_id = str(ctx.author.id)
        account = await self._get_cached_account(user_id)
        
        if not account:
            raise AccountNotFoundError("You don't have an account! Use `/create_account` to open one.")
            
        # Check if user has an active loan
        if not account.get('loan') or account['loan'].get('status') != 'active':
            raise LoanError("You don't have an active loan to repay.")
            
        # Validate amount if provided
        if amount is not None:
            is_valid, error_message = self._validate_amount(amount)
            if not is_valid:
                raise ValidationError(error_message)
        
        # Process loan payment
        try:
            payment_result = await self.db.repay_loan(user_id, amount)
            
            # Invalidate cache
            await self._invalidate_account_cache(user_id)
            
            # Create response embed
            if payment_result['fully_paid']:
                embed = discord.Embed(
                    title="Loan Fully Repaid",
                    description="Congratulations! You have fully repaid your loan.",
                    color=discord.Color.green()
                )
                
                embed.add_field(
                    name="Amount Paid",
                    value=f"${payment_result['amount_paid']:,.2f}",
                    inline=True
                )
                
                embed.add_field(
                    name="Remaining Balance",
                    value="$0.00",
                    inline=True
                )
                
                embed.add_field(
                    name="Loan Status",
                    value="Paid ✅",
                    inline=True
                )
                
                embed.set_footer(text="Thank you for choosing Quantum Bank!")
                
            else:
                embed = discord.Embed(
                    title="Loan Payment Successful",
                    description=f"Your loan payment of ${payment_result['amount_paid']:,.2f} has been processed.",
                    color=discord.Color.green()
                )
                
                embed.add_field(
                    name="Remaining Balance",
                    value=f"${payment_result['remaining_amount']:,.2f}",
                    inline=True
                )
                
                embed.add_field(
                    name="Next Payment Due",
                    value=f"{(datetime.utcnow() + timedelta(days=30)).strftime('%Y-%m-%d')}",
                    inline=True
                )
                
                embed.add_field(
                    name="Loan Status",
                    value="Active",
                    inline=True
                )
                
            await ctx.respond(embed=embed)
            
        except Exception as e:
            if isinstance(e, (AccountNotFoundError, LoanError, InsufficientFundsError, DatabaseError)):
                raise e
            self.logger.error({
                'event': 'Error in repay_loan command',
                'error': str(e),
                'user_id': user_id,
                'level': 'error'
            })
            raise DatabaseError(f"Failed to process loan payment: {str(e)}")
            
    @discord.slash_command(description="Check your loan status")
    async def loan_status(self, ctx):
        """Check the status of your current loan"""
        if not self.db:
            raise ConnectionError("Database connection not initialized")
            
        # Get user account
        user_id = str(ctx.author.id)
        account = await self._get_cached_account(user_id)
        
        if not account:
            raise AccountNotFoundError("You don't have an account! Use `/create_account` to open one.")
            
        # Get loan status
        loan_status = await self.db.check_loan_status(user_id)
        
        if not loan_status:
            embed = discord.Embed(
                title="No Active Loans",
                description="You don't have any active loans. Use `/apply_loan` to apply for a loan.",
                color=discord.Color.blue()
            )
            await ctx.respond(embed=embed)
            return
            
        # Create response embed based on loan status
        if loan_status['status'] == 'paid':
            embed = discord.Embed(
                title="Loan Status - Paid",
                description="Your loan has been fully repaid.",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="Original Amount",
                value=f"${loan_status['amount']:,.2f}",
                inline=True
            )
            
            embed.add_field(
                name="Interest Rate",
                value=f"{loan_status['interest_rate']}%",
                inline=True
            )
            
            embed.add_field(
                name="Term",
                value=f"{loan_status['term_months']} months",
                inline=True
            )
            
            embed.add_field(
                name="Paid On",
                value=f"{loan_status['end_date'].strftime('%Y-%m-%d')}",
                inline=True
            )
            
        else:  # Active loan
            title_color = discord.Color.red() if loan_status['is_overdue'] else discord.Color.gold()
            status_text = "Overdue" if loan_status['is_overdue'] else "Active"
            
            embed = discord.Embed(
                title=f"Loan Status - {status_text}",
                description="Here are the details of your current loan:",
                color=title_color
            )
            
            embed.add_field(
                name="Loan Amount",
                value=f"${loan_status['amount']:,.2f}",
                inline=True
            )
            
            embed.add_field(
                name="Interest Rate",
                value=f"{loan_status['interest_rate']}%",
                inline=True
            )
            
            embed.add_field(
                name="Term",
                value=f"{loan_status['term_months']} months",
                inline=True
            )
            
            embed.add_field(
                name="Monthly Payment",
                value=f"${loan_status['monthly_payment']:,.2f}",
                inline=True
            )
            
            embed.add_field(
                name="Remaining Amount",
                value=f"${loan_status['remaining_amount']:,.2f}",
                inline=True
            )
            
            embed.add_field(
                name="Progress",
                value=f"{loan_status['progress_percent']:.1f}%",
                inline=True
            )
            
            # Format next payment info
            if loan_status['is_overdue']:
                next_payment_text = f"OVERDUE by {abs(loan_status['days_to_next_payment'])} days"
            else:
                next_payment_text = f"Due in {loan_status['days_to_next_payment']} days"
                
            embed.add_field(
                name="Next Payment",
                value=f"{loan_status['next_payment_date'].strftime('%Y-%m-%d')} ({next_payment_text})",
                inline=False
            )
            
            embed.add_field(
                name="Loan Period",
                value=f"From {loan_status['start_date'].strftime('%Y-%m-%d')} to {loan_status['end_date'].strftime('%Y-%m-%d')}",
                inline=False
            )
            
            # Add payment instructions
            embed.add_field(
                name="Make a Payment",
                value="Use `/repay_loan` to make payments toward your loan.",
                inline=False
            )
            
        embed.set_footer(text="Quantum Bank Loans")
        await ctx.respond(embed=embed)
        
    @discord.slash_command(description="View loan calculator")
    async def loan_calculator(self, ctx, amount: discord.Option(float, "Loan amount", min_value=100),
                             term_months: discord.Option(int, "Loan term in months", min_value=1, max_value=60),
                             interest_rate: discord.Option(float, "Annual interest rate", min_value=1, max_value=30) = 12.0):
        """Calculate loan payments and interest"""
        
        # Calculate loan details
        total_interest = (amount * interest_rate * term_months) / (12 * 100)
        total_repayment = amount + total_interest
        monthly_payment = total_repayment / term_months
        
        embed = discord.Embed(
            title="Loan Calculator Results",
            description="Here's a breakdown of your potential loan:",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="Loan Amount",
            value=f"${amount:,.2f}",
            inline=True
        )
        
        embed.add_field(
            name="Term",
            value=f"{term_months} months",
            inline=True
        )
        
        embed.add_field(
            name="Interest Rate",
            value=f"{interest_rate}%",
            inline=True
        )
        
        embed.add_field(
            name="Monthly Payment",
            value=f"${monthly_payment:,.2f}",
            inline=True
        )
        
        embed.add_field(
            name="Total Interest",
            value=f"${total_interest:,.2f}",
            inline=True
        )
        
        embed.add_field(
            name="Total Repayment",
            value=f"${total_repayment:,.2f}",
            inline=True
        )
        
        # Calculate different term comparisons
        comparisons = []
        for months in [3, 6, 12, 24, 36, 60]:
            if months != term_months:  # Skip the current term
                comp_interest = (amount * interest_rate * months) / (12 * 100)
                comp_total = amount + comp_interest
                comp_monthly = comp_total / months
                comparisons.append(f"**{months} months**: ${comp_monthly:,.2f}/month (Total: ${comp_total:,.2f})")
        
        if comparisons:
            embed.add_field(
                name="Term Comparisons",
                value="\n".join(comparisons),
                inline=False
            )
            
        embed.add_field(
            name="Apply for a Loan",
            value="Use `/apply_loan` to apply for a personal loan.",
            inline=False
        )
        
        embed.set_footer(text="Quantum Bank Loan Calculator")
        await ctx.respond(embed=embed)

    @discord.slash_command(description="Check your credit score and credit history")
    async def credit_score(self, ctx):
        """View your credit score"""
        if not self.db:
            raise ConnectionError("Database connection not initialized")
            
        # Get user account
        user_id = str(ctx.author.id)
        account = await self._get_cached_account(user_id)
        
        if not account:
            raise AccountNotFoundError("You don't have an account! Use `/create_account` to open one.")
            
        # Get credit score
        credit_score = account.get('credit_score', 600)
        credit_rating = self._get_credit_rating(credit_score)
        
        # Create embedded response
        embed = discord.Embed(
            title="Your Credit Score",
            description=f"Your current credit score is **{credit_score}** ({credit_rating})",
            color=self._get_credit_score_color(credit_score)
        )
        
        # Add credit score meter visualization with emojis
        score_meter = self._generate_credit_score_meter(credit_score)
        embed.add_field(
            name="Score Range",
            value=score_meter,
            inline=False
        )
        
        # Add credit rating explanation
        embed.add_field(
            name="What This Means",
            value=self._get_credit_rating_explanation(credit_rating),
            inline=False
        )
        
        # Add actions to improve score
        if credit_score < 700:
            embed.add_field(
                name="Improve Your Score",
                value="• Make regular deposits\n• Pay loans on time\n• Maintain a positive balance\n• Avoid overdrafts",
                inline=False
            )
            
        # Add footer with detailed report link
        embed.set_footer(text="Use /credit_report for a detailed credit history")
        
        await ctx.respond(embed=embed)
        
    @discord.slash_command(description="View your detailed credit report")
    async def credit_report(self, ctx):
        """View your detailed credit report and history"""
        if not self.db:
            raise ConnectionError("Database connection not initialized")
            
        # Get user account
        user_id = str(ctx.author.id)
        
        try:
            # Get credit report from database
            credit_report = await self.db.get_credit_report(user_id)
            
            # Create embedded response
            embed = discord.Embed(
                title="Your Credit Report",
                description=f"Credit Score: **{credit_report['credit_score']}** ({credit_report['credit_rating']})",
                color=self._get_credit_score_color(credit_report['credit_score'])
            )
            
            # Account information
            embed.add_field(
                name="Account Information",
                value=f"• Account Age: {credit_report['account_age_days']} days\n"
                     f"• Recent Transactions: {credit_report['transaction_count_30d']} (last 30 days)\n"
                     f"• Current Balance: ${credit_report['average_balance']:,.2f}",
                inline=False
            )
            
            # Loan information if applicable
            if credit_report['has_active_loan']:
                embed.add_field(
                    name="Loan Status",
                    value=f"• Active Loan: Yes\n"
                         f"• Repayment Status: {credit_report['loan_repayment_status']}",
                    inline=False
                )
            
            # Credit limits and rates
            embed.add_field(
                name="Credit Benefits",
                value=f"• Loan Borrowing Limit: {credit_report['credit_limit_multiplier']}x your balance\n"
                     f"• Loan Interest Rate: {credit_report['loan_interest_rate']}%",
                inline=False
            )
            
            # Recent credit history
            recent_history = credit_report.get('recent_credit_events', [])
            if recent_history:
                history_text = ""
                for event in reversed(recent_history[-5:]):  # Show 5 most recent events, oldest first
                    date_str = event['date'].strftime("%Y-%m-%d")
                    change_str = f"+{event['change']}" if event['change'] > 0 else str(event['change'])
                    history_text += f"• {date_str}: {event['action']} ({change_str} points) - {event['reason']}\n"
                
                embed.add_field(
                    name="Recent Credit History",
                    value=history_text,
                    inline=False
                )
            
            # Tips for improvement
            if credit_report['credit_score'] < 700:
                embed.add_field(
                    name="Tips to Improve Your Score",
                    value="• Make regular deposits\n"
                         "• Pay loans on time\n"
                         "• Keep your account active\n"
                         "• Maintain a high balance\n"
                         "• Avoid overdrafts",
                    inline=False
                )
            
            await ctx.respond(embed=embed)
            
        except Exception as e:
            self.logger.error({
                'event': 'Error in credit_report command',
                'error': str(e),
                'user_id': user_id,
                'level': 'error'
            })
            raise CreditScoreError(f"Could not retrieve your credit report: {str(e)}")
            
    def _get_credit_rating(self, credit_score: int) -> str:
        """Convert numeric credit score to rating label"""
        if credit_score >= 800:
            return "Excellent"
        elif credit_score >= 750:
            return "Very Good"
        elif credit_score >= 700:
            return "Good"
        elif credit_score >= 650:
            return "Fair"
        elif credit_score >= 600:
            return "Poor"
        elif credit_score >= 550:
            return "Very Poor"
        else:
            return "Bad"
            
    def _get_credit_score_color(self, credit_score: int) -> discord.Color:
        """Get color for credit score visualization"""
        if credit_score >= 800:
            return discord.Color.from_rgb(0, 128, 0)  # Green
        elif credit_score >= 750:
            return discord.Color.from_rgb(102, 204, 0)  # Light green
        elif credit_score >= 700:
            return discord.Color.from_rgb(204, 204, 0)  # Yellow-green
        elif credit_score >= 650:
            return discord.Color.from_rgb(255, 204, 0)  # Yellow
        elif credit_score >= 600:
            return discord.Color.from_rgb(255, 153, 0)  # Orange
        elif credit_score >= 550:
            return discord.Color.from_rgb(255, 102, 0)  # Dark orange
        else:
            return discord.Color.from_rgb(255, 0, 0)    # Red
            
    def _generate_credit_score_meter(self, credit_score: int) -> str:
        """Generate a visual representation of credit score using emojis"""
        # Normalize score to 0-100 range (from 300-850)
        normalized_score = int((credit_score - 300) / 5.5)
        
        # Create 10-segment meter
        meter = ""
        segments = 10
        filled = min(segments, max(0, normalized_score // 10))
        
        # Use different emojis based on score range
        if credit_score >= 700:     # Good and above
            filled_emoji = "🟢"
            empty_emoji = "⚪"
        elif credit_score >= 600:   # Poor to Fair
            filled_emoji = "🟡"
            empty_emoji = "⚪"
        else:                       # Bad to Very Poor
            filled_emoji = "🔴" 
            empty_emoji = "⚪"
            
        meter = filled_emoji * filled + empty_emoji * (segments - filled)
        
        # Add score range indicators
        return f"300 {meter} 850"
        
    def _get_credit_rating_explanation(self, rating: str) -> str:
        """Get explanation text for credit rating"""
        explanations = {
            "Excellent": "You have an exceptional credit score! You qualify for the best loan terms and highest credit limits.",
            "Very Good": "Your credit score is very strong. You qualify for favorable loan terms and high credit limits.",
            "Good": "You have a healthy credit score. You qualify for standard loan terms and moderate credit limits.",
            "Fair": "Your credit is acceptable. You may qualify for loans with moderate interest rates and limited credit.",
            "Poor": "Your credit score needs improvement. Loan options may be limited and interest rates higher.",
            "Very Poor": "Your credit score is concerning. You may face restrictions on loans and higher interest rates.",
            "Bad": "Your credit score is at a critical level. Focus on improving it to qualify for better banking services."
        }
        return explanations.get(rating, "No rating information available.")

    def _get_account_age(self, created_at):
        """Convert account creation date to a human-readable age"""
        if not created_at:
            return "Unknown"
            
        # Convert string to datetime if needed
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            except ValueError:
                return "Unknown"
        
        # Calculate age
        now = datetime.utcnow()
        
        if not isinstance(created_at, datetime):
            return "Unknown"
            
        delta = now - created_at
        
        if delta.days > 365:
            years = delta.days // 365
            return f"{years} year{'s' if years != 1 else ''}"
        elif delta.days > 30:
            months = delta.days // 30
            return f"{months} month{'s' if months != 1 else ''}"
        elif delta.days > 0:
            return f"{delta.days} day{'s' if delta.days != 1 else ''}"
        else:
            hours = delta.seconds // 3600
            if hours > 0:
                return f"{hours} hour{'s' if hours != 1 else ''}"
            else:
                minutes = delta.seconds // 60
                return f"{minutes} minute{'s' if minutes != 1 else ''}"
                
    @commands.slash_command(name="balance", description="Check your account balance")
    async def balance_command(self, ctx):
        """Check your current bank account balance"""
        try:
            # Check if database is available
            if not hasattr(self.bot, 'db') or self.bot.db is None:
                await ctx.respond("⚠️ Unable to check balance: Database service unavailable", ephemeral=True)
                self.logger.error(f"Failed balance check for {ctx.author.name}: Database unavailable")
                return
            
            # Get user information
            user_id = str(ctx.author.id)
            guild_id = str(ctx.guild.id)
            
            # Get account
            account = await self.bot.db.get_account(user_id, guild_id)
            
            if not account:
                await ctx.respond("You don't have a bank account yet! Use `/register` to create one.", ephemeral=True)
                return
                
            # Create embed for response
            balance = account.get('balance', 0)
            
            embed = discord.Embed(
                title="💰 Account Balance",
                description=f"Here's your current account status, {ctx.author.mention}",
                color=discord.Color.blue()
            )
            embed.add_field(name="Balance", value=f"${balance:,.2f}", inline=True)
            embed.add_field(name="Account ID", value=f"||{str(account.get('_id'))[-6:]}||", inline=True)
            embed.add_field(name="Account Age", 
                           value=self._get_account_age(account.get('created_at')), inline=True)
            
            # Add credit score if available
            if 'credit_score' in account:
                credit_score = account['credit_score']
                embed.add_field(name="Credit Score", value=f"{credit_score} ({self._get_credit_rating(credit_score)})", inline=True)
            
            embed.set_footer(text=f"Transaction Count: {account.get('transaction_count', 0)}")
            
            await ctx.respond(embed=embed)
            self.logger.info(f"Balance checked by {ctx.author.name} - ${balance:,.2f}")
            
        except Exception as e:
            await ctx.respond("⚠️ An error occurred while checking your balance", ephemeral=True)
            self.logger.error(f"Error in balance command: {str(e)}")