import asyncio
import json
import logging
import os
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import discord
from discord.ext import commands, tasks

# Try to import DevCycle, if not available use fallback
try:
    print("Attempting to import devcycle_python_sdk...")
    # Import with correct class names based on official documentation
    from devcycle_python_sdk import DevCycleLocalClient, DevCycleLocalOptions
    from devcycle_python_sdk.models.user import DevCycleUser
    print(f"DevCycle SDK import successful")
    DEVCYCLE_AVAILABLE = True
except ImportError as e:
    print(f"DevCycle SDK import error: {str(e)}")
    DEVCYCLE_AVAILABLE = False
    # Define fallback classes for DevCycle
    class DevCycleLocalOptions:
        def __init__(self, **kwargs):
            self.options = kwargs
    
    class DevCycleLocalClient:
        def __init__(self, sdk_key, options=None):
            self.sdk_key = sdk_key
            self.options = options
            
        def all_features(self, user):
            return {}
            
        def variable_value(self, user, key, default):
            return default
            
    # Fallback user class
    class DevCycleUser:
        def __init__(self, user_id):
            self.user_id = user_id
            self.custom_data = {}

COG_METADATA = {
    "name": "feature_flags",
    "enabled": True,
    "version": "1.1",
    "description": "Manages feature flags using DevCycle for gradual rollouts and experimentation",
}


async def setup(bot):
    """Add the cog to the bot"""
    bot.add_cog(FeatureFlags(bot))


