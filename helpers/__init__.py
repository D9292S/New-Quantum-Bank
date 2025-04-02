"""
Helper utilities for the Quantum Bank Discord bot.

This package contains various helper functions and classes used throughout the bot.
"""

# Import constants for easy access
from .cache_manager import CacheManager, cached

# Import advanced scalability helpers
from .connection_pool import ConnectionPoolManager
from .constants import (
    BLUE,
    CREDIT_LIMIT_MULTIPLIERS,
    CREDIT_SCORE_BAD,
    CREDIT_SCORE_EXCELLENT,
    CREDIT_SCORE_FAIR,
    CREDIT_SCORE_GOOD,
    CREDIT_SCORE_POOR,
    DEFAULT_CREDIT_SCORE,
    DEFAULT_INTEREST_RATE,
    DEFAULT_LOAN_TERM,
    DEFAULT_PREFIX,
    GOLD,
    GREEN,
    INTEREST_RATES,
    ONE_DAY,
    ONE_HOUR,
    ONE_MINUTE,
    ONE_MONTH,
    ONE_WEEK,
    ORANGE,
    PINK,
    PURPLE,
    RED,
)

# Import exceptions
from .exceptions import (
    AccountAlreadyExistsError,
    AccountError,
    AccountNotFoundError,
    AccountTypeError,
    ConnectionError,
    CreditScoreError,
    DatabaseError,
    InsufficientCreditScoreError,
    InsufficientFundsError,
    InvalidTransactionError,
    KYCError,
    LoanAlreadyExistsError,
    LoanError,
    LoanLimitError,
    LoanRepaymentError,
    PassbookError,
    TransactionError,
    TransactionLimitError,
    ValidationError,
)

# Import feature flags
from .feature_flags import feature_flag, get_feature_variable, is_feature_enabled, percentage_rollout

# Import rate limiter
from .rate_limiter import RateLimiter, cooldown, rate_limit
from .shard_manager import ShardManager

# Version info
__version__ = "1.0.0"

__all__ = [
    "RateLimiter",
    "rate_limit",
    "cooldown",
    "ConnectionPoolManager",
    "CacheManager",
    "cached",
    "ShardManager",
    # Add feature flag utilities
    "feature_flag",
    "is_feature_enabled",
    "get_feature_variable",
    "percentage_rollout",
    # Add exceptions to __all__
    "AccountAlreadyExistsError",
    "AccountError",
    "AccountNotFoundError",
    "AccountTypeError",
    "ConnectionError",
    "CreditScoreError",
    "DatabaseError",
    "InsufficientCreditScoreError",
    "InsufficientFundsError",
    "InvalidTransactionError",
    "KYCError",
    "LoanAlreadyExistsError",
    "LoanError",
    "LoanLimitError",
    "LoanRepaymentError",
    "PassbookError",
    "TransactionError",
    "TransactionLimitError",
    "ValidationError",
    # Add constants to __all__
    "BLUE",
    "RED",
    "GREEN",
    "GOLD",
    "ORANGE",
    "PINK",
    "PURPLE",
    "CREDIT_SCORE_EXCELLENT",
    "CREDIT_SCORE_GOOD",
    "CREDIT_SCORE_FAIR",
    "CREDIT_SCORE_POOR",
    "CREDIT_SCORE_BAD",
    "CREDIT_LIMIT_MULTIPLIERS",
    "INTEREST_RATES",
    "ONE_MINUTE",
    "ONE_HOUR",
    "ONE_DAY",
    "ONE_WEEK",
    "ONE_MONTH",
    "DEFAULT_CREDIT_SCORE",
    "DEFAULT_INTEREST_RATE",
    "DEFAULT_LOAN_TERM",
    "DEFAULT_PREFIX",
]
