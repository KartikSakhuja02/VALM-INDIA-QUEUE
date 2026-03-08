#!/bin/bash
# Ultra-light installer - installs ONLY binary packages, no compilation

echo "=================================================="
echo "Ultra-Light Google Generative AI Installer"
echo "=================================================="
echo ""

cd ~/Documents/Valorant-Mobile-India-Queue
source venv/bin/activate

echo "Installing only pre-built binary packages..."
echo "This avoids compilation and prevents crashes."
echo ""

# Install with --only-binary :all: to prevent ANY compilation
pip install --no-cache-dir --only-binary :all: protobuf tqdm typing-extensions requests 2>/dev/null

# Install pydantic (might need --no-binary pydantic-core if crashes)
echo "Installing pydantic..."
pip install --no-cache-dir pydantic 2>/dev/null || pip install --no-cache-dir --only-binary :all: pydantic 2>/dev/null

# Install google packages without heavy dependencies
echo "Installing Google packages (minimal)..."
pip install --no-cache-dir --only-binary :all: googleapis-common-protos proto-plus 2>/dev/null
pip install --no-cache-dir --only-binary :all: google-auth 2>/dev/null

# Install google-api-core WITHOUT grpc extras
echo "Installing google-api-core (REST only, no gRPC)..."
pip install --no-cache-dir --only-binary :all: google-api-core 2>/dev/null

# Install the generative AI packages without dependencies first
echo "Installing google-ai-generativelanguage..."
pip install --no-cache-dir --no-deps google-ai-generativelanguage 2>/dev/null

echo "Installing google-api-python-client..."
pip install --no-cache-dir --only-binary :all: google-api-python-client 2>/dev/null

echo "Installing google-generativeai (no deps)..."
pip install --no-cache-dir --no-deps google-generativeai 2>/dev/null

echo ""
echo "=================================================="
echo "Testing imports..."
echo "=================================================="

if python3 -c "import google.generativeai; import PIL; print('✅ All imports working!')" 2>/dev/null; then
    echo ""
    echo "=================================================="
    echo "✅ SUCCESS! Bot is ready to use!"
    echo "=================================================="
    echo ""
    echo "Start your bot with:"
    echo "sudo systemctl restart valmindiaqueue"
else
    echo ""
    echo "⚠️  Some packages missing. Installing minimal fallback..."
    pip install --no-cache-dir googleapis-common-protos proto-plus google-auth
    
    if python3 -c "import google.generativeai; import PIL; print('✅ Working now!')" 2>/dev/null; then
        echo "✅ Success with fallback!"
    else
        echo "❌ Installation incomplete. Bot will run without OCR."
        echo "The screenshot feature won't work, but everything else will."
    fi
fi

echo ""
