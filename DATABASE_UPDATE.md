# Database Update Instructions

## Adding Player Profiles Table

This guide will help you update your PostgreSQL database on the Raspberry Pi to add the new `player_profiles` table for IGN registration.

### Option 1: Using psql (Recommended)

1. **Connect to PostgreSQL with valmbot user**:
   ```bash
   psql -U valmbot -d valmindiaqueue -h localhost
   ```
   
   When prompted, enter the password: `valorantmobileindia`

2. **Create the player_profiles table**:
   ```sql
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
   ```

3. **Create indexes for better performance**:
   ```sql
   CREATE INDEX IF NOT EXISTS idx_player_profiles_mmr ON player_profiles(mmr DESC);
   CREATE INDEX IF NOT EXISTS idx_player_profiles_ign ON player_profiles(player_ign);
   ```

4. **Verify the table was created**:
   ```sql
   \d player_profiles
   ```

5. **Exit psql**:
   ```sql
   \q
   ```

### Option 2: Using schema.sql File

1. **Navigate to your bot directory**:
   ```bash
   cd ~/Documents/Valorant-Mobile-India-Queue
   ```

2. **Run the updated schema**:
   ```bash
   PGPASSWORD=valorantmobileindia psql -U valmbot -d valmindiaqueue -h localhost < schema.sql
   ```

   This will create any missing tables without affecting existing data.

### Option 3: Let Bot Auto-Create (Easiest)

The bot will automatically create the `player_profiles` table when it starts up, thanks to the updated `initialize_schema()` method in `database.py`.

1. **Just restart the bot**:
   ```bash
   sudo systemctl restart valmindiaqueue
   ```

2. **Check the logs to confirm**:
   ```bash
   sudo journalctl -u valmindiaqueue -n 50 -f
   ```

   You should see: `✅ Database schema initialized`

### Verify Everything Works

1. **Check bot status**:
   ```bash
   sudo systemctl status valmindiaqueue
   ```

2. **Try the /ign command in Discord**:
   ```
   /ign YourIGNHere
   ```

3. **Verify registration in database** (optional):
   ```bash
   psql -U valmbot -d valmindiaqueue -h localhost
   ```
   Enter password: `valorantmobileindia`
   ```sql
   SELECT * FROM player_profiles;
   \q
   ```

## Table Structure

The `player_profiles` table stores:
- **user_id**: Discord user ID (primary key)
- **discord_username**: Discord username
- **player_ign**: Valorant Mobile in-game name
- **mmr**: Matchmaking rating (starts at 0)
- **wins**: Total wins (starts at 0)
- **losses**: Total losses (starts at 0)
- **games**: Total games played (starts at 0)
- **streak**: Current win/loss streak (starts at 0)
- **peak_mmr**: Highest MMR achieved (starts at 0)
- **peak_streak**: Highest streak achieved (starts at 0)
- **winrate**: Win rate percentage (starts at 0.00)
- **registered_at**: Registration timestamp
- **last_updated**: Last update timestamp

## Troubleshooting

### Error: "relation already exists"
This is fine - it means the table already exists. No action needed.

### Error: "permission denied"
Make sure you're using the `valmbot` user with the correct password: `valorantmobileindia`

### Bot not starting
1. Check logs: `sudo journalctl -u valmindiaqueue -n 50`
2. Check database connection: Verify `DATABASE_URL` in `.env`
3. Restart PostgreSQL: `sudo systemctl restart postgresql`

### Can't connect to database
1. Check PostgreSQL is running: `sudo systemctl status postgresql`
2. Verify database exists: `psql -U valmbot -h localhost -l | grep valmindiaqueue`
3. Test connection: `psql -U valmbot -d valmindiaqueue -h localhost` (password: `valorantmobileindia`)
