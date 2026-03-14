import discord
from discord import app_commands
from discord.ext import commands
from database import db
import os
import asyncio
import random
from typing import Optional
from datetime import datetime
import io
import re
import base64
import aiohttp

# Try to import OCR dependencies (optional)
try:
    from PIL import Image
    OCR_AVAILABLE = True
    # Check if API key is available
    if not os.getenv('GEMINI_API_KEY'):
        OCR_AVAILABLE = False
        print("⚠️  Warning: GEMINI_API_KEY not set. OCR features will be disabled.")
except ImportError as e:
    OCR_AVAILABLE = False
    print(f"⚠️  Warning: OCR dependencies not installed. Screenshot feature will be disabled.")
    print(f"   Missing: {e}")
    print("   To enable OCR, install: pip install Pillow")

# Dictionary to track active matches
active_matches = {}

# Dictionary to track active sub requests {request_id: {data}}
active_sub_requests = {}

# Dictionary to track queue inactivity timers {channel_id: asyncio.Task}
queue_inactivity_timers = {}

# Lock to prevent race condition with autoping
autoping_lock = asyncio.Lock()

# MMR Rank Thresholds and Role IDs
MMR_RANKS = [
    (700, 850, 'IRON_ROLE_ID', 'Iron'),
    (850, 1000, 'BRONZE_ROLE_ID', 'Bronze'),
    (1000, 1150, 'SILVER_ROLE_ID', 'Silver'),
    (1150, 1300, 'GOLD_ROLE_ID', 'Gold'),
    (1300, 1450, 'PLAT_ROLE_ID', 'Plat'),
    (1450, 1600, 'DIAMOND_ROLE_ID', 'Diamond'),
    (1600, 1750, 'ASCENDANT_ROLE_ID', 'Ascendant'),
    (1750, 1900, 'IMMORTAL_ROLE_ID', 'Immortal'),
    (1900, 2200, 'RADIANT_ROLE_ID', 'Radiant'),
]

def get_rank_role_id(mmr: int) -> tuple[int | None, str]:
    """Get the appropriate rank role ID based on MMR
    
    Args:
        mmr: Player's MMR value
    
    Returns:
        Tuple of (role_id, rank_name) or (None, 'Unranked')
    """
    for min_mmr, max_mmr, env_key, rank_name in MMR_RANKS:
        if min_mmr <= mmr < max_mmr:
            role_id_str = os.getenv(env_key)
            if role_id_str:
                return int(role_id_str), rank_name
            return None, rank_name
    
    # MMR above Radiant threshold
    if mmr >= 2200:
        role_id_str = os.getenv('RADIANT_ROLE_ID')
        if role_id_str:
            return int(role_id_str), 'Radiant'
        return None, 'Radiant'
    
    return None, 'Unranked'

async def update_player_rank_role(guild: discord.Guild, user_id: int, mmr: int):
    """Update a player's rank role based on their MMR
    
    Args:
        guild: Discord guild object
        user_id: Player's Discord user ID
        mmr: Player's current MMR
    """
    try:
        member = guild.get_member(user_id)
        if not member:
            return
        
        # Get the new rank role
        new_role_id, rank_name = get_rank_role_id(mmr)
        if not new_role_id:
            return
        
        new_role = guild.get_role(new_role_id)
        if not new_role:
            return
        
        # Get all rank role IDs
        all_rank_role_ids = []
        for _, _, env_key, _ in MMR_RANKS:
            role_id_str = os.getenv(env_key)
            if role_id_str:
                all_rank_role_ids.append(int(role_id_str))
        
        # Remove all other rank roles
        roles_to_remove = [role for role in member.roles if role.id in all_rank_role_ids and role.id != new_role_id]
        if roles_to_remove:
            await member.remove_roles(*roles_to_remove)
        
        # Add new rank role if not already assigned
        if new_role not in member.roles:
            await member.add_roles(new_role)
            print(f"✅ Updated {member.display_name}'s rank to {rank_name} ({mmr} MMR)")
    
    except Exception as e:
        print(f"❌ Error updating rank role for user {user_id}: {e}")

class ReadyButton(discord.ui.Button):
    """Button for players to confirm they're ready"""
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="I'm Ready!",
            emoji="✅"
        )
    
    async def callback(self, interaction: discord.Interaction):
        match_data = active_matches.get(self.view.match_id)
        if not match_data:
            await interaction.response.send_message("❌ Match data not found.", ephemeral=True)
            return
        
        player1_id = match_data['player1'].id
        player2_id = match_data['player2'].id
        
        # Check if user is one of the players
        if interaction.user.id not in [player1_id, player2_id]:
            await interaction.response.send_message("❌ Only players in this match can ready up!", ephemeral=True)
            return
        
        # Check if already ready
        if interaction.user.id in match_data['ready_players']:
            await interaction.response.send_message("✅ You're already ready!", ephemeral=True)
            return
        
        # Mark as ready
        match_data['ready_players'].add(interaction.user.id)
        
        # Update display
        await self.view.update_ready_display(interaction)

class ReadyView(discord.ui.View):
    """View for ready check"""
    def __init__(self, match_id: int, bot):
        super().__init__(timeout=None)
        self.match_id = match_id
        self.bot = bot
        self.message: Optional[discord.Message] = None
        self.add_item(ReadyButton())
    
    async def update_ready_display(self, interaction: discord.Interaction):
        """Update the ready embed"""
        match_data = active_matches.get(self.match_id)
        if not match_data:
            return
        
        ready_count = len(match_data['ready_players'])
        player1 = match_data['player1']
        player2 = match_data['player2']
        
        p1_ready = "✅" if player1.id in match_data['ready_players'] else "⏳"
        p2_ready = "✅" if player2.id in match_data['ready_players'] else "⏳"
        
        embed = discord.Embed(
            title="🎮 Ready Check",
            description=f"Both players must confirm they're ready to proceed.\n\n{p1_ready} {player1.mention}\n{p2_ready} {player2.mention}",
            color=0x5865F2
        )
        embed.add_field(
            name="Status",
            value=f"{ready_count}/2 players ready",
            inline=False
        )
        
        # If both ready, proceed
        if ready_count >= 2:
            await interaction.response.defer()
            # Disable button
            for item in self.children:
                item.disabled = True
            
            if self.message:
                await self.message.edit(embed=embed, view=self)
            await self.start_match(match_data)
        else:
            # First player ready - acknowledge the interaction
            await interaction.response.edit_message(embed=embed, view=self)
    
    async def start_match(self, match_data):
        """Start the match after both players are ready"""
        text_channel = match_data['text_channel']
        player1 = match_data['player1']
        player2 = match_data['player2']
        
        # Send start message
        start_embed = discord.Embed(
            title="🎮 Match Starting",
            description=(
                f"**{player1.mention} vs {player2.mention}**\n\n"
                f"• Any one of you can host a 1v1 custom match\n"
                f"• Play your match and take a screenshot of the final scoreboard\n"
                f"• After the match, click the **Submit Screenshot** button below to upload the result\n\n"
                f"**Good luck, have fun!** 🔥"
            ),
            color=0x00FF00
        )
        await text_channel.send(embed=start_embed)
        
        # Send submit screenshot UI
        await asyncio.sleep(2)
        submit_embed = discord.Embed(
            title="📸 Submit Match Result",
            description="Once your match is complete, upload the final scoreboard screenshot using the button below.",
            color=0xED4245
        )
        
        submit_view = SubmitSSView(self.match_id, self.bot)
        submit_message = await text_channel.send(embed=submit_embed, view=submit_view)
        submit_view.message = submit_message

class SubmitSSButton(discord.ui.Button):
    """Button to submit screenshot"""
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label="Submit Screenshot",
            emoji="📸"
        )
    
    async def callback(self, interaction: discord.Interaction):
        match_data = active_matches.get(self.view.match_id)
        if not match_data:
            await interaction.response.send_message("❌ Match data not found.", ephemeral=True)
            return
        
        # Check if OCR is available
        if not OCR_AVAILABLE:
            await interaction.response.send_message(
                "❌ **Screenshot feature is not available!**\n\n"
                "OCR dependencies are not installed on this server.\n"
                "Please contact the administrator to enable this feature.\n\n"
                "Required: `pip install google-generativeai Pillow`",
                ephemeral=True
            )
            return
        
        player1_id = match_data['player1'].id
        player2_id = match_data['player2'].id
        
        # Check if user is one of the players
        if interaction.user.id not in [player1_id, player2_id]:
            await interaction.response.send_message("❌ Only players in this match can submit screenshots!", ephemeral=True)
            return
        
        # Check if already processing
        if match_data.get('processing_ss', False):
            await interaction.response.send_message("⏳ Already processing a screenshot. Please wait...", ephemeral=True)
            return
        
        match_data['processing_ss'] = True
        
        await interaction.response.send_message(
            "📸 **Please upload your screenshot now!**\n\nYou have **3 minutes** to upload the final scoreboard screenshot.\n\nJust send the image in this channel.",
            ephemeral=True
        )
        
        # Wait for image upload
        def check(m):
            return (
                m.channel.id == interaction.channel_id and
                m.author.id == interaction.user.id and
                len(m.attachments) > 0 and
                m.attachments[0].content_type and
                m.attachments[0].content_type.startswith('image/')
            )
        
        try:
            msg = await self.view.bot.wait_for('message', check=check, timeout=180)  # 3 minutes
            
            # Process the screenshot
            attachment = msg.attachments[0]
            await self.view.process_screenshot(attachment, interaction.channel)
            
        except asyncio.TimeoutError:
            match_data['processing_ss'] = False
            await interaction.followup.send(
                "⏰ **Timeout!** You didn't upload a screenshot in 3 minutes.\n\nPlease click the **Submit Screenshot** button again to try.",
                ephemeral=True
            )

