import logging
from functools import wraps

import discord
from discord.ext import commands

from helper.exceptions import (
    AccountError,
    KYCError,
    PassbookError,
    TransactionError,
    ValidationError,
)

COGS_METADATA = {
    "name": "error_handler",
    "description": "Handles errors and exceptions across the bot",
    "category": "System",
    "hidden": True,
}


async def setup(bot):
    await bot.add_cog(ErrorHandler(bot))


class ErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("quantum_bank.error_handler")

    async def cog_load(self):
        """Set up error handlers when the cog is loaded"""
        self.bot.add_listener(self.on_app_command_error)
        self.bot.add_listener(self.on_error)

    @staticmethod
    def handle_errors(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except (AccountError, ValidationError, TransactionError, KYCError, PassbookError) as e:
                # For slash commands, ctx is args[1]
                ctx = args[1] if len(args) > 1 else None
                if ctx and hasattr(ctx, "respond"):
                    await ctx.respond(str(e), ephemeral=True)
                return
            except Exception as e:
                # Log only unexpected errors
                logging.getLogger("bot").error(
                    {"event": f"Error in {func.__name__}", "error": str(e), "level": "error"}
                )
                # Re-raise to be caught by on_app_command_error
                raise

    async def on_app_command_error(self, ctx: discord.ApplicationContext, error: Exception):
        """Handle errors in slash commands"""
        # Get the original error if it's wrapped in ApplicationCommandInvokeError
        error = getattr(error, "original", error)

        if isinstance(error, commands.CommandOnCooldown):
            minutes = int(error.retry_after / 60)
            seconds = int(error.retry_after % 60)
            cooldown_msg = "This command is on cooldown! Try again in "
            if minutes > 0:
                cooldown_msg += f"{minutes} minutes and "
            cooldown_msg += f"{seconds} seconds."
            await ctx.respond(cooldown_msg, ephemeral=True)
            return
        elif isinstance(error, commands.MissingPermissions):
            await ctx.respond("You don't have permission to use this command.", ephemeral=True)
            return
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.respond("I don't have permission to do that.", ephemeral=True)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.respond(f"Missing required argument: {error.param.name}", ephemeral=True)
        elif isinstance(error, commands.BadArgument):
            await ctx.respond("Invalid argument provided.", ephemeral=True)
        elif isinstance(error, (AccountError, ValidationError, TransactionError, KYCError, PassbookError)):
            # Don't log user-facing errors
            await ctx.respond(str(error), ephemeral=True)
            return

        # Log only unexpected errors
        self.logger.error(
            {
                "event": "Unexpected command error",
                "error": str(error),
                "command": ctx.command.name if ctx.command else "Unknown",
                "level": "error",
            }
        )
        await ctx.respond("An unexpected error occurred. Please try again later.", ephemeral=True)

    async def on_error(self, event: str, *args, **kwargs):
        """Handle errors in event listeners"""
        self.logger.error({"event": f"Error in {event}", "error": str(args[0]), "level": "error"}, exc_info=True)
