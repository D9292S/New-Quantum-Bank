import discord
from discord.ext import commands
import asyncio
from datetime import datetime
from mongo import get_account, create_account, set_upi_id, get_transactions, log_transaction, update_balance, log_failed_kyc_attempt

from PIL import Image, ImageDraw, ImageFont
import io

import requests

class Account(commands.Cog):  
    """
    A cog that handles user account-related functionalities.

    This cog is responsible for managing and interacting with user accounts.
    It provides commands to create accounts, view account balances, and possibly
    handle other user-specific account actions like transactions.

    Attributes:
        bot (commands.Bot): The bot instance to which this cog is attached.
    """
    def __init__(self, bot):
        self.bot = bot

    @discord.slash_command(description="Initiate KYC verification for account creation.")
    async def create_account(self, ctx):
        """
        Initiates KYC verification for account creation.
        The user will be prompted to provide their proof of identity (Discord User ID)
        and proof of Residence (Guild ID) via private message.
        """
        actual_user_id = str(ctx.author.id)
        actual_guild_id = str(ctx.guild.id)
        username = ctx.author.name
        guild_name = ctx.guild.name

        existing_account = get_account(actual_user_id)
        if existing_account:
            embed = discord.Embed(
                title="Account Already Exists",
                description=f"You already have an account at the **'{existing_account['branch_name']}'** branch!",
                color=discord.Color.red()
            )
            await ctx.respond(embed=embed) 
            return

        welcome_embed = discord.Embed(
            title="Hi 👋 Welcome to the **QUANTUM BANK ⚛️**",
            description="To create an account, you need to verify your identity and residence.\n\n"
                        "Please check your DMs for further instructions.",
            color=discord.Color.gold()  
        )
        await ctx.respond(embed=welcome_embed)

        # Wait a moment before sending DMs
        await asyncio.sleep(2)

        while True:
            # Send DM for KYC verification
            try:
                dm_embed = discord.Embed(
                    title="KYC Verification Required",
                    description="Please provide your proof of identity (**Discord User ID**) and Proof of residence (**Guild ID**).\n\n"
                                "**Format**: '<Your Discord User ID> <Your Guild ID>'\n\n"
                                "**For Example**: `1234567890 1234567890`\n\n"
                                "If you don't know how to get your Discord User ID, click [here](https://support.discord.com/hc/en-us/articles/206346498-Where-can-I-find-my-User-Server-Message-ID-)\n\n"
                                "**NOTE**: You have 2 minutes to respond.",
                    color=discord.Color.gold()
                )
                await ctx.author.send(embed=dm_embed)

            except discord.Forbidden:
                error_embed = discord.Embed(
                    title="KYC Verification Failed",
                    description="I couldn't send you a DM. Please enable DMs from server members and try again.",
                    color=discord.Color.red()
                )
                await ctx.respond(embed=error_embed)
                return

            # Wait for user's response in DM
            def check(msg):
                """
                Checks if the message is sent by the command author and in a DM channel.

                This function is used to filter messages based on two conditions:
                1. The message must be sent by the same user who invoked the command.
                2. The message must be sent in a direct message (DM) channel.

                Parameters:
                    msg (discord.Message): The message object to check.

                Returns:
                    bool: Returns True if the message is from the command author
                    and is in a DM channel, otherwise returns False.
                """
                return msg.author == ctx.author and isinstance(msg.channel, discord.DMChannel)

            try:
                dm_response = await self.bot.wait_for('message', check=check, timeout=120)  # Wait for 2 minutes
                provided_data = dm_response.content.split()

                if len(provided_data) != 2:
                    invalid_format_embed = discord.Embed(
                        title="Invalid Format",
                        description="Please provide your Discord User ID and Guild ID in the correct format. For example: `1234567890 1234567890`",
                        color=discord.Color.red()
                    )
                    await ctx.author.send(embed=invalid_format_embed)
                    continue

                # Processing Your KYC details in Central Database Please wait for 10 seconds
                processing_embed = discord.Embed(
                    title="Processing Your KYC details in Central Database",
                    description="Please wait while we verify your KYC details.",
                    color=discord.Color.gold()
                )
                await ctx.author.send(embed=processing_embed)

                provided_user_id, provided_guild_id = provided_data

                await asyncio.sleep(10)  # Simulate processing time

                # Validate KYC details
                if provided_user_id != actual_user_id or provided_guild_id != actual_guild_id:
                    # Log failed KYC attempt
                    log_failed_kyc_attempt(user_id=actual_user_id, 
                                            provided_user_id=provided_user_id,
                                            guild_id=actual_guild_id,
                                            provided_guild_id=provided_guild_id,
                                            reason="KYC details mismatch")

                    kyc_failed_embed = discord.Embed(
                        title="KYC Verification Failed",
                        description="The provided details do not match your actual Discord User ID and Guild ID. Please try again.",
                        color=discord.Color.red()
                    )
                    await ctx.author.send(embed=kyc_failed_embed) 
                    continue

                # Create new account if KYC is successful using create_account function
                success = create_account(actual_user_id, actual_guild_id, username, guild_name)

                if success:
                    success_embed = discord.Embed(
                        title="Account Created",
                        description=f"Your account has been successfully created at the **'{guild_name}'** branch!",
                        color=discord.Color.green()
                    )
                    await ctx.author.send(embed=success_embed)

                    account_details_embed = discord.Embed(
                        title="Your Account Details",
                        description=f"**Username**: {username}\n**User ID**: {actual_user_id}\n**Branch Name**: {guild_name}\n**Branch ID**: {actual_guild_id}\n**Balance**: 0\n**Account Created At**: {datetime.now()}",
                        color=discord.Color.blue()
                        )
                    account_details_embed.set_thumbnail(url=ctx.author.avatar.url)
                    account_details_embed.set_footer(text="Powered By Quantum Bank ⚛️")


                    await ctx.author.send(embed=account_details_embed)

                    public_success_embed = discord.Embed(
                        title="Account Created",
                        description=f"{ctx.author.name} has successfully created an account. Check your DMs for the details.",
                        color=discord.Color.green()
                    )
                    await ctx.respond(embed=public_success_embed)
                    break 
                error_embed = discord.Embed(
                    title="Account Creation Failed",
                    description="An error occurred while creating your account. Please try again later.",
                    color=discord.Color.red()
                )
                await ctx.author.send(embed=error_embed)
                break

            except asyncio.TimeoutError:
                timeout_embed = discord.Embed(
                    title="KYC Verification Timed Out",
                    description="You took too long to provide your KYC details. Please try again.",
                    color=discord.Color.red()
                )
                await ctx.author.send(embed=timeout_embed)
                break

    @discord.slash_command(description="Generate a UPI ID for your account.")
    async def generate_upi(self, ctx):
        """
        Generates a UPI ID for the user's account.

        This command allows the user to generate a unique UPI ID associated
        with their account. The UPI ID will be tied to the user's account and
        can be used for future payment operations.

        Parameters:
            ctx (discord.ApplicationContext): The context of the interaction, 
            which contains details about the user who invoked the command.

        Returns:
            None: The function executes actions related to generating the UPI ID
            and sends a message to the user with their newly generated UPI ID.
        """
        user_id = str(ctx.author.id)

        # Fetch account details from the database
        account = get_account(user_id)

        if not account:
            await ctx.respond("You don't have an account! Use `!create_account` to open one.")
            return

        # Check if UPI ID already exists
        if "upi_id" in account and account["upi_id"]:
            await ctx.respond(f"You already have a UPI ID: `{account['upi_id']}`. You cannot generate another one.")
            return

        # Generate and set UPI ID
        upi_id = set_upi_id(user_id)

        embed = self.bot.BlueEmbed(
            title="UPI ID Generated",
            description=f"Your new UPI ID is: `{upi_id}`\nYou can use this for transactions.",
            color=discord.Color.green()
        )

        await ctx.respond(embed=embed)

    @discord.slash_command(description="Make a payment using your UPI ID.")
    async def upi_payment(self, ctx, upi_id: str, amount: float):
        """
        Processes a payment using the user's UPI ID.

        This command allows a user to make a payment by providing their UPI ID 
        and the amount they wish to pay. The bot processes the payment 
        by extracting the UPI ID and amount from the user's input and 
        performing necessary operations, such as validating the UPI ID 
        and processing the payment.

        Parameters:
            ctx (discord.ApplicationContext): The context of the interaction, 
            which includes information about the user who invoked the command.
            upi_id (str): The user's UPI ID, which will be used to process the payment.
            amount (float): The amount to be paid.

        Returns:
            None: The function executes actions related to the payment but 
            does not return a value directly. It might send a message 
            indicating whether the payment was successful.
        """
        sender_id = str(ctx.author.id)

        # Fetch account details from the database
        sender_account = get_account(sender_id)

        if not sender_account:
            await ctx.respond("You don't have an account! Use `!create_account` to open one.")
            return

        if amount <= 0:
            await ctx.respond("You must pay a positive amount.")
            return

        if amount > sender_account['balance']:
            await ctx.respond("You do not have enough balance to make this payment.")
            return

        # Check if the provided UPI ID belongs to an existing user
        receiver_account = get_account(upi_id.split('@')[0])  # Assuming the format is <userID>@<bank>

        if not receiver_account:
            await ctx.respond(f"No account found for the provided UPI ID: {upi_id}.")
            return

        # Create confirmation and decline buttons
        confirm_button = discord.ui.Button(label="Confirm Payment", style=discord.ButtonStyle.green)
        decline_button = discord.ui.Button(label="Decline Payment", style=discord.ButtonStyle.red)

        async def confirm_callback(interaction):
            """
            Handles the callback for confirming a payment.

            This function is invoked when the user interacts with the 'confirm' button
            to proceed with a payment. It deducts the specified amount from the sender's
            balance and processes the payment.

            Parameters:
                interaction (discord.Interaction): The interaction object representing
                the user's action with the confirm button.

            Actions:
                - Deducts the specified `amount` from the sender's account balance.
                - Assumes the existence of `sender_account` and `amount` variables.
                - Updates the balance after deduction.
            """
            # Deduct amount from sender's balance
            new_sender_balance = sender_account['balance'] - amount

            # Add amount to receiver's balance
            new_receiver_balance = receiver_account['balance'] + amount

            # Log transaction for sender
            log_transaction(sender_id, 'send_upi_payment', amount, receiver_account['user_id'])

            # Log transaction for receiver as well
            log_transaction(receiver_account['user_id'], 'received_upi_payment', amount, sender_id)

            # Update balances in the database
            update_balance(sender_id, new_sender_balance)  # Update sender's balance
            update_balance(receiver_account['user_id'], new_receiver_balance)  # Update receiver's balance

            embed = discord.Embed(
                title="Payment Successful",
                description=f"You have successfully paid ${amount:.2f} using your UPI ID `{upi_id}`.",
                color=discord.Color.green()
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        async def decline_callback(interaction):
            """
            Handles the callback for when a payment is declined.

            This function is invoked when the user interacts with a button
            that triggers a payment decline. It sends a message to the user
            indicating that the payment has been declined.

            Parameters:
                interaction (discord.Interaction): The interaction object
                representing the user's action with the button.
            """
            await interaction.response.send_message("Payment has been declined.", ephemeral=True)

        confirm_button.callback = confirm_callback
        decline_button.callback = decline_callback

        view = discord.ui.View()
        view.add_item(confirm_button)
        view.add_item(decline_button)

        await ctx.respond("Are you sure you want to make this payment?", view=view)

    @discord.slash_command(description="Check your account balance and view your passbook.")
    async def passbook(self, ctx):
        """Generates and displays a passbook for the user."""
        user_id = str(ctx.author.id)

        # Fetch account details from the database
        account = get_account(user_id)

        if not account:
            await ctx.respond("You don't have an account! Use `/create_account` to open one.")
            return

        # Fetch transactions for the user
        transactions = get_transactions(user_id)

        # Generate the passbook image
        passbook_image = self.create_passbook_image(ctx.author.name, account, transactions, ctx.author.avatar.url)

        if passbook_image is None:
            await ctx.respond("Failed to generate your passbook. Please try again later.")
            return

        # Send the generated image as an attachment
        with io.BytesIO() as image_binary:
            passbook_image.save(image_binary, 'PNG')
            image_binary.seek(0)  # Move to the start of the BytesIO buffer

            await ctx.respond(file=discord.File(fp=image_binary, filename='passbook.png'))

    @staticmethod
    def create_passbook_image(username, account, transactions, avatar_url):
        """
        Creates a decorative passbook-like image with account information and transaction history.
        Returns the image object.
        """
        try:
            # Use a relative path for the background image
            background_path = "images/Technology-for-more-than-technologys-sake-1024x614.jpg"

            # Load background image from local path
            background_image = Image.open(background_path)

            # Resize background if necessary
            background_image = background_image.resize((600, 400))

            # Create a new blank image with the background
            passbook = Image.new('RGB', (600, 400))
            passbook.paste(background_image)

            draw = ImageDraw.Draw(passbook)

            # Load custom fonts (make sure to have .ttf files in your project directory)
            title_font_path = "fonts/arial.ttf"  # Ensure this path is correct and accessible
            text_font_path = "fonts/arial.ttf"    # Ensure this path is correct and accessible

            title_font = ImageFont.truetype(title_font_path, size=24)  # Larger font for title
            text_font = ImageFont.truetype(text_font_path, size=18)   # Larger font for text

            # Draw title and account information with white text
            draw.text((20, 20), f"Passbook for {username}", fill='white', font=title_font)
            draw.text((20, 60), f"Branch Name: {account['branch_name']}", fill='white', font=text_font)
            draw.text((20, 90), f"Balance: ${account['balance']:.2f}", fill='white', font=text_font)

            # Load user avatar
            avatar_image = Image.open(requests.get(avatar_url, stream=True).raw).convert("RGBA")

            # Resize avatar if necessary
            avatar_image = avatar_image.resize((50, 50))  # Resize avatar to fit nicely on the card

            # Paste user avatar onto the card (position it at (500, 10))
            passbook.paste(avatar_image, (500, 10), avatar_image)  # Use mask for transparency

            # Draw transaction history title without a background
            draw.text((20, 130), "Transaction History:", fill='white', font=text_font)

            y_offset = 160
            for txn in transactions[:5]:  # Limit to last 5 transactions for display
                txn_info = f"{txn['type'].capitalize()} 💵: ${txn['amount']} on {txn['timestamp']}"
                draw.text((20, y_offset), txn_info, fill='white', font=text_font)
                y_offset += 25

            return passbook

        except Exception as e:
            print(f"Error creating passbook: {e}")
            return None


    @discord.user_command(name="Show UPI ID")
    async def get_upi_id(self, ctx, user: discord.Member):
        # Fetch account details from the database
        account = get_account(str(user.id))

        if account and 'upi_id' in account:
            embed = discord.Embed(
                title="UPI ID Information",
                description=f"{user.name}'s UPI ID: `{account['upi_id']}`",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="UPI ID Information",
                description=f"No UPI ID found for {user.name}",
                color=discord.Color.red()
            )

        await ctx.respond(embed=embed, ephemeral=True)



def setup(bot):
    """
    Sets up the Account cog for the bot.

    This function is called when the cog is loaded, adding the `Account`
    cog to the bot and making it ready for use. The cog contains commands
    and functionality related to account management within the bot.

    Parameters:
        bot (commands.Bot): The instance of the bot that is being extended
                             with the cog.
    """
    bot.add_cog(Account(bot))
