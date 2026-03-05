import discord
from discord import app_commands
from discord.ext import commands
from database import db
import os
import asyncio
import random
from typing import Optional

# Dictionary to track active matches
active_matches = {}

class SubmitButton(discord.ui.Button):
    """Button for submitting match screenshot"""
    def __init__(self, host_id: int):
        super().__init__(
            style=discord.ButtonStyle.green,
            label="Submit Result"
        )
        self.host_id = host_id
    
    async def callback(self, interaction: discord.Interaction):
        # Only non-host can submit
        if interaction.user.id == self.host_id:
            await interaction.response.send_message(
                "You cannot submit the result as you are the host. The other player must submit.",
                ephemeral=True
            )
            return
        
        # Acknowledge interaction
        await interaction.response.send_message(
            "Please upload your screenshot within 2 minutes.",
            ephemeral=True
        )
        
        # Wait for screenshot (we'll implement later)
        # For now, just acknowledge
        await interaction.channel.send(
            f"{interaction.user.mention} Please upload your match result screenshot in this channel within 2 minutes."
        )

class SubmitView(discord.ui.View):
    """View containing the submit button"""
    def __init__(self, host_id: int):
        super().__init__(timeout=None)
        self.add_item(SubmitButton(host_id))

class QueueButton(discord.ui.Button):
    """Button for joining the queue"""
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.blurple,
            label="Join Queue",
            emoji=None
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
        
        # Respond to interaction immediately (Discord requires response within 3 seconds)
        await interaction.response.defer(ephemeral=True)
        
        # Get updated queue
        queue = await db.get_queue()
        
        # Update the queue display
        await self.view.update_queue_display(interaction)
        
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
            
            # Update the queue display again (now empty)
            await self.view.update_queue_display(interaction)
            
            # Get the next match number
            match_number_str = await db.get_config('next_match_number')
            match_number = int(match_number_str) if match_number_str else 1
            
            # Format as 4 digits: 0001, 0002, etc.
            match_name = f"{match_number:04d}-scrimmish"
            
            # Get the guild and category
            guild = interaction.guild
            category_id = int(os.getenv('MATCH_CATEGORY_ID', 0))
            category = guild.get_channel(category_id) if category_id else None
            
            # Get the player members
            member1 = guild.get_member(player1['user_id'])
            member2 = guild.get_member(player2['user_id'])
            
            # Set up permissions - only these 2 players can see the channels
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False, view_channel=False),
                member1: discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True, connect=True, speak=True),
                member2: discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True, connect=True, speak=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True, view_channel=True)
            }
            
            # Create private text channel
            text_channel = await guild.create_text_channel(
                name=match_name,
                category=category,
                overwrites=overwrites
            )
            
            # Create private voice channel
            voice_channel = await guild.create_voice_channel(
                name=match_name,
                category=category,
                overwrites=overwrites
            )
            
            # Store match info
            active_matches[text_channel.id] = {
                'match_number': match_number,
                'player1': member1,
                'player2': member2,
                'text_channel': text_channel,
                'voice_channel': voice_channel,
                'match_id': match_id
            }
            
            # Send initial message asking players to join VC
            initial_embed = discord.Embed(
                title=f"Scrimmish Match #{match_number:04d}",
                description=f"{member1.mention} vs {member2.mention}\n\nPlease join {voice_channel.mention} within 5 minutes to proceed.",
                color=0xED4245
            )
            initial_embed.set_footer(text="Match will be cancelled if both players don't join within 5 minutes")
            
            await text_channel.send(
                content=f"{member1.mention} {member2.mention}",
                embed=initial_embed
            )
            
            # Increment the match number for next time
            await db.set_config('next_match_number', str(match_number + 1))
            
            # Start the match flow handler
            self.view.bot.loop.create_task(
                self.view.handle_match_flow(text_channel.id)
            )

class LeaveButton(discord.ui.Button):
    """Button for leaving the queue"""
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.red,
            label="Leave Queue",
            emoji=None
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
            # Respond to interaction immediately
            await interaction.response.defer(ephemeral=True)
            # Update the queue display
            await self.view.update_queue_display(interaction)
        else:
            await interaction.response.send_message(
                "❌ Failed to leave queue. Please try again.",
                ephemeral=True
            )

class LeaderboardButton(discord.ui.Button):
    """Button for viewing leaderboard"""
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.gray,
            label="Leaderboard",
            emoji=None
        )
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Leaderboard feature coming soon!",
            ephemeral=True
        )

