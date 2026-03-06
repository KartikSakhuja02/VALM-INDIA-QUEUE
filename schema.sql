-- VALM India Queue Database Schema
-- PostgreSQL Database Schema

-- Bot Config Table
-- Stores bot configuration like message IDs, channel IDs, etc.
CREATE TABLE IF NOT EXISTS bot_config (
    key VARCHAR(255) PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Skrimmish Queue Table
-- Stores players currently in the 1v1 queue
CREATE TABLE IF NOT EXISTS skrimmish_queue (
    id SERIAL PRIMARY KEY,
    user_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255) NOT NULL,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    valorant_ign VARCHAR(255),
    rank VARCHAR(50)
);

-- Skrimmish Matches Table
-- Stores all match records
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
);

-- User Statistics Table
-- Stores player stats and rankings
CREATE TABLE IF NOT EXISTS user_stats (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    total_matches INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    elo_rating INTEGER DEFAULT 1000,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Player Profiles Table
-- Stores registered player IGNs and comprehensive stats
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
);

-- Indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_skrimmish_queue_user_id ON skrimmish_queue(user_id);
CREATE INDEX IF NOT EXISTS idx_skrimmish_queue_joined_at ON skrimmish_queue(joined_at);
CREATE INDEX IF NOT EXISTS idx_skrimmish_matches_player1 ON skrimmish_matches(player1_id);
CREATE INDEX IF NOT EXISTS idx_skrimmish_matches_player2 ON skrimmish_matches(player2_id);
CREATE INDEX IF NOT EXISTS idx_skrimmish_matches_created_at ON skrimmish_matches(created_at);
CREATE INDEX IF NOT EXISTS idx_user_stats_elo ON user_stats(elo_rating DESC);
CREATE INDEX IF NOT EXISTS idx_player_profiles_mmr ON player_profiles(mmr DESC);
CREATE INDEX IF NOT EXISTS idx_player_profiles_ign ON player_profiles(player_ign);
