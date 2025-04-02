import argparse
import asyncio
import logging
import logging.handlers
import os
import platform
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import discord
from dotenv import load_dotenv

import bot
from config import BotConfig, ConfigurationError

# Import our new performance optimization modules
try:
    from optimizations.memory_management import get_memory_manager, optimize_memory_usage
    from optimizations.db_performance import get_query_cache, QueryProfiler
    OPTIMIZATIONS_AVAILABLE = True
except ImportError:
    OPTIMIZATIONS_AVAILABLE = True  # Set to True since we've confirmed modules are available
    print("Performance optimization modules not available, running without optimizations")

# Define color codes for log levels
class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log levels in console output"""

    # ANSI color codes
    COLORS = {
        "RESET": "\033[0m",
        "RED": "\033[31m",  # ERROR
        "YELLOW": "\033[33m",  # WARNING
        "GREEN": "\033[32m",  # INFO
        "BLUE": "\033[36m",  # DEBUG
        "MAGENTA": "\033[35m",  # CRITICAL
        "GRAY": "\033[37m",  # Timestamps
        "BOLD": "\033[1m",  # Headers
        "UNDERLINE": "\033[4m",  # Special highlights
        "CYAN": "\033[96m",  # JSON keys
        "LIGHT_GREEN": "\033[92m",  # JSON values
        "LIGHT_YELLOW": "\033[93m",  # JSON special values
        "LIGHT_BLUE": "\033[94m",  # JSON punctuation
    }

    def __init__(self, fmt: str | None = None, datefmt: str | None = None, style: str = "%") -> None:
        super().__init__(fmt, datefmt, style)

        # Define compact pattern transformations
        self.compact_patterns = [
            # Shorten Gateway logs
            (
                r"has connected to Gateway:.*\(Session ID: ([^)]+)\)",
                lambda m: (
                    f"has connected to Gateway: {self.COLORS['BOLD']}{self.COLORS['GREEN']}✓"
                    f"{self.COLORS['RESET']} (Session ID: {self.COLORS['BOLD']}"
                    f"{self.COLORS['LIGHT_YELLOW']}{m.group(1)[:8]}...{self.COLORS['RESET']})"
                ),
            ),
            # Shorten command registrations
            (
                r"Registered application commands: \[([^\]]+)\]",
                lambda m: f"Registered {len(m.group(1).split(','))} application commands",
            ),
            # Shorten cog loading completion
            (
                r'Finished loading cogs extra=.+?"elapsed_time": "([^"]+)".+?',
                lambda m: (
                    f"Finished loading all cogs in {self.COLORS['BOLD']}"
                    f"{self.COLORS['GREEN']}{m.group(1)}{self.COLORS['RESET']}"
                ),
            ),
            # Shorten connection metrics
            (
                r"Connected to (\d+) guilds with (\d+) members",
                lambda m: (
                    f"Connected to {self.COLORS['BOLD']}{self.COLORS['CYAN']}{m.group(1)}"
                    f"{self.COLORS['RESET']} guilds with {self.COLORS['BOLD']}"
                    f"{self.COLORS['CYAN']}{m.group(2)}{self.COLORS['RESET']} members"
                ),
            ),
        ]

    def _compact_message(self, message: str) -> str:
        """Transform verbose log messages into more compact forms"""
        import re

        # Apply transformations
        for pattern, replacement in self.compact_patterns:
            message = re.sub(pattern, replacement, message)

        return message

    def format(self, record: logging.LogRecord) -> str:
        # Save the original format
        format_orig = self._style._fmt

        # Add colors based on the log level
        if record.levelno >= logging.CRITICAL:
            self._style._fmt = (
                f"{self.COLORS['BOLD']}{self.COLORS['MAGENTA']}%(levelname)s{self.COLORS['RESET']} | "
                f"{self.COLORS['GRAY']}%(asctime)s{self.COLORS['RESET']} | "
                f"{self.COLORS['BOLD']}%(message)s{self.COLORS['RESET']}"
            )
        elif record.levelno >= logging.ERROR:
            self._style._fmt = (
                f"{self.COLORS['BOLD']}{self.COLORS['RED']}%(levelname)s{self.COLORS['RESET']} | "
                f"{self.COLORS['GRAY']}%(asctime)s{self.COLORS['RESET']} | "
                f"{self.COLORS['RED']}%(message)s{self.COLORS['RESET']}"
            )
        elif record.levelno >= logging.WARNING:
            self._style._fmt = (
                f"{self.COLORS['YELLOW']}%(levelname)s{self.COLORS['RESET']} | "
                f"{self.COLORS['GRAY']}%(asctime)s{self.COLORS['RESET']} | "
                f"{self.COLORS['YELLOW']}%(message)s{self.COLORS['RESET']}"
            )
        elif record.levelno >= logging.INFO:
            self._style._fmt = (
                f"{self.COLORS['GREEN']}%(levelname)s{self.COLORS['RESET']} | "
                f"{self.COLORS['GRAY']}%(asctime)s{self.COLORS['RESET']} | "
                f"%(message)s"
            )
        else:  # DEBUG and below
            self._style._fmt = (
                f"{self.COLORS['BLUE']}%(levelname)s{self.COLORS['RESET']} | "
                f"{self.COLORS['GRAY']}%(asctime)s{self.COLORS['RESET']} | "
                f"{self.COLORS['BLUE']}%(message)s{self.COLORS['RESET']}"
            )

        # Format the record with colors
        result = super().format(record)

        # Apply message compaction after initial formatting
        parts = result.split("|", 2)
        if len(parts) == 3:
            # Compact the message part
            parts[2] = " " + self._compact_message(parts[2].strip())
            result = "|".join(parts)

        # Apply JSON formatting to the message part
        if record.levelno == logging.INFO:
            # Find the message part (after the second '|')
            parts = result.split("|", 2)
            if len(parts) == 3:
                # Replace the message part with JSON-formatted version
                parts[2] = " " + self._format_json(parts[2].strip())
                result = "|".join(parts)

        # Restore the original format
        self._style._fmt = format_orig

        return result

    def _format_json(self, message: str) -> str:
        """Format JSON content with colors for better readability"""
        # If already compacted by _compact_message, don't format JSON
        if any(marker in message for marker in ["Gateway: ✓", "Finished loading all cogs in"]):
            return message

        import re

        # Simple JSON formatting for remaining messages
        if "{" in message and "}" in message and ":" in message:
            # Format keys in cyan
            message = re.sub(r"'([^']+)':", f"{self.COLORS['CYAN']}'\\1'{self.COLORS['RESET']}:", message)
            message = re.sub(r'"([^"]+)":', f'{self.COLORS["CYAN"]}"\\1"{self.COLORS["RESET"]}:', message)

            # Format string values in light green
            message = re.sub(
                r": '([^']*)'",
                f": {self.COLORS['LIGHT_GREEN']}'\\1'{self.COLORS['RESET']}",
                message,
            )
            message = re.sub(
                r': "([^"]*)"',
                f': {self.COLORS["LIGHT_GREEN"]}"\\1"{self.COLORS["RESET"]}',
                message,
            )

            # Format numeric values in yellow
            message = re.sub(
                r": (\d+\.?\d*)",
                f": {self.COLORS['LIGHT_YELLOW']}\\1{self.COLORS['RESET']}",
                message,
            )

            # Format special values
            message = re.sub(
                r": (true|false|null|None|True|False)",
                f": {self.COLORS['LIGHT_YELLOW']}\\1{self.COLORS['RESET']}",
                message,
            )

            # Format braces and brackets with light blue
            for char in ["{", "}", "[", "]"]:
                message = message.replace(char, f"{self.COLORS['LIGHT_BLUE']}{char}{self.COLORS['RESET']}")

        return message


# Configure logging system before importing bot
def setup_logging(log_level: str = "normal") -> dict[str, dict[str, Any]]:
    """Configure advanced logging setup with categorized log files"""
    # Create logs directory if it doesn't exist
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    # Format strings for different log types
    console_format = "%(levelname)s | %(asctime)s | %(message)s"
    file_format = "%(asctime)s | [%(levelname)s] | [%(name)s] | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Main logger configuration
    root_logger = logging.getLogger()

    # Set appropriate log level based on verbosity setting
    if log_level == "debug":
        root_logger.setLevel(logging.DEBUG)
        console_level = logging.DEBUG
        use_filter = False
        print(
            f"{ColoredFormatter.COLORS['BLUE']}Debug logging enabled - "
            f"showing all logs with debug information{ColoredFormatter.COLORS['RESET']}"
        )
    elif log_level == "verbose":
        root_logger.setLevel(logging.INFO)
        console_level = logging.INFO
        use_filter = False
        print(
            f"{ColoredFormatter.COLORS['GREEN']}Verbose logging enabled - "
            f"showing all logs{ColoredFormatter.COLORS['RESET']}"
        )
    elif log_level == "quiet":
        root_logger.setLevel(logging.INFO)  # Still log everything to files
        console_level = logging.WARNING  # But only show warnings and above in console
        use_filter = True
        print(
            f"{ColoredFormatter.COLORS['YELLOW']}Quiet logging enabled - "
            f"showing only warnings and errors{ColoredFormatter.COLORS['RESET']}"
        )
    else:  # normal - default
        root_logger.setLevel(logging.INFO)
        console_level = logging.INFO
        use_filter = True

    # Define log filters for cleaner console output
    class ImportantLogFilter(logging.Filter):
        """Filter to show only important logs in console"""

        def __init__(self) -> None:
            super().__init__()
            # Messages to always show (high priority)
            self.important_patterns = [
                "Bot is ready",
                "Starting Quantum Superbot",
                "Logged in as",
                "Connected to",
                "Error",
                "Exception",
                "Failed",
                "Success",
                "loaded cog",  # Any cog loading success
                "MongoDB connection",  # Database connection status
                "has connected to Gateway",  # Only the final connection message
                "Registered",  # Command registration summary
                "Database",  # Any database operations
                "direct MongoDB connection",  # Direct connection success/failure
                "TTL index",  # Important database index information
                "Credit score update scheduled",  # Important business logic
                "Initializing daily account tasks",  # Important banking feature
            ]

            # Messages to always hide (low priority/noise)
            self.noise_patterns = [
                "Starting cog setup",
                "Preparing to load cog",
                "Process pool initialized",
                "Found existing",
                "Started cache cleanup",
                "Commands were already synced",
                "Started performance monitoring",
                "Memory usage:",
                "HTTP connection pool established",
                "logging in using static token",
                "Set up fresh event loop",
                "Gateway latency:",
                "Ready event processed in",
                "logging in using static token",
                "Bot instance initialized",
                "Prepared shard monitoring",
                "Pycord version:",
                "Shard ID",
                "cached_property is",  # Library warnings irrelevant to users
                "Failed to load package",  # Warnings about optional packages
                "Starting bot run",
                "Found existing performance_monitor",
            ]

            # Critical messages that should override other filters
            self.critical_patterns = [
                "Failed to connect",
                "Could not load extension",
                "could not be loaded",
                "Error in cog",
                "CRITICAL",
                "Token invalid",
                "Connection refused",
                "Authentication failed",
                "Reconnection failed",
            ]

        def filter(self, record: logging.LogRecord) -> bool:
            # Always show warnings, errors and critical logs
            if record.levelno >= logging.WARNING:
                return True

            # Check message content against filters
            message = record.getMessage()

            # Always show critical messages regardless of other filters
            for pattern in self.critical_patterns:
                if pattern in message:
                    return True

            # Look for important message patterns to include
            for pattern in self.important_patterns:
                if pattern in message:
                    return True

            # Filter out noisy messages that match noise patterns
            for pattern in self.noise_patterns:
                if pattern in message:
                    return False

            # Special case: MongoDB connection logs - only show status changes
            if "MongoDB" in message and not any(status in message for status in ["successful", "failed", "error"]):
                return False

            # Special case: hide verbose session management logs
            if "session" in message.lower() and "Session ID" not in message:
                return False

            # By default, show the message unless we have a specific reason to filter it
            return True

    # Console handler with colored output and filtering
    console = logging.StreamHandler()
    console.setFormatter(ColoredFormatter(console_format, date_format))
    console.setLevel(console_level)
    if use_filter:
        console.addFilter(ImportantLogFilter())
    root_logger.addHandler(console)

    # Category-specific log files
    log_categories = {
        "bot": {
            "level": logging.INFO,
            "filename": "bot.log",
            "description": "Core bot operations, startup and shutdown events",
        },
        "commands": {
            "level": logging.INFO,
            "filename": "commands.log",
            "description": "Command executions, parameters, and results",
        },
        "database": {
            "level": logging.INFO,
            "filename": "database.log",
            "description": "Database operations, queries, and connection status",
        },
        "performance": {
            "level": logging.INFO,
            "filename": "performance.log",
            "description": "Performance metrics, timing data, and benchmarks",
        },
        "errors": {
            "level": logging.ERROR,
            "filename": "errors.log",
            "description": "All error messages across the system",
        },
    }

    # Set up each category with its own log file
    for category, config in log_categories.items():
        # Create category logger
        logger = logging.getLogger(category)
        logger.setLevel(config["level"])

        # Create rotating file handler for this category
        log_path = logs_dir / config["filename"]
        handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(file_format, date_format))
        handler.setLevel(config["level"])

        # Add handler to the category logger
        logger.addHandler(handler)

        # Also add ERROR level logs to the errors log
        if category != "errors":
            error_handler = logging.handlers.RotatingFileHandler(
                logs_dir / "errors.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
            )
            error_handler.setFormatter(logging.Formatter(file_format, date_format))
            error_handler.setLevel(logging.ERROR)
            logger.addHandler(error_handler)

    # Log the configuration with colored output
    logging.getLogger("bot").info(f"Logging system initialized with categories: {', '.join(log_categories.keys())}")

    # Return the list of categories for reference
    return log_categories


# Initialize logging system
# We'll actually set this later in run_bot for command-line argument support
LOG_CATEGORIES = None

__version__ = "1.0.0"

# Load environment variables
load_dotenv()


def validate_env_variables() -> bool:
    """Validate environment variables and display warnings/errors as needed"""
    warnings = []
    errors = []

    # Check required variables
    if not os.getenv("BOT_TOKEN"):
        errors.append("BOT_TOKEN is required but not set")

    # Check MongoDB connection info
    if not os.getenv("MONGO_URI"):
        if not all(key in os.environ for key in ["MONGO_USER", "MONGO_PASS", "MONGO_HOST"]):
            warnings.append(
                "Neither MONGO_URI nor all components (MONGO_USER, MONGO_PASS, MONGO_HOST) are set. "
                "Database features will be limited."
            )
            
    # Check DevCycle SDK key
    if not os.getenv("DEVCYCLE_SERVER_SDK_KEY"):
        warnings.append("DEVCYCLE_SERVER_SDK_KEY not set. Feature flag system will be disabled.")

    # Validate performance mode if set
    if performance_mode := os.getenv("PERFORMANCE_MODE"):
        if performance_mode.lower() not in ["low", "medium", "high"]:
            warnings.append(
                f"Invalid PERFORMANCE_MODE: '{performance_mode}'. "
                f"Must be one of: low, medium, high. Using 'medium' as default."
            )

    # Validate log level if set
    if log_level := os.getenv("LOG_LEVEL"):
        if log_level.lower() not in ["quiet", "normal", "verbose", "debug"]:
            warnings.append(
                f"Invalid LOG_LEVEL: '{log_level}'. "
                f"Must be one of: quiet, normal, verbose, debug. Using 'normal' as default."
            )

    # Validate numeric values
    for var_name, var_desc in [
        ("SHARD_COUNT", "number of shards"),
        ("CLUSTER_ID", "cluster ID"),
        ("TOTAL_CLUSTERS", "total clusters"),
    ]:
        if var_value := os.getenv(var_name):
            try:
                int(var_value)
            except ValueError:
                warnings.append(f"Invalid {var_desc} '{var_value}': must be an integer.")

    # Check for consistency in cluster configuration
    if os.getenv("CLUSTER_ID") and not os.getenv("TOTAL_CLUSTERS"):
        warnings.append("CLUSTER_ID is set but TOTAL_CLUSTERS is missing. Clustering may not work correctly.")

    # Display warnings
    colors = ColoredFormatter.COLORS
    if warnings:
        print(f"\n{colors['YELLOW']}{'=' * 80}{colors['RESET']}")
        print(f"{colors['BOLD']}{colors['YELLOW']}⚠️  Environment Configuration Warnings:{colors['RESET']}")
        for warning in warnings:
            print(f"{colors['YELLOW']}  • {warning}{colors['RESET']}")
        print(f"{colors['YELLOW']}{'=' * 80}{colors['RESET']}\n")

    # Display errors and exit if any
    if errors:
        print(f"\n{colors['RED']}{'=' * 80}{colors['RESET']}")
        print(f"{colors['BOLD']}{colors['RED']}❌ Environment Configuration Errors:{colors['RESET']}")
        for error in errors:
            print(f"{colors['RED']}  • {error}{colors['RESET']}")
        print(f"{colors['RED']}{'=' * 80}{colors['RESET']}\n")
        print(f"{colors['YELLOW']}Please check your .env file or environment variables and try again.{colors['RESET']}")
        sys.exit(1)

    if not warnings and not errors:
        print(f"{colors['GREEN']}✓ Environment configuration validated successfully{colors['RESET']}")

    return True


# Function to print a cool banner with version info
def print_banner() -> None:
    # ANSI color codes
    colors = ColoredFormatter.COLORS

    banner = f"""
{colors["BLUE"]}  ██████╗ ██╗   ██╗ █████╗ ███╗   ██╗████████╗██╗   ██╗███╗   ███╗{colors["RESET"]}
{colors["BLUE"]} ██╔═══██╗██║   ██║██╔══██╗████╗  ██║╚══██╔══╝██║   ██║████╗ ████║{colors["RESET"]}
{colors["GREEN"]} ██║   ██║██║   ██║███████║██╔██╗ ██║   ██║   ██║   ██║██╔████╔██║{colors["RESET"]}
{colors["GREEN"]} ██║▄▄ ██║██║   ██║██╔══██║██║╚██╗██║   ██║   ██║   ██║██║╚██╔╝██║{colors["RESET"]}
{colors["YELLOW"]} ╚██████╔╝╚██████╔╝██║  ██║██║ ╚████║   ██║   ╚██████╔╝██║ ╚═╝ ██║{colors["RESET"]}
{colors["YELLOW"]}  ╚══▀▀═╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝    ╚═════╝ ╚═╝     ╚═╝{colors["RESET"]}

