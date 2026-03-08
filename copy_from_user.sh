#!/bin/bash
# Copy Google packages from user-installed location

echo "=================================================="
echo "Copying Google Packages from User Install"
echo "=================================================="
echo ""

SOURCE="/home/kartiksakhuja02/.local/lib/python3.13/site-packages"
TARGET="/home/kartiksakhuja02/Documents/Valorant-Mobile-India-Queue/venv/lib/python3.13/site-packages"

echo "Source: $SOURCE"
echo "Target: $TARGET"
echo ""

# Copy all Google packages
echo "Copying google packages..."
cp -r "$SOURCE"/google* "$TARGET/" 2>&1 | grep -v "^'" | head -5

echo "Copying grpc packages..."
cp -r "$SOURCE"/grpc* "$TARGET/" 2>&1 | grep -v "^'" | head -5

echo "Copying proto packages..."
cp -r "$SOURCE"/proto* "$TARGET/" 2>&1 | head -3
cp -r "$SOURCE"/_proto* "$TARGET/" 2>&1 | head -3

echo "Copying all dependencies..."
cp -r "$SOURCE"/pydantic* "$TARGET/" 2>&1 | head -2
cp -r "$SOURCE"/annotated* "$TARGET/" 2>&1 | head -2
cp -r "$SOURCE"/pydantic_core* "$TARGET/" 2>&1 | head -2
cp -r "$SOURCE"/cryptography* "$TARGET/" 2>&1 | head -2
cp -r "$SOURCE"/tqdm* "$TARGET/" 2>&1 | head -2
cp -r "$SOURCE"/typing_extensions* "$TARGET/" 2>&1 | head -2
cp -r "$SOURCE"/attrs* "$TARGET/" 2>&1 | head -2
cp -r "$SOURCE"/httplib2* "$TARGET/" 2>&1 | head -2
cp -r "$SOURCE"/pyparsing* "$TARGET/" 2>&1 | head -2
cp -r "$SOURCE"/uritemplate* "$TARGET/" 2>&1 | head -2

echo ""
echo "=================================================="
echo "✅ Packages copied!"
echo "=================================================="
echo ""

cd /home/kartiksakhuja02/Documents/Valorant-Mobile-India-Queue
source venv/bin/activate

echo "Testing imports..."
if python3 -c "import google.generativeai; import PIL; print('✅ All working!')" 2>&1; then
    echo ""
    echo "=================================================="
    echo "SUCCESS! Start your bot:"
    echo "sudo systemctl restart valmindiaqueue"
    echo "=================================================="
else
    echo ""
    echo "Checking what's still missing..."
    python3 -c "import google.generativeai" 2>&1
fi
