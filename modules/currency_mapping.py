from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Mapping, Tuple


MASTER_CURRENCY_PATH = Path(__file__).resolve().parent.parent / "data" / "master" / "currency_codes.json"

# Confirmed mappings from production data.
CONFIRMED_SHORT_CODE_TO_CODE: Dict[str, str] = {
    "EUR": "50",
    "USD": "167",
    "GBP": "133",
    "JPY": "78",
}

# Short-code targets must match exact currency names from master JSON.
SHORT_CODE_TARGET_NAME: Dict[str, str] = {
    "EUR": "EURO",
    "USD": "US DOLLAR",
    "GBP": "POUND STERLING",
    "JPY": "JAPANESE YEN",
    "AUD": "AUSTRALIAN DOLLAR",
    "SGD": "SINGAPORE DOLLAR",
    "CHF": "SWISS FRANC",
    "CAD": "CANADIAN DOLLAR",
    "CNY": "YUAN RENMINBI",
    "SEK": "SWEDISH KRONA",
    "NOK": "NORWEGIAN KRONES",
    "DKK": "DANISH KRONE",
    "NZD": "NEW ZEALAND DOLLAR",
}


def load_currency_exact_index(path: Path | None = None) -> Dict[str, str]:
    source = path or MASTER_CURRENCY_PATH
    try:
        with open(source, "r", encoding="utf8") as f:
            raw = json.load(f)
    except Exception:
        return {}

    index: Dict[str, str] = {}
    if not isinstance(raw, list):
        return index
    for row in raw:
        if not isinstance(row, dict):
            continue
        name = str(row.get("currency") or "").strip().upper()
        code = str(row.get("code") or "").strip()
        if name and code:
            index[name] = code
    return index


def validate_short_code_targets(currency_index: Mapping[str, str]) -> Tuple[Dict[str, Dict[str, str]], Dict[str, str]]:
    resolved: Dict[str, Dict[str, str]] = {}
    missing: Dict[str, str] = {}
    for short_code, target_name in SHORT_CODE_TARGET_NAME.items():
        code = currency_index.get(target_name)
        if code:
            resolved[short_code] = {"name": target_name, "code": code}
        else:
            missing[short_code] = target_name
    return resolved, missing


def resolve_short_code_currency(
    short_code: str,
    currency_index: Mapping[str, str],
) -> Dict[str, str]:
    short = (short_code or "").strip().upper()
    target_name = SHORT_CODE_TARGET_NAME.get(short)
    if not target_name:
        return {}
    code = currency_index.get(target_name)
    if not code:
        return {}
    return {"short_code": short, "name": target_name, "code": code}


def preselect_currency_code(
    current_code: str,
    short_code: str,
    currency_index: Mapping[str, str],
) -> Tuple[str, bool]:
    code = (current_code or "").strip()
    if code:
        return code, code == "-1"
    resolved = resolve_short_code_currency(short_code, currency_index)
    if resolved:
        return resolved["code"], False
    if (short_code or "").strip():
        return "", True
    return "", False


def is_currency_code_valid_for_xml(code: str) -> bool:
    cleaned = (code or "").strip()
    return bool(cleaned and cleaned != "-1")
