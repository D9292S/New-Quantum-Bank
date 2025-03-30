# Type Migration Plan

This document outlines the plan for adding comprehensive type annotations to the Quantum Bank codebase.

## Motivation

Adding proper type annotations to the codebase provides many benefits:

1. **Better IDE support**: Type hints enable more accurate autocompletion and in-line documentation
2. **Error prevention**: Static type checking catches potential bugs before runtime
3. **Documentation**: Types serve as documentation that never goes out of date
4. **Maintainability**: Makes refactoring easier and safer
5. **Code quality**: Encourages better design and abstraction

## Current Status

The codebase currently has incomplete type annotations:

- Many functions lack return type annotations
- Many function parameters lack type hints
- Some methods use outdated type hint syntax (Union instead of |)
- Structural typing is inconsistently applied

## Phases of Migration

### Phase 1: Infrastructure Setup (Completed)

- Added mypy configuration in pyproject.toml
- Updated ruff configuration to check for type annotations (temporarily disabled)
- Created scripts/add_type_annotations.py to help identify and suggest type annotations

### Phase 2: Core Module Annotations

Focus on adding type annotations to core modules in this order:

1. **bot.py**: Core bot functionality
2. **config.py**: Configuration classes
3. **cogs/mongo.py**: Database interaction layer
4. **helpers/**: Utility modules that are widely used

### Phase 3: Feature Module Annotations

Add type annotations to feature-specific modules:

1. **cogs/accounts.py**: Banking account functionality
2. **cogs/admin.py**: Admin commands
3. **cogs/utility.py**: Utility commands
4. **cogs/performance_monitor.py**: Performance monitoring
5. Other remaining modules

### Phase 4: Test Suite Annotations

Add type annotations to test files, ensuring proper typing for:

- Fixtures
- Test helpers
- Mock objects

## Implementation Strategy

### Using the Type Annotation Helper

1. Run the annotation helper script on a module:
   ```bash
   python scripts/add_type_annotations.py bot.py
   ```

2. Review generated suggestions in `type_annotation_fixes.md`

3. Apply appropriate fixes to the codebase

### Common Types

We'll standardize on these common types:

```python
# Discord types
from discord.ext.commands import Bot, Context, Cog
from discord import (
    User, Member, Guild, TextChannel, VoiceChannel,
    Message, Embed, Interaction
)

# Database types
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo.results import InsertOneResult, UpdateResult, DeleteResult

# Utility types
from typing import (
    Dict, List, Set, Tuple, Optional, Union, Any,
    Callable, Awaitable, TypeVar, Generic, cast,
    Protocol, Literal
)
```

### Custom Type Definitions

Create custom type definitions for common structures:

```python
# Type alias examples
AccountId = str
UserId = str
GuildId = str

# Custom type definitions
class Account(TypedDict):
    _id: Any  # ObjectId is not easily typable
    user_id: str
    username: str
    guild_id: str
    guild_name: str
    balance: float
    created_at: datetime
    last_updated: datetime
    credit_score: int
    transaction_count: int
```

## Handling Dynamic Types

For areas where static typing is difficult:

- Use `Any` as a last resort
- Provide type comments where necessary
- Use `# type: ignore` for false positives, with explanation

## Timeline

- Phase 1: Complete
- Phase 2: Target 2 weeks
- Phase 3: Target 4 weeks
- Phase 4: Target 2 weeks

## Validation

- Run mypy on the codebase regularly during migration
- Update CI pipeline to include type checking once migration is complete
- Add pre-commit hook to validate type annotations

## References

- [Python Type Checking Guide](https://realpython.com/python-type-checking/)
- [MyPy Cheat Sheet](https://mypy.readthedocs.io/en/stable/cheat_sheet_py3.html)
- [PEP 484 - Type Hints](https://peps.python.org/pep-0484/)
- [PEP 585 - Type Hinting Generics In Standard Collections](https://peps.python.org/pep-0585/)
- [PEP 604 - Allow writing union types as X | Y](https://peps.python.org/pep-0604/)
