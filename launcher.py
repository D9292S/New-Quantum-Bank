import discord
import os
import sys
import platform
import argparse
import json
import asyncio
import logging
import logging.handlers
import datetime
from pathlib import Path
from collections import namedtuple
from urllib.parse import quote_plus
from dotenv import load_dotenv

# Define color codes for log levels
class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log levels in console output"""
    # ANSI color codes
    COLORS = {
        'RESET': '\033[0m',
        'RED': '\033[31m',      # ERROR
        'YELLOW': '\033[33m',   # WARNING
        'GREEN': '\033[32m',    # INFO
        'BLUE': '\033[36m',     # DEBUG
        'MAGENTA': '\033[35m',  # CRITICAL
        'GRAY': '\033[37m',     # Timestamps
        'BOLD': '\033[1m',      # Headers
        'UNDERLINE': '\033[4m', # Special highlights
        'CYAN': '\033[96m',     # JSON keys
        'LIGHT_GREEN': '\033[92m', # JSON values
        'LIGHT_YELLOW': '\033[93m', # JSON special values
        'LIGHT_BLUE': '\033[94m'   # JSON punctuation
    }
    
    def __init__(self, fmt=None, datefmt=None, style='%'):
        super().__init__(fmt, datefmt, style)
        
        # Define compact pattern transformations
        self.compact_patterns = [
            # Shorten Gateway logs
            (r'has connected to Gateway:.*\(Session ID: ([^)]+)\)', 
             lambda m: f"has connected to Gateway: {self.COLORS['BOLD']}{self.COLORS['GREEN']}✓{self.COLORS['RESET']} (Session ID: {self.COLORS['BOLD']}{self.COLORS['LIGHT_YELLOW']}{m.group(1)[:8]}...{self.COLORS['RESET']})"),
            
            # Shorten command registrations
            (r'Registered application commands: \[([^\]]+)\]',
             lambda m: f"Registered {len(m.group(1).split(','))} application commands"),
             
            # Shorten cog loading completion
            (r'Finished loading cogs extra=.+?"elapsed_time": "([^"]+)".+?',
             lambda m: f"Finished loading all cogs in {self.COLORS['BOLD']}{self.COLORS['GREEN']}{m.group(1)}{self.COLORS['RESET']}"),
             
            # Shorten connection metrics
            (r'Connected to (\d+) guilds with (\d+) members',
             lambda m: f"Connected to {self.COLORS['BOLD']}{self.COLORS['CYAN']}{m.group(1)}{self.COLORS['RESET']} guilds with {self.COLORS['BOLD']}{self.COLORS['CYAN']}{m.group(2)}{self.COLORS['RESET']} members")
        ]
    
    def _compact_message(self, message):
        """Transform verbose log messages into more compact forms"""
        import re
        
        # Apply transformations
        for pattern, replacement in self.compact_patterns:
            message = re.sub(pattern, replacement, message)
            
        return message
    
    def format(self, record):
        # Save the original format
        format_orig = self._style._fmt
        
        # Add colors based on the log level
        if record.levelno >= logging.CRITICAL:
            self._style._fmt = f"{self.COLORS['BOLD']}{self.COLORS['MAGENTA']}%(levelname)s{self.COLORS['RESET']} | " \
                              f"{self.COLORS['GRAY']}%(asctime)s{self.COLORS['RESET']} | " \
                              f"{self.COLORS['BOLD']}%(message)s{self.COLORS['RESET']}"
        elif record.levelno >= logging.ERROR:
            self._style._fmt = f"{self.COLORS['BOLD']}{self.COLORS['RED']}%(levelname)s{self.COLORS['RESET']} | " \
                              f"{self.COLORS['GRAY']}%(asctime)s{self.COLORS['RESET']} | " \
                              f"{self.COLORS['RED']}%(message)s{self.COLORS['RESET']}"
        elif record.levelno >= logging.WARNING:
            self._style._fmt = f"{self.COLORS['YELLOW']}%(levelname)s{self.COLORS['RESET']} | " \
                              f"{self.COLORS['GRAY']}%(asctime)s{self.COLORS['RESET']} | " \
                              f"{self.COLORS['YELLOW']}%(message)s{self.COLORS['RESET']}"
        elif record.levelno >= logging.INFO:
            self._style._fmt = f"{self.COLORS['GREEN']}%(levelname)s{self.COLORS['RESET']} | " \
                              f"{self.COLORS['GRAY']}%(asctime)s{self.COLORS['RESET']} | " \
                              f"%(message)s"
        else:  # DEBUG and below
            self._style._fmt = f"{self.COLORS['BLUE']}%(levelname)s{self.COLORS['RESET']} | " \
                              f"{self.COLORS['GRAY']}%(asctime)s{self.COLORS['RESET']} | " \
                              f"{self.COLORS['BLUE']}%(message)s{self.COLORS['RESET']}"
        
        # Format the record with colors
        result = super().format(record)
        
        # Apply message compaction after initial formatting
        parts = result.split('|', 2)
        if len(parts) == 3:
            # Compact the message part
            parts[2] = ' ' + self._compact_message(parts[2].strip())
            result = '|'.join(parts)
        
        # Apply JSON formatting to the message part
        if record.levelno == logging.INFO:
            # Find the message part (after the second '|')
            parts = result.split('|', 2)
            if len(parts) == 3:
                # Replace the message part with JSON-formatted version
                parts[2] = ' ' + self._format_json(parts[2].strip())
                result = '|'.join(parts)
        
        # Restore the original format
        self._style._fmt = format_orig
        
        return result

    def _format_json(self, message):
        """Format JSON content with colors for better readability"""
        # If already compacted by _compact_message, don't format JSON
        if any(marker in message for marker in ["Gateway: ✓", "Finished loading all cogs in"]):
            return message
            
        import re
        
        # Simple JSON formatting for remaining messages
        if '{' in message and '}' in message and ':' in message:
            # Format keys in cyan
            message = re.sub(r"'([^']+)':", f"{self.COLORS['CYAN']}'\\1'{self.COLORS['RESET']}:", message)
            message = re.sub(r'"([^"]+)":', f"{self.COLORS['CYAN']}\"\\1\"{self.COLORS['RESET']}:", message)
            
            # Format string values in light green
            message = re.sub(r": '([^']*)'", f": {self.COLORS['LIGHT_GREEN']}'\\1'{self.COLORS['RESET']}", message)
            message = re.sub(r': "([^"]*)"', f": {self.COLORS['LIGHT_GREEN']}\"\\1\"{self.COLORS['RESET']}", message)
            
            # Format numeric values in yellow
            message = re.sub(r": (\d+\.?\d*)", f": {self.COLORS['LIGHT_YELLOW']}\\1{self.COLORS['RESET']}", message)
            
            # Format special values
            message = re.sub(r": (true|false|null|None|True|False)", 
                          f": {self.COLORS['LIGHT_YELLOW']}\\1{self.COLORS['RESET']}", message)
            
            # Format braces and brackets with light blue
            for char in ['{', '}', '[', ']']:
                message = message.replace(char, f"{self.COLORS['LIGHT_BLUE']}{char}{self.COLORS['RESET']}")
        
        return message

# Configure logging system before importing bot
def setup_logging(log_level="normal"):
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
        print(f"{ColoredFormatter.COLORS['BLUE']}Debug logging enabled - showing all logs with debug information{ColoredFormatter.COLORS['RESET']}")
    elif log_level == "verbose":
        root_logger.setLevel(logging.INFO)
        console_level = logging.INFO
        use_filter = False
        print(f"{ColoredFormatter.COLORS['GREEN']}Verbose logging enabled - showing all logs{ColoredFormatter.COLORS['RESET']}")
    elif log_level == "quiet":
        root_logger.setLevel(logging.INFO)  # Still log everything to files
        console_level = logging.WARNING  # But only show warnings and above in console
        use_filter = True
        print(f"{ColoredFormatter.COLORS['YELLOW']}Quiet logging enabled - showing only warnings and errors{ColoredFormatter.COLORS['RESET']}")
    else:  # normal - default
        root_logger.setLevel(logging.INFO)
        console_level = logging.INFO
        use_filter = True
    
    # Define log filters for cleaner console output
    class ImportantLogFilter(logging.Filter):
        """Filter to show only important logs in console"""
        def __init__(self):
            super().__init__()
            # Messages to always show (high priority)
            self.important_patterns = [
                "Bot is ready",
                "Starting Quantum Bank",
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
                "Credit score update scheduled", # Important business logic
                "Initializing daily account tasks" # Important banking feature
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
                "cached_property is", # Library warnings irrelevant to users
                "Failed to load package", # Warnings about optional packages
                "Starting bot run",
                "Found existing performance_monitor"
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
                "Reconnection failed"
            ]
        
        def filter(self, record):
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
            if "session" in message.lower() and not "Session ID" in message:
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
            "description": "Core bot operations, startup and shutdown events"
        },
        "commands": {
            "level": logging.INFO,
            "filename": "commands.log",
            "description": "Command executions, parameters, and results"
        },
        "database": {
            "level": logging.INFO,
            "filename": "database.log",
            "description": "Database operations, queries, and connection status"
        },
        "performance": {
            "level": logging.INFO,
            "filename": "performance.log", 
            "description": "Performance metrics, timing data, and benchmarks"
        },
        "errors": {
            "level": logging.ERROR,
            "filename": "errors.log",
            "description": "All error messages across the system"
        }
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
            maxBytes=5*1024*1024,  # 5 MB
            backupCount=5,
            encoding='utf-8'
        )
        handler.setFormatter(logging.Formatter(file_format, date_format))
        handler.setLevel(config["level"])
        
        # Add handler to the category logger
        logger.addHandler(handler)
        
        # Also add ERROR level logs to the errors log
        if category != "errors":
            error_handler = logging.handlers.RotatingFileHandler(
                logs_dir / "errors.log",
                maxBytes=5*1024*1024,
                backupCount=5,
                encoding='utf-8'
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

import bot

__version__ = "1.0.0"

# Load environment variables
load_dotenv()

# Function to print a cool banner with version info
def print_banner():
    # ANSI color codes
    COLORS = ColoredFormatter.COLORS
    
    banner = f"""
{COLORS['BLUE']}  ██████╗ ██╗   ██╗ █████╗ ███╗   ██╗████████╗██╗   ██╗███╗   ███╗{COLORS['RESET']}
{COLORS['BLUE']} ██╔═══██╗██║   ██║██╔══██╗████╗  ██║╚══██╔══╝██║   ██║████╗ ████║{COLORS['RESET']}
{COLORS['GREEN']} ██║   ██║██║   ██║███████║██╔██╗ ██║   ██║   ██║   ██║██╔████╔██║{COLORS['RESET']}
{COLORS['GREEN']} ██║▄▄ ██║██║   ██║██╔══██║██║╚██╗██║   ██║   ██║   ██║██║╚██╔╝██║{COLORS['RESET']}
{COLORS['YELLOW']} ╚██████╔╝╚██████╔╝██║  ██║██║ ╚████║   ██║   ╚██████╔╝██║ ╚═╝ ██║{COLORS['RESET']}
{COLORS['YELLOW']}  ╚══▀▀═╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝    ╚═════╝ ╚═╝     ╚═╝{COLORS['RESET']}
                                                                  
