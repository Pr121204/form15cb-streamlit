from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Dict, Optional

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


PROMPT = """Extract the following fields from this invoice as JSON only, no explanation:
{
  "remitter_name": "exact legal company name of the sender/issuer/from-party",
  "remitter_address": "full address of the sender/issuer",
  "beneficiary_name": "exact legal company name of the recipient/to-party/bill-to party",
  "invoice_number": "invoice number or reference number as printed",
  "invoice_date": "date in DD/MM/YYYY format",
  "amount": "total invoice amount as a number only, no symbols, no commas",
  "currency": "3-letter ISO currency code (EUR, USD, GBP, JPY, etc.)"
}
Return only valid JSON. If a field cannot be found, return an empty string for it.
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
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(text, fmt).date()
            return d.isoformat(), d.strftime("%d.%m.%Y")
        except ValueError:
            continue
    return "", text


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

    # Beneficiary (foreign) address pattern like: "Ullsteinstra3e 128, 12109 Berlin, Germany"
    m_foreign = re.search(
        r"([A-Za-z0-9\.\-\/ ]{4,80}),\s*(\d{4,6})\s*([A-Za-z\-\s]{2,40}),\s*(Germany|Spain|Poland|USA|United Kingdom|UK|Singapore|United States of America)",
        t,
        flags=re.IGNORECASE,
    )
    if m_foreign:
        street = " ".join(m_foreign.group(1).split()).strip(" ,")
        pin = m_foreign.group(2).strip()
        city = " ".join(m_foreign.group(3).split()).strip(" ,")
        country = m_foreign.group(4).strip()
        out["beneficiary_street"] = street
        out["beneficiary_zip_text"] = pin
        out["beneficiary_city"] = city
        out["beneficiary_country_text"] = country
    if not str(out.get("beneficiary_country_text") or "").strip():
        explicit_country = _extract_country_from_text(t)
        if explicit_country:
            out["beneficiary_country_text"] = explicit_country.title()
            logger.info("country_text_extracted_from_ocr country=%s", out["beneficiary_country_text"])

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
    }
    if not text or len(text.strip()) < 20:
        logger.warning("gemini_extract_skipped reason=empty_or_short_text text_len=%s", len(str(text or "")))
        return out
    if not GEMINI_API_KEY or genai is None:
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
    iso_date, display_date = parse_invoice_date(out["invoice_date_raw"])
    out["invoice_date_iso"] = iso_date
    out["invoice_date_display"] = display_date
    out["amount"] = _normalize_amount(str(parsed.get("amount") or ""))
    out["currency_short"] = str(parsed.get("currency") or "").strip().upper()
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
        },
    )
    return out
