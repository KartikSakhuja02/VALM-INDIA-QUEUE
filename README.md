# VALM India Queue Bot

A Discord bot for managing Valorant matchmaking queues for the Indian community.

## Features

- `/ping` - Check bot latency and uptime
- More features coming soon...

## Prerequisites

- Python 3.8 or higher
- Discord Bot Token (see setup instructions below)
- Git

## Setup Instructions

### 1. Create a Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name
3. Go to the "Bot" tab and click "Add Bot"
4. Under the bot token section, click "Reset Token" and copy it (you'll need this for `.env`)
5. Enable these Privileged Gateway Intents:
   - Server Members Intent
   - Message Content Intent
6. Go to "OAuth2" → "URL Generator"
7. Select scopes: `bot` and `applications.commands`
8. Select bot permissions:
   - Send Messages
   - Embed Links
   - Read Message History
   - Use Slash Commands
   - Manage Channels (for creating match channels)
9. Copy the generated URL and use it to invite the bot to your server

### 2. Local Development Setup (Laptop)

```bash
# Clone the repository (after initial push)
git clone https://github.com/yourusername/VALM-India-Queue.git
cd VALM-India-Queue

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
# Copy .env.example to .env and fill in your bot token
cp .env.example .env
# Edit .env and add your DISCORD_BOT_TOKEN

# Run the bot
python bot.py
```

### 3. Raspberry Pi Setup (24/7 Hosting)

#### Initial Setup on Raspberry Pi

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and pip (if not already installed)
sudo apt install python3 python3-pip python3-venv git -y

# Navigate to home directory
cd ~

# Clone the repository
git clone https://github.com/yourusername/VALM-India-Queue.git
cd VALM-India-Queue

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
nano .env  # Add your DISCORD_BOT_TOKEN

# Create logs directory
mkdir -p logs

# Test the bot
python bot.py
# Press Ctrl+C to stop after confirming it works
```

#### Setting up the Systemd Service

```bash
# Copy the service file to systemd directory
sudo cp valmindiaqueue.service /etc/systemd/system/

# If your username is not 'pi', edit the service file
sudo nano /etc/systemd/system/valmindiaqueue.service
# Change 'User=pi' to your username
# Change all paths from /home/pi/ to your home directory

# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable valmindiaqueue

# Start the service
sudo systemctl start valmindiaqueue

# Check status
sudo systemctl status valmindiaqueue
```

#### Managing the Service

```bash
# Start the bot
sudo systemctl start valmindiaqueue

# Stop the bot
sudo systemctl stop valmindiaqueue

# Restart the bot
sudo systemctl restart valmindiaqueue

# Check status
sudo systemctl status valmindiaqueue

# View logs
tail -f ~/VALM-India-Queue/logs/bot.log

# View error logs
tail -f ~/VALM-India-Queue/logs/bot.error.log
```

### 4. Workflow: Laptop → Raspberry Pi

#### On Your Laptop

```bash
# Make your changes to the code
# Test locally

# Commit and push changes
git add .
git commit -m "Your commit message"
git push origin main
```

#### On Your Raspberry Pi

```bash
# Navigate to the project directory
cd ~/VALM-India-Queue

# Pull the latest changes
git pull origin main

# If you updated dependencies, reinstall them
source venv/bin/activate
pip install -r requirements.txt

# Restart the bot service
sudo systemctl restart valmindiaqueue

# Check if it's running properly
sudo systemctl status valmindiaqueue
```

## Project Structure

```
VALM-India-Queue/
├── bot.py                    # Main bot file
├── requirements.txt          # Python dependencies
├── .env                      # Environment variables (not in git)
├── .env.example             # Example environment file
├── .gitignore               # Git ignore file
├── valmindiaqueue.service   # Systemd service file
├── README.md                # This file
└── logs/                    # Log files (created automatically)
    ├── bot.log
    └── bot.error.log
```

## Environment Variables

- `DISCORD_BOT_TOKEN` - Your Discord bot token (required)
- `GUILD_ID` - Discord server ID for faster command sync during development (optional)
- `DATABASE_URL` - PostgreSQL database connection string (required)
- `QUEUE_CHANNEL_ID` - Channel ID where the queue UI will be posted on bot startup (required)
- `MATCH_CATEGORY_ID` - Category ID where private match text/voice channels will be created (required)
- `LOGS_CHANNEL_ID` - Channel ID where match results will be logged (required)

### Getting Channel/Category IDs

1. Enable Developer Mode in Discord:
   - User Settings → App Settings → Advanced → Enable "Developer Mode"
2. Right-click on a channel and select "Copy Channel ID"
3. Right-click on a category and select "Copy Category ID"
4. Paste these IDs into your `.env` file

## Commands

- `/ping` - Shows bot latency and uptime information

## Troubleshooting

### Bot doesn't respond to commands

1. Make sure you've enabled the necessary intents in the Discord Developer Portal
2. Wait up to 1 hour for global commands to sync, or set `GUILD_ID` in `.env` for instant sync during development
3. Check that the bot has proper permissions in your Discord server

### Service won't start on Raspberry Pi

1. Check logs: `sudo journalctl -u valmindiaqueue -n 50`
2. Verify paths in the service file match your setup
3. Ensure the virtual environment exists and has all dependencies installed
4. Check that `.env` file exists and has the correct token

### Bot keeps restarting

1. Check error logs: `tail -f ~/VALM-India-Queue/logs/bot.error.log`
2. Verify your Discord bot token is correct
3. Check internet connection on Raspberry Pi

## Future Features

- Queue management system
- Team balancing
- Match history
- Player statistics
- Server region selection
- Custom match configurations

## Contributing

Feel free to submit issues and pull requests!

## License

MIT License