class QueueView(discord.ui.View):
    """Persistent view for the queue buttons"""
    def __init__(self, bot=None):
        super().__init__(timeout=None)
        self.add_item(QueueButton())
        self.add_item(LeaveButton())
        self.add_item(LeaderboardButton())
        self.message: Optional[discord.Message] = None
        self.bot = bot
    
    async def update_queue_display(self, interaction: discord.Interaction):
        """Update the queue embed display"""
        queue = await db.get_queue()
        queue_count = len(queue)
        
        # Create embed matching NeatQueue style with better spacing
        embed = discord.Embed(
            title="Valorant Mobile India Matchmaking Queue",
            color=0xED4245  # Discord red/NeatQueue red
        )
        
        # Add spacing and format players nicely
        if queue:
            players_text = ", ".join([f"<@{player['user_id']}>" for player in queue])
        else:
            players_text = "*No players in queue*"
        
        # Add queue section with extra spacing
        embed.add_field(
            name=f"\nQueue {queue_count}/2\n",
            value=f"{players_text}\n\u200b",  # Add invisible character for spacing
            inline=False
        )
        
        embed.timestamp = discord.utils.utcnow()
        
        # Update the message
        if self.message:
            try:
                await self.message.edit(embed=embed)
            except:
                pass
    
    async def handle_match_flow(self, text_channel_id: int):
        """Handle the complete match flow with timers and state checks"""
        match_data = active_matches.get(text_channel_id)
        if not match_data:
            return
        
        text_channel = match_data['text_channel']
        voice_channel = match_data['voice_channel']
        member1 = match_data['player1']
        member2 = match_data['player2']
        
        # Wait 4 minutes
        await asyncio.sleep(240)
        
        # Check who's in the voice channel
        members_in_vc = voice_channel.members
        player1_in_vc = member1 in members_in_vc
        player2_in_vc = member2 in members_in_vc
        
        # Send warnings based on who's in VC
        if not player1_in_vc and not player2_in_vc:
            # Both missing - warn both
            warning_embed = discord.Embed(
                title="Final Warning",
                description=f"{member1.mention} {member2.mention}\n\nYou have 1 minute to join {voice_channel.mention} or the match will be cancelled.",
                color=0xFF0000
            )
            await text_channel.send(embed=warning_embed)
        elif not player1_in_vc:
            # Only player1 missing
            warning_embed = discord.Embed(
                title="Final Warning",
                description=f"{member1.mention} You have 1 minute to join {voice_channel.mention} or the match will be cancelled.",
                color=0xFF0000
            )
            await text_channel.send(embed=warning_embed)
        elif not player2_in_vc:
            # Only player2 missing
            warning_embed = discord.Embed(
                title="Final Warning",
                description=f"{member2.mention} You have 1 minute to join {voice_channel.mention} or the match will be cancelled.",
                color=0xFF0000
            )
            await text_channel.send(embed=warning_embed)
        else:
            # Both are in VC - proceed immediately
            await self.proceed_to_match(text_channel_id)
            return
        
        # Wait 1 more minute
        await asyncio.sleep(60)
        
        # Final check
        members_in_vc = voice_channel.members
        player1_in_vc = member1 in members_in_vc
        player2_in_vc = member2 in members_in_vc
        
        if player1_in_vc and player2_in_vc:
            # Both joined - proceed
            await self.proceed_to_match(text_channel_id)
        else:
            # Cancel match
            cancel_embed = discord.Embed(
                title="Match Cancelled",
                description="Both players did not join the voice channel in time. Channels will be deleted in 10 seconds.",
                color=0xFF0000
            )
            await text_channel.send(embed=cancel_embed)
            await asyncio.sleep(10)
            
            # Delete channels
            try:
                await text_channel.delete()
                await voice_channel.delete()
            except:
                pass
            
            # Remove from active matches
            if text_channel_id in active_matches:
                del active_matches[text_channel_id]
    
    async def proceed_to_match(self, text_channel_id: int):
        """Proceed with match when both players are in VC"""
        match_data = active_matches.get(text_channel_id)
        if not match_data:
            return
        
        text_channel = match_data['text_channel']
        member1 = match_data['player1']
        member2 = match_data['player2']
        
        # Randomly choose host
        host = random.choice([member1, member2])
        guest = member2 if host == member1 else member1
        
        # Ask host to send RCP
        host_embed = discord.Embed(
            title="Match Ready",
            description=f"{host.mention} has been selected as the host.\n\nPlease create a custom 1v1 match and send the room code in this chat.",
            color=0xED4245
        )
        await text_channel.send(embed=host_embed)
        
        # Wait for host's message with room code
        def check(m):
            return m.author.id == host.id and m.channel.id == text_channel.id
        
        try:
            room_code_msg = await self.bot.wait_for('message', check=check, timeout=300)  # 5 min timeout
            
            # Ping the room code to the guest
            guest_embed = discord.Embed(
                title="Room Code Received",
                description=f"{guest.mention} Please join the match with the following room code:\n\n**{room_code_msg.content}**",
                color=0xED4245
            )
            await text_channel.send(embed=guest_embed)
            
            # Send good luck message with submit button
            glhf_embed = discord.Embed(
                title="Match In Progress",
                description=f"{member1.mention} vs {member2.mention}\n\nGood luck, have fun!\n\nOnce the match is complete, {guest.mention} should submit the result using the button below.",
                color=0xED4245
            )
            
            submit_view = SubmitView(host.id)
            await text_channel.send(embed=glhf_embed, view=submit_view)
            
        except asyncio.TimeoutError:
            # Host didn't send room code in time
            timeout_embed = discord.Embed(
                title="Match Cancelled",
                description=f"{host.mention} did not provide the room code in time. Channels will be deleted in 10 seconds.",
                color=0xFF0000
            )
            await text_channel.send(embed=timeout_embed)
            await asyncio.sleep(10)
            
            # Delete channels
            try:
                await text_channel.delete()
                await match_data['voice_channel'].delete()
            except:
                pass
            
            # Remove from active matches
            if text_channel_id in active_matches:
                del active_matches[text_channel_id]