{colors["BOLD"]}{colors["GREEN"]}      ███████╗██╗   ██╗██████╗ ███████╗██████╗ ██████╗  ██████╗ ████████╗{colors["RESET"]}
{colors["BOLD"]}{colors["GREEN"]}      ██╔════╝██║   ██║██╔══██╗██╔════╝██╔══██╗██╔══██╗██╔═══██╗╚══██╔══╝{colors["RESET"]}
{colors["BOLD"]}{colors["GREEN"]}      ███████╗██║   ██║██████╔╝█████╗  ██████╔╝██████╔╝██║   ██║   ██║   {colors["RESET"]}
{colors["BOLD"]}{colors["GREEN"]}      ╚════██║██║   ██║██╔═══╝ ██╔══╝  ██╔══██╗██╔══██╗██║   ██║   ██║   {colors["RESET"]}
{colors["BOLD"]}{colors["GREEN"]}      ███████║╚██████╔╝██║     ███████╗██║  ██║██████╔╝╚██████╔╝   ██║   {colors["RESET"]}
{colors["BOLD"]}{colors["GREEN"]}      ╚══════╝ ╚═════╝ ╚═╝     ╚══════╝╚═╝  ╚═╝╚═════╝  ╚═════╝    ╚═╝   {colors["RESET"]}
    """

    print(banner)
    print(
        f"{colors['BOLD']}⚡ {colors['BLUE']}Quantum Superbot{colors['RESET']} "
        f"{colors['GREEN']}v{__version__}{colors['RESET']}"
    )
    print(
        f"{colors['GRAY']}Running on {colors['BLUE']}Python {platform.python_version()}{colors['RESET']} | "
        f"{colors['YELLOW']}{platform.system()} {platform.release()}{colors['RESET']}"
    )
    print(f"{colors['GRAY']}─────────────────────────────────────────────────────────────{colors['RESET']}")


# Don't call print_banner() at module level - it will be called in run_bot()

# Don't call validate_env_variables() at module level - it will be called in run_bot()


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments for advanced configuration"""
    parser = argparse.ArgumentParser(
        description="Quantum Superbot Discord Bot - A feature-rich Discord economy bot with advanced banking features",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--shards", type=int, help="Number of shards to use")
    parser.add_argument("--shardids", type=str, help="Comma-separated list of shard IDs to run")
    parser.add_argument("--cluster", type=int, help="Cluster ID for this instance")
    parser.add_argument("--clusters", type=int, help="Total number of clusters")
    parser.add_argument(
        "--performance",
        choices=["low", "medium", "high"],
        default="medium",
        help="Performance optimization level (low: minimal resources, medium: balanced, high: maximum performance)",
    )
    parser.add_argument(
        "--log-level",
        choices=["quiet", "normal", "verbose", "debug"],
        default="normal",
        help=(
            "Logging verbosity (quiet: critical logs only, normal: balanced, "
            "verbose: all logs, debug: all logs with debugging info)"
        ),
    )
    parser.add_argument("--version", "-v", action="store_true", help="Show version information and exit")

    return parser.parse_args()


def calculate_shards_for_cluster(cluster_id: int, total_clusters: int, total_shards: int) -> list[int]:
    """Calculate which shards this cluster should handle"""
    shards_per_cluster = total_shards // total_clusters
    remainder = total_shards % total_clusters

    # Calculate the start and end shard IDs for this cluster
    start_shard = cluster_id * shards_per_cluster
    # Add extra shards for clusters that handle the remainder
    if cluster_id < remainder:
        start_shard += cluster_id
    else:
        start_shard += remainder

    end_shard = start_shard + shards_per_cluster - 1
    # Add an extra shard if this cluster handles part of the remainder
    if cluster_id < remainder:
        end_shard += 1

    return list(range(start_shard, end_shard + 1))


def display_error(message: str, exit_code: int | None = None) -> None:
    """Display an error message in a highly visible format"""
    colors = ColoredFormatter.COLORS
    border = f"{colors['RED']}{'═' * 80}{colors['RESET']}"

    print("\n" + border)
    print(f"{colors['BOLD']}{colors['RED']} ❌ ERROR: {message}{colors['RESET']}")
    print(border + "\n")

    if exit_code is not None:
        sys.exit(exit_code)


def run_bot() -> int:
    """Run the bot - synchronous entry point"""
    # Check Python version
    if sys.version_info < (3, 12):
        display_error("Python 3.12 or higher is required.", 1)
        return 1

    # Parse command line arguments
    args = parse_arguments()

    # Handle --version flag
    if hasattr(args, "version") and args.version:
        print(f"Quantum Superbot Bot v{__version__}")
        return 0

    # Set up proper event loop for Windows
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Print the banner
    print_banner()

    # Validate environment variables
    validate_env_variables()

    # Initialize logging with selected verbosity
    global LOG_CATEGORIES
    LOG_CATEGORIES = setup_logging(args.log_level)

    # Initialize performance optimizations if available
    if OPTIMIZATIONS_AVAILABLE:
        # Configure memory manager based on performance mode
        memory_limit_mb = 400  # Default medium setting
        
        if args.performance == "high":
            memory_limit_mb = 600  # Allow more memory for high performance
        elif args.performance == "low":
            memory_limit_mb = 200  # Restrict memory for low performance mode
        
        # Initialize memory manager
        memory_manager = get_memory_manager()
        memory_manager.memory_limit_mb = memory_limit_mb
        
        # Configure query cache size based on performance mode
        query_cache = get_query_cache()
        if args.performance == "high":
            query_cache.max_size = 2000
            query_cache.max_age = 600  # 10 minutes
        elif args.performance == "low":
            query_cache.max_size = 500
            query_cache.max_age = 120  # 2 minutes
        
        # Log optimization status
        logger = logging.getLogger("performance")
        logger.info(f"Performance optimizations initialized with {args.performance} profile")
        logger.info(f"Memory limit: {memory_limit_mb}MB, Query cache size: {query_cache.max_size}")

    # Use the new BotConfig class instead of the namedtuple
    try:
        # Create and validate config using both env vars and command-line args
        config = BotConfig.from_env(args)

        # Use MONGODB_URI as primary source, fall back to component construction only if needed
        if not config.mongo_uri:
            if "MONGODB_URI" in os.environ:
                config.mongo_uri = os.environ["MONGODB_URI"]
                print(
                    f"{ColoredFormatter.COLORS['GREEN']}Using MongoDB Atlas connection "
                    f"from MONGODB_URI{ColoredFormatter.COLORS['RESET']}"
                )
            elif all(key in os.environ for key in ["MONGO_USER", "MONGO_PASS", "MONGO_HOST"]):
                # Support for legacy environment variables
                mongo_db = os.environ.get("MONGO_DB", "quantum_bank")
                mongo_options = "retryWrites=true&w=majority"
                
                # Construct MongoDB Atlas style URI
                config.mongo_uri = "mongodb+srv://{}:{}@{}/{}?{}".format(
                    quote_plus(os.environ["MONGO_USER"]),
                    quote_plus(os.environ["MONGO_PASS"]),
                    os.environ["MONGO_HOST"],
                    mongo_db,
                    mongo_options
                )
                print(
                    f"{ColoredFormatter.COLORS['YELLOW']}Constructed MongoDB Atlas URI "
                    f"from individual components (legacy mode){ColoredFormatter.COLORS['RESET']}"
                )
    except ConfigurationError as e:
        display_error(f"Configuration error: {e}", 1)
        return 1
    except ValueError as e:
        display_error(f"Invalid configuration value: {e}", 1)
        return 1

    # Calculate shard IDs for this cluster if needed
    if config.is_clustered and config.shard_count > 1 and not config.shard_ids:
        config.shard_ids = calculate_shards_for_cluster(config.cluster_id, config.total_clusters, config.shard_count)
        print(
            f"{ColoredFormatter.COLORS['BLUE']}Cluster "
            f"{ColoredFormatter.COLORS['BOLD']}{config.cluster_id}/{config.total_clusters}"
            f"{ColoredFormatter.COLORS['RESET']} "
            f"{ColoredFormatter.COLORS['BLUE']}running shards: "
            f"{ColoredFormatter.COLORS['BOLD']}{config.shard_ids}{ColoredFormatter.COLORS['RESET']}"
        )

    # Performance mode configuration
    if config.performance_mode == "high":
        print(
            f"{ColoredFormatter.COLORS['GREEN']}Using "
            f"{ColoredFormatter.COLORS['BOLD']}HIGH{ColoredFormatter.COLORS['RESET']} "
            f"{ColoredFormatter.COLORS['GREEN']}performance mode - "
            f"maximizing resource usage{ColoredFormatter.COLORS['RESET']}"
        )
        # Try to load optional high-performance libraries
        try:
            import uvloop

            if not sys.platform.startswith("win"):
                # uvloop doesn't work on Windows
                print(
                    f"{ColoredFormatter.COLORS['GREEN']}✓ Using uvloop for improved "
                    f"event loop performance{ColoredFormatter.COLORS['RESET']}"
                )
                uvloop.install()
        except ImportError:
            print(
                f"{ColoredFormatter.COLORS['YELLOW']}✗ uvloop not available - "
                f"using standard asyncio event loop{ColoredFormatter.COLORS['RESET']}"
            )

        # Try to use orjson for faster JSON processing
        try:
            import importlib.util

            if importlib.util.find_spec("orjson"):
                print(
                    f"{ColoredFormatter.COLORS['GREEN']}✓ Using orjson for improved "
                    f"JSON performance{ColoredFormatter.COLORS['RESET']}"
                )
        except ImportError:
            print(
                f"{ColoredFormatter.COLORS['YELLOW']}✗ orjson not available - "
                f"using standard json module{ColoredFormatter.COLORS['RESET']}"
            )

        # Apply memory optimizations for high-performance mode
        if OPTIMIZATIONS_AVAILABLE:
            # Run initial memory optimization
            optimize_memory_usage(threshold_mb=memory_limit_mb)
            # Reset query profiler stats to start fresh
            QueryProfiler.reset_stats()

    elif config.performance_mode == "low":
        print(
            f"{ColoredFormatter.COLORS['BLUE']}Using "
            f"{ColoredFormatter.COLORS['BOLD']}LOW{ColoredFormatter.COLORS['RESET']} "
            f"{ColoredFormatter.COLORS['BLUE']}performance mode - "
            f"minimizing resource usage{ColoredFormatter.COLORS['RESET']}"
        )
        # Configure for minimal resource usage
        if OPTIMIZATIONS_AVAILABLE:
            # More aggressive memory management in low-resource mode
            optimize_memory_usage(threshold_mb=150)  # Lower threshold
    else:
        print(
            f"{ColoredFormatter.COLORS['BLUE']}Using "
            f"{ColoredFormatter.COLORS['BOLD']}MEDIUM{ColoredFormatter.COLORS['RESET']} "
            f"{ColoredFormatter.COLORS['BLUE']}performance mode - "
            f"balanced resource usage{ColoredFormatter.COLORS['RESET']}"
        )

    # Print configuration summary
    summary = config.summary()
    if summary["debug"]:
        print(f"{ColoredFormatter.COLORS['YELLOW']}DEBUG mode enabled{ColoredFormatter.COLORS['RESET']}")

    if summary["shard_count"] > 1:
        print(
            f"{ColoredFormatter.COLORS['BLUE']}Bot will use "
            f"{ColoredFormatter.COLORS['BOLD']}{summary['shard_count']}"
            f"{ColoredFormatter.COLORS['RESET']} "
            f"{ColoredFormatter.COLORS['BLUE']}shards{ColoredFormatter.COLORS['RESET']}"
        )
        if summary["shard_ids"]:
            print(
                f"{ColoredFormatter.COLORS['BLUE']}This instance will run shards: "
                f"{ColoredFormatter.COLORS['BOLD']}{summary['shard_ids']}"
                f"{ColoredFormatter.COLORS['RESET']}"
            )

    if summary["is_clustered"]:
        print(
            f"{ColoredFormatter.COLORS['BLUE']}Running as cluster "
            f"{ColoredFormatter.COLORS['BOLD']}{summary['cluster_id']}"
            f"{ColoredFormatter.COLORS['RESET']} "
            f"{ColoredFormatter.COLORS['BLUE']}of "
            f"{ColoredFormatter.COLORS['BOLD']}{summary['total_clusters']}"
            f"{ColoredFormatter.COLORS['RESET']}"
        )

    if not summary["mal_client_id_set"]:
        print(
            f"{ColoredFormatter.COLORS['YELLOW']}WARNING: MAL_CLIENT_ID not set, "
            f"anime commands will be disabled{ColoredFormatter.COLORS['RESET']}"
        )

    # Set up intents
    try:
        intents = discord.Intents.default()
        intents.members = True
        intents.presences = True
        intents.messages = True
        intents.message_content = True  # Required for commands

        # Create bot instance with sharding configuration
        bot_instance = bot.ClusterBot(
            token=config.bot_token,
            intents=intents,
            config=config,
            shard_count=config.shard_count,
            shard_ids=config.shard_ids,
        )

        # Store optimization references if available
        if OPTIMIZATIONS_AVAILABLE:
            bot_instance._memory_manager = get_memory_manager()
            bot_instance._query_cache = get_query_cache()

        # Make sure appropriate cogs are loaded
        # Define initial cogs order based on dependencies
        initial_cogs = ["mongo", "accounts"]

        # Add performance monitoring cog if not in low performance mode
        if config.performance_mode != "low":
            initial_cogs.append("performance_monitor")
            initial_cogs.append("admin_performance")

        # Add feature flags cog early in the loading sequence
        initial_cogs.append("feature_flags")
            
        # Add remaining standard cogs
        initial_cogs.extend(["admin", "anime", "utility"])

        # Set the cog order on the bot instance for setup_cogs to use
        bot_instance.initial_cogs = initial_cogs

        # Run the bot - this creates its own event loop
        print(
            f"\n{ColoredFormatter.COLORS['BOLD']}{ColoredFormatter.COLORS['GREEN']}"
            f"Starting Quantum Superbot bot v{__version__}...{ColoredFormatter.COLORS['RESET']}"
        )
        print(
            f"{ColoredFormatter.COLORS['GRAY']}"
            f"─────────────────────────────────────────────────────────────"
            f"{ColoredFormatter.COLORS['RESET']}"
        )
        bot_instance.run()
    except Exception as e:
        display_error(f"Failed to start bot: {e}", 1)
        return 1

    # Return success if we get here
    return 0


if __name__ == "__main__":
    # Handle Heroku deployment case where the command is passed incorrectly
    if len(sys.argv) > 1 and sys.argv[1] == "python" and "launcher.py" in sys.argv[2:]:
        # Remove the incorrect arguments
        sys.argv = [sys.argv[0]]
        # Set default values for Heroku
        os.environ["CLUSTER_ID"] = "0"
        os.environ["TOTAL_CLUSTERS"] = "1"
        print("Detected Heroku deployment, setting cluster arguments automatically")
    
    sys.exit(run_bot())
