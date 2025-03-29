"""
Constants used throughout the Quantum Bank bot.
"""

import discord

# Discord color constants
BLUE = discord.Color.blue()
RED = discord.Color.red()
GREEN = discord.Color.green()
GOLD = discord.Color.gold()
ORANGE = discord.Color.orange()
PINK = 0xFFC0CB  # Custom pink color
PURPLE = discord.Color.purple()

# Credit score rating thresholds
CREDIT_SCORE_EXCELLENT = 750  # 750-850: Excellent
CREDIT_SCORE_GOOD = 700  # 700-749: Good
CREDIT_SCORE_FAIR = 650  # 650-699: Fair
CREDIT_SCORE_POOR = 600  # 600-649: Poor
CREDIT_SCORE_BAD = 300  # 300-599: Bad

# Credit limit multipliers based on credit score
CREDIT_LIMIT_MULTIPLIERS = {
    "excellent": 10.0,  # 750-850
    "good": 7.5,  # 700-749
    "fair": 5.0,  # 650-699
    "poor": 2.5,  # 600-649
    "bad": 1.0,  # 300-599
}

# Interest rates based on credit score
INTEREST_RATES = {
    "excellent": 8.0,  # 750-850: 8.0%
    "good": 10.0,  # 700-749: 10.0%
    "fair": 12.0,  # 650-699: 12.0%
    "poor": 14.0,  # 600-649: 14.0%
    "bad": 16.0,  # 300-599: 16.0%
}

# Time constants (in seconds)
ONE_MINUTE = 60
ONE_HOUR = 3600
ONE_DAY = 86400
ONE_WEEK = 604800
ONE_MONTH = 2592000  # 30 days

# Default values
DEFAULT_CREDIT_SCORE = 600
DEFAULT_INTEREST_RATE = 2.5  # 2.5% annual interest for savings accounts
DEFAULT_LOAN_TERM = 12  # 12 months
DEFAULT_PREFIX = "!"
