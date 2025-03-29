# Quantum Bank Discord Bot

Quantum Bank is a feature-rich Discord economy bot with advanced banking features, built using Discord.py and MongoDB.

![Quantum Bank Banner](images/quantum_bank_banner.png)

## Features

- 🏦 **Complete banking system** with accounts, transactions, and interest
- 💰 **Multiple account types** (Savings, Checking, Fixed Deposits)
- 💳 **Credit system** with credit scores and loan management
- 💹 **Advanced economy features** including investments and stock market simulation
- 🎮 **Economy-based minigames** and activities
- 🔒 **Secure transactions** with detailed logging
- 📊 **User-friendly statistics** and leaderboards
- 🎨 **Colorful console logs** with JSON formatting
- 🔄 **Seamless MongoDB integration** for reliable data storage
- ⚡ **High performance design** with sharding and clustering support

## Command Examples

### Account Management
```
/account create - Create a new bank account
/account balance - Check your current balance
/account statement - View your recent transactions
/account close - Close your bank account
```

### Transactions
```
/deposit <amount> - Deposit funds into your account
/withdraw <amount> - Withdraw funds from your account
/transfer <user> <amount> - Transfer funds to another user
```

### Loans and Credit
```
/loan apply <amount> <duration> - Apply for a loan
/loan repay <amount> - Make a payment towards your loan
/credit score - Check your credit score
```

### Investments
```
/invest <amount> <stock> - Invest in a stock
/portfolio - View your investment portfolio
/market - View current market conditions
```

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
   MONGO_URI=your_mongodb_connection_string
   MAL_CLIENT_ID=your_myanimelist_client_id  # Optional, for anime commands
   ACTIVITY_STATUS=Quantum Bank | /help  # Custom status
   DEBUG=false  # Set to true for debug mode
   ```

5. Run the bot:
   ```bash
   python launcher.py
   ```

## Advanced Configuration

Quantum Bank supports advanced configuration options for scaling and performance:

```bash
# Run with specific performance mode
python launcher.py --performance high

# Run with specific logging level
python launcher.py --log-level verbose

# Run with sharding configuration
python launcher.py --shards 3

# Run as part of a cluster 
python launcher.py --cluster 0 --clusters 3
```

You can also configure these options via environment variables in your `.env` file:

```
BOT_TOKEN=your_discord_bot_token
MONGO_URI=mongodb://username:password@host:port/dbname
DEBUG=false
PERFORMANCE_MODE=medium  # Options: low, medium, high
SHARD_COUNT=1
```

## Deployment

### Docker Deployment
```bash
# Build the Docker image
docker build -t quantum-bank .

# Run the container
docker run -d \
  --name quantum-bank \
  --restart unless-stopped \
  -e BOT_TOKEN=your_token \
  -e MONGO_URI=your_mongodb_uri \
  quantum-bank
```

### VPS/Dedicated Server
For production use, we recommend:
- A VPS with at least 1GB RAM
- Setting up a systemd service for auto-restart
- Using a monitoring solution like PM2

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Discord.py](https://github.com/Rapptz/discord.py)
- [Motor](https://github.com/mongodb/motor)
- All contributors who have helped to improve this project
