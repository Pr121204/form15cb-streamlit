from __future__ import annotations

import re
import unicodedata

SAFE_PUNCTUATION = ".,;:!?()-_/\\#&%+@='\"[]{}"

# Characters that are not reliably handled by NFD decomposition
# and frequently seen in invoice text from multiple locales.
SPECIAL_MAP = {
    # German
    "ü": "u",
    "Ü": "U",
    "ö": "o",
    "Ö": "O",
    "ä": "a",
    "Ä": "A",
    "ß": "ss",
    # Portuguese / Spanish
    "ã": "a",
    "õ": "o",
    "ç": "c",
    "Ç": "C",
    "á": "a",
    "à": "a",
    "â": "a",
    "Â": "A",
    "é": "e",
    "ê": "e",
    "É": "E",
    "í": "i",
    "Í": "I",
    "ó": "o",
    "ô": "o",
    "Ó": "O",
    "ú": "u",
    "Ú": "U",
    "ñ": "n",
    "Ñ": "N",
    # French
    "è": "e",
    "ë": "e",
    "î": "i",
    "ï": "i",
    "ù": "u",
    "û": "u",
    "ẞ": "SS",
    "œ": "oe",
    "Œ": "OE",
    "æ": "ae",
    "Æ": "AE",
    # Turkish
    "ı": "i",
    "İ": "I",
    "ğ": "g",
    "Ğ": "G",
    "ş": "s",
    "Ş": "S",
    # Polish / Czech / Romanian
    "ł": "l",
    "Ł": "L",
    "ź": "z",
    "ż": "z",
    "š": "s",
    "č": "c",
    "ž": "z",
    "ř": "r",
    "ă": "a",
    "ș": "s",
    "ț": "t",
    # Scandinavian
    "å": "a",
    "Å": "A",
    "ø": "o",
    "Ø": "O",
    "ð": "d",
    "Ð": "D",
    "þ": "th",
    "Þ": "TH",
    "ĳ": "ij",
    "Ĳ": "IJ",
    # Punctuation lookalikes
    "\u2019": "'",
    "\u2018": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": "-",
    "\u00b0": "",
    "\u00a0": " ",
    "ƒ": "f",
}


def _apply_special_map(text: str) -> str:
    out = text
    for src, dst in SPECIAL_MAP.items():
        out = out.replace(src, dst)
    return out


def normalize_invoice_text(text: str, keep_newlines: bool = True) -> str:
    if not text:
        return ""
    t = _apply_special_map(str(text))
    # Remove combining marks while preserving base letters and unknown scripts.
    t = unicodedata.normalize("NFD", t)
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    # Remove only non-printable control chars; keep unknown/non-transliterable chars.
    t = "".join(ch if (ch in "\n\t" or unicodedata.category(ch) != "Cc") else " " for ch in t)

    if keep_newlines:
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in t.splitlines()]
        # Keep structure, but avoid too many blank lines.
        collapsed: list[str] = []
        blank_run = 0
        for line in lines:
            if line:
                collapsed.append(line)
                blank_run = 0
            else:
                blank_run += 1
                if blank_run <= 1:
                    collapsed.append("")
        return "\n".join(collapsed).strip()

    return re.sub(r"\s+", " ", t).strip()


def normalize_single_line_text(text: str) -> str:
    return normalize_invoice_text(text, keep_newlines=False)


def is_ascii_clean(text: str) -> bool:
    s = str(text or "")
    return all(ord(ch) < 128 for ch in s)
