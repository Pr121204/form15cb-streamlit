import os
import shutil
# Path to tesseract executable - change this after installing Tesseract on your machine
# Example Windows: r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSERACT_PATH = os.getenv("TESSERACT_PATH") or shutil.which("tesseract") or "/usr/bin/tesseract"

# folders (absolute paths to avoid confusion)
ROOT = os.getcwd()
INPUT_FOLDER = os.path.join(ROOT, "data", "input")
OUTPUT_FOLDER = os.path.join(ROOT, "data", "output")
LOG_FOLDER = os.path.join(ROOT, "data", "logs")

# ensure folders exist can be called from file_manager.ensure_folders
