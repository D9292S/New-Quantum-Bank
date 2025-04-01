"""
Canary Deployment Traffic Router

This script configures traffic routing between canary and production deployments
by updating Discord bot gateway configurations to control shard distribution.
"""

import os
import sys
import json
import logging
import argparse
import requests
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('traffic_router.log')
    ]
)
logger = logging.getLogger('traffic_router')


class TrafficRouter:
    """Manages traffic routing between canary and production deployments."""
    
    def __init__(
        self,
        canary_app_name: str,
        production_app_name: str,
        heroku_api_key: str,
        discord_token: str
    ):
        """Initialize the traffic router.
        
        Args:
            canary_app_name: Name of the canary Heroku app
            production_app_name: Name of the production Heroku app
            heroku_api_key: Heroku API key for authentication
            discord_token: Discord bot token for gateway configuration
        """
        self.canary_app_name = canary_app_name
        self.production_app_name = production_app_name
        self.heroku_api_key = heroku_api_key
        self.discord_token = discord_token
        self.heroku_headers = {
            'Accept': 'application/vnd.heroku+json; version=3',
            'Authorization': f'Bearer {heroku_api_key}',
            'Content-Type': 'application/json'
        }
        self.discord_headers = {
            'Authorization': f'Bot {discord_token}',
            'Content-Type': 'application/json'
        }
    
    def get_gateway_info(self) -> Dict[str, Any]:
        """Get Discord gateway information.
        
        Returns:
            Dictionary with gateway information
        """
        try:
            response = requests.get(
                'https://discord.com/api/v10/gateway/bot',
                headers=self.discord_headers
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get gateway info: {response.status_code}")
                logger.error(response.text)
                return {}
        except Exception as e:
            logger.error(f"Error getting gateway info: {e}")
            return {}
    
    def update_heroku_config(self, app_name: str, config: Dict[str, str]) -> bool:
        """Update Heroku app configuration.
        
        Args:
            app_name: Name of the Heroku app
            config: Dictionary of configuration variables to update
        
        Returns:
            True if successful, False otherwise
        """
        try:
            response = requests.patch(
                f'https://api.heroku.com/apps/{app_name}/config-vars',
                headers=self.heroku_headers,
                json=config
            )
            
            if response.status_code == 200:
                logger.info(f"Updated config for {app_name}")
                return True
            else:
                logger.error(f"Failed to update config for {app_name}: {response.status_code}")
                logger.error(response.text)
                return False
        except Exception as e:
            logger.error(f"Error updating config for {app_name}: {e}")
            return False
    
    def restart_heroku_app(self, app_name: str) -> bool:
        """Restart a Heroku app.
        
        Args:
            app_name: Name of the Heroku app
        
        Returns:
            True if successful, False otherwise
        """
        try:
            response = requests.delete(
                f'https://api.heroku.com/apps/{app_name}/dynos',
                headers=self.heroku_headers
            )
            
            if response.status_code == 202:
                logger.info(f"Restarted {app_name}")
                return True
            else:
                logger.error(f"Failed to restart {app_name}: {response.status_code}")
                logger.error(response.text)
                return False
        except Exception as e:
            logger.error(f"Error restarting {app_name}: {e}")
            return False
    
    def configure_traffic_split(self, canary_percentage: int) -> bool:
        """Configure traffic split between canary and production.
        
        Args:
            canary_percentage: Percentage of traffic to route to canary (0-100)
        
        Returns:
            True if successful, False otherwise
        """
        if not 0 <= canary_percentage <= 100:
            logger.error(f"Invalid canary percentage: {canary_percentage}")
            return False
        
        # Get Discord gateway information
        gateway_info = self.get_gateway_info()
        if not gateway_info:
            return False
        
        total_shards = gateway_info.get('shards', 1)
        logger.info(f"Discord recommends {total_shards} total shards")
        
        # Calculate shard distribution
        canary_shards = max(1, int(total_shards * (canary_percentage / 100)))
        production_shards = total_shards - canary_shards
        
        logger.info(f"Shard distribution: Canary: {canary_shards}, Production: {production_shards}")
        
        # Configure canary app
        canary_config = {
            'SHARD_COUNT': str(total_shards),
            'SHARD_IDS': ','.join(str(i) for i in range(canary_shards)),
            'TRAFFIC_PERCENTAGE': str(canary_percentage)
        }
        
        # Configure production app
        production_config = {
            'SHARD_COUNT': str(total_shards),
            'SHARD_IDS': ','.join(str(i) for i in range(canary_shards, total_shards)),
            'TRAFFIC_PERCENTAGE': str(100 - canary_percentage)
        }
        
        # Update Heroku configs
        canary_success = self.update_heroku_config(self.canary_app_name, canary_config)
        production_success = self.update_heroku_config(self.production_app_name, production_config)
        
        if not canary_success or not production_success:
            logger.error("Failed to update one or both app configurations")
            return False
        
        # Restart apps to apply changes
        canary_restart = self.restart_heroku_app(self.canary_app_name)
        production_restart = self.restart_heroku_app(self.production_app_name)
        
        if not canary_restart or not production_restart:
            logger.error("Failed to restart one or both apps")
            return False
        
        logger.info(f"Successfully configured traffic split: {canary_percentage}% to canary, "
                   f"{100 - canary_percentage}% to production")
        return True
    
    def route_all_traffic_to_production(self) -> bool:
        """Route all traffic to production (0% to canary).
        
        Returns:
            True if successful, False otherwise
        """
        return self.configure_traffic_split(0)
    
    def route_all_traffic_to_canary(self) -> bool:
        """Route all traffic to canary (100% to canary).
        
        Returns:
            True if successful, False otherwise
        """
        return self.configure_traffic_split(100)


def main():
    """Main entry point for traffic router."""
    parser = argparse.ArgumentParser(description='Configure traffic routing for canary deployments')
    parser.add_argument('--canary-app', default='quantum-superbot-canary',
                      help='Name of the canary Heroku app')
    parser.add_argument('--production-app', default='quantum-superbot',
                      help='Name of the production Heroku app')
    parser.add_argument('--percentage', type=int, required=True,
                      help='Percentage of traffic to route to canary (0-100)')
    parser.add_argument('--heroku-api-key',
                      help='Heroku API key (or set HEROKU_API_KEY env var)')
    parser.add_argument('--discord-token',
                      help='Discord bot token (or set DISCORD_TOKEN env var)')
    args = parser.parse_args()
    
    # Get API keys from args or environment
    heroku_api_key = args.heroku_api_key or os.environ.get('HEROKU_API_KEY')
    discord_token = args.discord_token or os.environ.get('DISCORD_TOKEN')
    
    if not heroku_api_key:
        logger.error("Heroku API key not provided")
        sys.exit(1)
    
    if not discord_token:
        logger.error("Discord token not provided")
        sys.exit(1)
    
    # Create router and configure traffic
    router = TrafficRouter(
        canary_app_name=args.canary_app,
        production_app_name=args.production_app,
        heroku_api_key=heroku_api_key,
        discord_token=discord_token
    )
    
    success = router.configure_traffic_split(args.percentage)
    
    if success:
        logger.info("Traffic routing configured successfully")
        sys.exit(0)
    else:
        logger.error("Failed to configure traffic routing")
        sys.exit(1)


if __name__ == '__main__':
    main()
