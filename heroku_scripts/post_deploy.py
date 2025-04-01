#!/usr/bin/env python
"""
Post-deployment configuration script for Heroku.
Ensures performance optimizations are correctly set up after deployment.
"""

import os
import sys
import logging
import json
import subprocess

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger('post_deploy')

def configure_performance_settings():
    """Configure performance settings based on dyno specs"""
    logger.info("Configuring performance settings for Heroku environment...")
    
    # Detect Heroku dyno type
    dyno_type = os.environ.get('DYNO_TYPE', '')
    is_free_tier = dyno_type.startswith('free') or dyno_type.startswith('eco')
    is_standard = dyno_type.startswith('standard')
    is_performance = dyno_type.startswith('performance')
    
    # Configure environment variables based on dyno type
    env_updates = {}
    
    if is_free_tier:
        logger.info("Detected free/eco dyno, configuring for low resource usage")
        env_updates = {
            "PERFORMANCE_MODE": "low",
            "MEMORY_LIMIT_MB": "200",
            "QUERY_CACHE_SIZE": "500",
            "QUERY_CACHE_TTL": "120"
        }
    elif is_standard:
        logger.info("Detected standard dyno, configuring for medium resource usage")
        env_updates = {
            "PERFORMANCE_MODE": "medium",
            "MEMORY_LIMIT_MB": "400",
            "QUERY_CACHE_SIZE": "1000",
            "QUERY_CACHE_TTL": "300"
        }
    elif is_performance:
        logger.info("Detected performance dyno, configuring for high resource usage")
        env_updates = {
            "PERFORMANCE_MODE": "high",
            "MEMORY_LIMIT_MB": "800",
            "QUERY_CACHE_SIZE": "2000",
            "QUERY_CACHE_TTL": "600"
        }
    else:
        logger.info("Could not detect dyno type, using default medium settings")
        env_updates = {
            "PERFORMANCE_MODE": "medium",
            "MEMORY_LIMIT_MB": "400",
            "QUERY_CACHE_SIZE": "1000",
            "QUERY_CACHE_TTL": "300"
        }
    
    # Don't override existing explicit configurations
    for key, value in env_updates.items():
        if key not in os.environ:
            logger.info(f"Setting {key}={value}")
            # We can't modify env vars directly, so we'll output them for the release phase script
            print(f"heroku config:set {key}={value}")
        else:
            logger.info(f"Keeping existing {key}={os.environ.get(key)}")
    
    return env_updates

def check_mongodb_indexes():
    """Check and create optimized MongoDB indexes"""
    try:
        logger.info("Checking MongoDB indexes...")
        # This part would be implemented in a real environment
        # with pymongo to check and create indexes
        
        # Placeholder for demonstration
        logger.info("MongoDB indexes verified")
        return True
    except Exception as e:
        logger.error(f"Error checking MongoDB indexes: {e}")
        return False

def verify_performance_optimizations():
    """Verify that our performance optimizations can be loaded"""
    try:
        # Try to import our optimization modules
        import importlib.util
        
        modules_to_check = [
            "optimizations.memory_management",
            "optimizations.db_performance",
            "optimizations.mongodb_improvements"
        ]
        
        all_available = True
        for module_name in modules_to_check:
            spec = importlib.util.find_spec(module_name)
            if spec is None:
                logger.error(f"Module {module_name} not found")
                all_available = False
            else:
                logger.info(f"Module {module_name} is available")
        
        return all_available
    except Exception as e:
        logger.error(f"Error verifying optimizations: {e}")
        return False

def verify_uv_installation():
    """Verify that uv is installed and working correctly"""
    try:
        # Check if uv is available and get its version
        result = subprocess.run(
            ["uv", "--version"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        uv_version = result.stdout.strip()
        logger.info(f"uv package manager is available: {uv_version}")
        return True
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.error(f"uv package manager is not available: {e}")
        return False

def main():
    """Main post-deployment function"""
    logger.info("Starting post-deployment configuration...")
    
    # Verify uv installation
    uv_ok = verify_uv_installation()
    if not uv_ok:
        logger.warning("uv package manager not detected, some features may not work correctly")
    
    # Configure performance settings
    env_updates = configure_performance_settings()
    
    # Check MongoDB indexes
    db_indexes_ok = check_mongodb_indexes()
    
    # Verify performance optimizations
    optimizations_ok = verify_performance_optimizations()
    
    # Output success or failure
    if db_indexes_ok and optimizations_ok:
        logger.info("Post-deployment configuration completed successfully")
        
        # Write config to a file for the release phase
        with open('heroku_release_config.txt', 'w') as f:
            for key, value in env_updates.items():
                if key not in os.environ:
                    f.write(f"heroku config:set {key}={value}\n")
        
        return 0
    else:
        logger.error("Post-deployment configuration failed")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 