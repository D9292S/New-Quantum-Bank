# Quantum Bank Bot Installation Guide

This guide provides detailed instructions for installing and setting up the Quantum Bank Discord bot on different operating systems.

## Prerequisites

- **Python 3.12 or higher**
- **Discord Bot Token** - You'll need to create a bot application in the [Discord Developer Portal](https://discord.com/developers/applications)
- **MongoDB** (optional but recommended for full functionality)

## Installation Methods

### Automated Setup (Recommended)

We provide automated setup scripts for both Unix-based systems (Linux/macOS) and Windows. These scripts utilize the UV package manager for significantly faster installations (10-100x faster than pip).

#### For Linux/macOS

1. Open a terminal and navigate to the project directory
2. Run the setup script:
   ```bash
   ./setup.sh
   ```
3. The script will:
   - Check if Python 3.12+ is installed
   - Install the uv package manager if needed
   - Create a virtual environment
   - Install all required dependencies using UV's efficient resolver

#### For Windows

1. Open Command Prompt and navigate to the project directory
2. Run the setup batch file:
   ```
   setup.bat
   ```
3. The script will:
   - Check if Python 3.12+ is installed
   - Install the uv package manager if needed
   - Create a virtual environment
   - Install all required dependencies

### Manual Setup

If you prefer to set up manually, follow these steps:

#### Step 1: Install uv package manager

**Linux/macOS**:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows**:
```
powershell -Command "Invoke-WebRequest -UseBasicParsing -Uri 'https://astral.sh/uv/install.ps1' -OutFile '%TEMP%\uv-install.ps1' && powershell -ExecutionPolicy Bypass -File '%TEMP%\uv-install.ps1'"
```

#### Step 2: Create and activate a virtual environment

**Linux/macOS**:
```bash
uv venv
source .venv/bin/activate
```

**Windows**:
```
uv venv
.venv\Scripts\activate.bat
```

#### Step 3: Install dependencies

For basic usage:
```bash
uv pip install -e "."
```

For development (includes testing and linting tools):
```bash
uv pip install -e ".[development]"
```

## Configuration

Create a `.env` file in the root directory with your configuration:

```
# Required settings
BOT_TOKEN=your_discord_bot_token
MONGO_URI=mongodb://username:password@host:port/dbname

# Optional settings
MAL_CLIENT_ID=your_myanimelist_client_id
DEBUG=false
PERFORMANCE_MODE=medium
LOG_LEVEL=normal
ACTIVITY_STATUS=Quantum Bank | /help
```

## Running the Bot

After installation and configuration, you can run the bot using:

```bash
# Basic usage
python launcher.py

# With command-line options
python launcher.py --log-level verbose --performance high
```

## Troubleshooting

### Common Issues

1. **Python version error**: Ensure you have Python 3.12 or higher installed. Check with `python --version`.

2. **Package installation fails**: Make sure you have internet access and the required build tools.
   - On Linux: `sudo apt-get install build-essential`
   - On Windows: Install Visual C++ Build Tools

3. **Discord connection issues**: Verify your bot token is correct and the bot has proper permissions.

4. **MongoDB connection error**: Check your MongoDB URI and ensure your IP is whitelisted if using Atlas.

### Getting Help

If you're still having trouble, please:
1. Check the detailed logs in the `logs/` directory
2. Open an issue on our GitHub repository with the error details
3. Join our Discord support server for direct assistance

## Next Steps

Once you have the bot running, check out these resources:
- [Configuration Guide](./CONFIGURATION.md) - Learn about all configuration options
- [Feature Guide](./FEATURES.md) - Explore all bot features
- [Command Reference](./COMMANDS.md) - Full list of available commands
- [Developer Guide](./DEVELOPERS.md) - Information for contributing to development 