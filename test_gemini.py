#!/usr/bin/env python3
# Test Gemini API and list available models

import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add venv to path
sys.path.insert(0, '/home/kartiksakhuja02/Documents/Valorant-Mobile-India-Queue/venv/lib/python3.13/site-packages')

try:
    import google.generativeai as genai
    
    # Get API key from environment
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("ERROR: GEMINI_API_KEY not set")
        sys.exit(1)
    
    genai.configure(api_key=api_key)
    
    print("Available models:")
    print("=" * 50)
    
    try:
        for model in genai.list_models():
            if 'generateContent' in model.supported_generation_methods:
                print(f"✓ {model.name}")
                print(f"  Display name: {model.display_name}")
                print(f"  Description: {model.description[:100]}...")
                print()
    except Exception as e:
        print(f"Could not list models: {e}")
        print()
        print("Trying common model names:")
        test_models = ['gemini-pro', 'gemini-pro-vision', 'models/gemini-pro', 'models/gemini-pro-vision']
        
        for model_name in test_models:
            try:
                model = genai.GenerativeModel(model_name)
                print(f"✓ {model_name} - Available")
            except Exception as e:
                print(f"✗ {model_name} - Error: {e}")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
