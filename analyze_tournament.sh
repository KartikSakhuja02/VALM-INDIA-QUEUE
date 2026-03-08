#!/bin/bash
# Discover OCR implementation in Valorant-Tournament project

echo "=================================================="
echo "Analyzing Valorant-Tournament OCR Implementation"
echo "=================================================="
echo ""

TOURNAMENT_DIR="/home/kartiksakhuja02/Documents/Valorant-Tournament"
TOURNAMENT_VENV="$TOURNAMENT_DIR/venv"

echo "Step 1: Checking what OCR packages are installed..."
source "$TOURNAMENT_VENV/bin/activate"
pip list | grep -iE "(google|OCR|tesseract|opencv|vision|gemini|generative)"
echo ""

echo "Step 2: Searching for OCR-related code..."
echo "Looking for imports and OCR usage in Python files..."
echo ""
grep -r "import.*google\|import.*genai\|import.*generative\|import.*OCR\|import.*vision" "$TOURNAMENT_DIR" --include="*.py" | head -20
echo ""

echo "Step 3: Checking if they use Gemini API..."
grep -r "genai\|generative\|GEMINI" "$TOURNAMENT_DIR" --include="*.py" | head -10
echo ""

echo "Step 4: Looking at their requirements.txt..."
if [ -f "$TOURNAMENT_DIR/requirements.txt" ]; then
    echo "Content of requirements.txt:"
    cat "$TOURNAMENT_DIR/requirements.txt"
else
    echo "No requirements.txt found"
fi
echo ""

echo "Step 5: Listing ALL packages in their venv..."
echo "(Saving to tournament_packages.txt)"
pip list > tournament_packages.txt
echo "Saved to tournament_packages.txt"
echo ""

deactivate

echo "=================================================="
echo "Analysis complete!"
echo "=================================================="
echo ""
echo "Now run: cat tournament_packages.txt"
echo "To see what they have installed"
