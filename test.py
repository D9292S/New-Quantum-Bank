import discord
import os
from discord import app_commands

print(f"Discord version: {discord.__version__}")

bot = discord.Bot(command_prefix="!", intents=discord.Intents.default())
bot.tree = app_commands.CommandTree(bot)

@bot.tree.command(name="test", description="A test command")
async def test_command(interaction: discord.Interaction):
    await interaction.response.send_message("Hello!")

@bot.event
async def on_ready():
    await bot.tree.sync()
    print("Bot ready, commands synced")


bot.run(os.getenv("BOT_TOKEN"))  # Run the bot with the token from .env