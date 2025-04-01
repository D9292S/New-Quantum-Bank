# Quantum Bank Discord Bot

Quantum Bank is a feature-rich Discord economy bot with advanced banking features, built using Pycord and MongoDB.

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
- 🚀 **Memory & database optimizations** with smart caching, memory monitoring, and batch processing

## Command Examples

### Account Management
```
/create_account - Create a new bank account with KYC verification
/balance - Check your current bank account balance
/passbook - Check your account balance and view your passbook
/view_transactions - View your transaction history
/view_account_details - View your account details
```

### Loans and Credit
```
/apply_loan amount:1000 term_months:12 - Apply for a personal loan
/repay_loan amount:100 - Make a payment towards your loan
/loan_status - Check your loan status
/credit_score - Check your credit score and credit history
/credit_report - View your detailed credit report
```

### Banking Services
```
/generate_upi - Generate a UPI ID for your account
/change_branch new_branch:"New York" - Change your bank branch
/loan_calculator amount:5000 term_months:24 - Calculate loan payments
```

## Prerequisites

- Python 3.12 or higher
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
   Or on Windows, run our setup script:
   ```
   setup.bat
   ```

3. Install the package with dependencies (uv will automatically create a virtual environment):
   ```bash
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

5. Run the bot using uv scripts:
   ```bash
   uv run run
   ```

   Or with debug mode:
   ```bash
   uv run run-debug
   ```

## Available Commands

The project includes several useful commands:

```bash
# Run the bot
python -m launcher

# Run the bot in debug mode
python -m launcher --debug

# Run the bot with high performance settings
python -m launcher --performance high

# Run the bot with verbose logging
python -m launcher --log-level verbose

# Run the bot with quiet logging (only warnings and errors)
python -m launcher --log-level quiet

# Run tests
pytest

# Run only unit tests
pytest tests/unit

# Run only integration tests
pytest tests/integration

# Run tests with coverage report
pytest --cov=./ --cov-report=term

# Run linting
ruff check .

# Format code
black .

# Check formatting without changing files
black --check .

# Fix linting issues and format code in one command
ruff check --fix . && black .
```

After installation via `uv pip install -e "."`, you can also run:

```bash
# Run the bot using the entry point
quantum-bank
```

## Advanced Configuration

Quantum Bank supports advanced configuration options for scaling and performance. These can be accessed using specialized scripts:

```bash
# Run with high performance mode
uv run run-performance-high

# Run with verbose logging
uv run run-verbose

# Run with quiet logging (only warnings and errors)
uv run run-quiet

# Run with debug mode
uv run run-debug
```

For more specific configurations, you'll need to use the launcher directly:

```bash
# Run with specific number of shards
python -m launcher --shards 3

# Run as part of a cluster
python -m launcher --cluster 0 --clusters 3

# Combine multiple options
python -m launcher --performance high --log-level verbose --shards 3
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

The bot can be easily deployed using Docker:

```bash
# Build and run using docker-compose (development mode)
docker-compose --profile dev up -d

# Build and run using docker-compose (production mode)
docker-compose --profile prod up -d

# View logs
docker-compose logs -f bot
```

For custom configurations, edit the `.env` file or override environment variables in `docker-compose.yml`.

#### Container Details

- **Bot**: Main Discord bot service
- **MongoDB**: Database for storing accounts, transactions, etc.
- **Redis**: Optional caching and shared state for clustered deployments

#### Scaling with Docker Compose

For multiple bot instances (clustered deployment):

```bash
# Scale to 3 bot instances in production mode
docker-compose --profile prod up -d --scale bot=3
```

Don't forget to properly configure your .env with appropriate sharding settings.

### VPS/Dedicated Server

For production use on a VPS, we recommend:

- A VPS with at least 1GB RAM
- Setting up a systemd service for auto-restart
- Using a monitoring solution like PM2

Example systemd service file (`/etc/systemd/system/quantum-bank.service`):

```ini
[Unit]
Description=Quantum Bank Discord Bot
After=network.target

[Service]
User=quantum
WorkingDirectory=/opt/quantum-bank
ExecStart=/usr/bin/python3 -m launcher --performance medium
Restart=always
RestartSec=10
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=quantum-bank

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl enable quantum-bank
sudo systemctl start quantum-bank
```

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Pycord](https://github.com/Pycord-Development/pycord)
- [Motor](https://github.com/mongodb/motor)
- All contributors who have helped to improve this project

## Advanced Package Management

This project uses the [uv](https://github.com/astral-sh/uv) package manager for fast, reliable Python dependency management. We provide several tools to make package management easier:

### Using the UV Tool

The project includes a convenient wrapper for common uv operations. On Windows, use `uv.bat`; on Unix systems, use `./uv.sh`:

```bash
# Update dependencies to latest compatible versions
./uv.sh update

# Clean the environment and rebuild from scratch
./uv.sh clean --dev

# Add a new package
./uv.sh add requests

# Add a development dependency
./uv.sh add --dev black

# Remove a package
./uv.sh remove requests

# List installed packages
./uv.sh list

# Check for outdated packages and compatibility issues
./uv.sh check
```

### Verifying Your Environment

To check if your environment is correctly set up for running the bot with Python 3.12+:

```bash
python scripts/check_environment.py
```

This will verify:
- Python version is 3.12+
- UV is installed and working
- Required system packages are available
- Project dependencies are correctly configured

## Performance Optimizations

Quantum Bank includes advanced performance optimizations to ensure smooth operation even with large user bases:

### Memory Management

The bot includes intelligent memory management that:
- Monitors memory usage and prevents memory leaks
- Automatically triggers garbage collection when needed
- Tracks resource-intensive operations
- Provides memory usage statistics for diagnostics

### Database Optimizations

Database performance is enhanced through:
- Smart query caching for frequently accessed data
- Batch processing for database operations
- Automatic retry mechanisms for transient errors
- Query profiling to identify and optimize slow queries

### Performance Monitoring

The bot continuously monitors its own performance:
- Real-time tracking of command execution times
- Memory usage statistics and trends
- Database query performance metrics
- Automatic detection of performance bottlenecks

To check if optimizations are functioning correctly, run:

```bash
python tools/check_optimizations.py
```

For detailed performance benchmarks, use:

```bash
python tools/run_performance_tests.py
```
