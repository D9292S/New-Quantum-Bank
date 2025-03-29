# Quantum Bank Discord Bot

Quantum Bank is a feature-rich Discord economy bot with advanced banking features, built using Discord.py and MongoDB.

## Features

- 🏦 Complete banking system with accounts, transactions, and interest
- 💹 Advanced economy features including investments and stock market simulation
- 🎮 Economy-based minigames and activities
- 🔒 Secure transactions with detailed logging
- 📊 User-friendly statistics and leaderboards
- 🎨 Colorful console logs with JSON formatting
- 🔄 Seamless MongoDB integration for reliable data storage

## Prerequisites

- Python 3.8 or higher
- MongoDB database (local or Atlas)
- Discord Bot Token

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/quantum-bank-bot.git
   cd quantum-bank-bot
   ```

2. Install uv if you don't have it yet:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
   Or on Windows:
   ```bash
   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

3. Create a virtual environment and install dependencies:
   ```bash
   uv venv
   uv pip install -e "."
   ```

   For development setup, include development dependencies:
   ```bash
   uv pip install -e ".[development]"
   ```

4. Create a `.env` file in the root directory with the following variables:
   ```
   BOT_TOKEN=your_discord_bot_token
   MONGODB_URI=your_mongodb_connection_string
   MONGODB_DB_NAME=your_database_name
   ```

5. Run the bot:
   ```bash
   python launcher.py
   ```

## Configuration

You can configure various aspects of the bot by modifying the appropriate values in your `.env` file:

- `BOT_TOKEN`: Your Discord bot token
- `MONGODB_URI`: MongoDB connection string
- `MONGODB_DB_NAME`: Name of your MongoDB database
- `DEBUG_MODE`: Set to `True` to enable debug logging (default: `False`)
- `PERFORMANCE_MODE`: Set to `HIGH`, `MEDIUM`, or `LOW` (default: `MEDIUM`)
- `SHARD_COUNT`: Number of shards to use (default: `1`)
- `CLUSTER_ID`: Cluster ID for multi-process setups (default: `0`)

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Discord.py](https://github.com/Rapptz/discord.py)
- [Motor](https://github.com/mongodb/motor)
- All contributors who have helped to improve this project
