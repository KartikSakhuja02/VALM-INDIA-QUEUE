import discord
from discord import app_commands
from discord.ext import commands
from database import db
import os
from typing import Optional

class QueueButton(discord.ui.Button):
    """Button for joining the queue"""
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.green,
            label="Join Queue",
            emoji="🎮"
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Check if user is already in queue
        in_queue = await db.is_in_queue(interaction.user.id)
        
        if in_queue:
            await interaction.response.send_message(
                "❌ You're already in the queue!",
                ephemeral=True
            )
            return
        
        # Add user to queue
        success = await db.add_to_queue(interaction.user.id, str(interaction.user))
        
        if not success:
            await interaction.response.send_message(
                "❌ Failed to join queue. Please try again.",
                ephemeral=True
            )
            return
        
        # Get updated queue
        queue = await db.get_queue()
        
        # Check if we have 2 players (match ready)
        if len(queue) >= 2:
            # Create match with first 2 players
            player1 = queue[0]
            player2 = queue[1]
            
            # Remove them from queue
            await db.remove_from_queue(player1['user_id'])
            await db.remove_from_queue(player2['user_id'])
            
            # Create match record
            match_id = await db.create_match(
                player1['user_id'], player2['user_id'],
                player1['username'], player2['username']
            )
            
            # Update the queue display
            await self.view.update_queue_display(interaction)
            
            # Send match found notification
            match_embed = discord.Embed(
                title="🎯 Skrimmish Match Found!",
                description=f"**Match ID:** #{match_id}\n\n"
                           f"**Player 1:** <@{player1['user_id']}>\n"
                           f"**Player 2:** <@{player2['user_id']}>\n\n"
                           f"Good luck, have fun! 🔥",
                color=discord.Color.gold()
            )
            match_embed.set_footer(text="Use /report to report match results")
            
            await interaction.response.send_message(
                content=f"<@{player1['user_id']}> <@{player2['user_id']}>",
                embed=match_embed
            )
        else:
            # Just update the queue display
            await self.view.update_queue_display(interaction)
            await interaction.response.send_message(
                f"✅ You joined the queue! **({len(queue)}/2)**",
                ephemeral=True
            )

class LeaveButton(discord.ui.Button):
    """Button for leaving the queue"""
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.red,
            label="Leave Queue",
            emoji="🚪"
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Check if user is in queue
        in_queue = await db.is_in_queue(interaction.user.id)
        
        if not in_queue:
            await interaction.response.send_message(
                "❌ You're not in the queue!",
                ephemeral=True
            )
            return
        
        # Remove user from queue
        success = await db.remove_from_queue(interaction.user.id)
        
        if success:
            await self.view.update_queue_display(interaction)
            await interaction.response.send_message(
                "✅ You left the queue.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Failed to leave queue. Please try again.",
                ephemeral=True
            )

class QueueView(discord.ui.View):
    """Persistent view for the queue buttons"""
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(QueueButton())
        self.add_item(LeaveButton())
        self.message: Optional[discord.Message] = None
    
    async def update_queue_display(self, interaction: discord.Interaction):
        """Update the queue embed display"""
        queue = await db.get_queue()
        
        embed = discord.Embed(
            title="🎮 Skrimmish Queue (1v1)",
            description="Click **Join Queue** to enter the queue!\nFirst 2 players will be matched automatically.",
            color=discord.Color.blue()
        )
        
        # Add queue slots
        if len(queue) >= 1:
            embed.add_field(
                name="Slot 1 👤",
                value=f"<@{queue[0]['user_id']}>",
                inline=True
            )
        else:
            embed.add_field(
                name="Slot 1 ⭕",
                value="*Empty*",
                inline=True
            )
        
        if len(queue) >= 2:
            embed.add_field(
                name="Slot 2 👤",
                value=f"<@{queue[1]['user_id']}>",
                inline=True
            )
        else:
            embed.add_field(
                name="Slot 2 ⭕",
                value="*Empty*",
                inline=True
            )
        
        # Additional players waiting
        if len(queue) > 2:
            waiting = [f"<@{player['user_id']}>" for player in queue[2:]]
            embed.add_field(
                name=f"⏳ Waiting ({len(queue) - 2})",
                value="\n".join(waiting),
                inline=False
            )
        
        embed.set_footer(text=f"Total in queue: {len(queue)}")
        
        # Update the message
        if self.message:
            try:
                await self.message.edit(embed=embed)
            except:
                pass

class SkrimmishCog(commands.Cog):
    """Cog for managing 1v1 skrimmish matches"""
    
    def __init__(self, bot):
        self.bot = bot
        self.queue_view = QueueView()
        self.queue_channel_id = int(os.getenv('QUEUE_CHANNEL_ID', 0))
    
    @app_commands.command(name="setup_queue", description="Setup the skrimmish queue in this channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_queue(self, interaction: discord.Interaction):
        """Setup the queue UI in the current channel"""
        
        # Clear any existing queue
        await db.clear_queue()
        
        # Create the queue embed
        embed = discord.Embed(
            title="🎮 Skrimmish Queue (1v1)",
            description="Click **Join Queue** to enter the queue!\nFirst 2 players will be matched automatically.",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Slot 1 ⭕", value="*Empty*", inline=True)
        embed.add_field(name="Slot 2 ⭕", value="*Empty*", inline=True)
        embed.set_footer(text="Total in queue: 0")
        
        # Send the message with buttons
        await interaction.response.send_message(
            embed=embed,
            view=self.queue_view
        )
        
        # Store the message reference
        message = await interaction.original_response()
        self.queue_view.message = message
        
        print(f"Queue setup in channel {interaction.channel_id}")
    
    @app_commands.command(name="clear_queue", description="Clear the entire queue")
    @app_commands.checks.has_permissions(administrator=True)
    async def clear_queue(self, interaction: discord.Interaction):
        """Clear all players from the queue"""
        await db.clear_queue()
        
        # Update the queue display
        if self.queue_view.message:
            await self.queue_view.update_queue_display(interaction)
        
        await interaction.response.send_message(
            "✅ Queue cleared!",
            ephemeral=True
        )
    
    @app_commands.command(name="queue_status", description="Check current queue status")
    async def queue_status(self, interaction: discord.Interaction):
        """Show the current queue status"""
        queue = await db.get_queue()
        
        if not queue:
            await interaction.response.send_message(
                "📊 The queue is empty!",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="📊 Current Queue Status",
            color=discord.Color.blue()
        )
        
        for i, player in enumerate(queue[:2], 1):
            embed.add_field(
                name=f"Slot {i}",
                value=f"<@{player['user_id']}>",
                inline=True
            )
        
        if len(queue) > 2:
            waiting = [f"<@{player['user_id']}>" for player in queue[2:]]
            embed.add_field(
                name=f"⏳ Waiting ({len(queue) - 2})",
                value="\n".join(waiting),
                inline=False
            )
        
        embed.set_footer(text=f"Total in queue: {len(queue)}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(SkrimmishCog(bot))
