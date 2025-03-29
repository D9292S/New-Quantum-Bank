# Quantum Bank Commands

This document provides detailed information on all available commands in the Quantum Bank bot.

## Account Management

### `/account create [type]`
Creates a new bank account.

**Options:**
- `type`: The type of account to create (default: checking)
  - `checking`: Standard account with no restrictions
  - `savings`: Higher interest rate but limited withdrawals
  - `premium`: Higher limits and benefits, requires credit score > 700

**Examples:**
```
/account create
/account create type:savings
```

### `/account balance`
Displays your current account balance with account details.

**Example:**
```
/account balance
```

### `/account statement [days]`
Generate a statement of your recent transactions.

**Options:**
- `days`: Number of days to include in statement (default: 7, max: 30)

**Examples:**
```
/account statement
/account statement days:14
```

### `/account close [confirm]`
Close your bank account.

**Options:**
- `confirm`: Type "confirm" to confirm account closure

**Example:**
```
/account close confirm:confirm
```

## Transactions

### `/deposit <amount>`
Deposit funds into your account.

**Arguments:**
- `amount`: Amount to deposit (min: 10, max: 1,000,000)

**Examples:**
```
/deposit amount:500
/deposit amount:1000
```

### `/withdraw <amount>`
Withdraw funds from your account.

**Arguments:**
- `amount`: Amount to withdraw (min: 10, max: depends on account type)

**Examples:**
```
/withdraw amount:200
/withdraw amount:1000
```

### `/transfer <recipient> <amount> [note]`
Transfer funds to another user.

**Arguments:**
- `recipient`: User to send funds to
- `amount`: Amount to transfer
- `note`: Optional message to include with transfer

**Examples:**
```
/transfer recipient:@username amount:500
/transfer recipient:@username amount:100 note:Paying you back for lunch
```

## Loans and Credit

### `/loan apply <amount> <duration>`
Apply for a loan.

**Arguments:**
- `amount`: Loan amount (min: 1000, max: based on credit score)
- `duration`: Loan duration in months (3, 6, 12, 24, or 36)

**Examples:**
```
/loan apply amount:5000 duration:12
/loan apply amount:10000 duration:24
```

### `/loan status`
Check the status of your current loans.

**Example:**
```
/loan status
```

### `/loan repay <amount> [loan_id]`
Make a payment towards your loan.

**Arguments:**
- `amount`: Amount to repay
- `loan_id`: Specific loan ID (optional, if you have multiple loans)

**Examples:**
```
/loan repay amount:500
/loan repay amount:1000 loan_id:L12345
```

### `/credit score`
Check your credit score.

**Example:**
```
/credit score
```

### `/credit history`
View your credit history and factors affecting your score.

**Example:**
```
/credit history
```

## Investments

### `/invest <amount> <stock>`
Invest in a stock.

**Arguments:**
- `amount`: Amount to invest
- `stock`: Stock symbol to invest in

**Examples:**
```
/invest amount:1000 stock:AAPL
/invest amount:500 stock:TSLA
```

### `/portfolio`
View your investment portfolio.

**Example:**
```
/portfolio
```

### `/market`
View current market conditions.

**Example:**
```
/market
```

### `/market search <query>`
Search for a stock by name or symbol.

**Arguments:**
- `query`: Stock name or symbol to search for

**Example:**
```
/market search query:Apple
```

## Fixed Deposits

### `/fd create <amount> <duration>`
Create a Fixed Deposit.

**Arguments:**
- `amount`: Amount to deposit
- `duration`: Duration in months (3, 6, 12, 24, or 36)

**Examples:**
```
/fd create amount:10000 duration:12
/fd create amount:5000 duration:6
```

### `/fd list`
List all your fixed deposits.

**Example:**
```
/fd list
```

### `/fd break <fd_id>`
Break a fixed deposit before maturity (penalties apply).

**Arguments:**
- `fd_id`: ID of the fixed deposit to break

**Example:**
```
/fd break fd_id:FD12345
```

## Utility Commands

### `/help [command]`
Display help information.

**Options:**
- `command`: Specific command to get help for

**Examples:**
```
/help
/help command:deposit
```

### `/daily`
Claim your daily bonus.

**Example:**
```
/daily
```

### `/leaderboard [category]`
View the server's leaderboard.

**Options:**
- `category`: Leaderboard category (wealth, credit, investments)

**Examples:**
```
/leaderboard
/leaderboard category:credit
```

## Admin Commands
*Note: These commands require admin permissions*

### `/admin set-interest <rate>`
Set the interest rate for the server.

**Arguments:**
- `rate`: New interest rate (%)

**Example:**
```
/admin set-interest rate:2.5
```

### `/admin reset-user <user>`
Reset a user's financial data.

**Arguments:**
- `user`: User to reset

**Example:**
```
/admin reset-user user:@username
```
