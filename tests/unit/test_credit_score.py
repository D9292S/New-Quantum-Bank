"""Unit tests for the credit score system."""

import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from helpers.exceptions import AccountNotFoundError, CreditScoreError


@pytest.mark.asyncio
@pytest.mark.credit
class TestCreditScoreSystem:
    """Tests for credit score calculations and updates."""
    
    @pytest.fixture
    async def mock_db(self):
        """Set up a mock Database instance with credit score operations."""
        db = AsyncMock()
        
        # Setup common mock methods
        db.get_account = AsyncMock()
        db.update_credit_score = AsyncMock()
        db.get_credit_report = AsyncMock()
        
        return db
    
    async def test_update_credit_score_increase(self, mock_db):
        """Test increasing a user's credit score."""
        # Set up test data
        user_id = "123456789"
        action = "on_time_payment"
        change = 10  # Positive change
        reason = "Made on-time loan payment"
        
        # Mock account
        mock_account = {
            "user_id": user_id,
            "username": "TestUser",
            "credit_score": 600,
            "credit_history": []
        }
        
        # Set up mock update result
        update_result = {
            "user_id": user_id,
            "old_score": 600,
            "new_score": 610,
            "change": change,
            "action": action,
            "timestamp": datetime.utcnow()
        }
        
        # Set up mocks
        mock_db.get_account.return_value = mock_account
        mock_db.update_credit_score.return_value = update_result
        
        # Call the method
        result = await mock_db.update_credit_score(user_id, action, change, reason)
        
        # Verify results
        assert result is not None
        assert result["old_score"] == 600
        assert result["new_score"] == 610
        assert result["change"] == change
        
        # Verify correct methods were called
        mock_db.get_account.assert_called_once_with(user_id)
        mock_db.update_credit_score.assert_called_once_with(user_id, action, change, reason)
    
    async def test_update_credit_score_decrease(self, mock_db):
        """Test decreasing a user's credit score."""
        # Set up test data
        user_id = "123456789"
        action = "late_payment"
        change = -15  # Negative change
        reason = "Payment was 10 days late"
        
        # Mock account
        mock_account = {
            "user_id": user_id,
            "username": "TestUser",
            "credit_score": 650,
            "credit_history": []
        }
        
        # Set up mock update result
        update_result = {
            "user_id": user_id,
            "old_score": 650,
            "new_score": 635,
            "change": change,
            "action": action,
            "timestamp": datetime.utcnow()
        }
        
        # Set up mocks
        mock_db.get_account.return_value = mock_account
        mock_db.update_credit_score.return_value = update_result
        
        # Call the method
        result = await mock_db.update_credit_score(user_id, action, change, reason)
        
        # Verify results
        assert result is not None
        assert result["old_score"] == 650
        assert result["new_score"] == 635
        assert result["change"] == change
        
        # Verify correct methods were called
        mock_db.get_account.assert_called_once_with(user_id)
        mock_db.update_credit_score.assert_called_once_with(user_id, action, change, reason)
    
    async def test_update_credit_score_account_not_found(self, mock_db):
        """Test updating credit score when account doesn't exist."""
        # Set up test data
        user_id = "123456789"
        action = "on_time_payment"
        change = 10
        reason = "Made on-time loan payment"
        
        # Mock account not found
        mock_db.get_account.return_value = None
        mock_db.update_credit_score.side_effect = AccountNotFoundError(f"Account not found for user {user_id}")
        
        # Call the method and check for exception
        with pytest.raises(AccountNotFoundError):
            await mock_db.update_credit_score(user_id, action, change, reason)
        
        # Verify correct methods were called
        mock_db.get_account.assert_called_once_with(user_id)
    
    async def test_credit_score_upper_limit(self, mock_db):
        """Test that credit score doesn't exceed the upper limit (850)."""
        # Set up test data
        user_id = "123456789"
        action = "loan_fully_paid"
        change = 30  # Large positive change
        reason = "Fully repaid loan"
        
        # Mock account with credit score near upper limit
        mock_account = {
            "user_id": user_id,
            "username": "TestUser",
            "credit_score": 840,
            "credit_history": []
        }
        
        # Set up mock update result
        update_result = {
            "user_id": user_id,
            "old_score": 840,
            "new_score": 850,  # Should cap at 850, not 870
            "change": change,
            "action": action,
            "timestamp": datetime.utcnow()
        }
        
        # Set up mocks
        mock_db.get_account.return_value = mock_account
        mock_db.update_credit_score.return_value = update_result
        
        # Call the method
        result = await mock_db.update_credit_score(user_id, action, change, reason)
        
        # Verify results
        assert result is not None
        assert result["new_score"] <= 850
        
        # Verify correct methods were called
        mock_db.get_account.assert_called_once_with(user_id)
        mock_db.update_credit_score.assert_called_once_with(user_id, action, change, reason)
    
    async def test_credit_score_lower_limit(self, mock_db):
        """Test that credit score doesn't go below the lower limit (300)."""
        # Set up test data
        user_id = "123456789"
        action = "loan_default"
        change = -50  # Large negative change
        reason = "Defaulted on loan"
        
        # Mock account with credit score near lower limit
        mock_account = {
            "user_id": user_id,
            "username": "TestUser",
            "credit_score": 310,
            "credit_history": []
        }
        
        # Set up mock update result
        update_result = {
            "user_id": user_id,
            "old_score": 310,
            "new_score": 300,  # Should floor at 300, not 260
            "change": change,
            "action": action,
            "timestamp": datetime.utcnow()
        }
        
        # Set up mocks
        mock_db.get_account.return_value = mock_account
        mock_db.update_credit_score.return_value = update_result
        
        # Call the method
        result = await mock_db.update_credit_score(user_id, action, change, reason)
        
        # Verify results
        assert result is not None
        assert result["new_score"] >= 300
        
        # Verify correct methods were called
        mock_db.get_account.assert_called_once_with(user_id)
        mock_db.update_credit_score.assert_called_once_with(user_id, action, change, reason)
    
    async def test_get_credit_report(self, mock_db):
        """Test getting a comprehensive credit report."""
        # Set up test data
        user_id = "123456789"
        
        # Mock account
        mock_account = {
            "user_id": user_id,
            "username": "TestUser",
            "credit_score": 720,
            "balance": 5000.0,
            "created_at": datetime.utcnow() - timedelta(days=365),  # 1 year old account
            "credit_history": [
                {
                    "date": datetime.utcnow() - timedelta(days=90),
                    "action": "on_time_payment",
                    "change": 5,
                    "reason": "Made on-time loan payment",
                    "old_score": 715,
                    "new_score": 720
                },
                {
                    "date": datetime.utcnow() - timedelta(days=120),
                    "action": "loan_taken",
                    "change": -5,
                    "reason": "Took a loan of $1,000.00",
                    "old_score": 720,
                    "new_score": 715
                }
            ]
        }
        
        # Set up mock credit report
        mock_report = {
            "user_id": user_id,
            "credit_score": 720,
            "credit_rating": "Good",
            "account_age_days": 365,
            "transaction_count_30d": 10,
            "average_balance": 5000.0,
            "has_active_loan": True,
            "loan_repayment_status": "Current",
            "credit_limit_multiplier": 6.0,
            "loan_interest_rate": 10.0,
            "recent_credit_events": mock_account["credit_history"]
        }
        
        # Set up mocks
        mock_db.get_account.return_value = mock_account
        mock_db.get_credit_report.return_value = mock_report
        
        # Call the method
        result = await mock_db.get_credit_report(user_id)
        
        # Verify results
        assert result is not None
        assert result["credit_score"] == 720
        assert result["credit_rating"] == "Good"
        assert result["account_age_days"] == 365
        assert result["has_active_loan"] is True
        assert len(result["recent_credit_events"]) == 2
        
        # Verify correct methods were called
        mock_db.get_credit_report.assert_called_once_with(user_id)
    
    async def test_get_credit_report_account_not_found(self, mock_db):
        """Test getting a credit report when account doesn't exist."""
        # Set up test data
        user_id = "123456789"
        
        # Mock account not found
        mock_db.get_account.return_value = None
        mock_db.get_credit_report.side_effect = AccountNotFoundError(f"Account not found for user {user_id}")
        
        # Call the method and check for exception
        with pytest.raises(AccountNotFoundError):
            await mock_db.get_credit_report(user_id)
        
        # Verify correct methods were called
        mock_db.get_credit_report.assert_called_once_with(user_id)
    
    async def test_credit_rating_calculation(self, mock_db):
        """Test that credit rating is correctly calculated from credit score."""
        # Define test cases with different credit scores
        test_cases = [
            {"score": 820, "expected_rating": "Excellent"},
            {"score": 760, "expected_rating": "Very Good"},
            {"score": 710, "expected_rating": "Good"},
            {"score": 660, "expected_rating": "Fair"},
            {"score": 610, "expected_rating": "Poor"},
            {"score": 560, "expected_rating": "Very Poor"},
            {"score": 500, "expected_rating": "Bad"}
        ]
        
        for case in test_cases:
            # Set up test data
            user_id = "123456789"
            
            # Set up mock credit report with the test case score
            mock_report = {
                "user_id": user_id,
                "credit_score": case["score"],
                "credit_rating": case["expected_rating"],
                "account_age_days": 365,
                "transaction_count_30d": 10,
                "average_balance": 5000.0,
                "has_active_loan": False,
                "loan_repayment_status": "N/A",
                "credit_limit_multiplier": 6.0,
                "loan_interest_rate": 10.0,
                "recent_credit_events": []
            }
            
            # Set up mocks
            mock_db.get_credit_report.return_value = mock_report
            
            # Call the method
            result = await mock_db.get_credit_report(user_id)
            
            # Verify results
            assert result is not None
            assert result["credit_score"] == case["score"]
            assert result["credit_rating"] == case["expected_rating"]


if __name__ == "__main__":
    unittest.main() 