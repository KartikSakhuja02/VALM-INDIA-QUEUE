#!/bin/bash
# Copy working Google packages from Tournament venv

echo "=================================================="
echo "Copying Google Packages from Tournament Venv"
echo "=================================================="
echo ""

# The venv is currently active, so we need to find it
# It's the one that has google-generativeai 0.8.6

# Try different possible locations
if [ -d "/home/kartiksakhuja02/Documents/Valorant-Mobile-Tournament/venv" ]; then
    SOURCE_VENV="/home/kartiksakhuja02/Documents/Valorant-Mobile-Tournament/venv"
elif [ -d "/home/kartiksakhuja02/Documents/Valorant-Tournament/venv" ]; then
    SOURCE_VENV="/home/kartiksakhuja02/Documents/Valorant-Tournament/venv"
else
    echo "❌ Could not find Tournament venv"
    exit 1
fi

TARGET_VENV="/home/kartiksakhuja02/Documents/Valorant-Mobile-India-Queue/venv"

SOURCE_SITE="$SOURCE_VENV/lib/python3.13/site-packages"
TARGET_SITE="$TARGET_VENV/lib/python3.13/site-packages"

echo "Copying from: $SOURCE_SITE"
echo "Copying to: $TARGET_SITE"
echo ""

# Copy ALL Google packages
echo "Copying google* packages..."
cp -rv "$SOURCE_SITE"/google* "$TARGET_SITE/" 2>&1 | grep -v "^'" | head -10

echo ""
echo "Copying grpc* packages (this is the key!)..."
cp -rv "$SOURCE_SITE"/grpc* "$TARGET_SITE/" 2>&1 | grep -v "^'" | head -10

echo ""
echo "Copying proto* packages..."
cp -rv "$SOURCE_SITE"/proto* "$TARGET_SITE/" 2>&1 | grep -v "^'" | head -5
cp -rv "$SOURCE_SITE"/_proto* "$TARGET_SITE/" 2>&1 | grep -v "^'" | head -5

echo ""
echo "Copying dependencies..."
cp -r "$SOURCE_SITE"/pydantic* "$TARGET_SITE/" 2>/dev/null
cp -r "$SOURCE_SITE"/annotated* "$TARGET_SITE/" 2>/dev/null
cp -r "$SOURCE_SITE"/pydantic_core* "$TARGET_SITE/" 2>/dev/null
cp -r "$SOURCE_SITE"/cryptography* "$TARGET_SITE/" 2>/dev/null
cp -r "$SOURCE_SITE"/tqdm* "$TARGET_SITE/" 2>/dev/null
cp -r "$SOURCE_SITE"/requests* "$TARGET_SITE/" 2>/dev/null
cp -r "$SOURCE_SITE"/urllib3* "$TARGET_SITE/" 2>/dev/null
cp -r "$SOURCE_SITE"/certifi* "$TARGET_SITE/" 2>/dev/null
cp -r "$SOURCE_SITE"/charset* "$TARGET_SITE/" 2>/dev/null
cp -r "$SOURCE_SITE"/idna* "$TARGET_SITE/" 2>/dev/null
cp -r "$SOURCE_SITE"/pyasn1* "$TARGET_SITE/" 2>/dev/null
cp -r "$SOURCE_SITE"/rsa* "$TARGET_SITE/" 2>/dev/null
cp -r "$SOURCE_SITE"/cachetools* "$TARGET_SITE/" 2>/dev/null
cp -r "$SOURCE_SITE"/typing* "$TARGET_SITE/" 2>/dev/null
cp -r "$SOURCE_SITE"/attrs* "$TARGET_SITE/" 2>/dev/null
cp -r "$SOURCE_SITE"/httplib2* "$TARGET_SITE/" 2>/dev/null
cp -r "$SOURCE_SITE"/pyparsing* "$TARGET_SITE/" 2>/dev/null

echo ""
echo "=================================================="
echo "Testing imports..."
echo "=================================================="

cd /home/kartiksakhuja02/Documents/Valorant-Mobile-India-Queue
source venv/bin/activate

if python3 -c "import google.generativeai; import PIL; print('✅ All imports working!')" 2>&1; then
    echo ""
    echo "=================================================="
    echo "✅ SUCCESS! OCR is ready!"
    echo "=================================================="
    echo ""
    echo "Start your bot with:"
    echo "sudo systemctl restart valmindiaqueue"
else
    echo ""
    echo "❌ Still missing some packages. Checking what's missing..."
    python3 -c "import google.generativeai" 2>&1
fi
