# Quantum Bank Discord Bot

A feature-rich banking bot for Discord servers, offering virtual economy management with beautifully formatted outputs and robust database integration.

![Quantum Bank Banner](https://example.com/quantum_bank_banner.png)

## Features

- **Virtual Economy System**: Complete banking system with accounts, transactions, and interest
- **Advanced Logging**: Colorful, well-formatted console outputs with customizable verbosity
- **MongoDB Integration**: Reliable data storage with automatic reconnection
- **Performance Monitoring**: Track bot performance metrics
- **Modular Architecture**: Extensible cog-based design
- **Scalable Infrastructure**: Sharding and clustering support for large deployments
- **Beautiful UI**: Colorful, readable interface for all bot outputs

## Installation

### Prerequisites
- Python 3.8 or higher
- MongoDB database
- Discord Bot Token

### Quick Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/quantum_bank.git
   cd quantum_bank
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Create environment file**
   ```bash
   # Create .env file with the following variables:
   BOT_TOKEN=your_discord_bot_token
   MONGO_URI=your_mongodb_connection_string
   # Optional:
   MAL_CLIENT_ID=your_myanimelist_client_id
   ACTIVITY_STATUS="Quantum Bank | /help"
   ```

4. **Run the bot**
   ```bash
   python launcher.py
   ```

## Command-Line Options

Quantum Bank can be configured with various command-line arguments:

| Option | Description |
|--------|-------------|
| `--debug` | Enable debug mode |
| `--log-level` | Logging verbosity: `quiet`, `normal`, `verbose`, `debug` |
| `--performance` | Performance mode: `low`, `medium`, `high` |
| `--shards` | Number of shards to use |
| `--shardids` | Comma-separated list of shard IDs to run |
| `--cluster` | Cluster ID for this instance |
| `--clusters` | Total number of clusters |

Examples:
```bash
# Run with normal logging
python launcher.py --log-level=normal

# Run with debug logging
python launcher.py --log-level=debug

# Run with high performance mode
python launcher.py --performance=high

# Run specific shards in a cluster
python launcher.py --shards=10 --cluster=0 --clusters=3
```

## Logging System

The bot features an advanced logging system with different verbosity levels:

- **quiet**: Only shows warnings, errors, and critical information
- **normal**: Shows important logs with intelligent filtering (default)
- **verbose**: Shows all logs without filtering
- **debug**: Shows all logs plus additional debugging information

All logs are saved to the `logs` directory in separate files by category.

## Bot Commands

### Account Management
- `/create` - Create a new bank account
- `/balance` - Check your account balance
- `/deposit` - Add funds to your account
- `/withdraw` - Remove funds from your account
- `/transfer` - Transfer funds to another user

### Admin Commands
- Various admin commands for server management and bot configuration

### Utility Commands
- `/help` - Display help information
- Other utility commands for server management

## Development

### Project Structure
```
quantum_bank/
├── bot.py                  # Bot instance definition
├── launcher.py             # Entry point and configuration
├── cogs/                   # Bot extensions
│   ├── mongo.py            # Database connection
│   ├── accounts.py         # Banking functionality
│   ├── admin.py            # Admin commands
│   ├── performance_monitor.py # Performance tracking
│   └── utility.py          # Utility commands
└── logs/                   # Log files
    ├── bot.log             # Core bot operations
    ├── commands.log        # Command executions
    ├── database.log        # Database operations
    ├── performance.log     # Performance metrics
    └── errors.log          # Error messages
```

### Testing

A comprehensive test checklist is available to verify all bot functionality:
- Run `python launcher.py --log-level=verbose` for full output during testing
- Check all command functionality
- Verify database connectivity and persistence
- Test error handling and recovery

## Troubleshooting

### Common Issues

1. **MongoDB Connection Problems**
   - Verify your MongoDB URI in the `.env` file
   - Check network connectivity to your MongoDB instance
   - Examine `logs/database.log` for detailed error information

2. **Bot Not Responding to Commands**
   - Ensure bot has proper permissions in Discord
   - Check `logs/commands.log` for command processing issues
   - Verify command registration in startup logs

3. **High Resource Usage**
   - Try running with `--performance=low` for reduced resource usage
   - Check `logs/performance.log` for resource consumption patterns

For additional issues, run with `--log-level=debug` to get more detailed diagnostic information.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgements

- Discord.py library
- MongoDB team
- All contributors to this project
