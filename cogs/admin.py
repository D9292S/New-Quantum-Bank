import asyncio
import logging
from datetime import datetime

import discord
from discord.ext import commands

from cogs.accounts import AccountError, TransactionError
from helpers.exceptions import ConnectionError, DatabaseError, ValidationError

COG_METADATA = {
    "name": "admin",
    "enabled": True,
    "version": "1.0",
    "description": "Admin commands for the banking bot",
}


async def setup(bot):
    # Ensure Database cog is loaded first
    if "Database" not in [cog.qualified_name for cog in bot.cogs.values()]:
        try:
            await bot.load_extension("cogs.mongo")
        except Exception as e:
            logging.getLogger("bot").error({"event": "Failed to load Database cog", "error": str(e), "level": "error"})
            return

    # Create and add the Admin cog
    cog = Admin(bot)
    bot.add_cog(cog)


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = None
        self.logger = logging.getLogger("bot")
        self.accounts_cog = None

    async def cog_load(self):
        """Called when the cog is loaded."""
        attempts = 0
        max_attempts = 3
        last_error = None

        while attempts < max_attempts:
            self.db = self.bot.get_cog("Database")
            if self.db:
                try:
                    # Try to ping the database - if it succeeds, we're good
                    if hasattr(self.db, "ping_db") and await self.db.ping_db():
                        # Get the accounts cog for cache operations
                        self.accounts_cog = self.bot.get_cog("Account")
                        if not self.accounts_cog:
                            self.logger.warning(
                                {
                                    "event": "Accounts cog not loaded",
                                    "message": "Some admin functionality may be limited",
                                    "level": "warning",
                                }
                            )
                        self.logger.info("Admin cog successfully initialized")
                        return
                    else:
                        last_error = "Database ping failed"
                except Exception as e:
                    last_error = str(e)
            else:
                last_error = "Database cog not found"

            attempts += 1
            if attempts < max_attempts:
                self.logger.warning(f"Database connection attempt {attempts} failed: {last_error}")
                await asyncio.sleep(1)

        # If we get here, we couldn't connect to the database
        # But we'll still initialize with degraded functionality instead of raising an error
        self.logger.error(f"Failed to initialize database connection after {max_attempts} attempts: {last_error}")
        self.logger.warning(
            "Running in degraded mode - most admin features will return errors until database connection is restored"
        )

    async def cog_command_error(self, ctx, error):
        """Handle errors from commands in this cog"""
        # Get the original error if it's wrapped
        error = getattr(error, "original", error)

        if isinstance(error, (AccountError, ValidationError, TransactionError, DatabaseError, ConnectionError)):
            # User-facing errors, show them directly
            await ctx.respond(str(error), ephemeral=True)
        else:
            # Unexpected error, log it and show a generic message
            self.logger.error(
                {
                    "event": f'Error in admin command {ctx.command.name if ctx.command else "Unknown"}',
                    "error": str(error),
                    "level": "error",
                }
            )
            await ctx.respond("An unexpected error occurred. Please try again later.", ephemeral=True)

    async def _is_bot_owner(self, ctx) -> bool:
        """Check if the command user is the bot owner"""
        application = await self.bot.application_info()
        is_owner = ctx.author.id == application.owner.id

        if not is_owner:
            await ctx.respond("❌ This command can only be used by the bot owner.", ephemeral=True)

        return is_owner

    async def _invalidate_account_cache(self, user_id: str) -> None:
        """Invalidate account cache when updates occur"""
        if self.accounts_cog and hasattr(self.accounts_cog, "_invalidate_account_cache"):
            await self.accounts_cog._invalidate_account_cache(user_id)
        else:
            self.logger.warning(
                {
                    "event": "Failed to invalidate account cache",
                    "reason": "Accounts cog not available",
                    "user_id": user_id,
                    "level": "warning",
                }
            )

    async def _invalidate_transactions_cache(self, user_id: str) -> None:
        """Invalidate transactions cache when updates occur"""
        if self.accounts_cog and hasattr(self.accounts_cog, "_invalidate_transactions_cache"):
            await self.accounts_cog._invalidate_transactions_cache(user_id)
        else:
            self.logger.warning(
                {
                    "event": "Failed to invalidate transactions cache",
                    "reason": "Accounts cog not available",
                    "user_id": user_id,
                    "level": "warning",
                }
            )

    @discord.slash_command(description="[ADMIN] Add money to a user's account")
    async def add_money(self, ctx, user_id: str, amount: float):
        """Add money to a user's account (Bot Owner Only)"""
        # Check if the command user is the bot owner
        if not await self._is_bot_owner(ctx):
            return

        if not self.db:
            raise ConnectionError("Database connection not initialized")

        if amount <= 0:
            raise ValidationError("Amount must be greater than 0")

        # Get the target account
        account = await self.db.get_account(user_id)
        if not account:
            raise AccountError(f"No account found for user ID: {user_id}")

        # Update the balance
        new_balance = account["balance"] + amount
        success = await self.db.update_balance(user_id, new_balance)

        if not success:
            raise DatabaseError("Failed to add money to the account")

        # Reset the interest calculation time if this is a savings account
        if account.get("account_type") == "savings":
            # Check if interest rate should change based on new balance
            old_interest_rate = account.get("interest_rate", 2.5)
            new_interest_rate = self.db._calculate_interest_rate_by_balance(new_balance)
            interest_changed = old_interest_rate != new_interest_rate

            # Update account with new interest rate if it changed
            update_data = {"last_interest_calculation": datetime.utcnow()}

            if interest_changed:
                update_data["interest_rate"] = new_interest_rate

            await self.db.update_account(user_id, update_data)

        # Log the transaction
        await self.db.log_transaction(user_id, "admin_add", amount, ctx.author.id)

        # Invalidate cache
        await self._invalidate_account_cache(user_id)

        # Format the response
        embed = discord.Embed(
            title="Money Added Successfully",
            description=(
                f"✅ Successfully added ${amount:,.2f} to account.\n\n"
                f"**User ID:** {user_id}\n"
                f"**Previous Balance:** ${account['balance']:,.2f}\n"
                f"**New Balance:** ${new_balance:,.2f}"
            ),
            color=discord.Color.green(),
        )

        # Add info about reset interest calculation if applicable
        if account.get("account_type") == "savings":
            old_interest_rate = account.get("interest_rate", 2.5)
            new_interest_rate = self.db._calculate_interest_rate_by_balance(new_balance)
            interest_rate_info = (
                f"Interest rate: {old_interest_rate}% → {new_interest_rate}%"
                if old_interest_rate != new_interest_rate
                else f"Interest rate: {old_interest_rate}%"
            )

            embed.add_field(
                name="Interest Calculation",
                value=f"Interest calculation time has been reset to now.\n{interest_rate_info}",
                inline=False,
            )

        embed.set_footer(text="Admin Operation")

        await ctx.respond(embed=embed)

    @discord.slash_command(description="[ADMIN] Check any user's account balance")
    async def check_user_balance(self, ctx, user_id: str):
        """Check balance of any user's account (Bot Owner Only)"""
        # Check if the command user is the bot owner
        if not await self._is_bot_owner(ctx):
            return

        if not self.db:
            raise ConnectionError("Database connection not initialized")

        # Get the target account
        account = await self.db.get_account(user_id)
        if not account:
            raise AccountError(f"No account found for user ID: {user_id}")

        # Get recent transactions
        transactions = await self.db.get_transactions(user_id, limit=5)

        # Format the response
        embed = discord.Embed(
            title="User Account Information",
            description=(
                f"**User ID:** {user_id}\n"
                f"**Username:** {account.get('username', 'Unknown')}\n"
                f"**Branch:** {account.get('branch_name', 'Unknown')}\n"
                f"**Balance:** ${account['balance']:,.2f}\n"
                f"**Account Type:** {account.get('account_type', 'standard').title()}\n"
                f"**Created At:** {account.get('created_at', 'Unknown')}"
            ),
            color=discord.Color.blue(),
        )

        # Add recent transactions if available
        if transactions:
            txn_list = []
            for i, txn in enumerate(transactions, 1):
                txn_time = txn.get("timestamp", "Unknown")
                txn_type = txn.get("type", "Unknown").replace("_", " ").title()
                txn_amount = txn.get("amount", 0)
                txn_list.append(f"{i}. {txn_type}: ${txn_amount:,.2f} ({txn_time})")

            embed.add_field(
                name="Recent Transactions",
                value="\n".join(txn_list) if txn_list else "No recent transactions",
                inline=False,
            )

        embed.set_footer(text="Admin Operation")
        await ctx.respond(embed=embed, ephemeral=True)

    @discord.slash_command(description="[ADMIN] Set interest rate for a user's account")
    async def set_interest_rate(self, ctx, user_id: str, interest_rate: float):
        """Set interest rate for a user's account (Bot Owner Only)"""
        # Check if the command user is the bot owner
        if not await self._is_bot_owner(ctx):
            return

        if not self.db:
            raise ConnectionError("Database connection not initialized")

        # Validate interest rate
        if interest_rate < 0 or interest_rate > 100:
            raise ValidationError("Interest rate must be between 0 and 100")

        # Get the target account
        account = await self.db.get_account(user_id)
        if not account:
            raise AccountError(f"No account found for user ID: {user_id}")

        # Check if account is a savings account
        if account.get("account_type") != "savings":
            await ctx.respond(
                f"⚠️ This account is not a savings account. Converting to savings with {interest_rate}% interest rate.",
                ephemeral=True,
            )

        # Update the account
        update_data = {
            "interest_rate": interest_rate,
            "account_type": "savings",
            "last_interest_calculation": datetime.utcnow(),  # Reset interest calculation time
        }

        success = await self.db.update_account(user_id, update_data)

        if not success:
            raise DatabaseError("Failed to update interest rate")

        # Invalidate cache
        await self._invalidate_account_cache(user_id)

        # Format the response
        embed = discord.Embed(
            title="Interest Rate Updated",
            description=(
                f"✅ Successfully updated interest rate for account.\n\n"
                f"**User ID:** {user_id}\n"
                f"**Previous Rate:** {account.get('interest_rate', 2.5)}%\n"
                f"**New Rate:** {interest_rate}%\n"
                f"**Account Type:** Savings\n"
                f"**Interest Calculation Reset:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
            ),
            color=discord.Color.green(),
        )

        embed.set_footer(text="Admin Operation")

        await ctx.respond(embed=embed)

    @discord.slash_command(description="[ADMIN] Remove money from a user's account")
    async def remove_money(self, ctx, user_id: str, amount: float):
        """Remove money from a user's account (Bot Owner Only)"""
        # Check if the command user is the bot owner
        if not await self._is_bot_owner(ctx):
            return

        if not self.db:
            raise ConnectionError("Database connection not initialized")

        if amount <= 0:
            raise ValidationError("Amount must be greater than 0")

        # Get the target account
        account = await self.db.get_account(user_id)
        if not account:
            raise AccountError(f"No account found for user ID: {user_id}")

        # Check if account has enough balance
        if account["balance"] < amount:
            raise TransactionError(f"Account does not have enough balance. Current balance: ${account['balance']:,.2f}")

        # Update the balance
        new_balance = account["balance"] - amount
        success = await self.db.update_balance(user_id, new_balance)

        if not success:
            raise DatabaseError("Failed to remove money from the account")

        # Reset the interest calculation time if this is a savings account
        if account.get("account_type") == "savings":
            # Check if interest rate should change based on new balance
            old_interest_rate = account.get("interest_rate", 2.5)
            new_interest_rate = self.db._calculate_interest_rate_by_balance(new_balance)
            interest_changed = old_interest_rate != new_interest_rate

            # Update account with new interest rate if it changed
            update_data = {"last_interest_calculation": datetime.utcnow()}

            if interest_changed:
                update_data["interest_rate"] = new_interest_rate

            await self.db.update_account(user_id, update_data)

        # Log the transaction
        await self.db.log_transaction(user_id, "admin_remove", amount, ctx.author.id)

        # Invalidate cache
        await self._invalidate_account_cache(user_id)

        # Format the response
        embed = discord.Embed(
            title="Money Removed Successfully",
            description=(
                f"✅ Successfully removed ${amount:,.2f} from account.\n\n"
                f"**User ID:** {user_id}\n"
                f"**Previous Balance:** ${account['balance']:,.2f}\n"
                f"**New Balance:** ${new_balance:,.2f}"
            ),
            color=discord.Color.green(),
        )

        # Add info about reset interest calculation if applicable
        if account.get("account_type") == "savings":
            old_interest_rate = account.get("interest_rate", 2.5)
            new_interest_rate = self.db._calculate_interest_rate_by_balance(new_balance)
            interest_rate_info = (
                f"Interest rate: {old_interest_rate}% → {new_interest_rate}%"
                if old_interest_rate != new_interest_rate
                else f"Interest rate: {old_interest_rate}%"
            )

            embed.add_field(
                name="Interest Calculation",
                value=f"Interest calculation time has been reset to now.\n{interest_rate_info}",
                inline=False,
            )

        embed.set_footer(text="Admin Operation")

        await ctx.respond(embed=embed)

    @discord.slash_command(description="[ADMIN] View all accounts in the system")
    async def list_accounts(self, ctx, limit: int = 10):
        """List all accounts in the system (Bot Owner Only)"""
        # Check if the command user is the bot owner
        if not await self._is_bot_owner(ctx):
            return

        if not self.db:
            raise ConnectionError("Database connection not initialized")

        # Validate limit
        if limit <= 0 or limit > 25:
            limit = 10  # Default to 10 if invalid

        # Get accounts
        accounts = await self.db.db.accounts.find().sort("balance", -1).limit(limit).to_list(None)

        if not accounts:
            await ctx.respond("No accounts found in the system.", ephemeral=True)
            return

        # Format the response
        embed = discord.Embed(
            title="System Accounts List",
            description=f"Showing top {len(accounts)} accounts by balance",
            color=discord.Color.blue(),
        )

        for i, acc in enumerate(accounts, 1):
            embed.add_field(
                name=f"{i}. {acc.get('username', 'Unknown')}",
                value=(
                    f"**User ID:** {acc.get('user_id', 'Unknown')}\n"
                    f"**Balance:** ${acc.get('balance', 0):,.2f}\n"
                    f"**Account Type:** {acc.get('account_type', 'standard').title()}\n"
                    f"**Branch:** {acc.get('branch_name', 'Unknown')}"
                ),
                inline=False,
            )

        embed.set_footer(text="Admin Operation")
        await ctx.respond(embed=embed, ephemeral=True)

    @discord.slash_command(description="[ADMIN] Calculate interest for all accounts manually")
    async def calculate_all_interest(self, ctx):
        """Manually trigger interest calculation for all savings accounts (Bot Owner Only)"""
        # Check if the command user is the bot owner
        if not await self._is_bot_owner(ctx):
            return

        if not self.db:
            raise ConnectionError("Database connection not initialized")

        await ctx.defer(ephemeral=True)  # This might take time, so defer the response

        # Set timeout for long-running operation
        try:
            async with asyncio.timeout(60):  # 60 second timeout
                # Get all savings accounts
                savings_accounts = await self.db.db.accounts.find({"account_type": "savings"}).to_list(None)

                if not savings_accounts:
                    await ctx.followup.send("No savings accounts found in the system.")
                    return

                # Calculate interest for each account
                success_count = 0
                total_interest = 0

                for account in savings_accounts:
                    try:
                        user_id = account["user_id"]
                        old_balance = account["balance"]

                        # Calculate interest
                        result = await self.db.calculate_interest(user_id)

                        if result:
                            # Get updated account to check how much interest was added
                            updated_account = await self.db.get_account(user_id)
                            interest_added = updated_account["balance"] - old_balance
                            total_interest += interest_added
                            success_count += 1

                            # Invalidate cache
                            await self._invalidate_account_cache(user_id)

                    except Exception as e:
                        self.logger.error(
                            {
                                "event": "Failed to calculate interest for account",
                                "error": str(e),
                                "user_id": account.get("user_id", "Unknown"),
                                "level": "error",
                            }
                        )

                # Format the response
                embed = discord.Embed(
                    title="Interest Calculation Complete",
                    description=(
                        f"✅ Successfully calculated interest for {success_count} out of {len(savings_accounts)} savings accounts.\n\n"
                        f"**Total Interest Added:** ${total_interest:,.2f}"
                    ),
                    color=discord.Color.green(),
                )

                embed.set_footer(text="Admin Operation")

                await ctx.followup.send(embed=embed)
        except TimeoutError:
            self.logger.error({"event": "Interest calculation timeout", "level": "error", "timeout": "60 seconds"})
            await ctx.followup.send(
                "⚠️ The interest calculation operation timed out after 60 seconds. "
                "Please try again with fewer accounts or increase the timeout limit.",
                ephemeral=True,
            )

    @discord.slash_command(description="[ADMIN] Delete a user's account")
    async def delete_account(self, ctx, user_id: str, confirm: bool = False):
        """Delete a user's account from the system (Bot Owner Only)"""
        # Check if the command user is the bot owner
        if not await self._is_bot_owner(ctx):
            return

        if not self.db:
            raise ConnectionError("Database connection not initialized")

        # Get the target account
        account = await self.db.get_account(user_id)
        if not account:
            raise AccountError(f"No account found for user ID: {user_id}")

        # Require confirmation
        if not confirm:
            embed = discord.Embed(
                title="⚠️ Confirm Account Deletion",
                description=(
                    f"Are you sure you want to delete the following account?\n\n"
                    f"**User ID:** {user_id}\n"
                    f"**Username:** {account.get('username', 'Unknown')}\n"
                    f"**Balance:** ${account.get('balance', 0):,.2f}\n\n"
                    f"To confirm, run the command again with `confirm=True`."
                ),
                color=discord.Color.red(),
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return

        # Delete the account
        try:
            result = await self.db.db.accounts.delete_one({"user_id": user_id})
            if result.deleted_count == 0:
                raise AccountError("Failed to delete account")

            # Invalidate cache
            await self._invalidate_account_cache(user_id)

            # Also delete related transactions
            await self.db.db.transactions.delete_many({"user_id": user_id})
            await self._invalidate_transactions_cache(user_id)

            embed = discord.Embed(
                title="Account Deleted",
                description=(
                    f"✅ Successfully deleted account for user ID: {user_id}\n"
                    f"Username: {account.get('username', 'Unknown')}"
                ),
                color=discord.Color.green(),
            )

            embed.set_footer(text="Admin Operation")
            await ctx.respond(embed=embed, ephemeral=True)

        except Exception as e:
            self.logger.error(
                {
                    "event": "Failed to delete account",
                    "error": str(e),
                    "user_id": user_id,
                    "level": "error",
                }
            )
            raise DatabaseError(f"Failed to delete account: {str(e)}")
