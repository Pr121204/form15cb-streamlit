import pdfplumber
import io

def extract_text_from_pdf(path):
    """Extract text from a PDF file at 'path'. Returns empty string if no embedded text."""
    text = ""
    try:
        with pdfplumber.open(path) as pdf:
            for p in pdf.pages:
                text += p.extract_text() or "\n"
    except Exception:
        return ""
    return text
