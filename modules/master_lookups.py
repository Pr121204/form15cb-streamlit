from __future__ import annotations

import functools
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from modules.logger import get_logger


ROOT = Path(__file__).resolve().parent.parent
MASTER_DIR = ROOT / "data" / "master"
logger = get_logger()


def _load_json(path: Path, default):
    try:
        with open(path, "r", encoding="utf8") as f:
            return json.load(f)
    except Exception:
        return default


def _normalize(s: str) -> str:
    t = (s or "").strip().upper()
    t = re.sub(r"[^A-Z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _compact(s: str) -> str:
    return _normalize(s).replace(" ", "")


def _canonical_company_name(s: str) -> str:
    t = _normalize(s)
    if not t:
        return ""
    words = t.split()
    mapped: List[str] = []
    for w in words:
        if w == "PVT":
            mapped.append("PRIVATE")
        elif w == "LTD":
            mapped.append("LIMITED")
        else:
            mapped.append(w)
    # Compact form is intentionally used to absorb master-data spacing errors.
    return "".join(mapped)


@functools.lru_cache(maxsize=1)
def load_bank_details() -> List[Dict[str, str]]:
    rows = _load_json(MASTER_DIR / "bank_details_with_bsr_code.json", [])
    out: List[Dict[str, str]] = []
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "name": str(row.get("Name") or "").strip(),
                "pan": str(row.get("PAN") or "").strip().upper(),
                "bank_name": str(row.get("Name of Bank") or "").strip(),
                "branch": str(row.get("Branch of the bank") or "").strip(),
                "bsr": "".join(ch for ch in str(row.get("BSR code of the bank branch (7 digit)") or "") if ch.isdigit()),
            }
        )
    return out


@functools.lru_cache(maxsize=1)
def load_bank_code_map() -> Dict[str, str]:
    rows = _load_json(MASTER_DIR / "bank_codes.json", [])
    out: Dict[str, str] = {}
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = _normalize(str(row.get("bank") or ""))
            code = str(row.get("code") or "").strip()
            if name and code:
                out[name] = code
    elif isinstance(rows, dict):
        for k, v in rows.items():
            name = _normalize(str(k))
            code = str(v).strip()
            if name and code:
                out[name] = code
    return out


@functools.lru_cache(maxsize=1)
def load_country_code_map() -> Dict[str, str]:
    rows = _load_json(MASTER_DIR / "country_codes.json", [])
    out: Dict[str, str] = {}
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = _normalize(str(row.get("country") or ""))
            code = str(row.get("code") or "").strip()
            if name and code:
                out[name] = code
    elif isinstance(rows, dict):
        for k, v in rows.items():
            name = _normalize(str(k))
            code = str(v).strip()
            if name and code:
                out[name] = code
    return out


@functools.lru_cache(maxsize=1)
def load_currency_code_map() -> Dict[str, str]:
    rows = _load_json(MASTER_DIR / "currency_codes.json", [])
    out: Dict[str, str] = {}
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = _normalize(str(row.get("currency") or ""))
            code = str(row.get("code") or "").strip()
            if name and code:
                out[name] = code
    elif isinstance(rows, dict):
        for k, v in rows.items():
            name = _normalize(str(k))
            code = str(v).strip()
            if name and code:
                out[name] = code
    return out


@functools.lru_cache(maxsize=1)
def load_nature_options() -> List[Dict[str, str]]:
    rows = _load_json(MASTER_DIR / "nature_rem_category.json", [])
    out: List[Dict[str, str]] = []
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code") or "").strip()
        label = str(row.get("label") or "").strip()
        if code and label:
            out.append({"code": code, "label": label})
    return out


