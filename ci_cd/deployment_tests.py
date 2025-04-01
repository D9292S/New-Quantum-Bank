"""
Deployment Readiness Tests for Quantum-Superbot

This module contains tests that verify the application is ready for deployment.
These tests are run as part of the CI/CD pipeline to ensure that the application
meets all requirements for deployment to staging or production environments.
"""

import os
import sys
import json
import logging
import asyncio
import argparse
from datetime import datetime

# Add the parent directory to the path so we can import the bot modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import bot modules
from bot import ClusterBot
from config import BotConfig
from helpers.cache_manager import CacheManager
from cogs.mongo import Database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('deployment_tests.log')
    ]
)
logger = logging.getLogger('deployment_tests')


class DeploymentReadinessTests:
    """Tests to verify the application is ready for deployment."""
    
    def __init__(self, environment='staging'):
        """Initialize the deployment readiness tests.
        
        Args:
            environment (str): The environment to test for ('staging' or 'production')
        """
        self.environment = environment
        self.results = {
            'tests_run': 0,
            'tests_passed': 0,
            'tests_failed': 0,
            'start_time': datetime.now().isoformat(),
            'end_time': None,
            'test_results': []
        }
        self.config = BotConfig()
        self.db = None
        self.bot = None
    
    async def setup(self):
        """Set up the test environment."""
        logger.info(f"Setting up test environment for {self.environment}")
        
        # Create a mock bot instance for testing
        self.bot = ClusterBot(command_prefix='!', test_mode=True)
        
        # Initialize database connection
        self.db = Database(self.bot)
        await self.db.connect()
        
        logger.info("Test environment setup complete")
    
    async def teardown(self):
        """Clean up the test environment."""
        logger.info("Tearing down test environment")
        
        if self.db:
            await self.db.close()
        
        if self.bot:
            await self.bot.close()
        
        logger.info("Test environment teardown complete")
    
    async def run_tests(self):
        """Run all deployment readiness tests."""
        logger.info(f"Running deployment readiness tests for {self.environment}")
        
        try:
            await self.setup()
            
            # Run database tests
            await self.test_database_connection()
            await self.test_database_indexes()
            await self.test_database_permissions()
            
            # Run configuration tests
            await self.test_required_env_vars()
            await self.test_feature_flags()
            
            # Run performance tests
            await self.test_memory_usage()
            await self.test_cache_performance()
            
            # Run security tests
            await self.test_sensitive_data_encryption()
            
            self.results['end_time'] = datetime.now().isoformat()
            logger.info(f"Tests completed: {self.results['tests_passed']} passed, "
                       f"{self.results['tests_failed']} failed")
            
            return self.results['tests_failed'] == 0
            
        except Exception as e:
            logger.error(f"Error running tests: {e}")
            self.results['end_time'] = datetime.now().isoformat()
            return False
        finally:
            await self.teardown()
    
    def record_result(self, test_name, passed, message=None, data=None):
        """Record a test result.
        
        Args:
            test_name (str): The name of the test
            passed (bool): Whether the test passed
            message (str, optional): A message describing the result
            data (dict, optional): Additional data about the test
        """
        self.results['tests_run'] += 1
        
        if passed:
            self.results['tests_passed'] += 1
            logger.info(f"✅ {test_name}: {message}")
        else:
            self.results['tests_failed'] += 1
            logger.error(f"❌ {test_name}: {message}")
        
        self.results['test_results'].append({
            'name': test_name,
            'passed': passed,
            'message': message,
            'data': data,
            'timestamp': datetime.now().isoformat()
        })
    
    async def test_database_connection(self):
        """Test that the database connection is working."""
        try:
            # Attempt to ping the database
            result = await self.db.ping()
            
            self.record_result(
                'database_connection',
                passed=True,
                message="Successfully connected to database",
                data={'ping_time_ms': result.get('ping_time_ms')}
            )
        except Exception as e:
            self.record_result(
                'database_connection',
                passed=False,
                message=f"Failed to connect to database: {str(e)}"
            )
    
    async def test_database_indexes(self):
        """Test that all required database indexes exist."""
        try:
            # Get list of collections and their indexes
            collections = ['accounts', 'transactions', 'loans']
            missing_indexes = []
            
            for collection in collections:
                indexes = await self.db.get_indexes(collection)
                
                # Check for required indexes based on collection
                if collection == 'accounts':
                    if not any(idx.get('name') == 'user_id_idx' for idx in indexes):
                        missing_indexes.append(f"{collection}.user_id_idx")
                
                elif collection == 'transactions':
                    if not any(idx.get('name') == 'account_id_timestamp_idx' for idx in indexes):
                        missing_indexes.append(f"{collection}.account_id_timestamp_idx")
                
                elif collection == 'loans':
                    if not any(idx.get('name') == 'account_id_status_idx' for idx in indexes):
                        missing_indexes.append(f"{collection}.account_id_status_idx")
            
            if not missing_indexes:
                self.record_result(
                    'database_indexes',
                    passed=True,
                    message="All required database indexes exist",
                    data={'collections_checked': collections}
                )
            else:
                self.record_result(
                    'database_indexes',
                    passed=False,
                    message="Missing required database indexes",
                    data={'missing_indexes': missing_indexes}
                )
        except Exception as e:
            self.record_result(
                'database_indexes',
                passed=False,
                message=f"Failed to check database indexes: {str(e)}"
            )
    
    async def test_database_permissions(self):
        """Test that the database user has the required permissions."""
        try:
            # Attempt operations that require different permissions
            operations = [
                ('read', await self.db.test_read_permission()),
                ('write', await self.db.test_write_permission()),
                ('index', await self.db.test_index_permission())
            ]
            
            failed_operations = [op[0] for op in operations if not op[1]]
            
            if not failed_operations:
                self.record_result(
                    'database_permissions',
                    passed=True,
                    message="Database user has all required permissions",
                    data={'operations_tested': [op[0] for op in operations]}
                )
            else:
                self.record_result(
                    'database_permissions',
                    passed=False,
                    message="Database user is missing required permissions",
                    data={'failed_operations': failed_operations}
                )
        except Exception as e:
            self.record_result(
                'database_permissions',
                passed=False,
                message=f"Failed to check database permissions: {str(e)}"
            )
    
    async def test_required_env_vars(self):
        """Test that all required environment variables are set."""
        required_vars = [
            'BOT_TOKEN',
            'MONGODB_URI',
            'ENVIRONMENT'
        ]
        
        # Add environment-specific required vars
        if self.environment == 'production':
            required_vars.extend([
                'PERFORMANCE_MODE',
                'ERROR_REPORTING_WEBHOOK'
            ])
        
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if not missing_vars:
            self.record_result(
                'required_env_vars',
                passed=True,
                message="All required environment variables are set",
                data={'vars_checked': required_vars}
            )
        else:
            self.record_result(
                'required_env_vars',
                passed=False,
                message="Missing required environment variables",
                data={'missing_vars': missing_vars}
            )
    
    async def test_feature_flags(self):
        """Test that feature flags are properly configured."""
        try:
            # Get feature flags from config
            feature_flags = self.config.get_feature_flags()
            
            # Check for environment-specific feature flags
            if self.environment == 'production':
                if feature_flags.get('enable_experimental_features', False):
                    self.record_result(
                        'feature_flags',
                        passed=False,
                        message="Experimental features should not be enabled in production",
                        data={'current_flags': feature_flags}
                    )
                    return
            
            self.record_result(
                'feature_flags',
                passed=True,
                message="Feature flags are properly configured for the environment",
                data={'current_flags': feature_flags}
            )
        except Exception as e:
            self.record_result(
                'feature_flags',
                passed=False,
                message=f"Failed to check feature flags: {str(e)}"
            )
    
    async def test_memory_usage(self):
        """Test that memory usage is within acceptable limits."""
        try:
            import psutil
            
            # Get current process memory usage
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)
            
            # Define limits based on environment
            limit_mb = 500 if self.environment == 'production' else 750
            
            if memory_mb <= limit_mb:
                self.record_result(
                    'memory_usage',
                    passed=True,
                    message=f"Memory usage is within acceptable limits ({memory_mb:.2f} MB)",
                    data={'memory_mb': memory_mb, 'limit_mb': limit_mb}
                )
            else:
                self.record_result(
                    'memory_usage',
                    passed=False,
                    message=f"Memory usage exceeds acceptable limits ({memory_mb:.2f} MB)",
                    data={'memory_mb': memory_mb, 'limit_mb': limit_mb}
                )
        except Exception as e:
            self.record_result(
                'memory_usage',
                passed=False,
                message=f"Failed to check memory usage: {str(e)}"
            )
    
    async def test_cache_performance(self):
        """Test cache performance."""
        try:
            # Initialize cache manager
            cache = CacheManager(max_size=1000, ttl=300)
            
            # Measure cache performance
            start_time = datetime.now()
            
            # Perform a series of cache operations
            for i in range(1000):
                cache.set(f"test_key_{i}", f"test_value_{i}")
            
            for i in range(1000):
                cache.get(f"test_key_{i}")
            
            end_time = datetime.now()
            duration_ms = (end_time - start_time).total_seconds() * 1000
            
            # Define performance thresholds based on environment
            threshold_ms = 200 if self.environment == 'production' else 300
            
            if duration_ms <= threshold_ms:
                self.record_result(
                    'cache_performance',
                    passed=True,
                    message=f"Cache performance is acceptable ({duration_ms:.2f} ms)",
                    data={'duration_ms': duration_ms, 'threshold_ms': threshold_ms}
                )
            else:
                self.record_result(
                    'cache_performance',
                    passed=False,
                    message=f"Cache performance is below acceptable levels ({duration_ms:.2f} ms)",
                    data={'duration_ms': duration_ms, 'threshold_ms': threshold_ms}
                )
        except Exception as e:
            self.record_result(
                'cache_performance',
                passed=False,
                message=f"Failed to check cache performance: {str(e)}"
            )
    
    async def test_sensitive_data_encryption(self):
        """Test that sensitive data is properly encrypted."""
        try:
            # Check if encryption is enabled and working
            from helpers.encryption import is_encryption_configured, encrypt, decrypt
            
            if not is_encryption_configured():
                self.record_result(
                    'sensitive_data_encryption',
                    passed=False,
                    message="Encryption is not configured"
                )
                return
            
            # Test encryption/decryption
            test_data = "sensitive_test_data"
            encrypted = encrypt(test_data)
            decrypted = decrypt(encrypted)
            
            if decrypted == test_data:
                self.record_result(
                    'sensitive_data_encryption',
                    passed=True,
                    message="Encryption is properly configured and working"
                )
            else:
                self.record_result(
                    'sensitive_data_encryption',
                    passed=False,
                    message="Encryption/decryption test failed"
                )
        except ImportError:
            self.record_result(
                'sensitive_data_encryption',
                passed=False,
                message="Encryption module not found"
            )
        except Exception as e:
            self.record_result(
                'sensitive_data_encryption',
                passed=False,
                message=f"Failed to check encryption: {str(e)}"
            )
    
    def save_results(self, output_file):
        """Save test results to a file.
        
        Args:
            output_file (str): The file to save results to
        """
        with open(output_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        logger.info(f"Test results saved to {output_file}")
    
    def print_summary(self):
        """Print a summary of test results."""
        print("\n" + "=" * 50)
        print(f"DEPLOYMENT READINESS TEST SUMMARY - {self.environment.upper()}")
        print("=" * 50)
        print(f"Tests Run: {self.results['tests_run']}")
        print(f"Tests Passed: {self.results['tests_passed']}")
        print(f"Tests Failed: {self.results['tests_failed']}")
        print("-" * 50)
        
        for result in self.results['test_results']:
            status = "✅ PASS" if result['passed'] else "❌ FAIL"
            print(f"{status} - {result['name']}: {result['message']}")
        
        print("=" * 50)
        print(f"Overall Status: {'✅ PASSED' if self.results['tests_failed'] == 0 else '❌ FAILED'}")
        print("=" * 50)


async def main():
    """Main entry point for deployment readiness tests."""
    parser = argparse.ArgumentParser(description='Run deployment readiness tests')
    parser.add_argument('--environment', choices=['staging', 'production'], default='staging',
                      help='The environment to test for')
    parser.add_argument('--output', default='deployment_test_results.json',
                      help='File to save test results to')
    args = parser.parse_args()
    
    # Run tests
    tests = DeploymentReadinessTests(environment=args.environment)
    success = await tests.run_tests()
    
    # Save and print results
    tests.save_results(args.output)
    tests.print_summary()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    asyncio.run(main())
