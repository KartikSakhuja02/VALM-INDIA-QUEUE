# Quick Setup Guide for Raspberry Pi

## If pip install gets "Killed" (Out of Memory)

### Option 1: Increase Swap (Recommended - Works on Any Linux)
```bash
# Check current swap
free -h

# Create a 1GB swap file
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Verify it's active
free -h

# Make it permanent (survives reboot)
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Now try installing again
cd ~/Documents/Valorant-Mobile-India-Queue
source venv/bin/activate
pip install --no-cache-dir google-generativeai==0.8.0
pip install --no-cache-dir Pillow==10.2.0
```

### Option 2: Use Quick Install Script
```bash
cd ~/Documents/Valorant-Mobile-India-Queue
git pull
source venv/bin/activate
chmod +x quick_install.sh
./quick_install.sh
```

### Option 3: Install Without Dependencies (Then Fix)
```bash
source venv/bin/activate
pip install --no-deps google-generativeai
pip install --no-deps Pillow
# Then install missing dependencies manually if needed
```

### Option 4: Use System Pillow + Manual Install
```bash
sudo apt install -y python3-pil python3-grpcio
source venv/bin/activate
pip install --no-cache-dir google-generativeai==0.8.0
```

## If Service Restart Takes Too Long

### Check what's wrong:
```bash
# Stop the service
sudo systemctl stop valmindiaqueue

# Check for errors
sudo journalctl -u valmindiaqueue -n 50

# Try running manually to see errors
cd ~/Documents/Valorant-Mobile-India-Queue
source venv/bin/activate
python bot.py
# Press Ctrl+C to stop

# If errors appear, they'll show here
```

### Common Issues:
1. **Missing GEMINI_API_KEY** - Add it to .env file
2. **Import errors** - Dependencies not fully installed
3. **Database connection** - PostgreSQL not running
4. **Port already in use** - Old process still running

### Force Kill Old Process:
```bash
# Find bot process
ps aux | grep bot.py

# Kill it (replace XXXX with actual PID)
kill -9 XXXX

# Or kill all Python processes (careful!)
sudo pkill -9 python

# Now restart service
sudo systemctl restart valmindiaqueue
```

### Quick Status Check:
```bash
# Check service status
sudo systemctl status valmindiaqueue

# Check real-time logs
sudo journalctl -u valmindiaqueue -f

# Check if bot is actually running
ps aux | grep bot.py
```
