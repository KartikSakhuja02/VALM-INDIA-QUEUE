#!/bin/bash
# Copy packages from working venv to this project's venv

echo "=================================================="
echo "Copying packages from working venv..."
echo "=================================================="
echo ""

SOURCE_VENV="/home/kartiksakhuja02/Documents/Valorant-Mobile-Tournament/venv"
TARGET_VENV="/home/kartiksakhuja02/Documents/Valorant-Mobile-India-Queue/venv"

echo "Source: $SOURCE_VENV"
echo "Target: $TARGET_VENV"
echo ""

# Find the Python version directory
SOURCE_SITE=$(find "$SOURCE_VENV/lib" -type d -name "site-packages" | head -n 1)
TARGET_SITE=$(find "$TARGET_VENV/lib" -type d -name "site-packages" | head -n 1)

echo "Copying packages..."
echo "From: $SOURCE_SITE"
echo "To: $TARGET_SITE"
echo ""

# List what we're about to copy
echo "Packages found in source:"
ls "$SOURCE_SITE" | grep -E "^(google|PIL|grpc|proto|pydantic|cryptography|tqdm|requests|urllib3|certifi|charset|idna|pyasn1|rsa|cachetools)" | head -20
echo ""

# Copy all necessary packages (show errors if any)
echo "Copying google*..."
cp -rv "$SOURCE_SITE"/google* "$TARGET_SITE/" 2>&1 | head -5

echo "Copying PIL*..."
cp -rv "$SOURCE_SITE"/PIL* "$TARGET_SITE/" 2>&1 | head -5

echo "Copying other dependencies..."
cp -r "$SOURCE_SITE"/grpc* "$TARGET_SITE/" 2>&1
cp -r "$SOURCE_SITE"/proto* "$TARGET_SITE/" 2>&1
cp -r "$SOURCE_SITE"/_proto* "$TARGET_SITE/" 2>&1
cp -r "$SOURCE_SITE"/pydantic* "$TARGET_SITE/" 2>&1
cp -r "$SOURCE_SITE"/cryptography* "$TARGET_SITE/" 2>&1
cp -r "$SOURCE_SITE"/tqdm* "$TARGET_SITE/" 2>&1
cp -r "$SOURCE_SITE"/requests* "$TARGET_SITE/" 2>&1
cp -r "$SOURCE_SITE"/urllib3* "$TARGET_SITE/" 2>&1
cp -r "$SOURCE_SITE"/certifi* "$TARGET_SITE/" 2>&1
cp -r "$SOURCE_SITE"/charset* "$TARGET_SITE/" 2>&1
cp -r "$SOURCE_SITE"/idna* "$TARGET_SITE/" 2>&1
cp -r "$SOURCE_SITE"/pyasn1* "$TARGET_SITE/" 2>&1
cp -r "$SOURCE_SITE"/rsa* "$TARGET_SITE/" 2>&1
cp -r "$SOURCE_SITE"/cachetools* "$TARGET_SITE/" 2>&1
cp -r "$SOURCE_SITE"/annotated* "$TARGET_SITE/" 2>&1
cp -r "$SOURCE_SITE"/typing* "$TARGET_SITE/" 2>&1

echo ""
echo "=================================================="
echo "✅ Packages copied successfully!"
echo "=================================================="
echo ""
echo "Now testing imports..."
cd /home/kartiksakhuja02/Documents/Valorant-Mobile-India-Queue
source venv/bin/activate
python3 -c "import google.generativeai; import PIL; print('✅ All imports working!')"

echo ""
echo "You can now start the bot!"
