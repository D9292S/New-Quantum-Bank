# Developer Guide

This guide provides comprehensive information for developers who want to contribute to the Quantum Bank Discord bot.

## Development Environment Setup

### Prerequisites

- Python 3.9 or higher
- MongoDB (locally installed or remote)
- Git
- A Discord Bot Token (for testing)

### Setting Up Your Development Environment

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/quantum-bank.git
   cd quantum-bank
   ```

2. **Set up a virtual environment:**
   
   Using uv (recommended):
   ```bash
   # Install uv if you don't have it
   curl -LsSf https://astral.sh/uv/install.sh | sh
   
   # Create a virtual environment and install dependencies
   uv venv
   uv pip install -e ".[development]"  # Includes dev dependencies
   ```
   
   Using standard venv:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e ".[development]"
   ```

3. **Configure environment variables:**
   
   Create a `.env` file in the root directory with:
   ```
   BOT_TOKEN=your_discord_bot_token
   MONGO_URI=mongodb://localhost:27017/quantum_bank_dev
   DEBUG=true
   ```

4. **Run the bot in development mode:**
   ```bash
   python launcher.py --log-level verbose
   ```

## Project Structure

```
quantum-bank/
├── bot.py                 # Main bot file
├── launcher.py            # Entry point
├── requirements.txt       # Dependencies
├── pyproject.toml         # Project metadata and build configuration
├── .env.example           # Example environment variables
├── .github/               # GitHub workflows and configs
├── cogs/                  # Bot commands organized by category
│   ├── __init__.py
│   ├── accounts.py        # Account management commands
│   ├── admin.py           # Admin commands
│   ├── anime.py           # Anime-related commands
│   ├── mongo.py           # Database integration
│   └── utility.py         # Utility commands
├── helper/                # Helper modules and utilities
│   ├── __init__.py
│   ├── constants.py       # Constants and config values
│   └── exceptions.py      # Custom exceptions
├── helpers/               # Additional utilities
│   └── __init__.py
├── tests/                 # Test directory
│   ├── __init__.py
│   ├── test_accounts.py
│   └── test_mongo.py
└── logs/                  # Log files
```

## Testing

We use pytest for testing. Run the test suite with:

```bash
pytest
```

Run specific test files:

```bash
pytest tests/test_accounts.py
```

Run with coverage report:

```bash
pytest --cov=./ --cov-report=term-missing
```

### Writing Tests

- All tests should be in the `tests/` directory
- Test files should be named `test_*.py`
- Use fixtures for common setup
- Use mocking for external dependencies (Discord API, MongoDB)

Example test:

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_create_account():
    # Setup
    mock_ctx = AsyncMock()
    mock_ctx.author.id = 123456789
    
    # Execute
    with patch('cogs.mongo.Database.get_user') as mock_get_user:
        mock_get_user.return_value = None  # User doesn't exist yet
        result = await create_account(mock_ctx)
    
    # Assert
    assert "Account created successfully" in result
```

## Code Style

We follow PEP 8 guidelines with some modifications. Our codebase is linted with ruff and formatted with black. Before submitting pull requests, please run:

```bash
# Check style
ruff check .

# Format code
black .
```

## Database Schema

The MongoDB database uses the following collections:

- **users**: User account information
- **accounts**: Bank account details
- **transactions**: Transaction history
- **loans**: Active loans
- **credit**: Credit score information
- **stocks**: Stock market data
- **cache**: Temporary cached data

See [SCHEMA.md](SCHEMA.md) for detailed schema information.

## Pull Request Process

1. Create a feature branch (`git checkout -b feature/amazing-feature`)
2. Make your changes
3. Run tests and linting
4. Commit with descriptive message
5. Push to your fork
6. Open a pull request

Please ensure your PR:
- Passes all CI checks
- Includes tests for new functionality
- Updates documentation as needed
- Follows our code style guidelines

## Documentation

Please update documentation for any changes you make:

- Update docstrings for functions and classes
- Update the appropriate Markdown files in the `docs/` directory
- For new commands, update `docs/COMMANDS.md`

## Getting Help

If you need help with development:

- Open an issue on GitHub
- Discuss in our [Discord server](https://discord.gg/quantum-bank)
- Check the existing documentation 