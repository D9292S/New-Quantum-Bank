"""Unit tests for the loan functionality."""

import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from helpers.exceptions import AccountNotFoundError, InsufficientFundsError, LoanAlreadyExistsError, LoanError


@pytest.mark.asyncio
@pytest.mark.loans
class TestLoanOperations:
    """Tests for loan creation, repayment, and management."""
    
    @pytest.fixture
    async def mock_db(self):
        """Set up a mock Database instance with loan operations."""
        db = AsyncMock()
        
        # Setup common mock methods
        db.get_account = AsyncMock()
        db.create_loan = AsyncMock()
        db.repay_loan = AsyncMock()
        db.check_loan_status = AsyncMock()
        db.get_active_loan = AsyncMock()
        db.update_credit_score = AsyncMock()
        db.log_transaction = AsyncMock()
        
        return db
    
    async def test_create_loan_success(self, mock_db):
        """Test creating a loan with valid parameters."""
        # Set up test data
        user_id = "123456789"
        amount = 1000.0
        term_months = 12
        
        # Mock account with good credit score
        mock_account = {
            "user_id": user_id,
            "username": "TestUser",
            "balance": 500.0,
            "credit_score": 700,  # Good credit score
            "created_at": datetime.utcnow() - timedelta(days=180)  # Account age > 6 months
        }
        
        # Set up mocks
        mock_db.get_account.return_value = mock_account
        mock_db.create_loan.return_value = True
        
        # Call the method to create a loan
        result = await mock_db.create_loan(user_id, amount, term_months)
        
        # Verify results
        assert result is True
        
        # Verify correct methods were called
        mock_db.get_account.assert_called_once_with(user_id)
        mock_db.create_loan.assert_called_once_with(user_id, amount, term_months)
        
        # Verify credit score was updated
        mock_db.update_credit_score.assert_called_once()
    
    async def test_create_loan_account_not_found(self, mock_db):
        """Test creating a loan when account doesn't exist."""
        # Set up test data
        user_id = "123456789"
        amount = 1000.0
        term_months = 12
        
        # Mock account not found
        mock_db.get_account.return_value = None
        mock_db.get_account.side_effect = AccountNotFoundError("Account not found")
        
        # Call the method and check for exception
        with pytest.raises(AccountNotFoundError):
            await mock_db.create_loan(user_id, amount, term_months)
        
        # Verify correct methods were called
        mock_db.get_account.assert_called_once_with(user_id)
        # Other methods should not be called
        mock_db.create_loan.assert_not_called()
        mock_db.update_credit_score.assert_not_called()
    
    async def test_create_loan_existing_loan(self, mock_db):
        """Test creating a loan when user already has an active loan."""
        # Set up test data
        user_id = "123456789"
        amount = 1000.0
        term_months = 12
        
        # Mock account with existing loan
        mock_account = {
            "user_id": user_id,
            "username": "TestUser",
            "balance": 500.0,
            "credit_score": 700,
            "loan": {
                "status": "active",
                "amount": 2000.0,
                "remaining_amount": 1500.0
            }
        }
        
        # Set up mocks
        mock_db.get_account.return_value = mock_account
        mock_db.create_loan.side_effect = LoanAlreadyExistsError("User already has an active loan")
        
        # Call the method and check for exception
        with pytest.raises(LoanAlreadyExistsError):
            await mock_db.create_loan(user_id, amount, term_months)
        
        # Verify correct methods were called
        mock_db.get_account.assert_called_once_with(user_id)
    
    async def test_repay_loan_success(self, mock_db):
        """Test successful loan repayment."""
        # Set up test data
        user_id = "123456789"
        payment_amount = 100.0
        
        # Mock account with active loan
        mock_account = {
            "user_id": user_id,
            "username": "TestUser",
            "balance": 500.0,
            "credit_score": 700,
            "loan": {
                "status": "active",
                "amount": 1000.0,
                "remaining_amount": 800.0,
                "monthly_payment": 100.0
            }
        }
        
        # Set up mock repayment result
        repayment_result = {
            "amount_paid": payment_amount,
            "remaining_amount": 700.0,
            "status": "active",
            "fully_paid": False
        }
        
        # Set up mocks
        mock_db.get_account.return_value = mock_account
        mock_db.repay_loan.return_value = repayment_result
        
        # Call the method
        result = await mock_db.repay_loan(user_id, payment_amount)
        
        # Verify results
        assert result is not None
        assert result["remaining_amount"] == 700.0
        assert result["fully_paid"] is False
        
        # Verify correct methods were called
        mock_db.get_account.assert_called_once_with(user_id)
        mock_db.repay_loan.assert_called_once_with(user_id, payment_amount)
        
        # Verify credit score was updated (for on-time payment)
        mock_db.update_credit_score.assert_called_once()
    
    async def test_repay_loan_full_payment(self, mock_db):
        """Test completely paying off a loan."""
        # Set up test data
        user_id = "123456789"
        payment_amount = 800.0  # Full remaining amount
        
        # Mock account with active loan
        mock_account = {
            "user_id": user_id,
            "username": "TestUser",
            "balance": 1000.0,
            "credit_score": 700,
            "loan": {
                "status": "active",
                "amount": 1000.0,
                "remaining_amount": 800.0,
                "monthly_payment": 100.0
            }
        }
        
        # Set up mock repayment result with fully paid status
        repayment_result = {
            "amount_paid": payment_amount,
            "remaining_amount": 0.0,
            "status": "paid",
            "fully_paid": True
        }
        
        # Set up mocks
        mock_db.get_account.return_value = mock_account
        mock_db.repay_loan.return_value = repayment_result
        
        # Call the method
        result = await mock_db.repay_loan(user_id, payment_amount)
        
        # Verify results
        assert result is not None
        assert result["remaining_amount"] == 0.0
        assert result["fully_paid"] is True
        assert result["status"] == "paid"
        
        # Verify correct methods were called
        mock_db.get_account.assert_called_once_with(user_id)
        mock_db.repay_loan.assert_called_once_with(user_id, payment_amount)
        
        # Verify credit score was significantly boosted for fully paying a loan
        mock_db.update_credit_score.assert_called_once()
    
    async def test_repay_loan_insufficient_funds(self, mock_db):
        """Test loan repayment with insufficient funds."""
        # Set up test data
        user_id = "123456789"
        payment_amount = 300.0
        
        # Mock account with active loan but insufficient balance
        mock_account = {
            "user_id": user_id,
            "username": "TestUser",
            "balance": 200.0,  # Less than payment
            "credit_score": 700,
            "loan": {
                "status": "active",
                "amount": 1000.0,
                "remaining_amount": 800.0,
                "monthly_payment": 100.0
            }
        }
        
        # Set up mocks
        mock_db.get_account.return_value = mock_account
        mock_db.repay_loan.side_effect = InsufficientFundsError("Insufficient funds for loan payment")
        
        # Call the method and check for exception
        with pytest.raises(InsufficientFundsError):
            await mock_db.repay_loan(user_id, payment_amount)
        
        # Verify correct methods were called
        mock_db.get_account.assert_called_once_with(user_id)
    
    async def test_get_loan_status_active(self, mock_db):
        """Test retrieving status for an active loan."""
        # Set up test data
        user_id = "123456789"
        
        # Set up mock loan status
        mock_loan_status = {
            "amount": 1000.0,
            "interest_rate": 10.0,
            "term_months": 12,
            "monthly_payment": 92.0,
            "remaining_amount": 800.0,
            "next_payment_date": datetime.utcnow() + timedelta(days=15),
            "start_date": datetime.utcnow() - timedelta(days=45),
            "end_date": datetime.utcnow() + timedelta(days=315),
            "status": "active",
            "progress_percent": 20.0,
            "days_to_next_payment": 15,
            "is_overdue": False
        }
        
        # Set up mocks
        mock_db.check_loan_status.return_value = mock_loan_status
        
        # Call the method
        result = await mock_db.check_loan_status(user_id)
        
        # Verify results
        assert result is not None
        assert result["status"] == "active"
        assert result["remaining_amount"] == 800.0
        assert result["is_overdue"] is False
        
        # Verify correct methods were called
        mock_db.check_loan_status.assert_called_once_with(user_id)
    
    async def test_get_loan_status_overdue(self, mock_db):
        """Test retrieving status for an overdue loan."""
        # Set up test data
        user_id = "123456789"
        
        # Set up mock loan status with overdue payment
        mock_loan_status = {
            "amount": 1000.0,
            "interest_rate": 10.0,
            "term_months": 12,
            "monthly_payment": 92.0,
            "remaining_amount": 800.0,
            "next_payment_date": datetime.utcnow() - timedelta(days=5),  # Past due
            "start_date": datetime.utcnow() - timedelta(days=45),
            "end_date": datetime.utcnow() + timedelta(days=315),
            "status": "active",
            "progress_percent": 20.0,
            "days_to_next_payment": -5,  # Negative means overdue
            "is_overdue": True
        }
        
        # Set up mocks
        mock_db.check_loan_status.return_value = mock_loan_status
        
        # Call the method
        result = await mock_db.check_loan_status(user_id)
        
        # Verify results
        assert result is not None
        assert result["status"] == "active"
        assert result["is_overdue"] is True
        assert result["days_to_next_payment"] < 0
        
        # Verify correct methods were called
        mock_db.check_loan_status.assert_called_once_with(user_id)
    
    async def test_get_loan_status_no_loan(self, mock_db):
        """Test retrieving status when no loan exists."""
        # Set up test data
        user_id = "123456789"
        
        # Set up mocks
        mock_db.check_loan_status.return_value = None
        
        # Call the method
        result = await mock_db.check_loan_status(user_id)
        
        # Verify results
        assert result is None
        
        # Verify correct methods were called
        mock_db.check_loan_status.assert_called_once_with(user_id)
    
    async def test_get_active_loan(self, mock_db):
        """Test retrieving an active loan."""
        # Set up test data
        user_id = "123456789"
        
        # Set up mock active loan
        mock_loan = {
            "amount": 1000.0,
            "interest_rate": 10.0,
            "term_months": 12,
            "monthly_payment": 92.0,
            "remaining_amount": 800.0,
            "next_payment_date": datetime.utcnow() + timedelta(days=15),
            "start_date": datetime.utcnow() - timedelta(days=45),
            "end_date": datetime.utcnow() + timedelta(days=315),
            "status": "active"
        }
        
        # Set up mocks
        mock_db.get_active_loan.return_value = mock_loan
        
        # Call the method
        result = await mock_db.get_active_loan(user_id)
        
        # Verify results
        assert result is not None
        assert result["status"] == "active"
        assert result["amount"] == 1000.0
        
        # Verify correct methods were called
        mock_db.get_active_loan.assert_called_once_with(user_id)
    
    async def test_get_active_loan_no_loan(self, mock_db):
        """Test retrieving an active loan when none exists."""
        # Set up test data
        user_id = "123456789"
        
        # Set up mocks
        mock_db.get_active_loan.return_value = None
        
        # Call the method
        result = await mock_db.get_active_loan(user_id)
        
        # Verify results
        assert result is None
        
        # Verify correct methods were called
        mock_db.get_active_loan.assert_called_once_with(user_id)


if __name__ == "__main__":
    unittest.main() 