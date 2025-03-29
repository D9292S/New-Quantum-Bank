class DatabaseError(Exception):
    """Raised when a database operation fails"""
    pass

class ValidationError(Exception):
    """Raised when input validation fails"""
    pass

class ConnectionError(Exception):
    """Raised when database connection fails"""
    pass

class AccountError(Exception):
    """Raised when account-related operations fail"""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

class AccountNotFoundError(AccountError):
    """Raised when an account is not found"""
    pass

class AccountTypeError(AccountError):
    """Raised when an operation is incompatible with the account type"""
    pass

class AccountAlreadyExistsError(AccountError):
    """Raised when attempting to create an account that already exists"""
    pass

class TransactionError(Exception):
    """Raised when transaction operations fail"""
    pass

class InsufficientFundsError(TransactionError):
    """Raised when a transaction fails due to insufficient funds"""
    pass

class TransactionLimitError(TransactionError):
    """Raised when a transaction exceeds defined limits"""
    pass

class InvalidTransactionError(TransactionError):
    """Raised when a transaction is invalid (e.g. negative amount)"""
    pass

class PassbookError(Exception):
    """Raised when passbook generation fails"""
    pass

class KYCError(Exception):
    """Exception raised for errors related to KYC verification"""
    pass

class LoanError(Exception):
    """Raised when loan-related operations fail"""
    pass

class LoanLimitError(LoanError):
    """Raised when a loan request exceeds the user's loan limit"""
    pass

class LoanRepaymentError(LoanError):
    """Raised when a loan repayment operation fails"""
    pass

class LoanAlreadyExistsError(LoanError):
    """Raised when a user tries to take a loan while already having an active loan"""
    pass

class CreditScoreError(Exception):
    """Raised when credit score operations fail"""
    pass

class InsufficientCreditScoreError(CreditScoreError):
    """Raised when a user's credit score is too low for a requested operation"""
    pass 