class SubmitSSView(discord.ui.View):
    """View for submitting screenshot"""
    def __init__(self, match_id: int, bot):
        super().__init__(timeout=None)
        self.match_id = match_id
        self.bot = bot
        self.message: Optional[discord.Message] = None
        self.add_item(SubmitSSButton())
    
    async def process_screenshot(self, attachment, channel):
        """Process the uploaded screenshot using Gemini OCR"""
        match_data = active_matches.get(self.match_id)
        if not match_data:
            return
        
        try:
            # Download image
            image_data = await attachment.read()
            
            # Send processing message
            processing_embed = discord.Embed(
                title="⏳ Processing Screenshot...",
                description="Analyzing the match results using AI...",
                color=0xFFA500
            )
            processing_msg = await channel.send(embed=processing_embed)
            
            # Convert image bytes to PIL Image and then to base64 for API
            import base64
            image = Image.open(io.BytesIO(image_data))
            
            # Convert to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Save to bytes
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='PNG')
            img_byte_arr = img_byte_arr.getvalue()
            image_b64 = base64.b64encode(img_byte_arr).decode('utf-8')
            
            prompt = """Analyze this Valorant Mobile match scoreboard screenshot and extract the player information.

The scoreboard has TWO players:
- TOP player: Has a YELLOW/GREEN/GOLD colored background (displayed at the top)
- BOTTOM player: Has a RED colored background (displayed at the bottom)

For each player, find:
1. Their IGN/username
2. Their score (the large number shown next to their name)

IMPORTANT: Report the EXACT scores as displayed. Do NOT swap or assume which score is higher.

Return ONLY in this exact format:
TOP_PLAYER: [name of player with yellow/green background at top]
TOP_SCORE: [exact score number for top player]
BOTTOM_PLAYER: [name of player with red background at bottom]
BOTTOM_SCORE: [exact score number for bottom player]

Example:
TOP_PLAYER: aimboss
TOP_SCORE: 10
BOTTOM_PLAYER: MatarPaneer
BOTTOM_SCORE: 8"""
            
            # Use direct REST API call to bypass deprecated SDK
            import aiohttp
            api_key = os.getenv('GEMINI_API_KEY')
            url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={api_key}"
            
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": image_b64
                            }
                        }
                    ]
                }]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise ValueError(f"API Error: {error_text}")
                    
                    result = await resp.json()
                    result_text = result['candidates'][0]['content']['parts'][0]['text']
            
            # Parse the response
            top_player_match = re.search(r'TOP_PLAYER:\s*(.+)', result_text, re.IGNORECASE)
            top_score_match = re.search(r'TOP_SCORE:\s*(\d+)', result_text, re.IGNORECASE)
            bottom_player_match = re.search(r'BOTTOM_PLAYER:\s*(.+)', result_text, re.IGNORECASE)
            bottom_score_match = re.search(r'BOTTOM_SCORE:\s*(\d+)', result_text, re.IGNORECASE)
            
            if not all([top_player_match, top_score_match, bottom_player_match, bottom_score_match]):
                raise ValueError("Could not extract match data from screenshot")
            
            top_player = top_player_match.group(1).strip()
            top_score = int(top_score_match.group(1))
            bottom_player = bottom_player_match.group(1).strip()
            bottom_score = int(bottom_score_match.group(1))
            
            # Determine winner based on scores
            winner_ign = top_player if top_score > bottom_score else bottom_player
            loser_ign = bottom_player if top_score > bottom_score else top_player
            winner_score = max(top_score, bottom_score)
            loser_score = min(top_score, bottom_score)
            
            # Debug: Print extracted IGNs
            print(f"🔍 OCR extracted: Top='{top_player}' ({top_score}), Bottom='{bottom_player}' ({bottom_score})")
            print(f"🔍 Determined: Winner='{winner_ign}' ({winner_score}), Loser='{loser_ign}' ({loser_score})")
            
            # Look up players in database by their IGNs
            winner_profile = await db.get_player_by_ign(winner_ign)
            loser_profile = await db.get_player_by_ign(loser_ign)
            
            if not winner_profile:
                print(f"⚠️ Winner IGN '{winner_ign}' not found in database")
            if not loser_profile:
                print(f"⚠️ Loser IGN '{loser_ign}' not found in database")
            
            # Get Discord user objects
            winner_user = None
            loser_user = None
            winner_registered = False
            loser_registered = False
            
            if winner_profile:
                winner_user = channel.guild.get_member(winner_profile['user_id'])
                if winner_user:
                    winner_registered = True
                    print(f"✅ Found winner: {winner_user.display_name} (IGN: {winner_ign})")
                else:
                    print(f"⚠️ Winner user with ID {winner_profile['user_id']} not in guild")
            
            if loser_profile:
                loser_user = channel.guild.get_member(loser_profile['user_id'])
                if loser_user:
                    loser_registered = True
                    print(f"✅ Found loser: {loser_user.display_name} (IGN: {loser_ign})")
                else:
                    print(f"⚠️ Loser user with ID {loser_profile['user_id']} not in guild")
            
            # If either player not found, show error
            if not winner_user or not loser_user:
                error_msg = "❌ Could not find players in database:\\n"
                if not winner_user:
                    error_msg += f"• Winner IGN '{winner_ign}' "
                    error_msg += "not registered" if not winner_profile else "not in this server"
                    error_msg += "\\n"
                if not loser_user:
                    error_msg += f"• Loser IGN '{loser_ign}' "
                    error_msg += "not registered" if not loser_profile else "not in this server"
                    error_msg += "\\n"
                error_msg += "\\nPlayers must be registered with `/ign` command before their stats can be updated."
                
                await channel.send(error_msg)
                await processing_msg.delete()
                # Don't continue with match completion
                return
            
            # Delete processing message
            await processing_msg.delete()
            
            # Update player stats in database (both players are registered at this point)
            winner_stats = await db.update_player_stats(winner_user.id, won=True, mmr_change=32)
            loser_stats = await db.update_player_stats(loser_user.id, won=False, mmr_change=-27)
            
            # Update rank roles
            if winner_stats:
                await update_player_rank_role(channel.guild, winner_user.id, winner_stats['mmr'])
            if loser_stats:
                await update_player_rank_role(channel.guild, loser_user.id, loser_stats['mmr'])
            
            # Send result in match channel (simple confirmation)
            result_embed = discord.Embed(
                title=f"✅ Match #{match_data['match_number']:04d} Complete",
                description=(
                    f"**Winner:** {winner_user.mention} - **{winner_score}**\\n"
                    f"**Runner-up:** {loser_user.mention} - **{loser_score}**\\n\\n"
                    f"Results posted to queue-results channel!"
                ),
                color=0x00FF00
            )
            await channel.send(embed=result_embed)
            
            # Disable submit button
            for item in self.children:
                item.disabled = True
            if self.message:
                await self.message.edit(view=self)
            
            # POST TO QUEUE-RESULTS CHANNEL
            results_channel_id = os.getenv('QUEUE_RESULTS_CHANNEL_ID')
            if results_channel_id:
                results_channel = channel.guild.get_channel(int(results_channel_id))
                if results_channel:
                    # Create detailed result embed for queue-results channel
                    result_embed = discord.Embed(
                        title=f"🏆 Winner For Queue#{match_data['match_number']:04d} 🏆",
                        color=0xFFD700  # Gold color
                    )
                    
                    # Add winner info with IGN
                    result_embed.add_field(
                        name=f"**{winner_ign}**",
                        value=f"{winner_user.mention}\n**Score:** {winner_score}",
                        inline=True
                    )
                    
                    # Add loser info with IGN  
                    result_embed.add_field(
                        name=f"**{loser_ign}**",
                        value=f"{loser_user.mention}\n**Score:** {loser_score}",
                        inline=True
                    )
                    
                    # Add MMR information
                    if winner_stats and loser_stats:
                        result_embed.add_field(
                            name="📊 MMR Changes",
                            value=(
                                f"**{winner_user.mention}:** {winner_stats['mmr']-32:,} → **{winner_stats['mmr']:,}** (+32)\\n"
                                f"**{loser_user.mention}:** {loser_stats['mmr']+27:,} → **{loser_stats['mmr']:,}** (-27)"
                            ),
                            inline=False
                        )
                    
                    # Add screenshot
                    result_embed.set_image(url=attachment.url)
                    
                    # Add timestamp
                    result_embed.timestamp = discord.utils.utcnow()
                    result_embed.set_footer(text="Vote for the MVP below! 🏆")
                    
                    # Create MVP voting view
                    mvp_view = MVPView(
                        str(self.match_id),
                        winner_user.id,
                        winner_user.display_name,
                        loser_user.id,
                        loser_user.display_name,
                        self.bot
                    )
                    
                    # Send result message
                    result_message = await results_channel.send(embed=result_embed, view=mvp_view)
                    mvp_view.message = result_message
                    
                    # Save match result to database
                    await db.save_match_result(
                        match_id=str(self.match_id),
                        match_number=match_data['match_number'],
                        winner_id=winner_user.id,
                        loser_id=loser_user.id,
                        winner_score=winner_score,
                        loser_score=loser_score,
                        screenshot_url=attachment.url,
                        result_message_id=result_message.id,
                        result_channel_id=results_channel.id
                    )
                    
                    # Log match result to scrimmish logs channel
                    logs_channel_id = os.getenv('LOGS_CHANNEL_ID')
                    if logs_channel_id:
                        logs_channel = channel.guild.get_channel(int(logs_channel_id))
                        if logs_channel:
                            log_embed = discord.Embed(
                                title=f"🏆 Match #{match_data['match_number']:04d} Complete",
                                color=0xFFD700
                            )
                            log_embed.add_field(
                                name="Winner",
                                value=f"{winner_user.mention} ({winner_ign})\n**Score:** {winner_score}",
                                inline=True
                            )
                            log_embed.add_field(
                                name="Loser",
                                value=f"{loser_user.mention} ({loser_ign})\n**Score:** {loser_score}",
                                inline=True
                            )
                            if winner_stats and loser_stats:
                                log_embed.add_field(
                                    name="MMR Changes",
                                    value=f"**{winner_user.mention}:** {winner_stats['mmr']:,} (+32)\n**{loser_user.mention}:** {loser_stats['mmr']:,} (-27)",
                                    inline=False
                                )
                            log_embed.add_field(
                                name="Result Posted",
                                value=f"[View in {results_channel.mention}]({result_message.jump_url})",
                                inline=False
                            )
                            log_embed.timestamp = discord.utils.utcnow()
                            await logs_channel.send(embed=log_embed)
            
            # Update rank tracking before refreshing leaderboards
            await db.update_all_ranks()
            
            # Update all active leaderboards
            await update_all_leaderboards()
            
            # Clean up match channels after 30 seconds
            await asyncio.sleep(30)
            try:
                await channel.delete()
                await match_data['voice_channel'].delete()
            except:
                pass
            
            if self.match_id in active_matches:
                del active_matches[self.match_id]
            
        except Exception as e:
            match_data['processing_ss'] = False
            error_embed = discord.Embed(
                title="❌ Error Processing Screenshot",
                description=f"Could not process the screenshot. Please make sure it's a clear image of the final scoreboard.\n\nError: {str(e)}",
                color=0xFF0000
            )
            await channel.send(embed=error_embed)

class CancelButton(discord.ui.Button):
    """Button for voting on match cancellation"""
    def __init__(self, vote_type: str):
        # vote_type is "yes" or "no"
        style = discord.ButtonStyle.red if vote_type == "yes" else discord.ButtonStyle.gray
        super().__init__(
            style=style,
            label=f"Vote {vote_type.upper()}",
            custom_id=f"cancel_{vote_type}"
        )
        self.vote_type = vote_type
    
    async def callback(self, interaction: discord.Interaction):
        cancel_data = self.view.cancel_data
        user_id = interaction.user.id
        
        # Check if user is one of the players
        player1_id = cancel_data['player1'].id
        player2_id = cancel_data['player2'].id
        
        if user_id not in [player1_id, player2_id]:
            await interaction.response.send_message("❌ Only players in this match can vote!", ephemeral=True)
            return
        
        # Check if user already voted
        if user_id in cancel_data['voters']:
            await interaction.response.send_message("❌ You have already voted!", ephemeral=True)
            return
        
        # Record the vote
        cancel_data['voters'].add(user_id)
        if self.vote_type == "yes":
            cancel_data['yes_votes'] += 1
        else:
            cancel_data['no_votes'] += 1
        
        # Update the display
        await self.view.update_display(interaction)
        
        # Check if both players voted - finalize immediately
        if len(cancel_data['voters']) == 2:
            await self.view.finalize_decision(early=True)

class CancelView(discord.ui.View):
    """View for match cancellation voting"""
    def __init__(self, bot, cancel_data: dict):
        super().__init__(timeout=60)  # 1 minute timeout
        self.bot = bot
        self.cancel_data = cancel_data
        self.message: Optional[discord.Message] = None
        self.finalized = False
        
        # Add yes and no buttons
        self.add_item(CancelButton("yes"))
        self.add_item(CancelButton("no"))
    
    async def update_display(self, interaction: discord.Interaction):
        """Update the vote counts in the embed"""
        yes_votes = self.cancel_data['yes_votes']
        no_votes = self.cancel_data['no_votes']
        
        embed = discord.Embed(
            title="⚠️ Match Cancellation Vote",
            description=f"Vote whether to cancel this match\n\n**Yes Votes:** {yes_votes}\n**No Votes:** {no_votes}\n\nWaiting for votes...",
            color=0xFF0000
        )
        embed.set_footer(text="Vote ends in 60 seconds or when both players vote")
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def finalize_decision(self, early: bool = False):
        """Finalize the cancellation vote and take action"""
        if self.finalized:
            return
        
        self.finalized = True
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        yes_votes = self.cancel_data['yes_votes']
        no_votes = self.cancel_data['no_votes']
        total_votes = len(self.cancel_data['voters'])
        
        # Determine the outcome
        if total_votes == 0:
            # No one voted
            result = "continue"
            reason = "No one voted"
        elif yes_votes > no_votes:
            result = "cancel"
            reason = f"Majority voted YES ({yes_votes}-{no_votes})"
        else:
            result = "continue"
            reason = f"Vote was NO or tied ({yes_votes}-{no_votes})"
        
        # Create result embed
        if result == "cancel":
            embed = discord.Embed(
                title="❌ Match Cancelled",
                description=f"{reason}\n\nThis match has been cancelled. Channels will be deleted in 30 seconds.",
                color=0xFF0000
            )
        else:
            embed = discord.Embed(
                title="✅ Match Continues",
                description=f"{reason}\n\nThe match will continue.",
                color=0x00FF00
            )
        
        if self.message:
            await self.message.edit(embed=embed, view=self)
        
        # Handle the outcome
        if result == "cancel":
            text_channel_id = self.cancel_data['text_channel_id']
            voice_channel_id = self.cancel_data['voice_channel_id']
            
            await asyncio.sleep(30)
            
            # Delete channels
            guild = self.bot.get_guild(int(os.getenv('GUILD_ID')))
            text_channel = guild.get_channel(text_channel_id)
            voice_channel = guild.get_channel(voice_channel_id)
            
            if text_channel:
                try:
                    await text_channel.delete()
                except:
                    pass
            if voice_channel:
                try:
                    await voice_channel.delete()
                except:
                    pass
            
            # Remove from active matches
            if text_channel_id in active_matches:
                del active_matches[text_channel_id]
        
        self.stop()
    
    async def on_timeout(self):
        """Called when the 60 second timeout occurs"""
        await self.finalize_decision(early=False)

