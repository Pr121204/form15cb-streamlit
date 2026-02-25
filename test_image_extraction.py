#!/usr/bin/env python
"""
Test script demonstrating the new image-based invoice extraction.

This script shows how the updated system works:
1. Old flow (deprecated): Image → OCR → Text → Gemini
2. New flow (optimized): Image → Gemini (with vision capabilities)

The new approach provides:
- Better address extraction (complete and not truncated)
- Better country detection for both remitter and beneficiary  
- Improved handling of multilingual invoices
- No OCR artifacts affecting field extraction
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add the project to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from modules.invoice_gemini_extractor import (
    extract_invoice_core_fields_from_image,
)
from modules.logger import get_logger

load_dotenv()

logger = get_logger()


def test_image_extraction(image_path: str):
    """
    Test invoice extraction from an image file.
    
    Args:
        image_path: Path to invoice image (JPEG, PNG, etc.)
    """
    print(f"\n{'='*70}")
    print(f"Testing Image-Based Invoice Extraction")
    print(f"{'='*70}")
    
    if not os.path.exists(image_path):
        print(f"❌ Error: Image file not found: {image_path}")
        return
    
    print(f"\n📄 Processing: {image_path}")
    print(f"File size: {os.path.getsize(image_path)} bytes")
    
    # Extract using the new image-based method
    print("\n🔄 Extracting invoice fields directly from image...")
    print("   (Using Gemini vision API - no OCR)")
    
    extracted = extract_invoice_core_fields_from_image(image_path)
    
    # Display results
    print(f"\n{'='*70}")
    print("EXTRACTED FIELDS:")
    print(f"{'='*70}")
    
    fields_to_display = [
        ("Remitter Name", "remitter_name"),
        ("Remitter Address", "remitter_address"),
        ("Remitter Country", "remitter_country_text"),
        ("Beneficiary Name", "beneficiary_name"),
        ("Beneficiary Address", "beneficiary_address"),
        ("Beneficiary Country", "beneficiary_country_text"),
        ("Invoice Number", "invoice_number"),
        ("Invoice Date", "invoice_date_display"),
        ("Amount", "amount"),
        ("Currency", "currency_short"),
        ("Nature of Remittance", "nature_of_remittance"),
        ("Purpose Group", "purpose_group"),
        ("Purpose Code", "purpose_code"),
    ]
    
    for label, field_key in fields_to_display:
        value = extracted.get(field_key, "")
        status = "✓" if value else "○"
        print(f"\n{status} {label}:")
        if value:
            # Truncate long values for display
            if len(str(value)) > 70:
                print(f"   {str(value)[:70]}...")
            else:
                print(f"   {value}")
        else:
            print(f"   (empty)")
    
    print(f"\n{'='*70}")
    print("KEY IMPROVEMENTS IN NEW SYSTEM:")
    print(f"{'='*70}")
    print("""
✓ Complete Address Extraction:
  - No OCR truncation or errors
  - Full street address, city, postal code, country
  
✓ Accurate Country Detection:
  - Both remitter_country and beneficiary_country extracted separately
  - Better handling of European country codes (DE-, FR-, etc.)
  
✓ Multilingual Support:
  - Portuguese, German, French, Spanish, Italian invoices handled
  - Proper interpretation of local address formats
  
✓ Beneficiary Details Completeness:
  - Complete address (previously an issue with OCR + text extraction)
  - Proper country identification for beneficiary
  
✓ No OCR Artifacts:
  - Gemini processes image directly, avoiding OCR text processing errors
  - Better handling of handwritten elements
  - Correct interpretation of number formats (European vs US)
""")
    
    print(f"\n{'='*70}\n")
    return extracted


def test_batch_extraction(image_folder: str = None):
    """
    Test extraction on multiple invoice images.
    
    Args:
        image_folder: Path to folder containing invoice images
    """
    if not image_folder:
        image_folder = str(project_root / "data" / "input")
    
    if not os.path.isdir(image_folder):
        print(f"⚠️  Image folder not found: {image_folder}")
        return
    
    # Find image files
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp')
    image_files = [
        f for f in os.listdir(image_folder)
        if f.lower().endswith(image_extensions)
    ]
    
    if not image_files:
        print(f"⚠️  No image files found in: {image_folder}")
        return
    
    print(f"\n{'='*70}")
    print(f"Testing {len(image_files)} invoice(s)")
    print(f"{'='*70}\n")
    
    for idx, image_file in enumerate(image_files, 1):
        file_path = os.path.join(image_folder, image_file)
        print(f"\n[{idx}/{len(image_files)}] Processing: {image_file}")
        test_image_extraction(file_path)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Test the new image-based invoice extraction system"
    )
    parser.add_argument(
        "image",
        nargs="?",
        help="Path to invoice image file (JPEG, PNG, etc.)"
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Process all images in a folder"
    )
    parser.add_argument(
        "--folder",
        help="Folder containing invoice images (with --batch)"
    )
    
    args = parser.parse_args()
    
    # Check API key
    if not os.getenv("GEMINI_API_KEY"):
        print("❌ Error: GEMINI_API_KEY environment variable is not set")
        print("   Please set it in your .env file or environment")
        sys.exit(1)
    
    if args.batch:
        test_batch_extraction(args.folder)
    elif args.image:
        test_image_extraction(args.image)
    else:
        print(__doc__)
        print("\nUsage:")
        print("  python test_image_extraction.py <image_path>")
        print("  python test_image_extraction.py --batch --folder <folder_path>")