{COLORS['BOLD']}{COLORS['GREEN']}               ██████╗  █████╗ ███╗   ██╗██╗  ██╗{COLORS['RESET']}
{COLORS['BOLD']}{COLORS['GREEN']}               ██╔══██╗██╔══██╗████╗  ██║██║ ██╔╝{COLORS['RESET']}
{COLORS['BOLD']}{COLORS['GREEN']}               ██████╔╝███████║██╔██╗ ██║█████╔╝ {COLORS['RESET']}
{COLORS['BOLD']}{COLORS['GREEN']}               ██╔══██╗██╔══██║██║╚██╗██║██╔═██╗ {COLORS['RESET']}
{COLORS['BOLD']}{COLORS['GREEN']}               ██████╔╝██║  ██║██║ ╚████║██║  ██╗{COLORS['RESET']}
{COLORS['BOLD']}{COLORS['GREEN']}               ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝{COLORS['RESET']}
    """
    
    print(banner)
    print(f"{COLORS['BOLD']}⚡ {COLORS['BLUE']}Quantum Bank Bot{COLORS['RESET']} {COLORS['GREEN']}v{__version__}{COLORS['RESET']}")
    print(f"{COLORS['GRAY']}Running on {COLORS['BLUE']}Python {platform.python_version()}{COLORS['RESET']} | {COLORS['YELLOW']}{platform.system()} {platform.release()}{COLORS['RESET']}")
    print(f"{COLORS['GRAY']}─────────────────────────────────────────────────────────────{COLORS['RESET']}")

print_banner()

Config = namedtuple(
    "Config",
    ["DEBUG", "BOT_TOKEN", "MONGO_URI", "MAL_CLIENT_ID", "ACTIVITY_STATUS", 
     "SHARD_COUNT", "SHARD_IDS", "CLUSTER_ID", "TOTAL_CLUSTERS", "PERFORMANCE_MODE"]
)

def parse_arguments():
    """Parse command line arguments for advanced configuration"""
    parser = argparse.ArgumentParser(description="Quantum Bank Discord Bot")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--shards", type=int, help="Number of shards to use")
    parser.add_argument("--shardids", type=str, help="Comma-separated list of shard IDs to run")
    parser.add_argument("--cluster", type=int, help="Cluster ID for this instance")
    parser.add_argument("--clusters", type=int, help="Total number of clusters")
    parser.add_argument("--performance", choices=["low", "medium", "high"], default="medium",
                       help="Performance optimization level (low: minimal resources, medium: balanced, high: maximum performance)")
    parser.add_argument("--log-level", choices=["quiet", "normal", "verbose", "debug"], default="normal",
                       help="Logging verbosity (quiet: critical logs only, normal: balanced, verbose: all logs, debug: all logs with debugging info)")
    
    return parser.parse_args()

def calculate_shards_for_cluster(cluster_id, total_clusters, total_shards):
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

def display_error(message, exit_code=None):
    """Display an error message in a highly visible format"""
    COLORS = ColoredFormatter.COLORS
    border = f"{COLORS['RED']}{'═' * 80}{COLORS['RESET']}"
    
    print("\n" + border)
    print(f"{COLORS['BOLD']}{COLORS['RED']} ❌ ERROR: {message}{COLORS['RESET']}")
    print(border + "\n")
    
    if exit_code is not None:
        sys.exit(exit_code)

def run_bot():
    """Run the bot - synchronous entry point"""
    # Check Python version
    if sys.version_info < (3, 8):
        display_error("Python 3.8 or higher is required.", 1)
    
    # Set up proper event loop for Windows
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Parse command line arguments
    args = parse_arguments()
    
    # Initialize logging with selected verbosity
    global LOG_CATEGORIES
    LOG_CATEGORIES = setup_logging(args.log_level)
    
    # Determine debug mode from args or env
    debug_mode = args.debug or os.getenv("DEBUG") in ("1", "True", "true")
    if debug_mode:
        print(f"{ColoredFormatter.COLORS['YELLOW']}Debug mode enabled{ColoredFormatter.COLORS['RESET']}")
        
    # Construct Mongo URI with error handling
    try:
        uri = os.getenv("MONGO_URI")
        if not uri:
            # Try to construct from components
            if all(key in os.environ for key in ["MONGO_USER", "MONGO_PASS", "MONGO_HOST"]):
                uri = "mongodb://{}:{}@{}".format(
                    quote_plus(os.environ["MONGO_USER"]),
                    quote_plus(os.environ["MONGO_PASS"]),
                    os.environ["MONGO_HOST"],
                )
                print(f"{ColoredFormatter.COLORS['GREEN']}Constructed MongoDB URI from individual components{ColoredFormatter.COLORS['RESET']}")
            else:
                print(f"{ColoredFormatter.COLORS['YELLOW']}WARNING: MongoDB URI not provided, some features may not work{ColoredFormatter.COLORS['RESET']}")
                uri = None
    except KeyError as e:
        display_error(f"Missing required MongoDB environment variable: {e}")
        uri = None

    # Sharding configuration
    total_shards = args.shards or int(os.getenv("SHARD_COUNT", "1"))
    
    # Determine shard IDs to run
    shard_ids = None
    if args.shardids:
        # Parse comma-separated list of shard IDs
        shard_ids = [int(s.strip()) for s in args.shardids.split(",")]
        print(f"{ColoredFormatter.COLORS['BLUE']}Running specific shards: {ColoredFormatter.COLORS['BOLD']}{shard_ids}{ColoredFormatter.COLORS['RESET']}")
    elif args.cluster is not None and args.clusters is not None:
        # Calculate shard IDs for this cluster
        cluster_id = args.cluster
        total_clusters = args.clusters
        shard_ids = calculate_shards_for_cluster(cluster_id, total_clusters, total_shards)
        print(f"{ColoredFormatter.COLORS['BLUE']}Cluster {ColoredFormatter.COLORS['BOLD']}{cluster_id}/{total_clusters}{ColoredFormatter.COLORS['RESET']} {ColoredFormatter.COLORS['BLUE']}running shards: {ColoredFormatter.COLORS['BOLD']}{shard_ids}{ColoredFormatter.COLORS['RESET']}")
    
    # Performance mode configuration
    performance_mode = args.performance or os.getenv("PERFORMANCE_MODE", "medium")
    
    if performance_mode == "high":
        print(f"{ColoredFormatter.COLORS['GREEN']}Using {ColoredFormatter.COLORS['BOLD']}HIGH{ColoredFormatter.COLORS['RESET']} {ColoredFormatter.COLORS['GREEN']}performance mode - maximizing resource usage{ColoredFormatter.COLORS['RESET']}")
        # Try to load optional high-performance libraries
        try:
            import uvloop
            if not sys.platform.startswith("win"):
                # uvloop doesn't work on Windows
                print(f"{ColoredFormatter.COLORS['GREEN']}✓ Using uvloop for improved event loop performance{ColoredFormatter.COLORS['RESET']}")
                uvloop.install()
        except ImportError:
            print(f"{ColoredFormatter.COLORS['YELLOW']}✗ uvloop not available - using standard asyncio event loop{ColoredFormatter.COLORS['RESET']}")
        
        # Try to use orjson for faster JSON processing
        try:
            import orjson
            print(f"{ColoredFormatter.COLORS['GREEN']}✓ Using orjson for improved JSON performance{ColoredFormatter.COLORS['RESET']}")
        except ImportError:
            print(f"{ColoredFormatter.COLORS['YELLOW']}✗ orjson not available - using standard json module{ColoredFormatter.COLORS['RESET']}")
            
    elif performance_mode == "low":
        print(f"{ColoredFormatter.COLORS['BLUE']}Using {ColoredFormatter.COLORS['BOLD']}LOW{ColoredFormatter.COLORS['RESET']} {ColoredFormatter.COLORS['BLUE']}performance mode - minimizing resource usage{ColoredFormatter.COLORS['RESET']}")
        # Configure for minimal resource usage
    else:
        print(f"{ColoredFormatter.COLORS['BLUE']}Using {ColoredFormatter.COLORS['BOLD']}MEDIUM{ColoredFormatter.COLORS['RESET']} {ColoredFormatter.COLORS['BLUE']}performance mode - balanced resource usage{ColoredFormatter.COLORS['RESET']}")
    
    # Create config
    config = Config(
        DEBUG=debug_mode,
        BOT_TOKEN=os.getenv("BOT_TOKEN"),
        MONGO_URI=uri,
        MAL_CLIENT_ID=os.getenv("MAL_CLIENT_ID"),
        ACTIVITY_STATUS=os.getenv("ACTIVITY_STATUS", "Quantum Bank | /help"),
        SHARD_COUNT=total_shards,
        SHARD_IDS=shard_ids,
        CLUSTER_ID=args.cluster,
        TOTAL_CLUSTERS=args.clusters,
        PERFORMANCE_MODE=performance_mode
    )

    # Print configuration summary
    if config.DEBUG:
        print(f"{ColoredFormatter.COLORS['YELLOW']}DEBUG mode enabled{ColoredFormatter.COLORS['RESET']}")
    
    if config.SHARD_COUNT > 1:
        print(f"{ColoredFormatter.COLORS['BLUE']}Bot will use {ColoredFormatter.COLORS['BOLD']}{config.SHARD_COUNT}{ColoredFormatter.COLORS['RESET']} {ColoredFormatter.COLORS['BLUE']}shards{ColoredFormatter.COLORS['RESET']}")
        if config.SHARD_IDS:
            print(f"{ColoredFormatter.COLORS['BLUE']}This instance will run shards: {ColoredFormatter.COLORS['BOLD']}{config.SHARD_IDS}{ColoredFormatter.COLORS['RESET']}")
    
    if config.CLUSTER_ID is not None:
        print(f"{ColoredFormatter.COLORS['BLUE']}Running as cluster {ColoredFormatter.COLORS['BOLD']}{config.CLUSTER_ID}{ColoredFormatter.COLORS['RESET']} {ColoredFormatter.COLORS['BLUE']}of {ColoredFormatter.COLORS['BOLD']}{config.TOTAL_CLUSTERS}{ColoredFormatter.COLORS['RESET']}")
    
    if not config.MAL_CLIENT_ID:
        print(f"{ColoredFormatter.COLORS['YELLOW']}WARNING: MAL_CLIENT_ID not set, anime commands will be disabled{ColoredFormatter.COLORS['RESET']}")

    # Check for required BOT_TOKEN
    if not config.BOT_TOKEN:
        display_error("BOT_TOKEN must be set in .env\nPlease create a .env file with BOT_TOKEN=your_token_here", 1)

    # Set up intents
    try:
        intents = discord.Intents.default()
        intents.members = True
        intents.presences = True
        intents.messages = True
        intents.message_content = True  # Required for commands
        
        # Create bot instance with sharding configuration
        bot_instance = bot.ClusterBot(
            token=config.BOT_TOKEN,
            intents=intents,
            config=config,
            shard_count=config.SHARD_COUNT,
            shard_ids=config.SHARD_IDS
        )
        
        # Make sure appropriate cogs are loaded
        # Define initial cogs order based on dependencies
        initial_cogs = ['mongo', 'accounts']
        
        # Add performance monitoring cog if not in low performance mode
        if config.PERFORMANCE_MODE != 'low':
            initial_cogs.append('performance_monitor')
            initial_cogs.append('admin_performance')
            
        # Add remaining standard cogs
        initial_cogs.extend(['admin', 'anime', 'utility'])
            
        # Set the cog order on the bot instance for setup_cogs to use
        bot_instance.initial_cogs = initial_cogs
        
        # Run the bot - this creates its own event loop
        print(f"\n{ColoredFormatter.COLORS['BOLD']}{ColoredFormatter.COLORS['GREEN']}Starting Quantum Bank bot v{__version__}...{ColoredFormatter.COLORS['RESET']}")
        print(f"{ColoredFormatter.COLORS['GRAY']}─────────────────────────────────────────────────────────────{ColoredFormatter.COLORS['RESET']}")
        bot_instance.run()
    except Exception as e:
        display_error(f"Failed to start bot: {e}", 1)

if __name__ == "__main__":
    # Run the bot without asyncio.run() since discord.py creates its own event loop
    run_bot()