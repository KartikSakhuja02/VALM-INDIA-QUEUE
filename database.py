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
            
            print("✅ Database schema initialized")
    
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

# Global database instance
db = Database()