class MVPButton(discord.ui.Button):
    """Button for voting MVP"""
    def __init__(self, user_id: int, display_name: str):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label=f"Vote {display_name}",
            emoji="🏆",
            custom_id=f"mvp_{user_id}"
        )
        self.voted_user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        match_id = self.view.match_id
        voter_id = interaction.user.id
        
        # Record the vote in database
        vote_recorded = await db.add_mvp_vote(match_id, voter_id, self.voted_user_id)
        
        if not vote_recorded:
            await interaction.response.send_message(
                "✅ You've already voted in this match!",
                ephemeral=True
            )
            return
        
        # Update the display
        await self.view.update_vote_display(interaction)
        
        # Check if we should finalize (5+ votes or timeout)
        total_votes = await db.get_total_mvp_votes(match_id)
        if total_votes >= 5:
            await self.view.finalize_mvp()

class MVPView(discord.ui.View):
    """View for MVP voting"""
    def __init__(self, match_id: str, player1_id: int, player1_name: str, 
                 player2_id: int, player2_name: str, bot):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.match_id = match_id
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.bot = bot
        self.message: Optional[discord.Message] = None
        self.finalized = False
        
        # Add voting buttons for both players
        self.add_item(MVPButton(player1_id, player1_name))
        self.add_item(MVPButton(player2_id, player2_name))
    
    async def update_vote_display(self, interaction: discord.Interaction):
        """Update the vote counts in real-time"""
        if self.finalized:
            return
        
        # Get current vote counts
        vote_counts = await db.get_mvp_votes(self.match_id)
        p1_votes = vote_counts.get(self.player1_id, 0)
        p2_votes = vote_counts.get(self.player2_id, 0)
        total_votes = p1_votes + p2_votes
        
        # Update button labels with vote counts
        for item in self.children:
            if isinstance(item, MVPButton):
                votes = vote_counts.get(item.voted_user_id, 0)
                player_name = interaction.guild.get_member(item.voted_user_id).display_name
                item.label = f"{player_name} ({votes} votes)"
        
        embed = self.message.embeds[0]
        embed.set_footer(text=f"🗳️ {total_votes} total votes • Voting ends in 5 minutes")
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def finalize_mvp(self):
        """Finalize MVP voting and declare winner"""
        if self.finalized:
            return
        
        self.finalized = True
        
        # Get final vote counts
        vote_counts = await db.get_mvp_votes(self.match_id)
        p1_votes = vote_counts.get(self.player1_id, 0)
        p2_votes = vote_counts.get(self.player2_id, 0)
        total_votes = p1_votes + p2_votes
        
        # Determine MVP based on votes
        if p1_votes > p2_votes:
            mvp_id = self.player1_id
            mvp_votes = p1_votes
        elif p2_votes > p1_votes:
            mvp_id = self.player2_id
            mvp_votes = p2_votes
        else:
            # Tie or no votes - no MVP
            if self.message:
                embed = self.message.embeds[0]
                embed.set_footer(text="⚖️ Voting ended in a tie - No MVP awarded")
                for item in self.children:
                    item.disabled = True
                await self.message.edit(embed=embed, view=self)
            return
        
        # Update database
        await db.update_player_mvp(mvp_id)
        await db.finalize_mvp(self.match_id, mvp_id, total_votes)
        
        # Update message with MVP winner
        if self.message:
            mvp_user = self.message.guild.get_member(mvp_id)
            embed = self.message.embeds[0]
            embed.add_field(
                name="🏆 Match MVP",
                value=f"{mvp_user.mention} with **{mvp_votes}** votes!",
                inline=False
            )
            embed.set_footer(text=f"✅ MVP Voting Complete • {total_votes} total votes")
            
            # Disable all buttons
            for item in self.children:
                item.disabled = True
            
            await self.message.edit(embed=embed, view=self)
    
    async def on_timeout(self):
        """Called when 5 minute timeout occurs"""
        await self.finalize_mvp()

class VoteButton(discord.ui.Button):
    """Button for voting on match winner"""
    def __init__(self, team_name: str, match_id: str, style: discord.ButtonStyle):
        super().__init__(
            style=style,
            label=team_name
        )
        self.team_name = team_name
        self.match_id = match_id
    
    async def callback(self, interaction: discord.Interaction):
        match_data = active_matches.get(self.match_id)
        if not match_data:
            await interaction.response.send_message("Match data not found.", ephemeral=True)
            return
        
        # Check if user already voted
        if interaction.user.id in match_data['voters']:
            await interaction.response.send_message("You have already voted!", ephemeral=True)
            return
        
        # Record vote
        match_data['voters'].add(interaction.user.id)
        match_data['votes'][self.team_name] += 1
        
        # Update the embed
        await self.view.update_vote_display(interaction)
        
        # Check if any team has 2 votes
        team1_name = match_data['team1_name']
        team2_name = match_data['team2_name']
        
        if match_data['votes'][team1_name] >= 2:
            await self.view.finalize_match(self.match_id, team1_name, interaction)
        elif match_data['votes'][team2_name] >= 2:
            await self.view.finalize_match(self.match_id, team2_name, interaction)
        else:
            await interaction.response.defer()

class VoteView(discord.ui.View):
    """View containing voting buttons"""
    def __init__(self, match_id: str, team1_name: str, team2_name: str, bot):
        super().__init__(timeout=None)
        self.match_id = match_id
        self.team1_name = team1_name
        self.team2_name = team2_name
        self.bot = bot
        self.message: Optional[discord.Message] = None
        
        # Add vote buttons (red style like NeatQueue)
        self.add_item(VoteButton(team1_name, match_id, discord.ButtonStyle.red))
        self.add_item(VoteButton(team2_name, match_id, discord.ButtonStyle.red))
    
    async def update_vote_display(self, interaction: discord.Interaction):
        """Update the voting embed with current vote counts"""
        match_data = active_matches.get(self.match_id)
        if not match_data:
            return
        
        team1_votes = match_data['votes'][self.team1_name]
        team2_votes = match_data['votes'][self.team2_name]
        match_number = match_data['match_number']
        
        embed = discord.Embed(
            title=f"Winner For Queue#{match_number:04d}",
            color=0xED4245
        )
        
        votes_needed = 2 - max(team1_votes, team2_votes)
        
        embed.add_field(
            name=self.team1_name,
            value=f"Votes: {team1_votes}",
            inline=True
        )
        embed.add_field(
            name=self.team2_name,
            value=f"Votes: {team2_votes}",
            inline=True
        )
        embed.add_field(
            name="\u200b",
            value=f"{votes_needed} more votes required!",
            inline=False
        )
        
        if self.message:
            try:
                await self.message.edit(embed=embed, view=self)
            except:
                pass
    
    async def finalize_match(self, match_id: str, winner_name: str, interaction: discord.Interaction):
        """Finalize the match and send logs"""
        match_data = active_matches.get(match_id)
        if not match_data:
            return
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        # Update final embed
        embed = discord.Embed(
            title=f"Winner For Queue#{match_data['match_number']:04d}",
            description=f"**{winner_name}** wins!",
            color=0x00FF00
        )
        
        team1_votes = match_data['votes'][self.team1_name]
        team2_votes = match_data['votes'][self.team2_name]
        
        embed.add_field(
            name=self.team1_name,
            value=f"Votes: {team1_votes}",
            inline=True
        )
        embed.add_field(
            name=self.team2_name,
            value=f"Votes: {team2_votes}",
            inline=True
        )
        
        if self.message:
            await self.message.edit(embed=embed, view=self)
        
        # Send to logs channel
        await self.send_match_logs(match_data, winner_name)
        
        # Clean up channels after 30 seconds
        await asyncio.sleep(30)
        try:
            await match_data['text_channel'].delete()
            await match_data['voice_channel'].delete()
        except:
            pass
        
        # Remove from active matches
        if match_id in active_matches:
            del active_matches[match_id]
    
    async def send_match_logs(self, match_data: dict, winner_name: str):
        """Send detailed match logs to logs channel"""
        logs_channel_id = int(os.getenv('LOGS_CHANNEL_ID', 0))
        if not logs_channel_id:
            print("⚠️ LOGS_CHANNEL_ID not set, skipping logs")
            return
        
        logs_channel = self.bot.get_channel(logs_channel_id)
        if not logs_channel:
            print(f"❌ Logs channel {logs_channel_id} not found")
            return
        
        member1 = match_data['player1']
        member2 = match_data['player2']
        match_number = match_data['match_number']
        timestamp = datetime.utcnow().strftime("%d %B %Y %H:%M")
        
        # Create results embed
        embed = discord.Embed(
            title=f"Results for Queue#{match_number:04d}",
            color=0xED4245
        )
        
        # Match Info section
        match_info = (
            f"Queue: player_stats\n"
            f"Map: valorant\n"
            f"Lobby Details:\n"
            f"Timestamp: {timestamp}"
        )
        embed.add_field(name="Match Info", value=match_info, inline=False)
        
        # Team 1 (winner gets trophy)
        team1_name = match_data['team1_name']
        team1_display = f"{member1.mention}"
        embed.add_field(name=team1_name, value=team1_display, inline=False)
        
        # Team 2
        team2_name = match_data['team2_name']
        team2_display = f"{member2.mention}"
        embed.add_field(name=team2_name, value=team2_display, inline=False)
        
        embed.set_footer(text=f"Winner: {winner_name}")
        
        await logs_channel.send(embed=embed)
        print(f"✅ Sent match logs for #{match_number:04d} to logs channel")

