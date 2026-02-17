import pytesseract
from pdf2image import convert_from_path, convert_from_bytes
from PIL import Image
import io
from config.settings import TESSERACT_PATH
from modules.preprocessor import enhance_image_for_ocr

# set tesseract path from config
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

def ocr_image_pil(pil_image, lang='eng'):
    try:
        processed = enhance_image_for_ocr(pil_image)
        text = pytesseract.image_to_string(processed, lang=lang)
    except Exception as e:
        # fallback: try without preprocessing
        text = pytesseract.image_to_string(pil_image)
    return text

def extract_text_from_image_file(path_or_bytes):
    # if bytes provided, use convert_from_bytes; otherwise convert_from_path
    if isinstance(path_or_bytes, (bytes, bytearray)):
        images = convert_from_bytes(path_or_bytes, dpi=300)
    else:
        images = convert_from_path(path_or_bytes, dpi=300)
    text = []
    for img in images:
        text.append(ocr_image_pil(img))
    return "\n".join(text)


# """
# Enhanced OCR Engine with Improved Preprocessing

# This module uses the improved preprocessor for significantly better OCR results.
# """

# import pytesseract
# from pdf2image import convert_from_path, convert_from_bytes
# from PIL import Image
# import io
# import logging
# from config.settings import TESSERACT_PATH
# from modules.preprocessor import enhance_image_for_ocr

# logger = logging.getLogger(__name__)

# # Set tesseract path from config
# try:
#     pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
# except Exception as e:
#     logger.warning(f"Could not set Tesseract path: {e}")


# def ocr_image_pil(pil_image, lang='eng'):
#     """
#     Perform OCR on a PIL Image with enhanced preprocessing.
    
#     Args:
#         pil_image: PIL Image object
#         lang: Tesseract language (default: 'eng')
        
#     Returns:
#         Extracted text string
#     """
#     try:
#         logger.info("🔧 Preprocessing image for OCR...")
        
#         # Apply enhanced preprocessing
#         processed = enhance_image_for_ocr(pil_image)
        
#         logger.info("📖 Running Tesseract OCR...")
        
#         # Run Tesseract with optimized config
#         # PSM 1 = Automatic page segmentation with OSD (best for forms)
#         # PSM 3 = Fully automatic page segmentation, but no OSD (alternative)
#         custom_config = r'--oem 3 --psm 1'
        
#         text = pytesseract.image_to_string(
#             processed,
#             lang=lang,
#             config=custom_config
#         )
        
#         logger.info(f"✅ OCR complete! Extracted {len(text)} characters")
        
#         if len(text) < 100:
#             logger.warning(f"⚠️ OCR result very short ({len(text)} chars). Document may be poor quality.")
        
#         return text
        
#     except pytesseract.TesseractNotFoundError:
#         logger.error("❌ Tesseract not found! Please install Tesseract OCR.")
#         logger.error("   Download from: https://github.com/tesseract-ocr/tesseract")
#         raise
        
#     except Exception as e:
#         logger.error(f"❌ OCR failed: {type(e).__name__}: {str(e)}")
        
#         # Try fallback without preprocessing
#         logger.warning("⚠️ Attempting fallback OCR without preprocessing...")
#         try:
#             text = pytesseract.image_to_string(pil_image, lang=lang)
#             logger.info(f"Fallback OCR extracted {len(text)} characters")
#             return text
#         except Exception as fallback_error:
#             logger.error(f"❌ Fallback OCR also failed: {fallback_error}")
#             raise


# def extract_text_from_image_file(path_or_bytes, dpi=300):
#     """
#     Extract text from an image file or PDF using OCR.
    
#     For PDFs, converts each page to image first, then applies OCR.
#     For images, directly applies OCR.
    
#     Args:
#         path_or_bytes: File path string or bytes
#         dpi: Resolution for PDF to image conversion (higher = better quality)
        
#     Returns:
#         Extracted text from all pages/images
#     """
    
#     logger.info("=" * 70)
#     logger.info("STARTING OCR EXTRACTION")
#     logger.info("=" * 70)
    
