# Feature Flags with DevCycle

This guide explains how to use DevCycle feature flags in Quantum SuperBot.

## Overview

Quantum SuperBot uses [DevCycle](https://devcycle.com/) for feature flag management, allowing for controlled feature rollouts, A/B testing, and targeted feature availability.

## Setup

1. **Set Environment Variable**: 
   - Add `DEVCYCLE_SERVER_SDK_KEY` to your `.env` file with your DevCycle server SDK key

2. **Create Flags in DevCycle Dashboard**:
   - Log in to [DevCycle Dashboard](https://app.devcycle.com/)
   - Create feature flags matching the ones defined in `config/devcycle.json`
   - Set targeting rules and rollout percentages as needed

## Using Feature Flags

### Checking if a Feature is Enabled

```python
from helpers import is_feature_enabled

# Basic usage
if is_feature_enabled(bot, "feature_key"):
    # Feature is enabled for everyone
    # Implement feature logic

# User-specific check
user_id = str(ctx.author.id)
if is_feature_enabled(bot, "premium_features", user_id):
    # User has access to premium features
    # Implement premium feature logic

# Guild/server specific check
guild_id = str(ctx.guild.id)
if is_feature_enabled(bot, "feature_key", user_id, guild_id):
    # Feature is enabled for this user in this guild
    # Implement feature logic
```

### Feature Flag Decorator

You can use the `@feature_flag` decorator to conditionally enable commands:

```python
from helpers import feature_flag

@discord.slash_command(name="premium_command", description="A premium feature")
@feature_flag("premium_features", default=False)
async def premium_command(self, ctx):
    # This command will only be available to users who have the premium_features flag enabled
    await ctx.respond("This is a premium feature!")
```

### Getting Variable Values

For more complex flags with variable values:

```python
from helpers import get_feature_variable

# Get a variable value with a default
limit = get_feature_variable(bot, "transaction_limit", user_id, default=1000)

# Get a complex value like a dictionary
config = get_feature_variable(bot, "feature_config", user_id, default={})
```

### Percentage-Based Rollout

For gradual rollouts without DevCycle:

```python
from helpers import percentage_rollout

# Roll out to 25% of users
if percentage_rollout(bot, "new_feature", 25, user_id):
    # User is in the rollout group
    # Implement feature logic
```

## Admin Commands

Administrators can use the following slash commands:

- `/features list` - List all available feature flags
- `/features check [feature_key] [user_id] [guild_id]` - Check if a feature is enabled
- `/features refresh` - Refresh feature flags from DevCycle

## Adding New Features

1. Add feature description to `config/devcycle.json`
2. Create the feature flag in DevCycle dashboard
3. Use the feature flag in code using methods above
4. Test with different targeting rules

## Best Practices

1. Always provide sensible defaults for feature flags
2. Keep feature flag checks close to the feature implementation
3. Clean up flags after fully rolling out a feature
4. Use descriptive names for feature flags 