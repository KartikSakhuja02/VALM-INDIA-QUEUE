#!/bin/bash
# Quick install script for Raspberry Pi - installs specific versions to avoid memory issues

echo "=================================================="
echo "VALM India Queue - Quick Installer for RPi"
echo "=================================================="
echo ""

echo "Step 1: Installing packages with specific versions (no dependency resolution)..."

# Install with exact versions to avoid pip resolver consuming all RAM
pip install --no-cache-dir google-generativeai==0.8.0
pip install --no-cache-dir Pillow==10.2.0

echo ""
echo "=================================================="
echo "✅ Installation complete!"
echo "=================================================="
echo ""