#     try:
#         # Determine if it's bytes or file path
#         if isinstance(path_or_bytes, (bytes, bytearray)):
#             logger.info("📄 Input: PDF bytes")
#             # Convert PDF bytes to images
#             images = convert_from_bytes(
#                 path_or_bytes,
#                 dpi=dpi,
#                 fmt='png'  # PNG preserves quality better
#             )
#             logger.info(f"📄 Converted PDF to {len(images)} page(s)")
#         else:
#             logger.info(f"📄 Input: File at {path_or_bytes}")
#             # Check if it's a PDF or image
#             if path_or_bytes.lower().endswith('.pdf'):
#                 # Convert PDF file to images
#                 images = convert_from_path(
#                     path_or_bytes,
#                     dpi=dpi,
#                     fmt='png'
#                 )
#                 logger.info(f"📄 Converted PDF to {len(images)} page(s)")
#             else:
#                 # It's an image file, open directly
#                 images = [Image.open(path_or_bytes)]
#                 logger.info("📄 Opened image file")
        
#         # Process each page/image
#         all_text = []
#         for i, img in enumerate(images, 1):
#             logger.info(f"\n🔄 Processing page {i}/{len(images)}...")
#             logger.info(f"   Image size: {img.size[0]}x{img.size[1]}px")
            
#             page_text = ocr_image_pil(img)
            
#             if page_text.strip():
#                 all_text.append(page_text)
#                 logger.info(f"   ✅ Extracted {len(page_text)} characters from page {i}")
#             else:
#                 logger.warning(f"   ⚠️ No text extracted from page {i}")
        
#         # Combine all pages
#         final_text = "\n\n--- PAGE BREAK ---\n\n".join(all_text)
        
#         logger.info("=" * 70)
#         logger.info(f"OCR EXTRACTION COMPLETE")
#         logger.info(f"Total pages processed: {len(images)}")
#         logger.info(f"Total characters extracted: {len(final_text)}")
#         logger.info("=" * 70)
        
#         if len(final_text) < 100:
#             logger.error("❌ OCR produced very little text!")
#             logger.error("Possible issues:")
#             logger.error("  1. Document quality is very poor")
#             logger.error("  2. Document is an image of an image (double compression)")
#             logger.error("  3. Tesseract is not configured properly")
#             logger.error("  4. PDF has encrypted or protected pages")
        
#         return final_text
        
#     except Exception as e:
#         logger.exception("OCR extraction failed")
#         raise RuntimeError(f"OCR extraction failed: {str(e)}")


# # For testing
# if __name__ == "__main__":
#     import sys
#     logging.basicConfig(
#         level=logging.INFO,
#         format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
#     )
    
#     if len(sys.argv) > 1:
#         file_path = sys.argv[1]
        
#         print(f"\n{'='*70}")
#         print(f"TESTING OCR ON: {file_path}")
#         print(f"{'='*70}\n")
        
#         try:
#             text = extract_text_from_image_file(file_path)
            
#             print(f"\n{'='*70}")
#             print("EXTRACTION RESULTS")
#             print(f"{'='*70}")
#             print(f"Total characters: {len(text)}")
#             print(f"Total lines: {len(text.splitlines())}")
#             print(f"\nFirst 1000 characters:")
#             print("-" * 70)
#             print(text[:1000])
#             print("-" * 70)
            
#             if len(text) < 100:
#                 print("\n⚠️ WARNING: Very little text extracted!")
#                 print("   Check document quality and Tesseract installation")
#             else:
#                 print("\n✅ OCR appears successful!")
            
#         except Exception as e:
#             print(f"\n❌ ERROR: {e}")
#             print("\nTroubleshooting:")
#             print("1. Check Tesseract installation: tesseract --version")
#             print("2. Verify file exists and is readable")
#             print("3. Try with a different file")
#             print("4. Check logs for detailed error messages")
    
#     else:
#         print("Usage: python ocr_engine.py <file_path>")
#         print("Example: python ocr_engine.py invoice.pdf")
#         print("         python ocr_engine.py document.jpg")