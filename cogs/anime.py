import os
from datetime import datetime

import discord
import requests
from discord.ext import commands


class AnimeView(discord.ui.View):
    def __init__(self, anime_data):
        super().__init__()
        self.anime_data = anime_data
        self.add_item(
            discord.ui.Button(
                label="📺 View on MyAnimeList",
                url=f"https://myanimelist.net/anime/{anime_data.get('id', '')}",
            )
        )

    @discord.ui.select(
        placeholder="📊 Select to view more information",
        options=[
            discord.SelectOption(label="Status", value="status", emoji="📌"),
            discord.SelectOption(label="Type", value="type", emoji="📺"),
            discord.SelectOption(label="Episodes", value="episodes", emoji="🎬"),
            discord.SelectOption(label="Score", value="score", emoji="⭐"),
            discord.SelectOption(label="Rank", value="rank", emoji="🏆"),
            discord.SelectOption(label="Popularity", value="popularity", emoji="📈"),
            discord.SelectOption(label="Members", value="members", emoji="👥"),
            discord.SelectOption(label="Favorites", value="favorites", emoji="❤️"),
        ],
    )
    async def select_callback(self, select, interaction):
        y = self.anime_data
        if select.values[0] == "status":
            await interaction.response.send_message(f"📌 Status: `{y.get('status', 'Unknown')}`", ephemeral=True)
        elif select.values[0] == "type":
            await interaction.response.send_message(f"📺 Type: `{y.get('media_type', 'Unknown')}`", ephemeral=True)
        elif select.values[0] == "episodes":
            await interaction.response.send_message(
                f"🎬 Episodes: `{y.get('num_episodes', 'Unknown')}`", ephemeral=True
            )
        elif select.values[0] == "score":
            await interaction.response.send_message(f"⭐ Score: `{y.get('mean', 'N/A')}/10`", ephemeral=True)
        elif select.values[0] == "rank":
            await interaction.response.send_message(f"🏆 Rank: `#{y.get('rank', 'N/A')}`", ephemeral=True)
        elif select.values[0] == "popularity":
            await interaction.response.send_message(f"📈 Popularity: `#{y.get('popularity', 'N/A')}`", ephemeral=True)
        elif select.values[0] == "members":
            await interaction.response.send_message(f"👥 Members: `{y.get('num_list_users', 0):,}`", ephemeral=True)
        elif select.values[0] == "favorites":
            await interaction.response.send_message(f"❤️ Favorites: `{y.get('num_favorites', 0):,}`", ephemeral=True)


COG_METADATA = {
    "name": "anime",
    "enabled": True,
    "version": "1.0",
    "description": "Search for anime information using MyAnimeList API",
}


async def setup(bot):
    if not os.getenv("MAL_CLIENT_ID"):
        bot.log.error("Anime cog requires MAL_CLIENT_ID in .env")
        return
    bot.add_cog(Anime(bot))


class Anime(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.base_url = "https://api.myanimelist.net/v2"
        self.client_id = os.getenv("MAL_CLIENT_ID")
        self.headers = {"X-MAL-CLIENT-ID": self.client_id}

    async def cog_unload(self):
        self.bot.log.info("Unloaded Anime cog")

    @discord.slash_command(description="Search for anime information from MyAnimeList")
    async def anime(self, ctx: discord.ApplicationContext, name: str):
        await ctx.defer()

        try:
            # Search for anime
            search_url = f"{self.base_url}/anime"
            params = {
                "q": name,
                "limit": 1,
                "fields": "id,title,main_picture,alternative_titles,start_date,end_date,synopsis,mean,rank,popularity,num_list_users,num_favorites,media_type,status,num_episodes,genres,rating,studios,source",
            }
            response = requests.get(search_url, params=params, headers=self.headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not data.get("data"):
                await ctx.respond("❌ No anime found with that name.")
                return

            anime_data = data["data"][0]["node"]

            # Create embed
            embed = self.bot.Embed(
                title=f"📺 {anime_data.get('title', 'Unknown Title')}",
                description=f"```{anime_data.get('synopsis', 'No synopsis available.')}```",
                url=f"https://myanimelist.net/anime/{anime_data['id']}",
            )

            if anime_data.get("main_picture", {}).get("large"):
                embed.set_thumbnail(url=anime_data["main_picture"]["large"])
            elif anime_data.get("main_picture", {}).get("medium"):
                embed.set_thumbnail(url=anime_data["main_picture"]["medium"])

            # Basic Information
            status_emoji = (
                "🟢"
                if anime_data.get("status") == "finished_airing"
                else "🔴" if anime_data.get("status") == "currently_airing" else "⚪"
            )
            basic_info = [
                f"{status_emoji} **Status:** {anime_data.get('status', 'Unknown').replace('_', ' ').title()}",
                f"📺 **Type:** {anime_data.get('media_type', 'Unknown').upper()}",
                f"🎬 **Episodes:** {anime_data.get('num_episodes', 'Unknown')}",
            ]
            embed.add_field(name="📌 Basic Information", value="\n".join(basic_info), inline=False)

            # Ratings
            ratings = [
                f"⭐ **Score:** {anime_data.get('mean', 'N/A')}/10",
                f"🏆 **Rank:** #{anime_data.get('rank', 'N/A')}",
                f"📈 **Popularity:** #{anime_data.get('popularity', 'N/A')}",
            ]
            embed.add_field(name="📊 Ratings", value="\n".join(ratings), inline=False)

            # Community
            community = [
                f"👥 **Members:** {anime_data.get('num_list_users', 0):,}",
                f"❤️ **Favorites:** {anime_data.get('num_favorites', 0):,}",
            ]
            embed.add_field(name="🌟 Community", value="\n".join(community), inline=False)

            # Add genres if available
            if anime_data.get("genres"):
                genres = [f"🎯 {genre['name']}" for genre in anime_data["genres"]]
                embed.add_field(name="🎯 Genres", value=" • ".join(genres), inline=False)

            # Add aired date if available
            if anime_data.get("start_date"):
                try:
                    aired_date = datetime.strptime(anime_data["start_date"], "%Y-%m-%d")
                    embed.add_field(name="📅 Aired", value=aired_date.strftime("%B %d, %Y"), inline=True)
                except ValueError:
                    pass

            embed.set_footer(
                text="Data from MyAnimeList",
                icon_url="https://cdn.myanimelist.net/img/sp/icon/apple-touch-icon-256.png",
            )

            # Create view with select menu
            view = AnimeView(anime_data)

            await ctx.respond(embed=embed, view=view)

        except requests.RequestException as e:
            await ctx.respond(f"❌ Failed to fetch anime data: {e}", ephemeral=True)
        except Exception as e:
            await ctx.respond(f"❌ An error occurred: {e}", ephemeral=True)
