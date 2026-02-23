from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv

try:
    from google import genai
except Exception:  # pragma: no cover
    genai = None  # type: ignore


load_dotenv()

try:
    import streamlit as st

    GEMINI_API_KEY: Optional[str] = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY"))
    GEMINI_MODEL_NAME: str = st.secrets.get("GEMINI_MODEL_NAME", os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash"))
except Exception:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")

from modules.master_lookups import load_country_code_map, match_remitter, resolve_country_code
from modules.logger import get_logger


logger = get_logger()

MASTER_DIR = Path(__file__).resolve().parent.parent / "data" / "master"


def _load_json(path: Path, default):
    """Load JSON file with fallback to default value."""
    try:
        with open(path, "r", encoding="utf8") as f:
            return json.load(f)
    except Exception:
        return default


def _load_purpose_rows() -> List[Dict[str, str]]:
    raw = _load_json(MASTER_DIR / "Purpose_code_List.json", {"purpose_codes": []})
    rows = raw.get("purpose_codes", []) if isinstance(raw, dict) else []
    out: List[Dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("purpose_code") or "").strip().upper()
        group = str(row.get("group_name") or "").strip()
        if code:
            out.append({"purpose_code": code, "group_name": group})
    return out


def _purpose_indexes() -> Tuple[set[str], Dict[str, str]]:
    valid_codes: set[str] = set()
    code_to_group: Dict[str, str] = {}
    for row in _load_purpose_rows():
        code = str(row.get("purpose_code") or "").strip().upper()
        group = str(row.get("group_name") or "").strip()
        if not code:
            continue
        valid_codes.add(code)
        if group and code not in code_to_group:
            code_to_group[code] = group
    return valid_codes, code_to_group


def _is_valid_purpose_code(code: str) -> bool:
    normalized = str(code or "").strip().upper()
    if not normalized:
        return False
    valid_codes, _ = _purpose_indexes()
    return normalized in valid_codes


def _purpose_group_for_code(code: str) -> str:
    normalized = str(code or "").strip().upper()
    if not normalized:
        return ""
    _, code_to_group = _purpose_indexes()
    return str(code_to_group.get(normalized) or "")


PROMPT = """Extract the following fields from this invoice as JSON only, no explanation:
{
  "remitter_name": "exact legal company name of the sender/issuer/from-party",
  "remitter_address": "full address of the sender/issuer",
  "beneficiary_name": "exact legal company name of the recipient/to-party/bill-to party",
  "invoice_number": "invoice number or reference number as printed",
  "invoice_date": "date in DD/MM/YYYY format",
  "amount": "total invoice amount as a number only, no symbols, no commas",
  "currency": "3-letter ISO currency code (EUR, USD, GBP, JPY, etc.)",
  "nature_of_remittance": "best matching label from this list - return EXACT label text or empty string: ADVERTISEMENT FEE, AMC CHARGES, ARCHITECTURAL SERVICES, BANDWIDTH CHARGES, BROKERAGE CHARGES, BUSINESS INCOME OTHER THAN THAT COVERED BY CATEGORIES ABOVE, CARGO HANDLING SERVICES INSPECTION & LOGISTICS SERVICES, CELLULAR ROAMING CHARGES, CHARTER HIRE CHARGES (SHIPPING), CLEARING & FORWARDING CHARGES, COMMISSION, COMPUTER & INFORMATION SERVICES, CONSULTING SERVICES, CUSTOM HOUSE AGENT CHARGES, DESIGNING CHARGES, DISTRIBUTION SERVICES, EDUCATIONAL SERVICES, ENGINEERING SERVICES, FACILITY RELATED SERVICES, FEES FOR TECHNICAL SERVICES, FOREIGN COMMISSION, FOREIGN HOSPITALITY, FOREIGN INSURANCE, FOREIGN SERVICE CHARGES, FREIGHT, GENERAL INSURANCE CLAIMS, GENERAL INSURANCE PREMIUM, GRAPHIC DESIGN CHARGES, HEALTH SERVICES, HOSPITALITY SERVICES, HOTEL & LODGING CHARGES, ISD CHARGES, INSURANCE AGENCY & BROKERAGE, INSURANCE PREMIUM, INSURANCE, INTERNET CHARGES, KNOWLEDGE BASED CONSULTING, LEGAL SERVICES, LIFE INSURANCE, LIFE INSURANCE PREMIUM, LIFE INSURANCE CLAIMS, LODGING CHARGES, MAINTENANCE & REPAIR CHARGES, MANAGEMENT FEES, MARINE INSURANCE PREMIUM, MARINE INSURANCE CLAIMS, MISCELLANEOUS PERSONAL SERVICES, MISCELLANEOUS PUBLISHED WORK, MISCELLANEOUS SERVICES, MISCELLANEOUS TECHNICAL SERVICES, MISCELLANEOUS TRANSPORT SERVICES, OPERATIONAL CHARGES FOR OVERSEAS OFFICES, OTHER DISTRIBUTION SERVICES, OTHER FINANCE CHARGES, OTHER MARITIME TRAFFIC MANAGEMENT, OTHER MISCELLANEOUS BUSINESS SERVICES, OTHER MISCELLANEOUS EDUCATIONAL SERVICES, OTHER MISCELLANEOUS HEALTH SERVICES, OTHER MISCELLANEOUS PROFESSIONAL SERVICES, OTHER MISCELLANEOUS SERVICES, PATIENT TREATMENT CHARGES, PERSONAL SERVICES, PHOTOGRAPHY CHARGES, POSTAL SERVICES, PUBLICATION SERVICES, PUBLISHING SERVICES, RADIO AND TELEVISION SERVICES, REIMBURSEMENT OF EXPENSES, REPAIR & MAINTENANCE CHARGES, REPAIR SERVICES, RESEARCH & DEVELOPMENT CHARGES, RESEARCH SERVICES, ROYALTY, ROYALTY ON COPYRIGHTS AND LITERARY WORKS, ROYALTY ON DESIGN & TRADEMARK, ROYALTY ON INDUSTRIAL PROCESS, ROYALTY ON PATENT, ROYALTY ON TECHNICAL KNOW-HOW, SOFTWARE LICENCES, SPACE & TIME LEASING & RENTAL CHARGES, SPACE AND TIME LEASING, SPACE/BANDWIDTH LEASING FOR TELECOMMUNICATION SERVICES, SPECIAL DRAWING RIGHTS (SDRS), SUBSCRIPTION FEES, SUBSCRIPTION FOR PERIODICALS & NEWSPAPERS, SUBSCRIPTION FOR PROFESSIONAL ASSOCIATIONS, SUBSCRIPTION FOR TECHNICAL DATA, SUBSCRIPTION SERVICES, SUPPORT & MAINTENANCE CHARGES, TAX AUDIT FEES, TECHNICAL ASSISTANCE FEES, TECHNICAL SERVICE FEES, TECHNICAL SUPPORT & MAINTENANCE, TELECOMMUNICATION CHARGES, TESTING & ANALYSIS CHARGES, TESTING CHARGES, CONSULTING SERVICES FOR TECHNICAL SERVICES, CONSULTANCY, TRAINING CHARGES, TRANSPORT SERVICES CHARGES, TRANSPORT SERVICES, TRANSPORT/SHIPPING CHARGES, TRAVEL CHARGES, TRAVEL & ACCOMODATION CHARGES, TRAVEL & ACCOMMODATION CHARGES, TRAVEL INSURANCE, TRIBUNAL LEVY, TRIMMING CHARGES, VIDEO PRODUCTION CHARGES, VISA FEES, VISA AND VACCINATION & HEALTH CHARGES, VISIT VISA FEES",
  "purpose_group": "best matching RBI purpose group name - return EXACT group name or empty string (e.g. 'Other Business Services', 'Charges for the use of intellectual property n.i.e', 'Telecommunication, Computer & Information Services', 'Financial and Insurance Services')",
  "purpose_code": "best matching RBI purpose code from the group above - return EXACT code (e.g. S1023, S0014, S1005) or empty string if unsure"
}
Return only valid JSON. If a field cannot be found, return an empty string for it.
Important:
- invoice_number must come from labels like "Invoice No", "Invoice Number", or "Reference Number".
- invoice_date must come from invoice date labels and must preserve the printed date value.
- For nature_of_remittance, purpose_group, purpose_code: return your best matching suggestion from the lists even if not 100% certain. Always return something unless the invoice gives absolutely no clue. Prefer returning a close match over returning empty.
"""


def _norm_country_token(raw: str) -> str:
    t = re.sub(r"[^A-Za-z\s]", " ", str(raw or "").upper())
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _resolve_country_candidate(raw: str) -> str:
    aliases = {
        "USA": "UNITED STATES OF AMERICA",
        "US": "UNITED STATES OF AMERICA",
        "U S A": "UNITED STATES OF AMERICA",
        "UK": "UNITED KINGDOM OF GREAT BRITAIN AND NORTHERN IRELAND",
        "U K": "UNITED KINGDOM OF GREAT BRITAIN AND NORTHERN IRELAND",
    }
    c = _norm_country_token(raw)
    if not c:
        return ""
    c = aliases.get(c, c)
    if resolve_country_code(c):
        return c
    if c in load_country_code_map():
        return c
    return ""


def _extract_country_from_text(text: str) -> str:
    for line in str(text or "").splitlines():
        s = " ".join(line.split()).strip()
        if not s:
            continue
        m = re.search(r"\bCOUNTRY\b\s*[:\-]\s*([A-Za-z][A-Za-z .&\-]{2,80})$", s, flags=re.IGNORECASE)
        if m:
            country = _resolve_country_candidate(m.group(1))
            if country:
                return country
        m = re.search(r"\bCOUNTRY OF (?:BENEFICIARY|REMITTANCE|DESTINATION)\b\s*[:\-]?\s*([A-Za-z][A-Za-z .&\-]{2,80})$", s, flags=re.IGNORECASE)
        if m:
            country = _resolve_country_candidate(m.group(1))
            if country:
                return country
        m = re.search(r"\b\d{4,6}\b[,\s]+([A-Za-z][A-Za-z .&\-]{2,50})\s*$", s)
        if m:
            country = _resolve_country_candidate(m.group(1))
            if country:
                return country
    return ""


def _extract_json(text: str) -> Dict[str, str]:
    if not text:
        return {}
    s = text.strip()
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else {}
    except Exception:
        pass
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    if not m:
        return {}
    try:
        v = json.loads(m.group(0))
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def _normalize_amount(raw: str) -> str:
    return re.sub(r"[^0-9.]", "", str(raw or ""))


def _normalize_company_name(name: str) -> str:
    n = str(name or "").strip()
    if not n:
        return ""
    # Common OCR confusion in Bosch IO invoices: lIO vs IO.
    n = re.sub(r"Bosch[\.\s]*lIO", "Bosch.IO", n, flags=re.IGNORECASE)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def parse_invoice_date(raw: str) -> tuple[str, str]:
    text = str(raw or "").strip()
    if not text:
        return "", ""
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            d = datetime.strptime(text, fmt).date()
            return d.isoformat(), d.strftime("%d.%m.%Y")
        except ValueError:
            continue
    return "", text


def _fallback_invoice_fields_from_text(text: str) -> Dict[str, str]:
    out = {"invoice_number": "", "invoice_date_raw": ""}
    t = str(text or "")
    if not t:
        return out

    number_patterns = [
        r"(?im)\b(?:invoice\s*(?:no\.?|number|#)|inv\.?\s*no\.?|reference\s*no\.?)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\/\-_\.]{2,})",
        r"(?im)\binvoice\s*#\s*([A-Z0-9][A-Z0-9\/\-_\.]{2,})",
    ]
    for pat in number_patterns:
        m = re.search(pat, t)
        if m:
            out["invoice_number"] = m.group(1).strip().strip(".,;:")
            break

    date_patterns = [
        r"(?im)\b(?:invoice\s*date|date)\s*[:\-]?\s*([0-3]?\d[./-][01]?\d[./-](?:19|20)?\d{2})",
        r"(?im)\bDT\.?\s*([0-3]?\d[./-][01]?\d[./-](?:19|20)?\d{2})\b",
        r"(?im)\b(?:invoice\s*date|date)\s*[:\-]?\s*((?:19|20)\d{2}[./-][01]?\d[./-][0-3]?\d)\b",
    ]
    for pat in date_patterns:
        m = re.search(pat, t)
        if m:
            out["invoice_date_raw"] = m.group(1).strip().strip(".,;:")
            break
    return out


def _likely_indian_entity(name: str) -> bool:
    n = str(name or "").strip()
    if not n:
        return False
    if match_remitter(n):
        return True
    u = n.upper()
    cues = [
        "PRIVATE LIMITED",
        "PVT LTD",
        "PVT. LTD",
        "INDIA",
        "INDIAN",
    ]
    return any(c in u for c in cues)


def _likely_foreign_entity(name: str) -> bool:
    u = str(name or "").upper()
    cues = [
        " GMBH",
        " S.L",
        " SP Z O O",
        " LLC",
        " B.V",
        " AG",
        " BV",
        " PLC",
    ]
    return any(c in u for c in cues)


def normalize_party_roles(extracted: Dict[str, str]) -> Dict[str, str]:
    """
    Ensure remitter is the likely Indian payer and beneficiary is the likely foreign party.
    This is a post-processing guard for invoices where issuer/receiver roles are flipped by AI.
    """
    out = dict(extracted or {})
    remitter = _normalize_company_name(str(out.get("remitter_name") or "").strip())
    beneficiary = _normalize_company_name(str(out.get("beneficiary_name") or "").strip())
    out["remitter_name"] = remitter
    out["beneficiary_name"] = beneficiary
    if not remitter or not beneficiary:
        return out

    rem_is_indian = _likely_indian_entity(remitter)
    ben_is_indian = _likely_indian_entity(beneficiary)
    rem_is_foreign = _likely_foreign_entity(remitter)
    ben_is_foreign = _likely_foreign_entity(beneficiary)

    should_swap = (ben_is_indian and not rem_is_indian) or (rem_is_foreign and not ben_is_foreign)
    if should_swap:
        out["remitter_name"], out["beneficiary_name"] = beneficiary, remitter
        # Prevent appending clearly wrong foreign address to Indian remitter after role swap.
        out["remitter_address"] = ""
    return out


def _enrich_addresses_from_text(text: str, extracted: Dict[str, str]) -> Dict[str, str]:
    out = dict(extracted)
    t = str(text or "")
    if not t:
        return out

    def _clean(s: str) -> str:
        return " ".join(str(s or "").split()).strip(" ,.;:-")

    # Prefer legal/company address lines over correspondence PO box lines.
    legal_patterns = [
        r"(?im)\b([A-Za-z][A-Za-z0-9\.\-\/ ]{3,120}\d{1,6})\s*,\s*DE\s*-\s*(\d{5})\s*([A-Za-z][A-Za-z\-\s]{2,60})(?=[,\n]|$)",
        r"(?im)\b([A-Za-z][A-Za-z0-9\.\-\/ ]{3,120}\d{1,6})\s*,\s*(?:[A-Z]{2}\s*-\s*)?(\d{4,6})\s*([A-Za-z][A-Za-z\-\s]{2,60})(?=[,\n]|$)",
    ]
    po_box_patterns = [
        r"(?im)\b(Postfach\s+[0-9 ]{3,30})\s*,\s*DE\s*-\s*(\d{5})\s*([A-Za-z][A-Za-z\-\s]{2,60})(?=[,\n]|$)",
        r"(?im)\b(Postfach\s+[0-9 ]{3,30})\s*,\s*(?:[A-Z]{2}\s*-\s*)?(\d{4,6})\s*([A-Za-z][A-Za-z\-\s]{2,60})(?=[,\n]|$)",
    ]

    chosen = None
    for pat in legal_patterns:
        m = re.search(pat, t)
        if m:
            chosen = (m.group(1), m.group(2), m.group(3), "legal")
            break
    if chosen is None:
        for pat in po_box_patterns:
            m = re.search(pat, t)
            if m:
                chosen = (m.group(1), m.group(2), m.group(3), "po_box")
                break

    if chosen is not None:
        street, pin, city, _source = chosen
        out["beneficiary_street"] = _clean(street)
        out["beneficiary_zip_text"] = _clean(pin)
        out["beneficiary_city"] = _clean(city)
        if re.search(r"\bDE\s*-\s*\d{5}\b", t, flags=re.IGNORECASE):
            out["beneficiary_country_text"] = "Germany"
    if not str(out.get("beneficiary_country_text") or "").strip():
        explicit_country = _extract_country_from_text(t)
        if explicit_country:
            out["beneficiary_country_text"] = explicit_country.title()
            logger.info("country_text_extracted_from_ocr country=%s", out["beneficiary_country_text"])
    if not str(out.get("beneficiary_country_text") or "").strip():
        if re.search(r"\bGERMANY\b", t, flags=re.IGNORECASE):
            out["beneficiary_country_text"] = "Germany"
        elif re.search(r"\bDE\s*-\s*\d{5}\b", t, flags=re.IGNORECASE):
            out["beneficiary_country_text"] = "Germany"

    # Remitter (Indian) address pattern from ship/services block with 6-digit PIN.
    if not str(out.get("remitter_address") or "").strip():
        m_india = re.search(
            r"(Cyber park[^\n,]*,\s*No\.\s*76,\s*77[^\n]*?(?:Bangalore|Bengaluru)[^\n]*)",
            t,
            flags=re.IGNORECASE,
        )
        if not m_india:
            m_india = re.search(
                r"([A-Za-z0-9,\-\s]{10,120}\b(?:Bangalore|Bengaluru)\b[^\n]{0,40}\b\d{6}\b)",
                t,
                flags=re.IGNORECASE,
            )
        if m_india:
            out["remitter_address"] = " ".join(m_india.group(1).split()).strip(" ,")
    return out


def _normalize_for_matching(s: str) -> str:
    """Normalize string for fuzzy matching: uppercase, remove non-alphanumeric, collapse spaces."""
    t = re.sub(r"[^A-Za-z0-9\s]", " ", str(s or "")).upper()
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _fuzzy_match_nature(gemini_suggestion: str) -> str:
    """
    Fuzzy-match Gemini's nature_of_remittance suggestion against nature_rem_category.json.
    Returns the exact label from the JSON if a match is found, otherwise empty string.
    """
    if not gemini_suggestion or not gemini_suggestion.strip():
        return ""
    
    try:
        nature_data = _load_json(MASTER_DIR / "nature_rem_category.json", [])
        if not isinstance(nature_data, list):
            return ""
        
        gemini_norm = _normalize_for_matching(gemini_suggestion)
        if not gemini_norm:
            return ""
        
        # First try exact match
        for row in nature_data:
            if not isinstance(row, dict):
                continue
            label = str(row.get("label") or "").strip()
            if _normalize_for_matching(label) == gemini_norm:
                return label
        
        # If no exact match, try substring/partial match
        gemini_words = set(gemini_norm.split())
        best_match = None
        best_score = 0
        
        for row in nature_data:
            if not isinstance(row, dict):
                continue
            label = str(row.get("label") or "").strip()
            label_norm = _normalize_for_matching(label)
            label_words = set(label_norm.split())
            
            # Calculate overlap score
            overlap = len(gemini_words & label_words)
            if overlap > best_score:
                best_score = overlap
                best_match = label
        
        # Return match only if significant overlap (at least 50% of words match)
        if best_match and best_score >= max(2, len(gemini_words) // 2):
            return best_match
        
        return ""
    
    except Exception as e:
        logger.warning("fuzzy_match_nature_error error=%s", str(e))
        return ""


def _fuzzy_match_purpose_group(gemini_suggestion: str) -> str:
    """
    Fuzzy-match Gemini's purpose_group suggestion against Purpose_code_List.json group_names.
    Returns the exact group_name from the JSON if a match is found, otherwise empty string.
    """
    if not gemini_suggestion or not gemini_suggestion.strip():
        return ""
    
    try:
        purpose_data = _load_json(MASTER_DIR / "Purpose_code_List.json", {"purpose_codes": []})
        purpose_codes = purpose_data.get("purpose_codes", [])
        
        if not isinstance(purpose_codes, list):
            return ""
        
        # Extract unique group names
        group_names = set()
        for row in purpose_codes:
            if isinstance(row, dict):
                group = str(row.get("group_name") or "").strip()
                if group:
                    group_names.add(group)
        
        gemini_norm = _normalize_for_matching(gemini_suggestion)
        if not gemini_norm:
            return ""
        
        # First try exact match
        for group in group_names:
            if _normalize_for_matching(group) == gemini_norm:
                return group
        
        # If no exact match, try substring/partial match
        gemini_words = set(gemini_norm.split())
        best_match = None
        best_score = 0
        
        for group in group_names:
            group_norm = _normalize_for_matching(group)
            group_words = set(group_norm.split())
            
            # Calculate overlap score
            overlap = len(gemini_words & group_words)
            if overlap > best_score:
                best_score = overlap
                best_match = group
        
        # Return match only if significant overlap
        if best_match and best_score >= max(2, len(gemini_words) // 2):
            return best_match
        
        return ""
    
    except Exception as e:
        logger.warning("fuzzy_match_purpose_group_error error=%s", str(e))
        return ""


def _fuzzy_match_purpose_code(gemini_suggestion: str, purpose_group: str = "") -> str:
    """
    Fuzzy-match Gemini's purpose_code suggestion against Purpose_code_List.json codes.
    If purpose_group is provided, only match within that group.
    Returns the exact code from the JSON if a match is found, otherwise empty string.
    """
    if not gemini_suggestion or not gemini_suggestion.strip():
        return ""
    
    try:
        purpose_data = _load_json(MASTER_DIR / "Purpose_code_List.json", {"purpose_codes": []})
        purpose_codes = purpose_data.get("purpose_codes", [])
        
        if not isinstance(purpose_codes, list):
            return ""
        
        gemini_norm = _normalize_for_matching(gemini_suggestion)
        if not gemini_norm:
            return ""
        
        # Filter by group if provided
        filtered_codes = []
        for row in purpose_codes:
            if not isinstance(row, dict):
                continue
            code = str(row.get("purpose_code") or "").strip().upper()
            group = str(row.get("group_name") or "").strip()
            
            if not code:
                continue
            
            # If purpose_group is specified, only consider codes from that group
            if purpose_group and _normalize_for_matching(group) != _normalize_for_matching(purpose_group):
                continue
            
            filtered_codes.append(code)
        
        # First try exact match (case-insensitive)
        for code in filtered_codes:
            if _normalize_for_matching(code) == gemini_norm:
                return code
        
        return ""
    
    except Exception as e:
        logger.warning("fuzzy_match_purpose_code_error error=%s", str(e))
        return ""


# Keyword-based fallback mappers for when Gemini returns empty
KEYWORD_NATURE_MAP = {
    "participant fee": "FEES FOR TECHNICAL SERVICES",
    "training": "FEES FOR TECHNICAL SERVICES",
    "seminar": "FEES FOR TECHNICAL SERVICES",
    "subscription": "SUBSCRIPTION FEES",
    "licence": "SOFTWARE LICENCES",
    "license": "SOFTWARE LICENCES",
    "royalt": "ROYALTY",
    "consult": "CONSULTING SERVICES",
    "amc": "AMC CHARGES",
    "maintenance": "AMC CHARGES",
    "reimburs": "REIMBURSEMENT OF EXPENSES",
    "advertisement": "ADVERTISEMENT FEE",
    "software": "SOFTWARE LICENCES",
}

KEYWORD_PURPOSE_MAP = {
    "participant fee": ("Other Business Services", "S1023"),
    "training": ("Other Business Services", "S1023"),
    "seminar": ("Other Business Services", "S1023"),
    "subscription": ("Telecommunication, Computer & Information Services", "S1022"),
    "software": ("Telecommunication, Computer & Information Services", "S1022"),
    "licence": ("Telecommunication, Computer & Information Services", "S1022"),
    "royalt": ("Charges for the use of intellectual property n.i.e", "S1010"),
    "consult": ("Other Business Services", "S1005"),
    "amc": ("Other Business Services", "S1023"),
    "maintenance": ("Other Business Services", "S1023"),
}


def keyword_fallback(ocr_text: str) -> tuple[str, str, str]:
    """
    Fallback keyword matcher for when Gemini returns empty for nature/group/code.
    Searches OCR text for common keywords and returns best matching nature/group/code.
    Returns tuple: (nature_label, purpose_group, purpose_code)
    """
    text_lower = str(ocr_text or "").lower()
    nature = ""
    group = ""
    code = ""
    
    # Find matching nature
    for kw, val in KEYWORD_NATURE_MAP.items():
        if kw in text_lower:
            nature = val
            break
    
    # Find matching group and code
    for kw, (grp, cd) in KEYWORD_PURPOSE_MAP.items():
        if kw in text_lower:
            group = grp
            code = cd
            break
    
    return nature, group, code


def extract_invoice_core_fields(text: str) -> Dict[str, str]:
    out = {
        "remitter_name": "",
        "remitter_address": "",
        "beneficiary_name": "",
        "invoice_number": "",
        "invoice_date_raw": "",
        "invoice_date_iso": "",
        "invoice_date_display": "",
        "amount": "",
        "currency_short": "",
        "nature_of_remittance": "",
        "purpose_group": "",
        "purpose_code": "",
    }
    if not text or len(text.strip()) < 20:
        fallback_fields = _fallback_invoice_fields_from_text(text)
        out["invoice_number"] = fallback_fields.get("invoice_number", "")
        out["invoice_date_raw"] = fallback_fields.get("invoice_date_raw", "")
        iso_date, display_date = parse_invoice_date(out["invoice_date_raw"])
        out["invoice_date_iso"] = iso_date
        out["invoice_date_display"] = display_date
        logger.warning("gemini_extract_skipped reason=empty_or_short_text text_len=%s", len(str(text or "")))
        return out
    if not GEMINI_API_KEY or genai is None:
        fallback_fields = _fallback_invoice_fields_from_text(text)
        out["invoice_number"] = fallback_fields.get("invoice_number", "")
        out["invoice_date_raw"] = fallback_fields.get("invoice_date_raw", "")
        iso_date, display_date = parse_invoice_date(out["invoice_date_raw"])
        out["invoice_date_iso"] = iso_date
        out["invoice_date_display"] = display_date
        logger.warning(
            "gemini_extract_skipped reason=missing_client_or_key has_key=%s genai_loaded=%s",
            bool(GEMINI_API_KEY),
            bool(genai is not None),
        )
        return out
    logger.info("gemini_extract_start text_len=%s model=%s", len(text), GEMINI_MODEL_NAME)
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL_NAME,
        contents=f"{PROMPT}\n\nINVOICE TEXT:\n{text[:60000]}",
        config={
            "temperature": 0,
            "response_mime_type": "application/json",
            "max_output_tokens": 2048,
        },
    )
    parsed = _extract_json(getattr(response, "text", "") or "")
    logger.info("gemini_extract_response parsed_keys=%s", sorted(parsed.keys()))
    out["remitter_name"] = _normalize_company_name(str(parsed.get("remitter_name") or "").strip())
    out["remitter_address"] = str(parsed.get("remitter_address") or "").strip()
    out["beneficiary_name"] = _normalize_company_name(str(parsed.get("beneficiary_name") or "").strip())
    out["invoice_number"] = str(parsed.get("invoice_number") or "").strip()
    out["invoice_date_raw"] = str(parsed.get("invoice_date") or "").strip()
    # Keep Gemini as primary extraction, but recover from OCR text when it misses date/number.
    fallback_fields = _fallback_invoice_fields_from_text(text)
    if not out["invoice_number"]:
        out["invoice_number"] = fallback_fields.get("invoice_number", "")
    if not out["invoice_date_raw"]:
        out["invoice_date_raw"] = fallback_fields.get("invoice_date_raw", "")
    iso_date, display_date = parse_invoice_date(out["invoice_date_raw"])
    out["invoice_date_iso"] = iso_date
    out["invoice_date_display"] = display_date
    out["amount"] = _normalize_amount(str(parsed.get("amount") or ""))
    out["currency_short"] = str(parsed.get("currency") or "").strip().upper()
    
    # Fuzzy-match and set nature_of_remittance
    nature_suggestion = str(parsed.get("nature_of_remittance") or "").strip()
    if nature_suggestion:
        matched_nature = _fuzzy_match_nature(nature_suggestion)
        out["nature_of_remittance"] = matched_nature
        if matched_nature:
            logger.info("nature_of_remittance_matched suggestion=%s matched=%s", nature_suggestion, matched_nature)
    
    # Fuzzy-match and set purpose_group
    group_suggestion = str(parsed.get("purpose_group") or "").strip()
    if group_suggestion:
        matched_group = _fuzzy_match_purpose_group(group_suggestion)
        out["purpose_group"] = matched_group
        if matched_group:
            logger.info("purpose_group_matched suggestion=%s matched=%s", group_suggestion, matched_group)
    
    # Fuzzy-match and set purpose_code (filtered by group if available)
    code_suggestion = str(parsed.get("purpose_code") or "").strip()
    if code_suggestion:
        matched_code = _fuzzy_match_purpose_code(code_suggestion, out["purpose_group"])
        out["purpose_code"] = matched_code
        if matched_code:
            logger.info("purpose_code_matched suggestion=%s matched=%s group=%s", code_suggestion, matched_code, out["purpose_group"])
    if out["purpose_code"] and not _is_valid_purpose_code(out["purpose_code"]):
        logger.warning("purpose_code_discarded_invalid source=gemini code=%s", out["purpose_code"])
        out["purpose_code"] = ""
    
    # Keyword fallback for any empty fields
    # IMPORTANT: Only apply fallback if fields are actually empty. Never mix code/group from different sources.
    if not out["nature_of_remittance"] or not out["purpose_code"]:
        fallback_nature, fallback_group, fallback_code = keyword_fallback(text)
        if not out["nature_of_remittance"] and fallback_nature:
            # Fuzzy-match the fallback value to get exact master label
            matched = _fuzzy_match_nature(fallback_nature)
            out["nature_of_remittance"] = matched if matched else fallback_nature
            logger.info("nature_of_remittance_fallback keyword=%s matched=%s", fallback_nature, out["nature_of_remittance"])
        # Only apply code fallback if no code was matched from Gemini
        if not out["purpose_code"] and fallback_code:
            # Fuzzy-match the fallback value to get exact master code
            matched = _fuzzy_match_purpose_code(fallback_code, out["purpose_group"])
            out["purpose_code"] = matched if matched and _is_valid_purpose_code(matched) else ""
            logger.info("purpose_code_fallback keyword=%s matched=%s group=%s", fallback_code, out["purpose_code"], out.get("purpose_group", ""))
    if out["purpose_code"]:
        # Keep group/code pair deterministic. Code is authoritative.
        derived_group = _purpose_group_for_code(out["purpose_code"])
        if derived_group:
            out["purpose_group"] = derived_group
    
    # NEVER apply fallback to purpose_group independently
    # If purpose_code exists, state_build will derive group from the code's JSON record
    # If purpose_code is empty, the form UI will let user select group manually

    
    out = normalize_party_roles(out)
    out = _enrich_addresses_from_text(text, out)
    logger.info(
        "gemini_extract_done summary=%s",
        {
            "remitter_name": out.get("remitter_name", ""),
            "beneficiary_name": out.get("beneficiary_name", ""),
            "invoice_number": out.get("invoice_number", ""),
            "amount": out.get("amount", ""),
            "currency_short": out.get("currency_short", ""),
            "beneficiary_country_text": out.get("beneficiary_country_text", ""),
            "nature_of_remittance": out.get("nature_of_remittance", ""),
            "purpose_group": out.get("purpose_group", ""),
            "purpose_code": out.get("purpose_code", ""),
        },
    )
    return out