class FeatureFlags(commands.Cog):
    """Manages feature flags using DevCycle for controlled rollouts and experimentation"""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("bot")
        self.initialized = False
        self.client = None
        self.features = {}
        self.last_sync_time = None
        self._config_path = "config/devcycle.json"
        self.feature_descriptions = {}
        
        # Get the DevCycle SDK key
        self.sdk_key = os.getenv("DEVCYCLE_SERVER_SDK_KEY")
        
        if not self.sdk_key or not DEVCYCLE_AVAILABLE:
            if not self.sdk_key:
                self.logger.warning("DEVCYCLE_SERVER_SDK_KEY not set in environment, feature flags will be disabled")
            if not DEVCYCLE_AVAILABLE:
                self.logger.warning("DevCycle SDK not available, using fallback implementation for feature flags")
            # Still continue with fallback implementation
            self._load_feature_descriptions()
            self.initialized = True
            self.client = DevCycleLocalClient("dummy_key") if not DEVCYCLE_AVAILABLE else None
            self.sync_features.start()
            return
            
        # Load flag descriptions
        self._load_feature_descriptions()
        
        # Initialize DevCycle client
        self._init_devcycle()
        
        # Start background tasks
        self.sync_features.start()

    def _init_devcycle(self):
        """Initialize the DevCycle client with configuration"""
        try:
            # Verify SDK is imported correctly
            self.logger.info(f"DevCycle SDK import successful. DEVCYCLE_AVAILABLE={DEVCYCLE_AVAILABLE}")
            
            # Check if SDK key is valid format (should be dvc_server_XXXXX)
            if not self.sdk_key.startswith("dvc_server_"):
                self.logger.warning(f"DevCycle SDK key '{self.sdk_key[:10]}...' may not be in the correct format. Server keys should start with 'dvc_server_'")
            
            # Configure the DevCycle client
            self.logger.info(f"Configuring DevCycle client with SDK key: {self.sdk_key[:10]}...")
            
            # Create a simple options object as per documentation
            options = DevCycleLocalOptions()  # Use default options
            
            # Create the client
            self.logger.info("Creating DevCycle client")
            self.client = DevCycleLocalClient(self.sdk_key, options)
            self.logger.info("DevCycle client created successfully")
            
            # Test the connection with a simple call before proceeding
            self._test_devcycle_connection()
            
            # Initialize by getting all features
            self.logger.info("Refreshing features")
            self._refresh_features()
            
            self.initialized = True
            self.logger.info("DevCycle feature flag system initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize DevCycle: {str(e)}")
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            self.logger.warning("Using fallback implementation for feature flags due to initialization error")
            
            # Initialize with fallback mode
            self.initialized = True
            self.client = DevCycleLocalClient("dummy_key") if not DEVCYCLE_AVAILABLE else None
            self.features = {}  # Empty features dictionary
            
    def _test_devcycle_connection(self):
        """Test the DevCycle connection with a simple call"""
        try:
            # Create a test user
            test_user = DevCycleUser(user_id="connection_test")
            
            # Make a simple call that will validate the SDK key
            self.client.variable_value(test_user, "test_connection", False)
            self.logger.info("DevCycle connection test successful - SDK key is valid")
            return True
        except Exception as e:
            error_message = str(e)
            if "Invalid SDK Key" in error_message:
                self.logger.error(f"DevCycle SDK key is invalid. Please check your DEVCYCLE_SERVER_SDK_KEY environment variable.")
                self.logger.error(f"Format should be: dvc_server_XXXXX (current key starts with: {self.sdk_key[:15]}...)")
                self.logger.error("You can get a valid key from the DevCycle dashboard: https://app.devcycle.com/")
                # Fall back to dummy implementation
                self.client = DevCycleLocalClient("dummy_key")
                return False
            else:
                self.logger.error(f"DevCycle connection test failed: {error_message}")
                raise

    def _load_feature_descriptions(self):
        """Load feature descriptions from config file if available"""
        try:
            if os.path.exists(self._config_path):
                with open(self._config_path, "r") as f:
                    config = json.load(f)
                    self.feature_descriptions = config.get("feature_descriptions", {})
            else:
                # Create default config
                os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
                with open(self._config_path, "w") as f:
                    json.dump({"feature_descriptions": {}}, f, indent=2)
        except Exception as e:
            self.logger.error(f"Error loading feature descriptions: {str(e)}")

    def _refresh_features(self):
        """Refresh the feature list from DevCycle"""
        if not self.initialized:
            return
            
        if not DEVCYCLE_AVAILABLE:
            self.features = {}
            self.last_sync_time = datetime.now()
            return
            
        try:
            # Create a proper user object for DevCycle
            dummy_user = DevCycleUser(user_id="system")
            dummy_user.is_system = True
            
            # Get all features for the dummy user
            all_features = self.client.all_features(dummy_user)
            
            # Log the raw response for debugging
            self.logger.info(f"DevCycle raw response: {all_features}")
            self.logger.info(f"DevCycle response type: {type(all_features)}")
            
            # If features is empty but we have a connection, something is wrong
            if not all_features and self.client:
                self.logger.warning("DevCycle connection is valid but no features were returned.")
                self.logger.warning("Check that your features are published and in the correct environment.")
                # Try to request a specific known feature by key as a diagnostic
                for feature_key in ["premium-loans", "investment-portfolio", "premium-features"]:
                    try:
                        value = self.client.variable_value(dummy_user, feature_key, False)
                        self.logger.info(f"Test request for feature '{feature_key}': {value}")
                    except Exception as e:
                        self.logger.warning(f"Test request for '{feature_key}' failed: {e}")
            
            # Store the features
            self.features = all_features
            self.last_sync_time = datetime.now()
            
            # Log the refresh
            self.logger.info(f"Refreshed feature flags: {len(self.features)} features available")
        except Exception as e:
            self.logger.error(f"Error refreshing features: {str(e)}")
            self.logger.error(f"Traceback: {traceback.format_exc()}")

    @tasks.loop(minutes=5)
    async def sync_features(self):
        """Periodically sync feature flags from DevCycle"""
        if not self.initialized:
            return
            
        try:
            self._refresh_features()
        except Exception as e:
            self.logger.error(f"Error in sync_features task: {str(e)}")
            self.logger.error(f"Traceback: {traceback.format_exc()}")

    @sync_features.before_loop
    async def before_sync_features(self):
        """Wait for the bot to be ready before starting feature sync"""
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)  # Give a few seconds after ready

    def is_enabled(self, feature_key: str, user_id: str = None, guild_id: str = None, default: bool = False) -> bool:
        """
        Check if a feature flag is enabled for a specific user/guild
        
        Args:
            feature_key (str): The feature flag key to check
            user_id (str, optional): The user ID to check against
            guild_id (str, optional): The guild/server ID to check against
            default (bool, optional): Default value if flag doesn't exist or error occurs
            
        Returns:
            bool: Whether the feature is enabled
        """
        if not self.initialized or not self.client:
            return default
            
        try:
            # Create DevCycle user with the provided user_id
            user_data = DevCycleUser(user_id=user_id or "system")
            
            # Add guild info if available
            if guild_id:
                user_data.custom_data = {"guild_id": guild_id}
                
            # Check if the feature is enabled
            variable = self.client.variable_value(user_data, feature_key, default)
            return bool(variable)
        except Exception as e:
            self.logger.error(f"Error checking feature flag {feature_key}: {str(e)}")
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return default

    def get_variable(self, feature_key: str, user_id: str = None, guild_id: str = None, default: Any = None) -> Any:
        """
        Get a feature variable value for a specific user/guild
        
        Args:
            feature_key (str): The feature variable key to retrieve
            user_id (str, optional): The user ID to check against
            guild_id (str, optional): The guild/server ID to check against
            default (Any, optional): Default value if variable doesn't exist or error occurs
            
        Returns:
            Any: The variable value
        """
        if not self.initialized or not self.client:
            return default
            
        try:
            # Create DevCycle user with the provided user_id
            user_data = DevCycleUser(user_id=user_id or "system")
            
            # Add guild info if available
            if guild_id:
                user_data.custom_data = {"guild_id": guild_id}
                
            # Get the variable value
            return self.client.variable_value(user_data, feature_key, default)
        except Exception as e:
            self.logger.error(f"Error getting variable {feature_key}: {str(e)}")
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return default

    def get_all_features(self) -> Dict[str, Any]:
        """Get all available feature flags"""
        return self.features if self.initialized else {}

    @commands.slash_command(name="features", description="Manage feature flags")
    @commands.has_permissions(administrator=True)
    async def features_group(self, ctx: discord.ApplicationContext):
        """Command group for feature flag management"""
        if not ctx.subcommand_passed:
            await ctx.respond("Please use a subcommand: `/features list`, `/features check`, or `/features refresh`")

    @commands.slash_command(name="features_list", description="List all available feature flags")
    @commands.has_permissions(administrator=True)
    async def list_features(self, ctx: discord.ApplicationContext):
        """List all feature flags available in the system"""
        if not self.initialized:
            await ctx.respond("Feature flag system is not initialized", ephemeral=True)
            return
            
        # Create embed with feature information
        embed = discord.Embed(
            title="Feature Flags",
            description=f"Feature flags control which features are enabled.\nLast sync: {self.last_sync_time.strftime('%Y-%m-%d %H:%M:%S') if self.last_sync_time else 'Never'}",
            color=discord.Color.blue()
        )
        
        # Add fields for each feature
        if not self.features:
            embed.add_field(name="No features available", value="No feature flags are currently defined", inline=False)
        else:
            for key, feature in self.features.items():
                description = self.feature_descriptions.get(key, "No description available")
                # Access Feature object properties directly instead of using .get()
                try:
                    # Try to get variation information if available
                    variation_info = f"{feature.variationName}" if hasattr(feature, 'variationName') else "Default"
                    embed.add_field(
                        name=f"🚩 {key}",
                        value=f"**Description:** {description}\n**Type:** {feature.type}\n**Variation:** {variation_info}",
                        inline=False
                    )
                except AttributeError:
                    # Fallback for any unexpected object structure
                    embed.add_field(
                        name=f"🚩 {key}",
                        value=f"**Description:** {description}\n**Type:** {str(type(feature))}",
                        inline=False
                    )
                
        await ctx.respond(embed=embed)

    @commands.slash_command(name="features_check", description="Check if a feature flag is enabled")
    @commands.has_permissions(administrator=True)
    async def check_feature(
        self,
        ctx: discord.ApplicationContext,
        feature_key: discord.Option(str, "The feature flag key to check"),
        user_id: discord.Option(str, "User ID to check against (defaults to command user)", required=False),
        guild_id: discord.Option(str, "Guild ID to check against (defaults to current guild)", required=False)
    ):
        """Check if a specific feature flag is enabled for a user/guild"""
        if not self.initialized:
            await ctx.respond("Feature flag system is not initialized", ephemeral=True)
            return
            
        # Use defaults if not specified
        user_id = user_id or str(ctx.author.id)
        guild_id = guild_id or str(ctx.guild.id)
        
        # Check the feature flag
        enabled = self.is_enabled(feature_key, user_id, guild_id)
        
        # Get feature description
        description = self.feature_descriptions.get(feature_key, "No description available")
        
        # Create response embed
        embed = discord.Embed(
            title=f"Feature Flag: {feature_key}",
            description=description,
            color=discord.Color.green() if enabled else discord.Color.red()
        )
        
        embed.add_field(name="Status", value=f"{'✅ Enabled' if enabled else '❌ Disabled'}", inline=False)
        embed.add_field(name="User ID", value=user_id, inline=True)
        embed.add_field(name="Guild ID", value=guild_id, inline=True)
        
        await ctx.respond(embed=embed)

    @commands.slash_command(name="features_refresh", description="Refresh feature flags from DevCycle")
    @commands.has_permissions(administrator=True)
    async def refresh_features(self, ctx: discord.ApplicationContext):
        """Refresh feature flags from DevCycle"""
        if not self.initialized:
            await ctx.respond("Feature flag system is not initialized", ephemeral=True)
            return
            
        # Create initial message
        await ctx.respond("Refreshing feature flags from DevCycle...", ephemeral=True)
        
        try:
            # Refresh the features
            self._refresh_features()
            
            # Get status information
            status_info = []
            status_info.append(f"SDK Key Valid: {'Yes' if self._test_devcycle_connection() else 'No'}")
            status_info.append(f"Features Found: {len(self.features)}")
            
            # Check specific features
            for feature_key in ["premium-loans", "investment-portfolio", "premium-features"]:
                test_result = self._test_specific_feature(feature_key)
                status_info.append(f"'{feature_key}': {test_result}")
            
            # Return success message with diagnostics
            status_message = "\n".join(status_info)
            await ctx.respond(
                f"✅ Feature flags refreshed\n\n**Diagnostics:**\n```{status_message}```",
                ephemeral=True
            )
        except Exception as e:
            # Return error message
            await ctx.respond(
                f"❌ Error refreshing feature flags: {str(e)}",
                ephemeral=True
            )
            
    def _test_specific_feature(self, feature_key: str) -> str:
        """Test if a specific feature can be retrieved"""
        try:
            dummy_user = DevCycleUser(user_id="test_user")
            value = self.client.variable_value(dummy_user, feature_key, False)
            if value is None:
                return "Not found"
            return f"Found (value: {value})"
        except Exception as e:
            return f"Error: {str(e)[:50]}..."

    @commands.slash_command(name="features_describe", description="Update the description of a feature flag")
    @commands.has_permissions(administrator=True)
    async def describe_feature(
        self,
        ctx: discord.ApplicationContext,
        feature_key: discord.Option(str, "The feature flag key to describe"),
        description: discord.Option(str, "The description for this feature flag")
    ):
        """Update the description of a feature flag"""
        if not self.initialized:
            await ctx.respond("Feature flag system is not initialized", ephemeral=True)
            return
            
        # Update description
        self.feature_descriptions[feature_key] = description
        
        # Save to file
        try:
            if os.path.exists(self._config_path):
                with open(self._config_path, "r") as f:
                    config = json.load(f)
                    
                config["feature_descriptions"] = self.feature_descriptions
                
                with open(self._config_path, "w") as f:
                    json.dump(config, f, indent=2)
                    
                await ctx.respond(f"✅ Description for '{feature_key}' updated", ephemeral=True)
            else:
                await ctx.respond("❌ Configuration file not found", ephemeral=True)
        except Exception as e:
            await ctx.respond(f"❌ Error updating description: {str(e)}", ephemeral=True)

    @commands.slash_command(name="features_debug", description="Debug feature flags with specific keys")
    @commands.has_permissions(administrator=True)
    async def debug_features(self, ctx: discord.ApplicationContext):
        """Debug feature flags with known keys"""
        if not self.initialized:
            await ctx.respond("Feature flag system is not initialized", ephemeral=True)
            return
            
        # Create initial message
        await ctx.respond("Debugging feature flags with known keys...", ephemeral=True)
        
        try:
            # Define the feature keys to test based on your DevCycle dashboard
            feature_keys = [
                # Keys matching your dashboard
                "premium-loans", "premium_loans",
                "investment-portfolio", "investment_portfolio",
                "premium-features", "premium_features",
                
                # Try different variations
                "premium_banking", "premium-banking"
            ]
            
            # Create a test user
            test_user = DevCycleUser(user_id="debug_user")
            test_user.is_system = True
            
            # Test each feature key
            results = []
            for key in feature_keys:
                try:
                    # Try to get the variable value with appropriate default value for each type
                    # Boolean default for flags
                    value = self.client.variable_value(test_user, key, False)
                    results.append(f"'{key}': {value}")
                except Exception as e:
                    results.append(f"'{key}': Error - {str(e)[:50]}...")
            
            # Get all features
            try:
                all_features = self.client.all_features(test_user)
                results.append(f"\nAll features ({len(all_features)} found):")
                for k, v in all_features.items():
                    try:
                        # Try to access information as object properties
                        variation_info = f"{v.variationName}" if hasattr(v, 'variationName') else "Default"
                        results.append(f"  - {k}: Type={v.type}, Variation={variation_info}")
                    except AttributeError:
                        # Fallback for any unexpected object structure
                        results.append(f"  - {k}: {str(type(v))}")
            except Exception as e:
                results.append(f"\nError getting all features: {str(e)}")
                
            # Return results
            result_message = "\n".join(results)
            await ctx.respond(
                f"**Feature Flag Debug Results:**\n```{result_message}```",
                ephemeral=True
            )
        except Exception as e:
            # Return error message
            await ctx.respond(
                f"❌ Error debugging feature flags: {str(e)}",
                ephemeral=True
            )

    def cog_unload(self):
        """Clean up when the cog is unloaded"""
        # Stop background tasks
        self.sync_features.cancel() 