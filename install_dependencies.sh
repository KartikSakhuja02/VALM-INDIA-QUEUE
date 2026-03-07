#!/bin/bash
# Installation script for Raspberry Pi dependencies

echo "=================================================="
echo "VALM India Queue - Dependency Installer"
echo "=================================================="
echo ""

# Check if running on Raspberry Pi or Linux
if [[ ! -f /etc/os-release ]]; then
    echo "Warning: This script is designed for Linux/Raspberry Pi"
fi

echo "Step 1: Installing system dependencies (one by one)..."
echo "Updating package lists..."
sudo apt update

echo ""
echo "Installing libjpeg-dev..."
sudo apt install -y libjpeg-dev || {
    echo "Warning: Failed to install libjpeg-dev, continuing..."
}

echo ""
echo "Installing zlib1g-dev..."
sudo apt install -y zlib1g-dev || {
    echo "Warning: Failed to install zlib1g-dev, continuing..."
}

echo ""
echo "Installing libpng-dev..."
sudo apt install -y libpng-dev || {
    echo "Warning: Failed to install libpng-dev, continuing..."
}

echo ""
echo "Step 2: Upgrading pip..."
pip install --upgrade pip

echo ""
echo "Step 3: Installing Python packages..."
echo "This may take several minutes on Raspberry Pi..."

# Install packages one by one with progress
packages=(
    "discord.py>=2.3.0"
    "python-dotenv>=1.0.0"
    "asyncpg>=0.29.0"
    "google-generativeai>=0.3.0"
    "Pillow>=10.0.0"
)

for package in "${packages[@]}"; do
    echo ""
    echo "Installing $package..."
    pip install "$package" --no-cache-dir || {
        echo "Failed to install $package"
        exit 1
    }
done

echo ""
echo "=================================================="
echo "✅ All dependencies installed successfully!"
echo "=================================================="
echo ""
echo "Next steps:"
echo "1. Configure your .env file with API keys"
echo "2. Run: python bot.py (to test)"
echo "3. Run: sudo systemctl restart valmindiaqueue (if using systemd)"
echo ""
