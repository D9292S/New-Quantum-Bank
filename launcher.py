import discord
import os
from collections import namedtuple
from urllib.parse import quote_plus
from dotenv import load_dotenv

import bot

load_dotenv()

Config = namedtuple(
    "Config",
    ["DEBUG", "BOT_TOKEN", "MONGO_URI"],
)

if __name__ == "__main__":
    # Construct Mongo URI with error handling
    try:
        uri = os.getenv("MONGO_URI")
        if not uri:
            uri = "mongodb://{}:{}@{}".format(
                quote_plus(os.environ["MONGO_USER"]),
                quote_plus(os.environ["MONGO_PASS"]),
                os.environ["MONGO_HOST"],
            )
    except KeyError as e:
        print(f"Error: Missing required MongoDB environment variable: {e}")
        uri = None

    config = Config(
        DEBUG=os.getenv("DEBUG") in ("1", "True", "true"),
        BOT_TOKEN=os.getenv("BOT_TOKEN"),
        MONGO_URI=uri,
    )

    if not config.BOT_TOKEN:
        print("Error: BOT_TOKEN must be set in .env")
        exit(1)

    intents = discord.Intents.default()
    intents.members = True
    intents.presences = True
    intents.messages = True
    intents.message_content = True  # Required for commands

    bot_instance = bot.ClusterBot(
        token=config.BOT_TOKEN,
        intents=intents,
        config=config,
    )

    bot_instance.run()  # No need to pass token again