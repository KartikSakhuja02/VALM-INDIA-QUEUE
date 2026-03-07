#!/bin/bash
# Minimal installation script - installs only essential packages without Pillow/OCR support

echo "=================================================="
echo "VALM India Queue - Minimal Installer"
echo "=================================================="
echo ""
echo "This installs the bot WITHOUT OCR support"
echo "The screenshot feature will not work!"
echo ""

echo "Step 1: Upgrading pip..."
pip install --upgrade pip

echo ""
echo "Step 2: Installing essential packages..."

# Install only core packages (no Pillow, no google-generativeai)
packages=(
    "discord.py>=2.3.0"
    "python-dotenv>=1.0.0"
    "asyncpg>=0.29.0"
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
echo "✅ Essential dependencies installed!"
echo "=================================================="
echo ""
echo "⚠️  WARNING: OCR features are disabled!"
echo "The Submit Screenshot button will not work."
echo ""
echo "To enable OCR later, run:"
echo "  sudo apt install -y libjpeg-dev zlib1g-dev libpng-dev"
echo "  pip install google-generativeai Pillow"
echo ""
