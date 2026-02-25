#!/usr/bin/env python
"""
Verify that the Gemini API setup is working correctly.
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

print("=" * 70)
print("GEMINI API CONFIGURATION VERIFICATION")
print("=" * 70)

# Check API Key
api_key = os.getenv("GEMINI_API_KEY")
model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")

print(f"\n✓ GEMINI_API_KEY: {'SET ✓' if api_key else '❌ MISSING'}")
if api_key:
    # Show masked API key
    masked = api_key[:10] + "..." + api_key[-5:] if len(api_key) > 20 else "***"
    print(f"  Value: {masked}")

print(f"\n✓ GEMINI_MODEL_NAME: {model_name}")

# Try importing the module
print("\n" + "=" * 70)
print("CHECKING MODULE IMPORTS")
print("=" * 70)

try:
    from modules.invoice_gemini_extractor import (
        extract_invoice_core_fields_from_image,
        extract_invoice_core_fields
    )
    print("\n✓ Successfully imported invoice extraction modules")
except Exception as e:
    print(f"\n❌ Failed to import modules: {e}")
    sys.exit(1)

# Try importing Gemini SDKs (legacy and modern)
legacy_genai = None
modern_genai = None
modern_types = None

try:
    import google.generativeai as legacy_genai
    print("✓ Successfully imported google.generativeai (legacy SDK)")
except Exception as e:
    print(f"⚠️ Legacy SDK unavailable: {e}")

try:
    from google import genai as modern_genai
    from google.genai import types as modern_types
    print("✓ Successfully imported google.genai (modern SDK)")
except Exception as e:
    print(f"⚠️ Modern SDK unavailable: {e}")

if legacy_genai is None and modern_genai is None:
    print("❌ No supported Gemini SDK available.")
    print("  Install one of:")
    print("  - pip install google-generativeai")
    print("  - pip install google-genai")
    sys.exit(1)

# Test basic Gemini connectivity
print("\n" + "=" * 70)
print("TESTING GEMINI API CONNECTIVITY")
print("=" * 70)

if not api_key:
    print("\n⚠️  Cannot test API: API key not configured in .env")
    sys.exit(1)

try:
    print("\nAttempting to connect to Gemini API...")
    if legacy_genai is not None:
        legacy_genai.configure(api_key=api_key)
        model = legacy_genai.GenerativeModel(model_name)
        _ = model.generate_content("{\"test\":\"ping\"}")
        print("✓ Gemini API client initialized successfully with legacy SDK")
        print(f"✓ Using model: {model_name}")
    else:
        client = modern_genai.Client(api_key=api_key)
        _ = client.models.generate_content(
            model=model_name,
            contents="{\"test\":\"ping\"}",
            config=modern_types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=64,
                response_mime_type="application/json",
            ),
        )
        print("✓ Gemini API client initialized successfully with modern SDK")
        print(f"✓ Using model: {model_name}")
    
except Exception as e:
    print(f"❌ Failed to initialize Gemini API: {e}")
    print(f"  Error type: {type(e).__name__}")
    print("\n  Troubleshooting:")
    print("  1. Verify your API key is valid")
    print("  2. Check that APIs are enabled in Google Cloud Console")
    print("  3. Verify internet connectivity")
    sys.exit(1)

print("\n" + "=" * 70)
print("✓ ALL CHECKS PASSED - SYSTEM IS READY!")
print("=" * 70)

print("\nYou can now use the image extraction system:")
print("""
from modules.invoice_gemini_extractor import extract_invoice_core_fields_from_image

# Extract fields from an invoice image
result = extract_invoice_core_fields_from_image("invoice.jpg")

print(result["remitter_name"])
print(result["beneficiary_address"])
print(result["amount"])
""")

print("\n" + "=" * 70)
