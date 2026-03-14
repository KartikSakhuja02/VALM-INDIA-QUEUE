import discord
from discord import app_commands
from discord.ext import commands
import os

class VerificationButton(discord.ui.Button):
    """Persistent button for verification"""
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="Verify & Get Access",
            emoji="✅",
            custom_id="verification_button"  # Persistent ID
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle verification button click"""
        # Get role ID from environment
        role_id = int(os.getenv('VERIFICATION_ROLE_ID'))
        role = interaction.guild.get_role(role_id)
        
        if not role:
            await interaction.response.send_message(
                "❌ Verification role not found. Please contact an admin.",
                ephemeral=True
            )
            return
        
        # Check if user already has the role
        if role in interaction.user.roles:
            await interaction.response.send_message(
                "✅ **Already Verified!**\nYou already have access to skrimmish matches.",
                ephemeral=True
            )
            return
        
        # Assign the role
        try:
            await interaction.user.add_roles(role)
            embed = discord.Embed(
                title="✅ Verification Successful",
                description=(
                    f"Welcome to **VALM India Queue**!\n\n"
                    f"You now have the {role.mention} role and can participate in skrimmish matches.\n\n"
                    f"**Next Steps:**\n"
                    f"• Register your IGN with `/ign <your_name>`\n"
                    f"• Head to the queue channel and click **Join Queue**\n"
                    f"• Good luck and have fun! 🎮"
                ),
                color=0x2ECC71  # Professional green
            )
            embed.set_footer(text="Your stats and progress will be tracked!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to assign roles. Please contact an admin.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )

class VerificationView(discord.ui.View):
    """Persistent view for verification"""
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view - never times out
        self.add_item(VerificationButton())

class VerificationCog(commands.Cog):
    """Cog for handling skrimmish verification"""
    def __init__(self, bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Add persistent view when bot starts"""
        # Register the persistent view
        self.bot.add_view(VerificationView())
        print("✅ Verification view registered")
    
    @app_commands.command(name="setup_verification", description="Setup verification UI in this channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_verification(self, interaction: discord.Interaction):
        """Setup the verification UI"""
        # Get verification role and channel from environment
        role_id = os.getenv('VERIFICATION_ROLE_ID')
        channel_id = os.getenv('VERIFICATION_CHANNEL_ID')
        
        if not role_id or not channel_id:
            await interaction.response.send_message(
                "❌ Please configure VERIFICATION_ROLE_ID and VERIFICATION_CHANNEL_ID in the .env file first.",
                ephemeral=True
            )
            return
        
        role = interaction.guild.get_role(int(role_id))
        if not role:
            await interaction.response.send_message(
                "❌ Verification role not found. Please check the VERIFICATION_ROLE_ID in .env.",
                ephemeral=True
            )
            return
        
        # Create embed
        embed = discord.Embed(
            title="🎯 VALM India Queue - Verification",
            description=(
                "**Welcome to Valorant Mobile India's Premier Matchmaking System!**\n\n"
                "Get verified to unlock access to competitive skrimmish matches, "
                "track your progress, and climb the leaderboards.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "**What You'll Get:**\n"
                f"✅ {role.mention} role\n"
                "✅ Access to ranked skrimmish matches\n"
                "✅ Personal stats tracking (Wins, Losses, MMR)\n"
                "✅ Leaderboard ranking\n"
                "✅ Match history & progression\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "**Ready to compete?** Click the button below to get started!"
            ),
            color=0x5865F2  # Discord Blurple - Professional color
        )
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.set_footer(
            text="VALM India • Competitive Skrimmish Matchmaking",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
        )
        
        # Send the verification message
        view = VerificationView()
        await interaction.channel.send(embed=embed, view=view)
        
        await interaction.response.send_message(
            "✅ Verification UI has been posted!",
            ephemeral=True
        )
    
    @setup_verification.error
    async def setup_verification_error(self, interaction: discord.Interaction, error):
        """Handle setup verification errors"""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ You need Administrator permissions to use this command.",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(VerificationCog(bot))
