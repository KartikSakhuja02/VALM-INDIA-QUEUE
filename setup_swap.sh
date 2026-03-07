#!/bin/bash
# Universal swap setup script for any Linux system

echo "=================================================="
echo "Setting up 1GB swap for Raspberry Pi"
echo "=================================================="
echo ""

# Check if swap file already exists
if [ -f /swapfile ]; then
    echo "⚠️  Swap file already exists. Removing old one..."
    sudo swapoff /swapfile 2>/dev/null
    sudo rm /swapfile
fi

echo "Creating 1GB swap file..."
sudo fallocate -l 1G /swapfile

echo "Setting permissions..."
sudo chmod 600 /swapfile

echo "Making swap..."
sudo mkswap /swapfile

echo "Activating swap..."
sudo swapon /swapfile

echo "Making swap permanent..."
if ! grep -q '/swapfile' /etc/fstab; then
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

echo ""
echo "=================================================="
echo "✅ Swap setup complete!"
echo "=================================================="
echo ""
echo "Current memory status:"
free -h
echo ""
echo "You can now install packages without running out of memory!"
