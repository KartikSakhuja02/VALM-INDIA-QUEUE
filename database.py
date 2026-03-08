import asyncpg
import os
from typing import Optional

class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Create a connection pool to the database"""
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            raise ValueError("DATABASE_URL not found in environment variables")
        
        self.pool = await asyncpg.create_pool(
            database_url,
            min_size=2,
            max_size=10,
            command_timeout=60
        )
        print("✅ Database connection pool created")
    
    async def disconnect(self):
        """Close the database connection pool"""
        if self.pool:
            await self.pool.close()
            print("❌ Database connection pool closed")
    
    async def initialize_schema(self):
        """Initialize database schema"""
        async with self.pool.acquire() as conn:
            # Create bot_config table for storing bot settings
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS bot_config (
                    key VARCHAR(255) PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create skrimmish_queue table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS skrimmish_queue (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT UNIQUE NOT NULL,
                    username VARCHAR(255) NOT NULL,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    valorant_ign VARCHAR(255),
                    rank VARCHAR(50)
                )
            ''')
            
            # Create skrimmish_matches table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS skrimmish_matches (
                    id SERIAL PRIMARY KEY,
                    player1_id BIGINT NOT NULL,
                    player2_id BIGINT NOT NULL,
                    player1_username VARCHAR(255) NOT NULL,
                    player2_username VARCHAR(255) NOT NULL,
                    match_status VARCHAR(50) DEFAULT 'pending',
                    winner_id BIGINT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
            ''')
            
            # Create user_stats table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_stats (
                    user_id BIGINT PRIMARY KEY,
                    username VARCHAR(255) NOT NULL,
                    total_matches INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0,
                    elo_rating INTEGER DEFAULT 1000,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create player_profiles table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS player_profiles (
                    user_id BIGINT PRIMARY KEY,
                    discord_username VARCHAR(255) NOT NULL,
                    player_ign VARCHAR(255) NOT NULL,
                    mmr INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0,
                    games INTEGER DEFAULT 0,
                    streak INTEGER DEFAULT 0,
                    peak_mmr INTEGER DEFAULT 0,
                    peak_streak INTEGER DEFAULT 0,
                    winrate DECIMAL(5,2) DEFAULT 0.00,
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create autoping_config table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS autoping_config (
                    channel_id BIGINT PRIMARY KEY,
                    role_id BIGINT NOT NULL,
                    size INTEGER NOT NULL,
                    delete_after INTEGER NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            print("✅ Database schema initialized")
    
    # Bot Config Methods
    async def set_config(self, key: str, value: str):
        """Set a configuration value"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                '''INSERT INTO bot_config (key, value, updated_at) 
                   VALUES ($1, $2, CURRENT_TIMESTAMP)
                   ON CONFLICT (key) 
                   DO UPDATE SET value = $2, updated_at = CURRENT_TIMESTAMP''',
                key, value
            )
    
    async def get_config(self, key: str):
        """Get a configuration value"""
        async with self.pool.acquire() as conn:
            value = await conn.fetchval(
                'SELECT value FROM bot_config WHERE key = $1',
                key
            )
            return value
    
    # Skrimmish Queue Methods
    async def add_to_queue(self, user_id: int, username: str):
        """Add a user to the skrimmish queue"""
        async with self.pool.acquire() as conn:
            try:
                await conn.execute(
                    'INSERT INTO skrimmish_queue (user_id, username) VALUES ($1, $2)',
                    user_id, username
                )
                return True
            except asyncpg.UniqueViolationError:
                return False
    
    async def remove_from_queue(self, user_id: int):
        """Remove a user from the skrimmish queue"""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                'DELETE FROM skrimmish_queue WHERE user_id = $1',
                user_id
            )
            return result != 'DELETE 0'
    
    async def get_queue(self):
        """Get all users in the queue"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT user_id, username, joined_at FROM skrimmish_queue ORDER BY joined_at ASC'
            )
            return rows
    
    async def get_queue_count(self):
        """Get the number of users in queue"""
        async with self.pool.acquire() as conn:
            count = await conn.fetchval('SELECT COUNT(*) FROM skrimmish_queue')
            return count
    
    async def is_in_queue(self, user_id: int):
        """Check if a user is in the queue"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                'SELECT EXISTS(SELECT 1 FROM skrimmish_queue WHERE user_id = $1)',
                user_id
            )
            return result
    
    async def clear_queue(self):
        """Clear the entire queue"""
        async with self.pool.acquire() as conn:
            await conn.execute('DELETE FROM skrimmish_queue')
    
    # Match Methods
    async def create_match(self, player1_id: int, player2_id: int, 
                          player1_username: str, player2_username: str):
        """Create a new match record"""
        async with self.pool.acquire() as conn:
            match_id = await conn.fetchval(
                '''INSERT INTO skrimmish_matches 
                   (player1_id, player2_id, player1_username, player2_username)
                   VALUES ($1, $2, $3, $4) RETURNING id''',
                player1_id, player2_id, player1_username, player2_username
            )
            return match_id
    
    async def get_user_stats(self, user_id: int):
        """Get user statistics"""
        async with self.pool.acquire() as conn:
            stats = await conn.fetchrow(
                'SELECT * FROM user_stats WHERE user_id = $1',
                user_id
            )
            return stats
    
    # Player Profile Methods
    async def register_player(self, user_id: int, discord_username: str, player_ign: str):
        """Register a new player with their IGN"""
        async with self.pool.acquire() as conn:
            try:
                await conn.execute(
                    '''INSERT INTO player_profiles 
                       (user_id, discord_username, player_ign, mmr, wins, losses, 
                        games, streak, peak_mmr, peak_streak, winrate)
                       VALUES ($1, $2, $3, 700, 0, 0, 0, 0, 700, 0, 0.00)''',
                    user_id, discord_username, player_ign
                )
                return True, "Registration successful!"
            except asyncpg.UniqueViolationError:
                # Player already registered, update IGN
                await conn.execute(
                    '''UPDATE player_profiles 
                       SET player_ign = $2, discord_username = $3, last_updated = CURRENT_TIMESTAMP
                       WHERE user_id = $1''',
                    user_id, player_ign, discord_username
                )
                return True, "IGN updated successfully!"
    
    async def get_player_profile(self, user_id: int):
        """Get a player's profile"""
        async with self.pool.acquire() as conn:
            profile = await conn.fetchrow(
                'SELECT * FROM player_profiles WHERE user_id = $1',
                user_id
            )
            return profile
    
    async def get_player_by_ign(self, player_ign: str):
        """Get a player's profile by their IGN (case-insensitive)
        
        Args:
            player_ign: Player's in-game name
            
        Returns:
            Player profile dict or None if not found
        """
        async with self.pool.acquire() as conn:
            profile = await conn.fetchrow(
                '''SELECT * FROM player_profiles 
                   WHERE LOWER(player_ign) = LOWER($1)''',
                player_ign
            )
            return profile
    
    async def is_player_registered(self, user_id: int):
        """Check if a player is registered"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                'SELECT EXISTS(SELECT 1 FROM player_profiles WHERE user_id = $1)',
                user_id
            )
            return result
    
    async def update_player_mmr(self, user_id: int, mmr_change: int):
        """Update a player's MMR (can be positive or negative)"""
        async with self.pool.acquire() as conn:
            # Update MMR and last_updated timestamp
            new_mmr = await conn.fetchval(
                '''UPDATE player_profiles 
                   SET mmr = mmr + $2, last_updated = CURRENT_TIMESTAMP
                   WHERE user_id = $1
                   RETURNING mmr''',
                user_id, mmr_change
            )
            
            # Update peak_mmr if new MMR is higher
            await conn.execute(
                '''UPDATE player_profiles 
                   SET peak_mmr = GREATEST(peak_mmr, mmr)
                   WHERE user_id = $1''',
                user_id
            )
            
            return new_mmr
    
    async def update_player_stats(self, user_id: int, won: bool, mmr_change: int):
        """Update player stats after a match
        
        Args:
            user_id: Discord user ID
            won: True if player won, False if lost
            mmr_change: MMR change (+32 for win, -27 for loss)
        """
        async with self.pool.acquire() as conn:
            profile = await conn.fetchrow(
                'SELECT wins, losses, games, streak, peak_mmr FROM player_profiles WHERE user_id = $1',
                user_id
            )
            
            if not profile:
                return None
            
            # Calculate new values
            new_wins = profile['wins'] + (1 if won else 0)
            new_losses = profile['losses'] + (0 if won else 1)
            new_games = profile['games'] + 1
            
            # Update streak
            if won:
                new_streak = profile['streak'] + 1 if profile['streak'] >= 0 else 1
            else:
                new_streak = profile['streak'] - 1 if profile['streak'] <= 0 else -1
            
            # Calculate winrate
            new_winrate = (new_wins / new_games * 100) if new_games > 0 else 0.0
            
            # Update database
            updated = await conn.fetchrow(
                '''UPDATE player_profiles 
                   SET mmr = mmr + $2,
                       wins = $3,
                       losses = $4,
                       games = $5,
                       streak = $6,
                       winrate = $7,
                       peak_mmr = GREATEST(peak_mmr, mmr + $2),
                       peak_streak = CASE 
                           WHEN $6 > peak_streak THEN $6 
                           ELSE peak_streak 
                       END,
                       last_updated = CURRENT_TIMESTAMP
                   WHERE user_id = $1
                   RETURNING mmr, wins, losses, games, streak, winrate, peak_mmr, peak_streak''',
                user_id, mmr_change, new_wins, new_losses, new_games, new_streak, new_winrate
            )
            
            return updated
    
    async def get_leaderboard(self, limit: int = 10):
        """Get the top players by MMR
        
        Args:
            limit: Number of players to return (default 10)
        
        Returns:
            List of player profiles ordered by MMR
        """
        async with self.pool.acquire() as conn:
            leaderboard = await conn.fetch(
                '''SELECT user_id, discord_username, player_ign, mmr, wins, losses, 
                          games, streak, winrate, peak_mmr, peak_streak
                   FROM player_profiles 
                   WHERE games > 0
                   ORDER BY mmr DESC 
                   LIMIT $1''',
                limit
            )
            return leaderboard
    
    async def get_leaderboard_page(self, limit: int = 10, offset: int = 0):
        """Get a page of the leaderboard with pagination
        
        Args:
            limit: Number of players per page (default 10)
            offset: Number of players to skip (default 0)
        
        Returns:
            List of player profiles ordered by MMR for the specified page
        """
        async with self.pool.acquire() as conn:
            leaderboard = await conn.fetch(
                '''SELECT user_id, discord_username, player_ign, mmr, wins, losses, 
                          games, streak, winrate, peak_mmr, peak_streak
                   FROM player_profiles 
                   ORDER BY mmr DESC, wins DESC
                   LIMIT $1 OFFSET $2''',
                limit, offset
            )
            return leaderboard
    
    async def get_total_players(self):
        """Get the total number of registered players
        
        Returns:
            Integer count of players
        """
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                '''SELECT COUNT(*) FROM player_profiles'''
            )
            return result if result else 0
    
    async def reset_all_player_stats(self):
        """Reset all player stats to default values (700 MMR, 0 wins/losses/games)
        
        Returns:
            Number of players reset
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                '''UPDATE player_profiles
                   SET mmr = 700,
                       wins = 0,
                       losses = 0,
                       games = 0,
                       streak = 0,
                       winrate = 0,
                       peak_mmr = 700,
                       peak_streak = 0,
                       last_updated = CURRENT_TIMESTAMP'''
            )
            # Extract number of rows updated from result string like "UPDATE 5"
            return int(result.split()[-1]) if result else 0
    
    # Autoping Configuration Methods
    async def set_autoping(self, channel_id: int, role_id: int, size: int, delete_after: int):
        """Set autoping configuration for a channel"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                '''INSERT INTO autoping_config (channel_id, role_id, size, delete_after, updated_at)
                   VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
                   ON CONFLICT (channel_id) 
                   DO UPDATE SET role_id = $2, size = $3, delete_after = $4, updated_at = CURRENT_TIMESTAMP''',
                channel_id, role_id, size, delete_after
            )
    
    async def get_autoping(self, channel_id: int):
        """Get autoping configuration for a channel"""
        async with self.pool.acquire() as conn:
            config = await conn.fetchrow(
                'SELECT * FROM autoping_config WHERE channel_id = $1',
                channel_id
            )
            return config
    
    async def remove_autoping(self, channel_id: int):
        """Remove autoping configuration for a channel"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                'DELETE FROM autoping_config WHERE channel_id = $1',
                channel_id
            )

# Global database instance
db = Database()