@functools.lru_cache(maxsize=1)
def load_purpose_grouped() -> Dict[str, List[Dict[str, str]]]:
    raw = _load_json(MASTER_DIR / "Purpose_code_List.json", {"purpose_codes": []})
    out: Dict[str, List[Dict[str, str]]] = {}
    for row in raw.get("purpose_codes", []):
        if not isinstance(row, dict):
            continue
        group = str(row.get("group_name") or "").strip()
        code = str(row.get("purpose_code") or "").strip().upper()
        gr_no = str(row.get("gr_no") or "").strip()
        desc = " ".join(str(row.get("description") or "").split())
        if group and code:
            out.setdefault(group, []).append({"purpose_code": code, "gr_no": gr_no, "description": desc})
    for rows in out.values():
        rows.sort(key=lambda x: x["purpose_code"])
    return out


@functools.lru_cache(maxsize=1)
def load_dtaa_map() -> Dict[str, Dict[str, str]]:
    rows = _load_json(MASTER_DIR / "DTAA__APPLICABLE_INFO.json", [])
    out: Dict[str, Dict[str, str]] = {}
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        country = str(row.get("country") or "").strip()
        key = _normalize(country)
        article = str(row.get("dtaa_applicable") or "").strip()
        percentage = row.get("percentage")
        if key:
            out[key] = {
                "country": country,
                "dtaa_applicable": article,
                "percentage": str(percentage).strip(),
            }
    return out


def match_remitter(name: str) -> Optional[Dict[str, str]]:
    q = _normalize(name)
    q_compact = _compact(name)
    q_canon = _canonical_company_name(name)
    if not q:
        return None
    best: Optional[Dict[str, str]] = None
    best_name = ""
    for row in load_bank_details():
        n = _normalize(row.get("name", ""))
        n_compact = _compact(row.get("name", ""))
        n_canon = _canonical_company_name(row.get("name", ""))
        if not n:
            continue
        if q == n or (q_compact and q_compact == n_compact) or (q_canon and q_canon == n_canon):
            logger.info("match_remitter_exact input=%s matched=%s", name, row.get("name", ""))
            return row
        if (
            q in n
            or n in q
            or (q_compact and n_compact and (q_compact in n_compact or n_compact in q_compact))
            or (q_canon and n_canon and (q_canon in n_canon or n_canon in q_canon))
        ):
            if best is None:
                best = row
                best_name = row.get("name", "")
    if best:
        logger.info("match_remitter_fuzzy input=%s matched=%s", name, best_name)
    else:
        logger.warning("match_remitter_none input=%s", name)
    return best


def resolve_bank_code(bank_name: str) -> str:
    return load_bank_code_map().get(_normalize(bank_name), "")


def resolve_country_code(country: str) -> str:
    return load_country_code_map().get(_normalize(country), "")


def resolve_country_name(code: str) -> str:
    code_s = str(code or "").strip()
    if not code_s:
        return ""
    for country_name, country_code in load_country_code_map().items():
        if str(country_code).strip() == code_s:
            return country_name
    return ""


def resolve_currency_code(currency_name: str) -> str:
    return load_currency_code_map().get(_normalize(currency_name), "")


def resolve_dtaa(country: str) -> Optional[Dict[str, str]]:
    return load_dtaa_map().get(_normalize(country))


def split_dtaa_article_text(dtaa_text: str) -> Tuple[str, str]:
    """
    Split DTAA text into:
    - without_article: suitable for RelevantDtaa
    - with_article: suitable for RelevantArtDtaa and ArtDtaa
    """
    with_article = str(dtaa_text or "").strip()
    if not with_article:
        return "", ""
    without_article = re.sub(
        r"^ARTICLE\s+\d+[A-Z]?\s+OF\s+",
        "",
        with_article,
        flags=re.IGNORECASE,
    ).strip()
    return without_article, with_article


def get_country_options() -> List[Tuple[str, str]]:
    rows = [(k, v) for k, v in load_country_code_map().items() if v != "-1"]
    return sorted(rows, key=lambda x: x[0])


def get_currency_options() -> List[Tuple[str, str]]:
    rows = [(k, v) for k, v in load_currency_code_map().items() if v != "-1"]
    return sorted(rows, key=lambda x: x[0])