class SubRequestView(discord.ui.View):
    """View for sub request accept/decline buttons"""
    def __init__(self, request_id: str):
        super().__init__(timeout=300)  # 5 minute timeout
        self.request_id = request_id
    
    @discord.ui.button(label="Accept Sub", style=discord.ButtonStyle.success, custom_id="sub_accept")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Accept the sub request"""
        if self.request_id not in active_sub_requests:
            await interaction.response.send_message("❌ This sub request has expired.", ephemeral=True)
            return
        
        request_data = active_sub_requests[self.request_id]
        
        # Check if the person clicking is the substitute
        if interaction.user.id != request_data['substitute'].id:
            await interaction.response.send_message("❌ Only the requested substitute can accept this.", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        # Update the match data
        match_data = request_data['match_data']
        original_player = request_data['original_player']
        substitute = request_data['substitute']
        text_channel = request_data['text_channel']
        voice_channel = request_data['voice_channel']
        
        # Update player in match data
        if match_data['player1'].id == original_player.id:
            match_data['player1'] = substitute
            match_data['team1_name'] = str(substitute.display_name)
        else:
            match_data['player2'] = substitute
            match_data['team2_name'] = str(substitute.display_name)
        
        # Update channel permissions - give sub full access
        await text_channel.set_permissions(substitute, read_messages=True, send_messages=True)
        await voice_channel.set_permissions(substitute, connect=True, speak=True)
        
        # Remove original player from channels
        await text_channel.set_permissions(original_player, overwrite=None)
        await voice_channel.set_permissions(original_player, overwrite=None)
        
        # Update both messages
        success_embed = discord.Embed(
            title="✅ Sub Request Accepted",
            description=f"{substitute.mention} has accepted the sub request!\n\n"
                       f"**You have 3 minutes to join {voice_channel.mention}**",
            color=0x00FF00
        )
        
        # Update DM message
        try:
            await request_data['dm_message'].edit(embed=success_embed, view=None)
        except:
            pass
        
        # Update channel message
        try:
            await request_data['channel_message'].edit(embed=success_embed, view=None)
        except:
            pass
        
        # Send notification in match channel
        await text_channel.send(
            f"✅ {substitute.mention} has subbed in for {original_player.mention}! "
            f"You have 3 minutes to join {voice_channel.mention}"
        )
        
        # Start 3-minute timer for sub to join VC
        await self.monitor_sub_join(match_data, substitute, text_channel, voice_channel)
        
        # Clean up request
        del active_sub_requests[self.request_id]
    
    @discord.ui.button(label="Decline Sub", style=discord.ButtonStyle.danger, custom_id="sub_decline")
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Decline the sub request"""
        if self.request_id not in active_sub_requests:
            await interaction.response.send_message("❌ This sub request has expired.", ephemeral=True)
            return
        
        request_data = active_sub_requests[self.request_id]
        
        # Check if the person clicking is the substitute
        if interaction.user.id != request_data['substitute'].id:
            await interaction.response.send_message("❌ Only the requested substitute can decline this.", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        text_channel = request_data['text_channel']
        substitute = request_data['substitute']
        original_player = request_data['original_player']
        
        # Remove channel access
        await text_channel.set_permissions(substitute, overwrite=None)
        
        # Update both messages
        decline_embed = discord.Embed(
            title="❌ Sub Request Declined",
            description=f"{substitute.mention} has declined the sub request.\n\n"
                       f"{original_player.mention} must continue with the match.",
            color=0xFF0000
        )
        
        # Update DM message
        try:
            await request_data['dm_message'].edit(embed=decline_embed, view=None)
        except:
            pass
        
        # Update channel message
        try:
            await request_data['channel_message'].edit(embed=decline_embed, view=None)
        except:
            pass
        
        # Send notification in match channel
        await text_channel.send(
            f"❌ {substitute.mention} declined the sub request. {original_player.mention} must continue."
        )
        
        # Clean up request
        del active_sub_requests[self.request_id]
    
    async def monitor_sub_join(self, match_data: dict, substitute: discord.Member, 
                              text_channel: discord.TextChannel, voice_channel: discord.VoiceChannel):
        """Monitor if substitute joins VC within 3 minutes"""
        start_time = asyncio.get_event_loop().time()
        timeout = 180  # 3 minutes
        check_interval = 5  # Check every 5 seconds
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            
            # Refresh voice channel
            voice_channel = text_channel.guild.get_channel(voice_channel.id)
            if not voice_channel:
                return
            
            # Check if sub is in VC
            if substitute in voice_channel.members:
                await text_channel.send(f"✅ {substitute.mention} has joined the voice channel!")
                return
            
            # Check timeout
            if elapsed >= timeout:
                await text_channel.send(
                    f"❌ {substitute.mention} failed to join within 3 minutes. Match may need to be cancelled."
                )
                return
            
            await asyncio.sleep(check_interval)

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
        
        # Log to scrimmish logs channel
        logs_channel_id = os.getenv('LOGS_CHANNEL_ID')
        if logs_channel_id:
            logs_channel = interaction.guild.get_channel(int(logs_channel_id))
            if logs_channel:
                log_embed = discord.Embed(
                    title="📥 Player Joined Queue",
                    description=f"{interaction.user.mention} joined the queue",
                    color=0x00FF00
                )
                log_embed.add_field(name="Queue Size", value=f"{len(queue)}/2", inline=True)
                log_embed.timestamp = discord.utils.utcnow()
                await logs_channel.send(embed=log_embed)
        
        # Start inactivity timer if this is the first player
        if len(queue) == 1:
            await self.view.start_inactivity_timer(interaction.channel_id, interaction.guild)
        
        # Send autoping if configured and queue has exactly 1 player (1 in queue, 1 more needed)
        # Use a lock to prevent race condition if multiple players join simultaneously
        async with autoping_lock:
            autoping_config = await db.get_autoping(interaction.channel_id)
            if autoping_config and len(queue) == 1:
                role = interaction.guild.get_role(autoping_config['role_id'])
                if role:
                    # Repeat the role mention 'size' times
                    ping_content = " ".join([role.mention] * autoping_config['size'])
                    
                    # Send the ping message
                    ping_msg = await interaction.channel.send(ping_content)
                    
                    # Schedule deletion after specified time
                    delete_after = autoping_config['delete_after']
                    if delete_after > 0:
                        async def delete_ping():
                            await asyncio.sleep(delete_after)
                            try:
                                await ping_msg.delete()
                            except:
                                pass
                        
                        # Start deletion task
                        self.view.bot.loop.create_task(delete_ping())
        
        # Check if we have 2 players (match ready)
        if len(queue) >= 2:
            # Cancel inactivity timer since match is starting
            await self.view.cancel_inactivity_timer(interaction.channel_id)
            
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
            
            # Create private text channel - same name as voice for easy pairing
            text_channel = await guild.create_text_channel(
                name=f"{match_number:04d}-queue",
                category=category,
                overwrites=overwrites
            )
            
            # Create private voice channel - same name as text for easy pairing
            voice_channel = await guild.create_voice_channel(
                name=f"{match_number:04d}-queue",
                category=category,
                overwrites=overwrites
            )
            
            # Store match info with vote tracking
            team1_name = str(member1.display_name)
            team2_name = str(member2.display_name)
            
            active_matches[text_channel.id] = {
                'match_number': match_number,
                'player1': member1,
                'player2': member2,
                'text_channel': text_channel,
                'voice_channel': voice_channel,
                'match_id': match_id,
                'team1_name': team1_name,
                'team2_name': team2_name,
                'votes': {team1_name: 0, team2_name: 0},
                'voters': set()
            }
            
            # Send initial message asking players to join VC
            initial_embed = discord.Embed(
                title=f"Scrimmish Match #{match_number:04d}",
                description=f"{member1.mention} vs {member2.mention}\n\nPlease join {voice_channel.mention} within 5 minutes to proceed.",
                color=0xED4245
            )
            initial_embed.set_footer(text="Match will be cancelled if both players don't join within 5 minutes")
            
            initial_message = await text_channel.send(
                content=f"{member1.mention} {member2.mention}",
                embed=initial_embed
            )
            
            # Store initial message reference for updates
            active_matches[text_channel.id]['initial_message'] = initial_message
            
            # Log match creation to scrimmish logs channel
            logs_channel_id = os.getenv('LOGS_CHANNEL_ID')
            if logs_channel_id:
                logs_channel = guild.get_channel(int(logs_channel_id))
                if logs_channel:
                    log_embed = discord.Embed(
                        title=f"🎮 Match #{match_number:04d} Created",
                        description=f"Match channels created for {member1.mention} vs {member2.mention}",
                        color=0x5865F2
                    )
                    log_embed.add_field(
                        name="Players",
                        value=f"**Player 1:** {member1.mention}\n**Player 2:** {member2.mention}",
                        inline=False
                    )
                    log_embed.add_field(
                        name="Channels",
                        value=f"**Text:** {text_channel.mention}\n**Voice:** {voice_channel.mention}",
                        inline=False
                    )
                    log_embed.timestamp = discord.utils.utcnow()
                    await logs_channel.send(embed=log_embed)
            
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
            
            # Get updated queue
            queue = await db.get_queue()
            
            # Cancel inactivity timer if queue is now empty
            if len(queue) == 0:
                await self.view.cancel_inactivity_timer(interaction.channel_id)
            
            # Log to scrimmish logs channel
            logs_channel_id = os.getenv('LOGS_CHANNEL_ID')
            if logs_channel_id:
                logs_channel = interaction.guild.get_channel(int(logs_channel_id))
                if logs_channel:
                    log_embed = discord.Embed(
                        title="📤 Player Left Queue",
                        description=f"{interaction.user.mention} left the queue",
                        color=0xFF0000
                    )
                    log_embed.add_field(name="Queue Size", value=f"{len(queue)}/2", inline=True)
                    log_embed.timestamp = discord.utils.utcnow()
                    await logs_channel.send(embed=log_embed)
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
            emoji="📊"
        )
    
    async def callback(self, interaction: discord.Interaction):
        leaderboard_channel_id = os.getenv('LEADERBOARD_CHANNEL_ID')
        
        if not leaderboard_channel_id:
            await interaction.response.send_message(
                "⚠️ Leaderboard channel not configured. Please contact an administrator.",
                ephemeral=True
            )
            return
        
        leaderboard_channel = interaction.guild.get_channel(int(leaderboard_channel_id))
        
        if not leaderboard_channel:
            await interaction.response.send_message(
                "❌ Leaderboard channel not found. Please contact an administrator.",
                ephemeral=True
            )
            return
        
        await interaction.response.send_message(
            f"📊 **View the leaderboard here:** {leaderboard_channel.mention}\n\n"
            f"Check out the rankings and see where you stand!",
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
    
    async def start_inactivity_timer(self, channel_id: int, guild: discord.Guild):
        """Start 60-minute inactivity timer for queue"""
        # Cancel existing timer if any
        await self.cancel_inactivity_timer(channel_id)
        
        async def inactivity_timeout():
            try:
                await asyncio.sleep(3600)  # 60 minutes
                
                # Clear the queue
                queue = await db.get_queue()
                for player in queue:
                    await db.remove_from_queue(player['user_id'])
                
                # Update queue display with inactivity message
                channel = guild.get_channel(channel_id)
                if channel and self.message:
                    embed = discord.Embed(
                        title="Valorant Mobile India Matchmaking Queue",
                        description="Emptying queue due to 60 minutes of inactivity\nRe-enter the queue if you are still looking to play!",
                        color=0x2B2D31  # Dark gray
                    )
                    embed.add_field(
                        name="",
                        value="**Queue 0/2**\n\n",
                        inline=False
                    )
                    embed.set_image(url="attachment://valm_india_banner.jpg")
                    embed.timestamp = discord.utils.utcnow()
                    
                    try:
                        await self.message.edit(embed=embed)
                    except:
                        pass
                    
                    # Log to scrimmish logs channel
                    logs_channel_id = os.getenv('LOGS_CHANNEL_ID')
                    if logs_channel_id:
                        logs_channel = guild.get_channel(int(logs_channel_id))
                        if logs_channel:
                            log_embed = discord.Embed(
                                title="⏰ Queue Cleared - Inactivity",
                                description="Queue was cleared due to 60 minutes of inactivity",
                                color=0xFF6B6B
                            )
                            log_embed.timestamp = discord.utils.utcnow()
                            await logs_channel.send(embed=log_embed)
                
                # Clean up timer reference
                if channel_id in queue_inactivity_timers:
                    del queue_inactivity_timers[channel_id]
                    
            except asyncio.CancelledError:
                # Timer was cancelled (player left or second player joined)
                pass
        
        # Create and store the timer task
        timer_task = asyncio.create_task(inactivity_timeout())
        queue_inactivity_timers[channel_id] = timer_task
    
    async def cancel_inactivity_timer(self, channel_id: int):
        """Cancel the inactivity timer for a channel"""
        if channel_id in queue_inactivity_timers:
            timer_task = queue_inactivity_timers[channel_id]
            timer_task.cancel()
            del queue_inactivity_timers[channel_id]
    
    async def update_queue_display(self, interaction: discord.Interaction):
        """Update the queue embed display"""
        queue = await db.get_queue()
        queue_count = len(queue)
        
        # Create embed with clean NeatQueue style
        embed = discord.Embed(
            title="VALM INDIA MATCHMAKING Queue",
            color=0xED4245  # Discord red
        )
        
        # Build queue display with proper spacing
        queue_text = f"**Queue {queue_count}/2**\n\n"
        
        # Add player mentions if any
        if queue:
            players_text = ", ".join([f"<@{player['user_id']}>" for player in queue])
            queue_text += f"{players_text}\n\n"
        
        # Add the queue field
        embed.add_field(
            name="",
            value=queue_text,
            inline=False
        )
        
        # Set the banner image
        embed.set_image(url="attachment://valm_india_banner.jpg")
        
        # Add timestamp at bottom
        embed.timestamp = discord.utils.utcnow()
        
        # Update the message (without re-uploading the file)
        if self.message:
            try:
                await self.message.edit(embed=embed)
            except:
                pass
    
    async def handle_match_flow(self, text_channel_id: int):
        """Handle the complete match flow with timers and state checks"""
        try:
            match_data = active_matches.get(text_channel_id)
            if not match_data:
                print(f"❌ No match data found for channel {text_channel_id}")
                return
            
            text_channel = match_data['text_channel']
            voice_channel = match_data['voice_channel']
            member1 = match_data['player1']
            member2 = match_data['player2']
            guild = text_channel.guild
            
            print(f"✅ Starting match flow for {match_data['match_number']:04d}")
            
            # Check every 3 seconds for up to 4 minutes if both players joined
            start_time = asyncio.get_event_loop().time()
            check_interval = 3  # Check every 3 seconds
            warning_time = 240  # 4 minutes
            timeout_time = 300  # 5 minutes
            
            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                
                # Fetch fresh voice channel to get current members
                voice_channel = guild.get_channel(voice_channel.id)
                if not voice_channel:
                    print(f"❌ Voice channel not found for match {text_channel_id}")
                    return
                
                # Check who's in the voice channel
                members_in_vc = voice_channel.members
                player1_in_vc = member1 in members_in_vc
                player2_in_vc = member2 in members_in_vc
                
                # If both players are in VC, proceed immediately
                if player1_in_vc and player2_in_vc:
                    print(f"✅ Both players joined VC after {elapsed:.1f} seconds")
                    await self.proceed_to_match(text_channel_id)
                    return
                
                # At 4 minutes, send warning
                if elapsed >= warning_time and elapsed < warning_time + check_interval:
                    print(f"⚠️ 4min warning - Player1 in VC: {player1_in_vc}, Player2 in VC: {player2_in_vc}")
                    
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
                
                # At 5 minutes, timeout
                if elapsed >= timeout_time:
                    print(f"❌ Timeout - Player1 in VC: {player1_in_vc}, Player2 in VC: {player2_in_vc}")
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
                    return
                
                # Wait before next check
                await asyncio.sleep(check_interval)
        
        except Exception as e:
            print(f"❌ Error in handle_match_flow: {e}")
            import traceback
            traceback.print_exc()
    
    async def proceed_to_match(self, text_channel_id: int):
        """Proceed with match when both players are in VC"""
        match_data = active_matches.get(text_channel_id)
        if not match_data:
            return
        
        text_channel = match_data['text_channel']
        member1 = match_data['player1']
        member2 = match_data['player2']
        
        # Initialize ready players set
        match_data['ready_players'] = set()
        
        # Send ready check
        ready_embed = discord.Embed(
            title="🎮 Ready Check",
            description=f"Both players must confirm they're ready to proceed.\n\n⏳ {member1.mention}\n⏳ {member2.mention}",
            color=0x5865F2
        )
        ready_embed.add_field(
            name="Status",
            value="0/2 players ready",
            inline=False
        )
        
        ready_view = ReadyView(text_channel_id, self.bot)
        ready_message = await text_channel.send(embed=ready_embed, view=ready_view)
        ready_view.message = ready_message

# Dictionary to store active leaderboard messages {channel_id: {'message': message, 'page': page}}
active_leaderboards = {}

class LeaderboardView(discord.ui.View):
    """Persistent view for leaderboard pagination"""
    def __init__(self, channel_id: int, page: int = 1):
        super().__init__(timeout=None)
        self.channel_id = channel_id
        self.page = page
    
    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="leaderboard_prev")
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous page"""
        if self.page > 1:
            self.page -= 1
            active_leaderboards[self.channel_id]['page'] = self.page
            # Save page to database
            message = active_leaderboards[self.channel_id]['message']
            await db.save_leaderboard(self.channel_id, message.id, self.page)
            await self.update_leaderboard_display(interaction)
        else:
            await interaction.response.send_message("You're already on the first page!", ephemeral=True)
    
    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary, custom_id="leaderboard_refresh")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Refresh leaderboard data"""
        await self.update_leaderboard_display(interaction)
    
    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, custom_id="leaderboard_next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next page"""
        # Calculate total pages
        total_players = await db.get_total_players()
        total_pages = (total_players + 9) // 10  # Ceiling division
        
        if self.page < total_pages:
            self.page += 1
            active_leaderboards[self.channel_id]['page'] = self.page
            # Save page to database
            message = active_leaderboards[self.channel_id]['message']
            await db.save_leaderboard(self.channel_id, message.id, self.page)
            await self.update_leaderboard_display(interaction)
        else:
            await interaction.response.send_message("You're already on the last page!", ephemeral=True)
    
    async def update_leaderboard_display(self, interaction: discord.Interaction):
        """Update the leaderboard embed display"""
        await interaction.response.defer()
        
        # Calculate offset
        offset = (self.page - 1) * 10
        
        # Get players for current page
        players = await db.get_leaderboard_page(limit=10, offset=offset)
        total_players = await db.get_total_players()
        total_pages = max(1, (total_players + 9) // 10)
        
        if not players and self.page > 1:
            # Page doesn't exist, go back to page 1
            self.page = 1
            active_leaderboards[self.channel_id]['page'] = 1
            return await self.update_leaderboard_display(interaction)
        
        # Build embed
        embed = await build_leaderboard_embed(players, self.page, total_pages, offset)
        
        # Update button states
        self.previous_button.disabled = (self.page == 1)
        self.next_button.disabled = (self.page >= total_pages)
        
        # Update message
        try:
            await interaction.message.edit(embed=embed, view=self)
        except Exception as e:
            print(f"Error updating leaderboard: {e}")

async def build_leaderboard_embed(players, page: int, total_pages: int, offset: int):
    """Build the leaderboard embed - FSN style with rank change arrows"""
    if not players:
        embed = discord.Embed(
            title="VALM India Leaderboard",
            description="No registered players found!",
            color=0x2B2D31
        )
        embed.set_footer(text=f"Last updated")
        embed.timestamp = discord.utils.utcnow()
        return embed
    
    embed = discord.Embed(
        title="VALM India Leaderboard",
        color=0x2B2D31,
        description=""
    )
    
    # Build description with all players
    description_lines = []
    for idx, player in enumerate(players, start=offset + 1):
        current_rank = idx
        previous_rank = player.get('previous_rank')
        
        # Determine rank change arrow using custom Discord emoji
        if previous_rank is None:
            rank_indicator = ""  # New player, no arrow
        elif previous_rank > current_rank:
            rank_indicator = "<:upvote:1481558409718534306> "  # Rank improved (moved up, lower number = better)
        elif previous_rank < current_rank:
            rank_indicator = "<:downvote:1481558346438934578> "  # Rank decreased (moved down)
        else:
            rank_indicator = "➡️ "  # Rank stayed the same
        
        # Get player name
        player_name = player['player_ign'] or player['discord_username'] or f"User{player['user_id']}"
        
        # Format: rank. name - MMR
        mmr = player['mmr']
        line = f"{rank_indicator}**{idx:2d}.** {player_name:<20s} – **{mmr}**"
        description_lines.append(line)
    
    embed.description = "\n".join(description_lines)
    embed.set_footer(text=f"Last updated")
    embed.timestamp = discord.utils.utcnow()
    return embed

async def update_all_leaderboards():
    """Update all active leaderboard messages"""
    for channel_id, data in list(active_leaderboards.items()):
        try:
            message = data['message']
            page = data['page']
            
            # Calculate offset
            offset = (page - 1) * 10
            
            # Get players for current page
            players = await db.get_leaderboard_page(limit=10, offset=offset)
            total_players = await db.get_total_players()
            total_pages = max(1, (total_players + 9) // 10)
            
            # Build and update embed
            embed = await build_leaderboard_embed(players, page, total_pages, offset)
            view = LeaderboardView(channel_id, page)
            view.previous_button.disabled = (page == 1)
            view.next_button.disabled = (page >= total_pages)
            
            await message.edit(embed=embed, view=view)
        except discord.NotFound:
            print(f"Leaderboard message in channel {channel_id} was deleted, removing from tracking")
            # Remove from memory and database
            del active_leaderboards[channel_id]
            await db.delete_leaderboard(channel_id)
        except Exception as e:
            print(f"Error updating leaderboard in channel {channel_id}: {e}")
            # Remove broken leaderboard from memory and database
            del active_leaderboards[channel_id]
            await db.delete_leaderboard(channel_id)

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
            await self.load_persistent_leaderboards()
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
            
            # Create the queue embed with NeatQueue style
            embed = discord.Embed(
                title="VALM INDIA MATCHMAKING Queue",
                color=0xED4245  # Discord red
            )
            
            # Build queue display with proper spacing
            queue_text = f"**Queue {queue_count}/2**\n\n"
            
            # Add player mentions if any
            if queue:
                players_text = ", ".join([f"<@{player['user_id']}>" for player in queue])
                queue_text += f"{players_text}\n\n"
            
            # Add the queue field
            embed.add_field(
                name="",
                value=queue_text,
                inline=False
            )
            
            # Set the banner image
            embed.set_image(url="attachment://valm_india_banner.jpg")
            
            # Add timestamp
            embed.timestamp = discord.utils.utcnow()
            
            # Load the banner image
            banner_path = os.path.join(os.getcwd(), 'GFX', 'valm_india_banner.jpg')
            banner_file = discord.File(banner_path, filename='valm_india_banner.jpg')
            
            # Send the new message with the banner
            message = await channel.send(file=banner_file, embed=embed, view=self.queue_view)
            self.queue_view.message = message
            
            # Store the new message ID in database
            await db.set_config('queue_message_id', str(message.id))
            await db.set_config('queue_channel_id', str(self.queue_channel_id))
            
            # Start inactivity timer if there's exactly 1 player waiting
            if queue_count == 1:
                await self.queue_view.start_inactivity_timer(channel.id, channel.guild)
                print(f"⏰ Started inactivity timer for existing queue")
            
            print(f"✅ Queue UI setup in channel {channel.name} (ID: {self.queue_channel_id})")
            
        except Exception as e:
            print(f"❌ Failed to setup queue on startup: {e}")
    
    async def load_persistent_leaderboards(self):
        """Load all persistent leaderboards from database on bot startup"""
        try:
            # Wait a moment for bot to be fully ready
            await asyncio.sleep(1)
            
            # Get all leaderboards from database
            leaderboards = await db.get_all_leaderboards()
            
            if not leaderboards:
                print("ℹ️ No persistent leaderboards found")
                return
            
            loaded_count = 0
            for lb_data in leaderboards:
                try:
                    channel_id = lb_data['channel_id']
                    message_id = lb_data['message_id']
                    page = lb_data['page']
                    
                    # Get the channel
                    channel = self.bot.get_channel(channel_id)
                    if not channel:
                        print(f"⚠️ Leaderboard channel {channel_id} not found, removing from database")
                        await db.delete_leaderboard(channel_id)
                        continue
                    
                    # Fetch the message
                    try:
                        message = await channel.fetch_message(message_id)
                    except discord.NotFound:
                        print(f"⚠️ Leaderboard message {message_id} not found in channel {channel.name}, removing from database")
                        await db.delete_leaderboard(channel_id)
                        continue
                    
                    # Store in active leaderboards
                    active_leaderboards[channel_id] = {
                        'message': message,
                        'page': page
                    }
                    
                    # Update the leaderboard with fresh data
                    offset = (page - 1) * 10
                    players = await db.get_leaderboard_page(limit=10, offset=offset)
                    total_players = await db.get_total_players()
                    total_pages = max(1, (total_players + 9) // 10)
                    
                    embed = await build_leaderboard_embed(players, page, total_pages, offset)
                    view = LeaderboardView(channel_id, page)
                    view.previous_button.disabled = (page == 1)
                    view.next_button.disabled = (page >= total_pages)
                    
                    await message.edit(embed=embed, view=view)
                    
                    loaded_count += 1
                    print(f"✅ Loaded leaderboard in channel {channel.name} (page {page})")
                    
                except Exception as e:
                    print(f"❌ Error loading leaderboard for channel {channel_id}: {e}")
                    await db.delete_leaderboard(channel_id)
            
            if loaded_count > 0:
                print(f"✅ Successfully loaded {loaded_count} persistent leaderboard(s)")
        
        except Exception as e:
            print(f"❌ Failed to load persistent leaderboards: {e}")
    
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
        
        # Create the queue embed with NeatQueue style
        embed = discord.Embed(
            title="VALM INDIA MATCHMAKING Queue",
            color=0xED4245  # Discord red
        )
        
        # Build queue display with proper spacing
        queue_text = f"**Queue {queue_count}/2**\n\n"
        
        # Add player mentions if any
        if queue:
            players_text = ", ".join([f"<@{player['user_id']}>" for player in queue])
            queue_text += f"{players_text}\n\n"
        
        # Add the queue field
        embed.add_field(
            name="",
            value=queue_text,
            inline=False
        )
        
        # Set the banner image
        embed.set_image(url="attachment://valm_india_banner.jpg")
        
        # Add timestamp
        embed.timestamp = discord.utils.utcnow()
        
        # Load the banner image
        banner_path = os.path.join(os.getcwd(), 'GFX', 'valm_india_banner.jpg')
        banner_file = discord.File(banner_path, filename='valm_india_banner.jpg')
        
        # Send the message with buttons and banner
        await interaction.response.send_message(
            file=banner_file,
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
    
    @app_commands.command(name="ign", description="Register your in-game name")
    @app_commands.describe(player_ign="Your Valorant Mobile in-game name")
    async def register_ign(self, interaction: discord.Interaction, player_ign: str):
        """Register or update player's in-game name"""
        user_id = interaction.user.id
        discord_username = str(interaction.user)
        
        # Check if player is already registered
        is_registered = await db.is_player_registered(user_id)
        
        # Register or update player
        success, message = await db.register_player(user_id, discord_username, player_ign)
        
        if success:
            if is_registered:
                embed = discord.Embed(
                    title="IGN Updated",
                    description=f"Your in-game name has been updated to: **{player_ign}**",
                    color=0xED4245
                )
            else:
                embed = discord.Embed(
                    title="Registration Complete",
                    description=f"Welcome! Your in-game name has been registered as: **{player_ign}**\n\nYou can now participate in ranked matches and earn MMR!",
                    color=0x00FF00
                )
                embed.add_field(name="Starting Stats", value="MMR: 700\nGames: 0\nWins: 0\nLosses: 0", inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Assign initial rank role for new players (starting MMR is 700 = Iron)
            if not is_registered:
                await update_player_rank_role(interaction.guild, user_id, 700)
            
            # Update all active leaderboards to show new player
            await update_all_leaderboards()
        else:
            await interaction.response.send_message(
                f"❌ Registration failed: {message}",
                ephemeral=True
            )
    
    @app_commands.command(name="admin-set-ign", description="[Admin] Set or update a player's in-game name")
    @app_commands.describe(
        player="The player to set IGN for",
        ign="The in-game name to set"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def admin_set_ign(self, interaction: discord.Interaction, player: discord.Member, ign: str):
        """Admin command to set or update any player's IGN"""
        await interaction.response.defer(ephemeral=True)
        
        user_id = player.id
        discord_username = str(player)
        
        # Check if player is already registered
        is_registered = await db.is_player_registered(user_id)
        
        # Register or update player
        success, message = await db.register_player(user_id, discord_username, ign)
        
        if success:
            if is_registered:
                embed = discord.Embed(
                    title="✅ IGN Updated",
                    description=f"{player.mention}'s in-game name has been updated to: **{ign}**",
                    color=0xED4245
                )
            else:
                embed = discord.Embed(
                    title="✅ Player Registered",
                    description=f"{player.mention} has been registered with IGN: **{ign}**",
                    color=0x00FF00
                )
                embed.add_field(name="Starting Stats", value="MMR: 700\nGames: 0\nWins: 0\nLosses: 0", inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Assign initial rank role for new players (starting MMR is 700 = Iron)
            if not is_registered:
                await update_player_rank_role(interaction.guild, user_id, 700)
            
            # Update all active leaderboards to show new/updated player
            await update_all_leaderboards()
        else:
            await interaction.followup.send(
                f"❌ Failed to set IGN: {message}",
                ephemeral=True
            )
    
    @app_commands.command(name="test-ocr", description="Test OCR on a Valorant Mobile scoreboard screenshot")
    async def test_ocr(self, interaction: discord.Interaction):
        """Test OCR functionality on a screenshot without updating stats"""
        if not OCR_AVAILABLE:
            await interaction.response.send_message(
                "❌ **OCR feature is not available!**\n\n"
                "OCR dependencies are not installed on this server.\n"
                "Required: `pip install google-generativeai Pillow`",
                ephemeral=True
            )
            return
        
        await interaction.response.send_message(
            "📸 **Upload a Valorant Mobile scoreboard screenshot**\n\n"
            "You have **2 minutes** to upload the screenshot.\n"
            "I'll analyze it and show you what data I can extract.",
            ephemeral=True
        )
        
        # Wait for image upload
        def check(m):
            return (
                m.channel.id == interaction.channel_id and
                m.author.id == interaction.user.id and
                len(m.attachments) > 0 and
                m.attachments[0].content_type and
                m.attachments[0].content_type.startswith('image/')
            )
        
        try:
            msg = await self.bot.wait_for('message', check=check, timeout=120)
            attachment = msg.attachments[0]
            
            # Process the screenshot
            await interaction.followup.send("⏳ Processing screenshot...", ephemeral=True)
            
            try:
                # Download image
                image_data = await attachment.read()
                
                # Convert to PIL Image
                import io
                from PIL import Image
                image = Image.open(io.BytesIO(image_data))
                
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                # Convert to base64
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format='PNG')
                img_byte_arr = img_byte_arr.getvalue()
                image_b64 = base64.b64encode(img_byte_arr).decode('utf-8')
                
                # Use Gemini API
                prompt = """Analyze this Valorant Mobile match scoreboard screenshot and extract the player information.

The scoreboard has TWO players:
- TOP player: Has a YELLOW/GREEN/GOLD colored background (displayed at the top)
- BOTTOM player: Has a RED colored background (displayed at the bottom)

For each player, find:
1. Their IGN/username
2. Their score (the large number shown next to their name)

IMPORTANT: Report the EXACT scores as displayed. Do NOT swap or assume which score is higher.

Return ONLY in this exact format:
TOP_PLAYER: [name of player with yellow/green background at top]
TOP_SCORE: [exact score number for top player]
BOTTOM_PLAYER: [name of player with red background at bottom]
BOTTOM_SCORE: [exact score number for bottom player]

Example:
TOP_PLAYER: aimboss
TOP_SCORE: 10
BOTTOM_PLAYER: MatarPaneer
BOTTOM_SCORE: 8"""
                
                api_key = os.getenv('GEMINI_API_KEY')
                url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={api_key}"
                
                payload = {
                    "contents": [{
                        "parts": [
                            {"text": prompt},
                            {
                                "inline_data": {
                                    "mime_type": "image/png",
                                    "data": image_b64
                                }
                            }
                        ]
                    }]
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload) as resp:
                        if resp.status != 200:
                            error_text = await resp.text()
                            raise ValueError(f"API Error: {error_text}")
                        
                        result = await resp.json()
                        result_text = result['candidates'][0]['content']['parts'][0]['text']
                
                # Parse the response
                top_player_match = re.search(r'TOP_PLAYER:\s*(.+)', result_text, re.IGNORECASE)
                top_score_match = re.search(r'TOP_SCORE:\s*(\d+)', result_text, re.IGNORECASE)
                bottom_player_match = re.search(r'BOTTOM_PLAYER:\s*(.+)', result_text, re.IGNORECASE)
                bottom_score_match = re.search(r'BOTTOM_SCORE:\s*(\d+)', result_text, re.IGNORECASE)
                
                if not all([top_player_match, top_score_match, bottom_player_match, bottom_score_match]):
                    await interaction.followup.send(
                        f"❌ **Could not parse OCR results**\n\n"
                        f"Raw API response:\n```\n{result_text}\n```",
                        ephemeral=True
                    )
                    return
                
                top_player = top_player_match.group(1).strip()
                top_score = int(top_score_match.group(1))
                bottom_player = bottom_player_match.group(1).strip()
                bottom_score = int(bottom_score_match.group(1))
                
                # Determine winner
                winner_ign = top_player if top_score > bottom_score else bottom_player
                loser_ign = bottom_player if top_score > bottom_score else top_player
                winner_score = max(top_score, bottom_score)
                loser_score = min(top_score, bottom_score)
                
                # Show results
                result_embed = discord.Embed(
                    title="🔍 OCR Test Results",
                    description=f"Successfully extracted match data from screenshot!",
                    color=0x00FF00
                )
                result_embed.add_field(
                    name="📊 Extracted Data",
                    value=f"**Top Player (Yellow/Green):** {top_player} - {top_score}\n"
                          f"**Bottom Player (Red):** {bottom_player} - {bottom_score}",
                    inline=False
                )
                result_embed.add_field(
                    name="🏆 Calculated Result",
                    value=f"**Winner:** {winner_ign} ({winner_score})\n"
                          f"**Loser:** {loser_ign} ({loser_score})",
                    inline=False
                )
                result_embed.add_field(
                    name="💡 Database Lookup",
                    value=f"Checking if these IGNs are registered...",
                    inline=False
                )
                result_embed.set_image(url=attachment.url)
                
                await interaction.followup.send(embed=result_embed, ephemeral=True)
                
                # Check database
                winner_profile = await db.get_player_by_ign(winner_ign)
                loser_profile = await db.get_player_by_ign(loser_ign)
                
                db_status = ""
                if winner_profile:
                    winner_user = interaction.guild.get_member(winner_profile['user_id'])
                    db_status += f"✅ Winner '{winner_ign}' → {winner_user.mention if winner_user else 'User not in server'}\n"
                else:
                    db_status += f"❌ Winner '{winner_ign}' not registered\n"
                
                if loser_profile:
                    loser_user = interaction.guild.get_member(loser_profile['user_id'])
                    db_status += f"✅ Loser '{loser_ign}' → {loser_user.mention if loser_user else 'User not in server'}\n"
                else:
                    db_status += f"❌ Loser '{loser_ign}' not registered\n"
                
                await interaction.followup.send(f"**Database Status:**\n{db_status}", ephemeral=True)
                
            except Exception as e:
                await interaction.followup.send(
                    f"❌ **Error processing screenshot:**\n```\n{str(e)}\n```",
                    ephemeral=True
                )
        
        except asyncio.TimeoutError:
            await interaction.followup.send(
                "⏰ **Timeout!** You didn't upload a screenshot in 2 minutes.",
                ephemeral=True
            )
    
    @app_commands.command(name="test-result", description="Test the queue-results channel with a screenshot (admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def test_result(self, interaction: discord.Interaction):
        """Test command to post a result to queue-results channel"""
        # Check if OCR is available
        if not OCR_AVAILABLE:
            await interaction.response.send_message(
                "❌ **OCR feature is not available!**\n\n"
                "OCR dependencies are not installed on this server.\n"
                "Required: `pip install google-generativeai Pillow`",
                ephemeral=True
            )
            return
        
        # Check if results channel is configured
        results_channel_id = os.getenv('QUEUE_RESULTS_CHANNEL_ID')
        if not results_channel_id:
            await interaction.response.send_message(
                "❌ **QUEUE_RESULTS_CHANNEL_ID not configured!**\n\n"
                "Please add `QUEUE_RESULTS_CHANNEL_ID=<channel_id>` to your .env file and restart the bot.",
                ephemeral=True
            )
            return
        
        results_channel = interaction.guild.get_channel(int(results_channel_id))
        if not results_channel:
            await interaction.response.send_message(
                "❌ **Queue results channel not found!**\n\n"
                "Please check your QUEUE_RESULTS_CHANNEL_ID configuration.",
                ephemeral=True
            )
            return
        
        await interaction.response.send_message(
            "📸 **Please upload your screenshot now!**\n\nYou have **2 minutes** to upload the final scoreboard screenshot.\n\nJust send the image in this channel.",
            ephemeral=True
        )
        
        # Wait for image upload
        def check(m):
            return (
                m.channel.id == interaction.channel_id and
                m.author.id == interaction.user.id and
                len(m.attachments) > 0 and
                m.attachments[0].content_type and
                m.attachments[0].content_type.startswith('image/')
            )
        
        try:
            msg = await self.bot.wait_for('message', check=check, timeout=120)
            attachment = msg.attachments[0]
            
            # Process with OCR
            await interaction.followup.send("⏳ Processing screenshot...", ephemeral=True)
            
            try:
                # Download image
                image_data = await attachment.read()
                
                # Convert to PIL Image and process
                import io
                from PIL import Image
                image = Image.open(io.BytesIO(image_data))
                
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                # Convert to base64
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format='PNG')
                img_byte_arr = img_byte_arr.getvalue()
                image_b64 = base64.b64encode(img_byte_arr).decode('utf-8')
                
                prompt = """Analyze this Valorant Mobile match scoreboard screenshot and extract the player information.

The scoreboard has TWO players:
- TOP player: Has a YELLOW/GREEN/GOLD colored background (displayed at the top)
- BOTTOM player: Has a RED colored background (displayed at the bottom)

For each player, find:
1. Their IGN/username
2. Their score (the large number shown next to their name)

IMPORTANT: Report the EXACT scores as displayed. Do NOT swap or assume which score is higher.

Return ONLY in this exact format:
TOP_PLAYER: [name of player with yellow/green background at top]
TOP_SCORE: [exact score number for top player]
BOTTOM_PLAYER: [name of player with red background at bottom]
BOTTOM_SCORE: [exact score number for bottom player]

Example:
TOP_PLAYER: aimboss
TOP_SCORE: 10
BOTTOM_PLAYER: MatarPaneer
BOTTOM_SCORE: 8"""
                
                # Call Gemini API
                api_key = os.getenv('GEMINI_API_KEY')
                url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={api_key}"
                
                payload = {
                    "contents": [{
                        "parts": [
                            {"text": prompt},
                            {
                                "inline_data": {
                                    "mime_type": "image/png",
                                    "data": image_b64
                                }
                            }
                        ]
                    }]
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload) as resp:
                        if resp.status != 200:
                            raise Exception(f"Gemini API error: {resp.status}")
                        
                        result = await resp.json()
                        result_text = result['candidates'][0]['content']['parts'][0]['text']
                
                # Parse response
                top_player_match = re.search(r'TOP_PLAYER:\s*(.+)', result_text, re.IGNORECASE)
                top_score_match = re.search(r'TOP_SCORE:\s*(\d+)', result_text, re.IGNORECASE)
                bottom_player_match = re.search(r'BOTTOM_PLAYER:\s*(.+)', result_text, re.IGNORECASE)
                bottom_score_match = re.search(r'BOTTOM_SCORE:\s*(\d+)', result_text, re.IGNORECASE)
                
                if not all([top_player_match, top_score_match, bottom_player_match, bottom_score_match]):
                    raise ValueError("Could not extract match data from screenshot")
                
                top_player = top_player_match.group(1).strip()
                top_score = int(top_score_match.group(1))
                bottom_player = bottom_player_match.group(1).strip()
                bottom_score = int(bottom_score_match.group(1))
                
                # Determine winner
                winner_ign = top_player if top_score > bottom_score else bottom_player
                loser_ign = bottom_player if top_score > bottom_score else top_player
                winner_score = max(top_score, bottom_score)
                loser_score = min(top_score, bottom_score)
                
                # Look up in database
                winner_profile = await db.get_player_by_ign(winner_ign)
                loser_profile = await db.get_player_by_ign(loser_ign)
                
                winner_user = None
                loser_user = None
                winner_stats = None
                loser_stats = None
                
                if winner_profile:
                    winner_user = interaction.guild.get_member(winner_profile['user_id'])
                    winner_stats = winner_profile
                
                if loser_profile:
                    loser_user = interaction.guild.get_member(loser_profile['user_id'])
                    loser_stats = loser_profile
                
                # Create test result embed
                test_match_number = 9999
                result_embed = discord.Embed(
                    title=f"🏆 Winner For Queue#{test_match_number:04d} 🏆 [TEST]",
                    color=0xFFD700
                )
                
                # Winner field
                winner_mention = winner_user.mention if winner_user else f"@{winner_ign}"
                result_embed.add_field(
                    name=f"**{winner_ign}**",
                    value=f"{winner_mention}\n**Score:** {winner_score}",
                    inline=True
                )
                
                # Loser field
                loser_mention = loser_user.mention if loser_user else f"@{loser_ign}"
                result_embed.add_field(
                    name=f"**{loser_ign}**",
                    value=f"{loser_mention}\n**Score:** {loser_score}",
                    inline=True
                )
                
                # MMR info (if available)
                if winner_stats and loser_stats:
                    result_embed.add_field(
                        name="📊 MMR Changes",
                        value=(
                            f"**{winner_mention}:** {winner_stats['mmr']:,} → **{winner_stats['mmr']+32:,}** (+32)\n"
                            f"**{loser_mention}:** {loser_stats['mmr']:,} → **{loser_stats['mmr']-27:,}** (-27)"
                        ),
                        inline=False
                    )
                else:
                    result_embed.add_field(
                        name="📊 MMR Changes",
                        value="*Players not registered - MMR changes not available*",
                        inline=False
                    )
                
                result_embed.set_image(url=attachment.url)
                result_embed.timestamp = discord.utils.utcnow()
                result_embed.set_footer(text="🧪 TEST RESULT - No stats affected | Vote for MVP below!")
                
                # Create MVP view
                mvp_view = MVPView(
                    f"test_{interaction.id}",
                    winner_user.id if winner_user else 0,
                    winner_ign,
                    loser_user.id if loser_user else 0,
                    loser_ign,
                    self.bot
                )
                
                # Post to results channel
                result_message = await results_channel.send(embed=result_embed, view=mvp_view)
                mvp_view.message = result_message
                
                await interaction.followup.send(
                    f"✅ **Test result posted to {results_channel.mention}!**\n\n"
                    f"**Winner:** {winner_ign} ({winner_score})\n"
                    f"**Loser:** {loser_ign} ({loser_score})\n\n"
                    f"*Note: This is a test - no stats were updated.*",
                    ephemeral=True
                )
                
            except Exception as e:
                await interaction.followup.send(
                    f"❌ **Error processing screenshot:**\n```\n{str(e)}\n```",
                    ephemeral=True
                )
        
        except asyncio.TimeoutError:
            await interaction.followup.send(
                "⏰ **Timeout!** You didn't upload a screenshot in 2 minutes.",
                ephemeral=True
            )
    
    @app_commands.command(name="cancel", description="Vote to cancel the current match")
    async def cancel_match(self, interaction: discord.Interaction):
        """Initiate a vote to cancel the current match"""
        user_id = interaction.user.id
        
        # Find which match the user is in
        match_found = None
        text_channel_id = None
        
        for channel_id, match_data in active_matches.items():
            if user_id in [match_data['player1'].id, match_data['player2'].id]:
                match_found = match_data
                text_channel_id = channel_id
                break
        
        if not match_found:
            await interaction.response.send_message("❌ You are not in an active match!", ephemeral=True)
            return
        
        # Check if they're in the match channel
        if interaction.channel_id != text_channel_id:
            await interaction.response.send_message("❌ You can only use this command in your match channel!", ephemeral=True)
            return
        
        # Create cancel vote data
        cancel_data = {
            'player1': match_found['player1'],
            'player2': match_found['player2'],
            'yes_votes': 0,
            'no_votes': 0,
            'voters': set(),
            'text_channel_id': text_channel_id,
            'voice_channel_id': match_found['voice_channel'].id
        }
        
        # Create and send the vote UI
        view = CancelView(self.bot, cancel_data)
        
        embed = discord.Embed(
            title="⚠️ Match Cancellation Vote",
            description=f"{interaction.user.mention} wants to cancel this match!\n\n**Yes Votes:** 0\n**No Votes:** 0\n\nBoth players can vote. You have 60 seconds.",
            color=0xFF0000
        )
        embed.set_footer(text="Vote ends in 60 seconds or when both players vote")
        
        await interaction.response.send_message(embed=embed, view=view)
        
        # Store message reference for updates
        message = await interaction.original_response()
        view.message = message
    
    @app_commands.command(name="sub-request", description="Request a substitute player for your match")
    @app_commands.describe(player="The player you want to substitute in")
    async def sub_request(self, interaction: discord.Interaction, player: discord.Member):
        """Request a substitute player to take your place in the match"""
        user_id = interaction.user.id
        
        # Check if the player mentioning themselves
        if player.id == user_id:
            await interaction.response.send_message("❌ You cannot substitute yourself!", ephemeral=True)
            return
        
        # Check if the substitute is a bot
        if player.bot:
            await interaction.response.send_message("❌ You cannot substitute a bot!", ephemeral=True)
            return
        
        # Find which match the user is in
        match_found = None
        text_channel_id = None
        
        for channel_id, match_data in active_matches.items():
            if user_id in [match_data['player1'].id, match_data['player2'].id]:
                match_found = match_data
                text_channel_id = channel_id
                break
        
        if not match_found:
            await interaction.response.send_message("❌ You are not in an active match!", ephemeral=True)
            return
        
        # Check if they're in the match channel
        if interaction.channel_id != text_channel_id:
            await interaction.response.send_message("❌ You can only use this command in your match channel!", ephemeral=True)
            return
        
        # Check if the substitute is already in a match
        for channel_id, match_data in active_matches.items():
            if player.id in [match_data['player1'].id, match_data['player2'].id]:
                await interaction.response.send_message("❌ That player is already in an active match!", ephemeral=True)
                return
        
        await interaction.response.defer()
        
        text_channel = match_found['text_channel']
        voice_channel = match_found['voice_channel']
        original_player = interaction.user
        
        # Give substitute access to the match channel
        await text_channel.set_permissions(player, read_messages=True, send_messages=True)
        
        # Create unique request ID
        request_id = f"{text_channel_id}_{player.id}_{int(datetime.utcnow().timestamp())}"
        
        # Create sub request embed
        request_embed = discord.Embed(
            title="🔄 Substitute Request",
            description=f"{original_player.mention} has requested you to substitute in their match!\n\n"
                       f"**Match:** #{match_found['match_number']:04d}\n"
                       f"**Opponent:** {match_found['player2'].mention if match_found['player1'].id == user_id else match_found['player1'].mention}\n\n"
                       f"Do you want to sub in?",
            color=0x5865F2
        )
        request_embed.set_footer(text="You have 5 minutes to respond")
        
        # Create view
        view = SubRequestView(request_id)
        
        # Send to DM
        dm_message = None
        try:
            dm_message = await player.send(embed=request_embed, view=view)
        except discord.Forbidden:
            await interaction.followup.send(
                f"❌ Could not send DM to {player.mention}. They may have DMs disabled.",
                ephemeral=True
            )
            await text_channel.set_permissions(player, overwrite=None)
            return
        
        # Send to channel
        channel_message = await text_channel.send(
            content=player.mention,
            embed=request_embed,
            view=view
        )
        
        # Store request data
        active_sub_requests[request_id] = {
            'original_player': original_player,
            'substitute': player,
            'match_data': match_found,
            'text_channel': text_channel,
            'voice_channel': voice_channel,
            'dm_message': dm_message,
            'channel_message': channel_message
        }
        
        await interaction.followup.send(
            f"✅ Sub request sent to {player.mention}! They can accept from either DM or this channel.",
            ephemeral=True
        )
    
    @app_commands.command(name="ping", description="Check bot latency or ping players not in VC")
    async def ping(self, interaction: discord.Interaction):
        """Context-aware ping: shows bot latency or pings players not in VC"""
        user_id = interaction.user.id
        
        # Check if this is a match channel
        match_found = None
        text_channel_id = None
        
        for channel_id, match_data in active_matches.items():
            if channel_id == interaction.channel_id:
                match_found = match_data
                text_channel_id = channel_id
                break
        
        # If in a match channel and user is a player
        if match_found and user_id in [match_found['player1'].id, match_found['player2'].id]:
            # Get the voice channel
            guild = interaction.guild
            voice_channel = guild.get_channel(match_found['voice_channel'].id)
            
            if not voice_channel:
                await interaction.response.send_message("❌ Voice channel not found!", ephemeral=True)
                return
            
            # Check who's in VC
            members_in_vc = voice_channel.members
            player1 = match_found['player1']
            player2 = match_found['player2']
            
            # Find who's NOT in VC
            not_in_vc = []
            if player1 not in members_in_vc:
                not_in_vc.append(player1)
            if player2 not in members_in_vc:
                not_in_vc.append(player2)
            
            if not not_in_vc:
                # Everyone is in VC
                await interaction.response.send_message("✅ All players are already in the voice channel!", ephemeral=True)
            else:
                # Ping players not in VC
                mentions = " ".join([player.mention for player in not_in_vc])
                embed = discord.Embed(
                    title="🔔 Voice Channel Reminder",
                    description=f"Please join {voice_channel.mention} to proceed with the match!",
                    color=0xFF0000
                )
                embed.set_footer(text=f"Reminder sent by {interaction.user.display_name}")
                
                # Send mentions in content (not embed) to trigger notifications
                await interaction.response.send_message(content=mentions, embed=embed)
        else:
            # Not in a match channel - show bot latency
            import time
            api_latency = round(self.bot.latency * 1000, 2)
            
            # Calculate uptime
            uptime_seconds = int(time.time() - self.bot.start_time)
            uptime_hours = uptime_seconds // 3600
            uptime_minutes = (uptime_seconds % 3600) // 60
            uptime_secs = uptime_seconds % 60
            
            # Create embed
            embed = discord.Embed(
                title="🏓 Pong!",
                description="Bot latency and status information",
                color=discord.Color.green()
            )
            embed.add_field(name="API Latency", value=f"`{api_latency}ms`", inline=True)
            embed.add_field(name="Uptime", value=f"`{uptime_hours}h {uptime_minutes}m {uptime_secs}s`", inline=True)
            embed.set_footer(text=f"Requested by {interaction.user.name}")
            
            await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="leaderboard", description="View the top players by MMR")
    async def leaderboard(self, interaction: discord.Interaction):
        """Show the leaderboard with top players ranked by MMR"""
        await interaction.response.defer()
        
        # Get top 10 players
        top_players = await db.get_leaderboard(limit=10)
        
        if not top_players:
            embed = discord.Embed(
                title="📊 Leaderboard",
                description="No players have played any matches yet!",
                color=0xFFD700
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Build leaderboard embed
        embed = discord.Embed(
            title="🏆 Skrimmish Leaderboard - Top 10",
            description="Ranked by MMR",
            color=0xFFD700
        )
        
        # Add players to embed
        for idx, player in enumerate(top_players, start=1):
            # Get rank emoji
            if idx == 1:
                rank_emoji = "🥇"
            elif idx == 2:
                rank_emoji = "🥈"
            elif idx == 3:
                rank_emoji = "🥉"
            else:
                rank_emoji = f"`#{idx}`"
            
            # Get streak emoji
            streak = player['streak']
            if streak > 0:
                streak_display = f"🔥 {streak}W"
            elif streak < 0:
                streak_display = f"❄️ {abs(streak)}L"
            else:
                streak_display = "➖"
            
            # Format player info
            player_name = player['discord_username'] or f"<@{player['user_id']}>"
            ign = player['player_ign']
            mmr = player['mmr']
            wins = player['wins']
            losses = player['losses']
            winrate = player['winrate']
            mvp_count = player.get('mvp_count', 0)
            
            mvp_display = f" | **MVPs:** 🏆 {mvp_count}" if mvp_count > 0 else ""
            
            embed.add_field(
                name=f"{rank_emoji} {player_name}",
                value=f"**IGN:** {ign}\n"
                      f"**MMR:** {mmr:,} | **W/L:** {wins}-{losses} ({winrate:.1f}%){mvp_display}\n"
                      f"**Streak:** {streak_display}",
                inline=False
            )
        
        embed.set_footer(text=f"Requested by {interaction.user.display_name}")
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="skrimmish-leaderboard", description="Create a persistent auto-updating leaderboard in this channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def skrimmish_leaderboard(self, interaction: discord.Interaction):
        """Create a persistent leaderboard that auto-updates when stats change"""
        await interaction.response.defer()
        
        channel_id = interaction.channel_id
        
        # Check if leaderboard already exists in this channel
        if channel_id in active_leaderboards:
            await interaction.followup.send(
                "⚠️ A leaderboard already exists in this channel! Delete the old message first.",
                ephemeral=True
            )
            return
        
        # Get first page of players
        players = await db.get_leaderboard_page(limit=10, offset=0)
        total_players = await db.get_total_players()
        total_pages = max(1, (total_players + 9) // 10)
        
        # Build embed
        embed = await build_leaderboard_embed(players, 1, total_pages, 0)
        
        # Create view
        view = LeaderboardView(channel_id, page=1)
        view.previous_button.disabled = True
        view.next_button.disabled = (total_pages == 1)
        
        # Send message
        message = await interaction.channel.send(embed=embed, view=view)
        
        # Store in active leaderboards
        active_leaderboards[channel_id] = {
            'message': message,
            'page': 1
        }
        
        # Save to database for persistence
        await db.save_leaderboard(channel_id, message.id, 1)
        
        await interaction.followup.send(
            "✅ Leaderboard created! It will automatically update when player stats change.",
            ephemeral=True
        )
    
    @app_commands.command(name="reset-leaderboard", description="Reset all player stats to 0 (CAUTION: Cannot be undone!)")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_leaderboard(self, interaction: discord.Interaction):
        """Reset all player stats to default values"""
        await interaction.response.defer(ephemeral=True)
        
        # Reset all player stats
        reset_count = await db.reset_all_player_stats()
        
        # Update rank tracking before refreshing leaderboards
        await db.update_all_ranks()
        
        # Update all active leaderboards
        await update_all_leaderboards()
        
        await interaction.followup.send(
            f"✅ Successfully reset stats for {reset_count} players!\n"
            f"All players now have:\n"
            f"• MMR: 700\n"
            f"• Wins: 0\n"
            f"• Losses: 0\n"
            f"• Games: 0\n"
            f"• Streak: 0",
            ephemeral=True
        )
    
    # Autoping command group
    autoping_group = app_commands.Group(name="autoping", description="Configure automatic role pings when players join queue")
    
    @autoping_group.command(name="set", description="Set up auto-ping for queue joins")
    @app_commands.describe(
        role="The role to ping",
        size="How many times to repeat the ping (1-10)",
        delete_after="Delete the ping after this many seconds (0 = don't delete)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def autoping_set(self, interaction: discord.Interaction, role: discord.Role, size: int, delete_after: int):
        """Set up auto-ping configuration"""
        # Validate inputs
        if size < 1 or size > 10:
            await interaction.response.send_message("❌ Size must be between 1 and 10!", ephemeral=True)
            return
        
        if delete_after < 0:
            await interaction.response.send_message("❌ Delete_after must be 0 or positive!", ephemeral=True)
            return
        
        # Save configuration
        await db.set_autoping(interaction.channel_id, role.id, size, delete_after)
        
        embed = discord.Embed(
            title="✅ Auto-Ping Configured",
            description=f"When players join the queue in this channel:",
            color=0x00FF00
        )
        embed.add_field(name="Role", value=role.mention, inline=False)
        embed.add_field(name="Repeat Count", value=f"{size}x", inline=True)
        embed.add_field(name="Delete After", value=f"{delete_after}s" if delete_after > 0 else "Never", inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @autoping_group.command(name="remove", description="Remove auto-ping configuration")
    @app_commands.checks.has_permissions(administrator=True)
    async def autoping_remove(self, interaction: discord.Interaction):
        """Remove auto-ping configuration"""
        await db.remove_autoping(interaction.channel_id)
        
        embed = discord.Embed(
            title="✅ Auto-Ping Removed",
            description="Auto-ping has been disabled for this channel.",
            color=0x00FF00
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @autoping_group.command(name="status", description="View current auto-ping configuration")
    async def autoping_status(self, interaction: discord.Interaction):
        """View auto-ping configuration"""
        config = await db.get_autoping(interaction.channel_id)
        
        if not config:
            await interaction.response.send_message(
                "❌ No auto-ping configured for this channel!",
                ephemeral=True
            )
            return
        
        role = interaction.guild.get_role(config['role_id'])
        
        embed = discord.Embed(
            title="📊 Auto-Ping Status",
            description="Current configuration for this channel:",
            color=0xED4245
        )
        embed.add_field(name="Role", value=role.mention if role else "Role not found", inline=False)
        embed.add_field(name="Repeat Count", value=f"{config['size']}x", inline=True)
        embed.add_field(name="Delete After", value=f"{config['delete_after']}s" if config['delete_after'] > 0 else "Never", inline=True)
        embed.add_field(name="Trigger", value="Pings when queue has 1 player (1 more needed)", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    # MMR command group
    mmr_group = app_commands.Group(name="mmr", description="Manage player MMR (admin only)")
    
    @mmr_group.command(name="add", description="Add MMR to a player")
    @app_commands.describe(
        player="The player to add MMR to",
        value="Amount of MMR to add"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def mmr_add(self, interaction: discord.Interaction, player: discord.Member, value: int):
        """Add MMR to a player"""
        # Check if value is positive
        if value <= 0:
            await interaction.response.send_message("❌ Value must be positive!", ephemeral=True)
            return
        
        # Check if player is registered
        is_registered = await db.is_player_registered(player.id)
        if not is_registered:
            await interaction.response.send_message(
                f"❌ {player.mention} is not registered! They need to use `/ign` first.",
                ephemeral=True
            )
            return
        
        # Update MMR
        new_mmr = await db.update_player_mmr(player.id, value)
        
        embed = discord.Embed(
            title="✅ MMR Added",
            description=f"Added **{value}** MMR to {player.mention}",
            color=0x00FF00
        )
        embed.add_field(name="New MMR", value=f"{new_mmr}", inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @mmr_group.command(name="subtract", description="Subtract MMR from a player")
    @app_commands.describe(
        player="The player to subtract MMR from",
        value="Amount of MMR to subtract"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def mmr_subtract(self, interaction: discord.Interaction, player: discord.Member, value: int):
        """Subtract MMR from a player"""
        # Check if value is positive
        if value <= 0:
            await interaction.response.send_message("❌ Value must be positive!", ephemeral=True)
            return
        
        # Check if player is registered
        is_registered = await db.is_player_registered(player.id)
        if not is_registered:
            await interaction.response.send_message(
                f"❌ {player.mention} is not registered! They need to use `/ign` first.",
                ephemeral=True
            )
            return
        
        # Update MMR (negative value)
        new_mmr = await db.update_player_mmr(player.id, -value)
        
        embed = discord.Embed(
            title="✅ MMR Subtracted",
            description=f"Subtracted **{value}** MMR from {player.mention}",
            color=0xED4245
        )
        embed.add_field(name="New MMR", value=f"{new_mmr}", inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    # Player command group
    player_group = app_commands.Group(name="player", description="Player management commands (admin only)")
    
    @player_group.command(name="sub", description="Substitute a player in an active match")
    @app_commands.describe(
        player_out="The player to substitute out",
        player_in="The player to substitute in"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def player_sub(self, interaction: discord.Interaction, player_out: discord.Member, player_in: discord.Member):
        """Substitute a player in an active match"""
        # Check if this is a match channel
        match_data = active_matches.get(interaction.channel_id)
        
        if not match_data:
            await interaction.response.send_message(
                "❌ This command can only be used in an active match channel!",
                ephemeral=True
            )
            return
        
        # Check if player_out is actually in this match
        player1 = match_data['player1']
        player2 = match_data['player2']
        
        if player_out.id not in [player1.id, player2.id]:
            await interaction.response.send_message(
                f"❌ {player_out.mention} is not in this match!",
                ephemeral=True
            )
            return
        
        # Check if player_in is already in the match
        if player_in.id in [player1.id, player2.id]:
            await interaction.response.send_message(
                f"❌ {player_in.mention} is already in this match!",
                ephemeral=True
            )
            return
        
        # Get channels
        text_channel = match_data['text_channel']
        voice_channel = match_data['voice_channel']
        guild = interaction.guild
        
        # Update channel permissions
        # Remove permissions from player_out
        await text_channel.set_permissions(player_out, overwrite=None)
        await voice_channel.set_permissions(player_out, overwrite=None)
        
        # Add permissions for player_in
        overwrites = discord.PermissionOverwrite(
            read_messages=True,
            send_messages=True,
            view_channel=True,
            connect=True,
            speak=True
        )
        await text_channel.set_permissions(player_in, overwrite=overwrites)
        await voice_channel.set_permissions(player_in, overwrite=overwrites)
        
        # Update match_data
        if player_out.id == player1.id:
            match_data['player1'] = player_in
            old_team = match_data['team1_name']
            match_data['team1_name'] = str(player_in.display_name)
        else:
            match_data['player2'] = player_in
            old_team = match_data['team2_name']
            match_data['team2_name'] = str(player_in.display_name)
        
        # Update votes dictionary keys (rename the team)
        if old_team in match_data['votes']:
            new_team = str(player_in.display_name)
            match_data['votes'][new_team] = match_data['votes'].pop(old_team)
        
        # Update the initial match message with new players
        if 'initial_message' in match_data:
            initial_message = match_data['initial_message']
            new_player1 = match_data['player1']
            new_player2 = match_data['player2']
            match_number = match_data['match_number']
            
            updated_embed = discord.Embed(
                title=f"Scrimmish Match #{match_number:04d}",
                description=f"{new_player1.mention} vs {new_player2.mention}\n\nPlease join {voice_channel.mention} within 5 minutes to proceed.",
                color=0xED4245
            )
            updated_embed.set_footer(text="Match will be cancelled if both players don't join within 5 minutes")
            
            try:
                await initial_message.edit(
                    content=f"{new_player1.mention} {new_player2.mention}",
                    embed=updated_embed
                )
            except:
                pass  # Message might be deleted or inaccessible
        
        # Send substitution notification
        embed = discord.Embed(
            title="🔄 Player Substitution",
            description=f"{player_out.mention} has been subbed out\n{player_in.mention} has been subbed in",
            color=0xED4245
        )
        embed.set_footer(text=f"Substitution by {interaction.user.display_name}")
        
        await interaction.response.send_message(
            content=f"{player_out.mention} {player_in.mention}",
            embed=embed
        )

async def setup(bot):
    await bot.add_cog(SkrimmishCog(bot))
