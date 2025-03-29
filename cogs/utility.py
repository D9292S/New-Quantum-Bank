import datetime
import logging
import os
import platform
import time
from typing import Optional

import discord
import psutil
from discord.ext import commands

COG_METADATA = {
    "name": "utility",
    "enabled": True,
    "version": "1.0",
    "description": "Utility commands like help, ping, and info",
}


async def setup(bot):
    bot.add_cog(Utility(bot))


class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("bot")
        self.start_time = time.time()

    @discord.slash_command(description="Check bot latency")
    async def ping(self, ctx):
        """Check the bot's latency to Discord"""
        start_time = time.time()
        message = await ctx.respond("Pinging...")

        # Calculate response time
        end_time = time.time()
        response_time = round((end_time - start_time) * 1000)

        # Get websocket latency
        websocket_latency = round(self.bot.latency * 1000)

        # Get uptime
        uptime = str(datetime.timedelta(seconds=int(round(time.time() - self.start_time))))

        embed = discord.Embed(title="🏓 Pong!", color=discord.Color.green())
        embed.add_field(name="Response Time", value=f"{response_time} ms", inline=True)
        embed.add_field(name="Websocket Latency", value=f"{websocket_latency} ms", inline=True)
        embed.add_field(name="Uptime", value=uptime, inline=True)

        await message.edit_original_response(content=None, embed=embed)

    @discord.slash_command(description="Get help with bot commands")
    async def help(self, ctx, command: Optional[str] = None):
        """Show help for all commands or a specific command"""
        if command:
            await self._show_command_help(ctx, command)
        else:
            await self._show_general_help(ctx)

    async def _show_general_help(self, ctx):
        """Show general help with command categories"""
        embed = discord.Embed(
            title="Quantum Bank Help",
            description="Here are the categories of commands available:",
            color=discord.Color.blue(),
        )

        # Create a dictionary to group commands by cog
        commands_by_cog = {}

        # Organize commands by cog
        for command in self.bot.application_commands:
            if not isinstance(command, discord.SlashCommand):
                continue

            # Try to determine which cog the command belongs to
            cog_name = "Uncategorized"
            for name, cog in self.bot.cogs.items():
                # Check each command in each cog
                for cmd in cog.__cog_commands__:
                    if isinstance(cmd, discord.SlashCommand) and cmd.name == command.name:
                        cog_name = name
                        break

            # Add command to the appropriate cog group
            if cog_name not in commands_by_cog:
                commands_by_cog[cog_name] = []
            commands_by_cog[cog_name].append(command)

        # Display commands by cog
        for cog_name, cmd_list in commands_by_cog.items():
            # Skip empty categories
            if not cmd_list:
                continue

            # Format command list
            command_list = ", ".join(f"`/{c.name}`" for c in cmd_list)
            embed.add_field(name=f"{cog_name} Commands", value=command_list, inline=False)

        embed.set_footer(text="Use /help [command] for details on a specific command")
        await ctx.respond(embed=embed)

    async def _show_command_help(self, ctx, command_name: str):
        """Show detailed help for a specific command"""
        # Find the command
        command = None
        for cmd in self.bot.application_commands:
            if isinstance(cmd, discord.SlashCommand) and cmd.name.lower() == command_name.lower():
                command = cmd
                break

        if not command:
            await ctx.respond(f"Command `/{command_name}` not found.", ephemeral=True)
            return

        # Create help embed
        embed = discord.Embed(
            title=f"Help: /{command.name}",
            description=command.description or "No description provided.",
            color=discord.Color.blue(),
        )

        # Add parameter info if available
        if command.options:
            params = []
            for option in command.options:
                required = "Required" if option.required else "Optional"
                default = (
                    f" (Default: {option.default})" if hasattr(option, "default") and option.default is not None else ""
                )
                params.append(f"• **{option.name}**: {option.description} [{required}]{default}")

            if params:
                embed.add_field(name="Parameters", value="\n".join(params), inline=False)

        # Add usage example
        params_str = " ".join(f"[{o.name}]" for o in command.options if o.required)
        optional_params = " ".join(f"({o.name})" for o in command.options if not o.required)

        usage = f"/{command.name}"
        if params_str:
            usage += f" {params_str}"
        if optional_params:
            usage += f" {optional_params}"

        embed.add_field(name="Usage", value=f"`{usage}`", inline=False)

        await ctx.respond(embed=embed)

    @discord.slash_command(description="Get information about the bot")
    async def info(self, ctx):
        """Show information about the bot"""
        # Bot information
        bot_version = "1.0.0"
        python_version = platform.python_version()
        discord_py_version = discord.__version__

        # System information
        os_info = platform.platform()
        cpu_usage = psutil.cpu_percent()
        memory_usage = psutil.Process(os.getpid()).memory_info().rss / 1024**2  # Convert to MB

        # Bot statistics
        guild_count = len(self.bot.guilds)
        user_count = sum(guild.member_count for guild in self.bot.guilds)
        channel_count = sum(len(guild.channels) for guild in self.bot.guilds)

        # Create embed
        embed = discord.Embed(
            title="Quantum Bank Bot Information",
            description="A Discord banking bot with advanced financial features.",
            color=discord.Color.blue(),
        )

        embed.set_thumbnail(url=self.bot.user.avatar.url)

        # Bot section
        embed.add_field(
            name="Bot Information",
            value=f"**Version:** {bot_version}\n"
            f"**Library:** Discord.py {discord_py_version}\n"
            f"**Python:** {python_version}\n"
            f"**Uptime:** {str(datetime.timedelta(seconds=int(round(time.time() - self.start_time))))}",
            inline=False,
        )

        # System section
        embed.add_field(
            name="System Information",
            value=f"**OS:** {os_info}\n" f"**CPU Usage:** {cpu_usage}%\n" f"**Memory Usage:** {memory_usage:.2f} MB",
            inline=False,
        )

        # Stats section
        embed.add_field(
            name="Statistics",
            value=f"**Servers:** {guild_count}\n" f"**Users:** {user_count}\n" f"**Channels:** {channel_count}",
            inline=False,
        )

        # Credits
        embed.add_field(name="Credits", value="Created with ❤️ by TheCodingGuy", inline=False)

        embed.set_footer(text="Quantum Bank ⚛️ | The future of banking")

        await ctx.respond(embed=embed)

    @discord.slash_command(description="Get information about the current server")
    async def server(self, ctx):
        """Display information about the current server"""
        guild = ctx.guild
        if not guild:
            await ctx.respond("This command can only be used in a server.", ephemeral=True)
            return

        # Create embed
        embed = discord.Embed(
            title=f"{guild.name} Server Information",
            description=guild.description or "No description",
            color=discord.Color.blue(),
        )

        # Set server icon if available
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        # General server information
        created_at = int(guild.created_at.timestamp())
        embed.add_field(
            name="General Information",
            value=f"**ID:** {guild.id}\n"
            f"**Owner:** {guild.owner.mention if guild.owner else 'Unknown'}\n"
            f"**Created:** <t:{created_at}:R>\n"
            f"**Verification Level:** {guild.verification_level.name.title()}\n"
            f"**Boost Level:** {guild.premium_tier}",
            inline=False,
        )

        # Member statistics - safely check if members are available
        try:
            # Calculate bot count only if we have access to member list
            if hasattr(guild, "members") and guild.members:
                bots = sum(1 for member in guild.members if member.bot)
                humans = guild.member_count - bots
            else:
                bots = "N/A"
                humans = "N/A"

            embed.add_field(
                name="Member Statistics",
                value=f"**Total Members:** {guild.member_count}\n" f"**Humans:** {humans}\n" f"**Bots:** {bots}",
                inline=True,
            )
        except Exception as e:
            self.logger.error(f"Error getting member statistics: {str(e)}")
            embed.add_field(
                name="Member Statistics",
                value=f"**Total Members:** {guild.member_count}",
                inline=True,
            )

        # Channel statistics
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)
        embed.add_field(
            name="Channel Statistics",
            value=f"**Text Channels:** {text_channels}\n"
            f"**Voice Channels:** {voice_channels}\n"
            f"**Categories:** {categories}",
            inline=True,
        )

        # Role information
        role_count = len(guild.roles) - 1  # Subtract @everyone
        embed.add_field(name="Role Information", value=f"**Roles:** {role_count}", inline=True)

        # Server features
        if guild.features:
            features = ", ".join(f"`{feature.replace('_', ' ').title()}`" for feature in guild.features)
            embed.add_field(name="Server Features", value=features, inline=False)

        embed.set_footer(text=f"Server ID: {guild.id}")

        await ctx.respond(embed=embed)

    @discord.slash_command(description="Display the bot's privacy policy")
    async def privacy(self, ctx):
        """Display the bot's privacy policy"""
        embed = discord.Embed(
            title="Quantum Bank Privacy Policy",
            description="We take your privacy seriously. Here's how we handle your data:",
            color=discord.Color.blue(),
        )

        embed.add_field(
            name="Data Collection",
            value="We collect your Discord user ID, username, and server ID to provide banking services. "
            "We also store transaction history and account information.",
            inline=False,
        )

        embed.add_field(
            name="Data Usage",
            value="Your data is used solely for providing banking functionality within Discord. "
            "We do not sell or share your data with third parties.",
            inline=False,
        )

        embed.add_field(
            name="Data Security",
            value="We encrypt sensitive information and use industry-standard security practices "
            "to protect your data.",
            inline=False,
        )

        embed.add_field(
            name="Data Retention",
            value="Your data is retained as long as you use our services. You can request data deletion "
            "by contacting the bot owner.",
            inline=False,
        )

        embed.set_footer(text="Last Updated: 2025-03-28")

        await ctx.respond(embed=embed)

    @discord.slash_command(description="Get bot invite link and support server information")
    async def invite(self, ctx):
        """Get invite links for the bot and support server"""
        embed = discord.Embed(
            title="Invite Quantum Bank",
            description="Add Quantum Bank to your server or join our support community!",
            color=discord.Color.blue(),
        )

        # Set bot avatar in thumbnail
        embed.set_thumbnail(url=self.bot.user.avatar.url)

        # Add bot invite link with proper permissions
        permissions = discord.Permissions(
            send_messages=True,
            embed_links=True,
            attach_files=True,
            read_messages=True,
            read_message_history=True,
            add_reactions=True,
            use_application_commands=True,
        )

        invite_url = discord.utils.oauth_url(
            client_id=self.bot.user.id,
            permissions=permissions,
            scopes=("bot", "applications.commands"),
        )

        embed.add_field(
            name="Add Bot to Server",
            value=f"[Click here to invite Quantum Bank]({invite_url})",
            inline=False,
        )

        # Add support server invite
        embed.add_field(
            name="Join Support Server",
            value="[Click here to join our support server](https://discord.gg/quantumbank)",
            inline=False,
        )

        # Add website info
        embed.add_field(name="Official Website", value="[quantumbank.gg](https://quantumbank.gg)", inline=False)

        embed.set_footer(text="Thank you for using Quantum Bank!")

        await ctx.respond(embed=embed)

    @discord.slash_command(description="Get information about voting for the bot")
    async def vote(self, ctx):
        """Get links to vote for the bot on various platforms"""
        embed = discord.Embed(
            title="Vote for Quantum Bank",
            description="Support us by voting! Voting helps more people discover Quantum Bank.",
            color=discord.Color.gold(),
        )

        # Set bot avatar in thumbnail
        embed.set_thumbnail(url=self.bot.user.avatar.url)

        # Add voting links
        embed.add_field(
            name="Top.gg",
            value="[Vote on Top.gg](https://top.gg/bot/1324764735492722860/vote)",
            inline=True,
        )

        embed.add_field(
            name="Discord Bot List",
            value="[Vote on DBL](https://discordbotlist.com/bots/quantum-bank/upvote)",
            inline=True,
        )

        # Add voting benefits
        embed.add_field(
            name="Voting Benefits",
            value="• Daily voting rewards\n• Special role in support server\n• Early access to new features\n• Support the development",
            inline=False,
        )

        embed.set_footer(text="Thank you for supporting Quantum Bank!")

        await ctx.respond(embed=embed)

    @commands.slash_command(name="performance", description="Show detailed performance metrics")
    @commands.has_permissions(administrator=True)
    async def performance_metrics(self, ctx):
        """Display detailed performance metrics and statistics"""
        # Start with basic metrics
        metrics = self.bot.get_system_metrics()

        # Create embed for response
        embed = self.bot.Embed(
            title="Performance Metrics",
            description="Detailed performance and resource usage statistics",
        )

        # System metrics
        embed.add_field(
            name="🖥️ System Resources",
            value=f"**Memory Usage:** {metrics.get('memory_usage_mb', 0):.2f} MB\n"
            f"**CPU Usage:** {metrics.get('cpu_percent', 0):.1f}%\n"
            f"**Threads:** {metrics.get('thread_count', 0)}\n"
            f"**Uptime:** {self._format_uptime(metrics.get('uptime', 0))}",
            inline=False,
        )

        # Bot statistics
        embed.add_field(
            name="🤖 Bot Statistics",
            value=f"**Guilds:** {metrics.get('guilds', 0):,}\n"
            f"**Users:** {metrics.get('users', 0):,}\n"
            f"**Messages:** {metrics.get('message_count', 0):,}\n"
            f"**Commands:** {metrics.get('command_count', 0):,}",
            inline=True,
        )

        # Shard information
        embed.add_field(
            name="⚡ Sharding",
            value=f"**Latency:** {metrics.get('latency', 0):.2f} ms\n"
            f"**Shards:** {metrics.get('shards', 1)}\n"
            f"**Cluster ID:** {getattr(self.bot.config, 'CLUSTER_ID', 0)}\n"
            f"**Total Clusters:** {getattr(self.bot.config, 'TOTAL_CLUSTERS', 1)}",
            inline=True,
        )

        # Cache metrics if available
        if "cache" in metrics:
            cache = metrics["cache"]
            hit_rate = cache.get("hit_rate", 0) * 100
            embed.add_field(
                name="🔄 Cache Performance",
                value=f"**Hit Rate:** {hit_rate:.1f}%\n"
                f"**Items Cached:** {cache.get('total_items', 0):,}\n"
                f"**Cache Size:** {cache.get('memory_usage_bytes', 0) / 1024 / 1024:.2f} MB\n"
                f"**Namespaces:** {cache.get('namespaces', 0)}",
                inline=False,
            )

        # Add benchmark button
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="Run Performance Test",
                style=discord.ButtonStyle.primary,
                custom_id="run_benchmark",
            )
        )

        await ctx.respond(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_interaction(self, interaction):
        if interaction.type == discord.InteractionType.component:
            if interaction.data.get("custom_id") == "run_benchmark":
                await interaction.response.defer(ephemeral=True)

                results = await self._run_performance_benchmark(interaction)

                benchmark_embed = self.bot.Embed(
                    title="Performance Benchmark Results",
                    description="Time taken for various operations",
                )

                for name, time_ms in results.items():
                    benchmark_embed.add_field(name=name, value=f"{time_ms:.2f} ms", inline=True)

                await interaction.followup.send(embed=benchmark_embed, ephemeral=True)

    async def _run_performance_benchmark(self, interaction):
        """Run performance benchmark on key operations"""
        results = {}

        # Test database access time (with and without cache)
        if hasattr(self.bot, "db") and self.bot.db:
            # Test with cache if available
            start = time.perf_counter()
            for _ in range(5):  # Run 5 times
                # Perform a simple MongoDB operation that should be cached
                await self.bot.db.get_global_settings()
            end = time.perf_counter()
            results["DB Access (Cached)"] = (end - start) * 1000 / 5  # Average in ms

            # Test without cache
            start = time.perf_counter()
            for _ in range(5):
                # Force DB operation by using a unique timestamp
                timestamp = time.time()
                await self.bot.db.db.settings.find_one({"timestamp": timestamp})
            end = time.perf_counter()
            results["DB Access (Uncached)"] = (end - start) * 1000 / 5  # Average in ms

        # Test Discord API calls
        start = time.perf_counter()
        await self.bot.fetch_channel(interaction.channel_id)
        end = time.perf_counter()
        results["Discord API Call"] = (end - start) * 1000

        # Test memory operations (dictionary access)
        start = time.perf_counter()
        for _ in range(10000):
            _ = {"key": "value"}["key"]
        end = time.perf_counter()
        results["Memory Operations (10K)"] = (end - start) * 1000

        # Test JSON serialization
        import json

        large_obj = {"items": [{"id": i, "value": f"test_{i}"} for i in range(1000)]}

        start = time.perf_counter()
        _ = json.dumps(large_obj)
        end = time.perf_counter()
        results["JSON Serialization"] = (end - start) * 1000

        # If orjson is available, benchmark it too
        try:
            import orjson

            start = time.perf_counter()
            _ = orjson.dumps(large_obj)
            end = time.perf_counter()
            results["orjson Serialization"] = (end - start) * 1000
        except ImportError:
            pass

        return results

    def _format_uptime(self, seconds):
        """Format seconds into a readable uptime string"""
        days, remainder = divmod(int(seconds), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if seconds > 0 or not parts:
            parts.append(f"{seconds}s")

        return " ".join(parts)

    async def cog_command_error(self, ctx, error):
        """Handle errors from commands in this cog"""
        # Get the original error if it's wrapped
        error = getattr(error, "original", error)
        command_name = ctx.command.name if ctx.command else "Unknown command"

        # Log the error
        self.logger.error(f"Error in utility command {command_name}: {str(error)}")

        # Provide user-friendly error message
        if isinstance(error, discord.errors.ApplicationCommandInvokeError):
            await ctx.respond(
                "There was an error processing your command. Please try again later.",
                ephemeral=True,
            )
        elif isinstance(error, discord.errors.NotFound):
            await ctx.respond("Could not find the requested resource.", ephemeral=True)
        elif isinstance(error, discord.errors.Forbidden):
            await ctx.respond("I don't have permission to complete this action.", ephemeral=True)
        else:
            await ctx.respond(f"An unexpected error occurred: {str(error)}", ephemeral=True)

    @discord.slash_command(description="Boost the server with various perks")
    async def boost(self, ctx):
        """Show information about boosting the server"""
        embed = discord.Embed(
            title="✨ Server Boost",
            description="Support the server and get exclusive perks by boosting!",
            color=discord.Color.pink(),
        )

        embed.add_field(
            name="Benefits",
            value=(
                "• Custom role and color\n"
                "• Priority support\n"
                "• Early access to new features\n"
                "• Support the development"
            ),
            inline=False,
        )