def get_bank_options() -> List[Tuple[str, str]]:
    rows = [(k, v) for k, v in load_bank_code_map().items() if v != "-1"]
    return sorted(rows, key=lambda x: x[0])


def infer_country_from_beneficiary_name(name: str, address: str = "") -> str:
    """
    Infer country code for beneficiary when explicit selection is missing.
    Uses deterministic heuristics based on company name and address.
    
    Args:
        name: Beneficiary company name
        address: Optional address string to scan for country indicators
    
    Returns:
        Country code (e.g., "49" for Germany, "175" for Portugal) or empty string
    """
    combined = f"{name} {address}".strip()
    raw_upper = combined.upper()
    n = _normalize(combined)
    if not n:
        return ""

    # Common aliases/abbreviations seen in invoices.
    alias_to_country = {
        "USA": "UNITED STATES OF AMERICA",
        "US": "UNITED STATES OF AMERICA",
        "U S A": "UNITED STATES OF AMERICA",
        "UK": "UNITED KINGDOM OF GREAT BRITAIN AND NORTHERN IRELAND",
        "U K": "UNITED KINGDOM OF GREAT BRITAIN AND NORTHERN IRELAND",
        "UAE": "UNITED ARAB EMIRATES",
        "KSA": "SAUDI ARABIA",
    }
    for alias, country in alias_to_country.items():
        if re.search(rf"\b{re.escape(alias)}\b", n):
            code = resolve_country_code(country)
            if code:
                return code

    # Postal prefix hints, e.g. "DE-12345 Berlin".
    postal_prefix_country = {
        "DE": "GERMANY",
        "FR": "FRANCE",
        "ES": "SPAIN",
        "PT": "PORTUGAL",
        "IT": "ITALY",
        "NL": "NETHERLANDS",
        "BE": "BELGIUM",
        "AT": "AUSTRIA",
        "CH": "SWITZERLAND",
        "PL": "POLAND",
        "UK": "UNITED KINGDOM OF GREAT BRITAIN AND NORTHERN IRELAND",
        "US": "UNITED STATES OF AMERICA",
    }
    for prefix, country in postal_prefix_country.items():
        if re.search(rf"\b{prefix}\s*-\s*\d{{4,6}}\b", raw_upper):
            code = resolve_country_code(country)
            if code:
                return code

    # Direct token matching against country master.
    country_map = load_country_code_map()
    for country_name in sorted(country_map.keys(), key=len, reverse=True):
        if len(country_name) < 4:
            continue
        if re.search(rf"\b{re.escape(country_name)}\b", n):
            code = country_map.get(country_name, "")
            if code and code != "-1":
                return code
    
    # Portugal-specific indicators (high confidence)
    portugal_indicators = [
        "NIPC",           # Portuguese tax ID
        "ATCUD",          # Portuguese invoice authentication code
        "PORTUGAL",
        "LISBOA",
        "AVEIRO",
        "COVILHA",
        "BRAGA",
        "PORTO",
        "MADEIRA",
        "ACORES",
    ]
    for indicator in portugal_indicators:
        if indicator in n:
            code = resolve_country_code("PORTUGAL")
            if code:
                return code
    
    # Direct country token match from DTAA master.
    dtaa = load_dtaa_map()
    for key, rec in dtaa.items():
        country = _normalize(str(rec.get("country") or ""))
        if country and country in n:
            return resolve_country_code(country)

    # Legal suffix heuristics for common counterparties.
    suffix_country = {
        " GMBH": "GERMANY",
        " S L": "SPAIN",
        " SP Z O O": "POLAND",
        " PLC": "UNITED KINGDOM",
        " LLC": "USA",
        " SA": "SPAIN",  # Common Spanish suffix
        " BV": "NETHERLANDS",
        " AG": "GERMANY",  # Also Swiss
    }
    for suffix, country in suffix_country.items():
        if n.endswith(suffix) or f"{suffix} " in n:
            code = resolve_country_code(country)
            if code:
                return code
    return ""
