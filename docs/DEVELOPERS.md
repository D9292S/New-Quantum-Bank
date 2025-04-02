# Developer Guide

This guide provides comprehensive information for developers who want to contribute to the Quantum Bank Discord bot.

## Development Environment Setup

### Prerequisites

- Python 3.12 or higher
- MongoDB Atlas (or local MongoDB instance for development)
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
   MONGODB_URI=mongodb+srv://username:password@your-cluster.mongodb.net/quantum_bank_dev?retryWrites=true&w=majority
   DEBUG=true
   PERFORMANCE_MODE=medium  # Options: low, medium, high
   ```

   > **Note:** For production environments, always use MongoDB Atlas. For local development, you can create a free tier cluster at [MongoDB Atlas](https://www.mongodb.com/cloud/atlas).

4. **Run the bot in development mode:**
   ```bash
   python launcher.py --log-level verbose
   ```

## Project Structure

```
quantum-bank/
├── bot.py                 # Main bot file
├── launcher.py            # Entry point
├── pyproject.toml         # Project metadata and build configuration
├── .env.example           # Example environment variables
├── .github/               # GitHub workflows and configs
├── optimizations/         # Performance optimization modules
│   ├── __init__.py
│   ├── memory_management.py  # Memory optimization and monitoring
│   ├── db_performance.py     # Database query caching and optimization
│   └── mongodb_improvements.py  # MongoDB-specific improvements
├── tools/                 # Development and diagnostic tools
│   ├── check_optimizations.py  # Script to verify optimizations
│   └── run_performance_tests.py  # Performance benchmark tool
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

## CI/CD Workflow

The project uses a robust CI/CD pipeline to ensure code quality and streamline deployments.

### Branch Strategy

- **Main Branch** (`main`): The stable codebase branch, used as the base for feature branches.
- **Feature Branches** (`feature/*`): For developing new features or fixing bugs.
- **Build Pipelines Branch** (`build-pipelines`): Integration branch for staging deployment.
- **Heroku Deployment Branch** (`heroku-deployment`): Production deployment branch.

### Workflow Files

Located in `.github/workflows/`:

- **Integration Tests** (`integration-tests.yml`): Runs automated tests on feature branches.
- **Staging Deployment** (`staging-deploy.yml`): Deploys to staging environment and validates changes.
- **Production Deployment** (`production-deploy.yml`): Handles advanced production deployment scenarios.
- **Heroku Deployment** (`heroku-deploy.yml`): Specifically handles Heroku production deployments.

### Development Workflow

1. Create a feature branch from `main`:
   ```bash
   git checkout main
   git pull
   git checkout -b feature/your-feature-name
   ```

2. Develop and test your feature locally.

3. Push your feature branch to trigger integration tests:
   ```bash
   git push origin feature/your-feature-name
   ```

4. Create a Pull Request to merge your feature into the `build-pipelines` branch.

5. After approval and merge, your changes will be automatically deployed to the staging environment.

6. After validation in staging, create/update a PR from `build-pipelines` to `heroku-deployment`.

7. Once approved and merged, your changes will be deployed to production.

For more detailed information about the CI/CD process, see [CI_CD_WORKFLOW_GUIDE.md](../CI_CD_WORKFLOW_GUIDE.md).

## Performance Optimization

The bot includes several performance optimization modules:

### Memory Management

Located in `optimizations/memory_management.py`, this module provides:

- Memory usage tracking and monitoring
- Automated garbage collection based on threshold
- Memory leak detection using weak references
- Resource limiting for memory-intensive operations

Usage example:
```python
from optimizations.memory_management import get_memory_manager

# Get the global memory manager instance
memory_manager = get_memory_manager()

# Check current memory usage
memory_mb = memory_manager.get_memory_usage()
print(f"Current memory usage: {memory_mb}MB")

# Force garbage collection if needed
memory_manager.force_collection()
```

### Query Caching

Located in `optimizations/db_performance.py`, this module provides:

- Caching for frequently-accessed database queries
- Query profiling to identify slow queries
- Retry mechanisms for transient database errors
- Batch processing for write operations

Usage example:
```python
from optimizations.db_performance import get_query_cache, cacheable_query

# Get the global query cache
cache = get_query_cache()

# Use the cache directly
cache.set("key", "value", ttl=300)  # Cache for 5 minutes
result = cache.get("key")

# Or use the decorator for async functions
@cacheable_query(ttl=300)
async def get_user_data(user_id):
    # Expensive database query here
    return await db.users.find_one({"user_id": user_id})
```

### Performance Testing

The `tools/` directory contains scripts for testing and benchmarking performance:

- `check_optimizations.py` - Verifies that optimizations are working correctly
- `run_performance_tests.py` - Runs benchmarks and generates performance reports

Run these tools to ensure optimizations are functioning as expected:
```bash
# Check if optimizations are working
python tools/check_optimizations.py

# Run performance benchmarks
python tools/run_performance_tests.py --quick
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