class SkrimmishCog(commands.Cog):
    """Cog for managing 1v1 skrimmish matches"""
    
    def __init__(self, bot):
        self.bot = bot
        self.queue_view = QueueView(bot)
        self.queue_channel_id = int(os.getenv('QUEUE_CHANNEL_ID', 0))
        self.setup_done = False
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Called when the bot is ready - setup queue UI automatically"""
        if not self.setup_done and self.queue_channel_id:
            await self.setup_queue_on_startup()
            self.setup_done = True
    
    async def setup_queue_on_startup(self):
        """Setup the queue UI automatically on bot startup"""
        try:
            # Wait a moment for bot to be fully ready
            await asyncio.sleep(1)
            
            # Get the channel
            channel = self.bot.get_channel(self.queue_channel_id)
            if not channel:
                print(f"❌ Queue channel {self.queue_channel_id} not found!")
                return
            
            # Get old message ID from database
            old_message_id = await db.get_config('queue_message_id')
            
            # Try to delete the old message
            if old_message_id:
                try:
                    old_message = await channel.fetch_message(int(old_message_id))
                    await old_message.delete()
                    print(f"🗑️ Deleted old queue message")
                except:
                    print(f"⚠️ Could not delete old queue message (may have been deleted already)")
            
            # Get existing queue from database (DON'T clear it - persistent queue!)
            queue = await db.get_queue()
            queue_count = len(queue)
            
            # Create the queue embed matching NeatQueue style
            embed = discord.Embed(
                title="Valorant Mobile India Matchmaking Queue",
                color=0xED4245  # Discord red/NeatQueue red
            )
            
            # Show existing queue
            if queue:
                players_text = ", ".join([f"<@{player['user_id']}>" for player in queue])
            else:
                players_text = "*No players in queue*"
            
            embed.add_field(
                name=f"\nQueue {queue_count}/2\n",
                value=f"{players_text}\n\u200b",
                inline=False
            )
            
            embed.timestamp = discord.utils.utcnow()
            
            # Send the new message
            message = await channel.send(embed=embed, view=self.queue_view)
            self.queue_view.message = message
            
            # Store the new message ID in database
            await db.set_config('queue_message_id', str(message.id))
            await db.set_config('queue_channel_id', str(self.queue_channel_id))
            
            print(f"✅ Queue UI setup in channel {channel.name} (ID: {self.queue_channel_id})")
            
        except Exception as e:
            print(f"❌ Failed to setup queue on startup: {e}")
    
    @app_commands.command(name="setup_queue", description="Setup the skrimmish queue in this channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_queue(self, interaction: discord.Interaction):
        """Setup the queue UI in the current channel (manual)"""
        
        # Get existing queue from database (persistent)
        queue = await db.get_queue()
        queue_count = len(queue)
        
        # Get old message if exists
        old_message_id = await db.get_config('queue_message_id')
        old_channel_id = await db.get_config('queue_channel_id')
        
        # Try to delete old message
        if old_message_id and old_channel_id:
            try:
                old_channel = self.bot.get_channel(int(old_channel_id))
                if old_channel:
                    old_message = await old_channel.fetch_message(int(old_message_id))
                    await old_message.delete()
            except:
                pass
        
        # Create the queue embed matching NeatQueue style
        embed = discord.Embed(
            title="Valorant Mobile India Matchmaking Queue",
            color=0xED4245  # Discord red/NeatQueue red
        )
        
        # Show existing queue
        if queue:
            players_text = ", ".join([f"<@{player['user_id']}>" for player in queue])
        else:
            players_text = "*No players in queue*"
        
        embed.add_field(
            name=f"\nQueue {queue_count}/2\n",
            value=f"{players_text}\n\u200b",
            inline=False
        )
        
        embed.timestamp = discord.utils.utcnow()
        
        # Send the message with buttons
        await interaction.response.send_message(
            embed=embed,
            view=self.queue_view
        )
        
        # Store the message reference
        message = await interaction.original_response()
        self.queue_view.message = message
        
        # Store in database
        await db.set_config('queue_message_id', str(message.id))
        await db.set_config('queue_channel_id', str(interaction.channel_id))
        
        print(f"✅ Queue setup in channel {interaction.channel_id}")
    
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
