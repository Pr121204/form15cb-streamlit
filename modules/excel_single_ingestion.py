from __future__ import annotations

import io
import os
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, List, Literal, Optional, TypedDict

import pandas as pd

from modules.form15cb_constants import MODE_NON_TDS, MODE_TDS, PROPOSED_DATE_OFFSET_DAYS


COLUMN_ALIASES: Dict[str, List[str]] = {
    "Reference": ["Reference"],
    "Document Date": ["Document Date"],
    "Posting Date": ["Posting Date"],
    "Amount in Foreign Currency": ["Amount in Foreign Currency", "Amount in doc. curr."],
    "Amount in INR": ["Amount in INR", "Amount in local currency"],
    "Currency": ["Currency", "Document currency"],
    "Mode": ["Mode"],
    "Gross Up Tax": ["Gross Up Tax"],
}

REQUIRED_COLUMNS = [
    "Reference",
    "Posting Date",
    "Amount in Foreign Currency",
    "Amount in INR",
    "Currency",
]

REQUIRED_LABELS = {
    "Reference": "Reference",
    "Posting Date": "Posting Date",
    "Amount in Foreign Currency": "Amount FCY",
    "Amount in INR": "Amount INR",
    "Currency": "Currency",
}


class MatchResult(TypedDict):
    status: Literal["matched", "ambiguous", "not_found"]
    matched_index: Optional[int]
    candidates: List[int]


def _normalize_header(raw: object) -> str:
    text = str(raw or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_ref(raw: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(raw or "").strip().upper())


def _parse_date_iso(raw: object) -> str:
    if raw is None:
        return ""
    if isinstance(raw, datetime):
        return raw.date().isoformat()
    if isinstance(raw, date):
        return raw.isoformat()
    text = str(raw).strip()
    if not text:
        return ""
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        parsed = pd.to_datetime(text, errors="coerce", dayfirst=False)
    if pd.isna(parsed):
        return ""
    return parsed.date().isoformat()


def _to_decimal(raw: object) -> Optional[Decimal]:
    text = str(raw or "").strip()
    if not text:
        return None
    neg = False
    if text.startswith("(") and text.endswith(")"):
        neg = True
        text = text[1:-1]
    text = text.replace(",", "").replace(" ", "")
    if not text:
        return None
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return -value if neg else value


def _format_decimal(value: Decimal, places: int) -> str:
    q = Decimal("1") if places == 0 else Decimal("1." + ("0" * places))
    rounded = value.quantize(q, rounding=ROUND_HALF_UP)
    text = f"{rounded:.{places}f}"
    if places > 0:
        text = text.rstrip("0").rstrip(".")
    return text


def _resolve_alias_columns(columns: List[object]) -> Dict[str, str]:
    normalized_to_raw: Dict[str, str] = {}
    for column in columns:
        raw = str(column or "").strip()
        if not raw:
            continue
        normalized_to_raw[_normalize_header(raw)] = raw

    resolved: Dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            key = _normalize_header(alias)
            if key in normalized_to_raw:
                resolved[canonical] = normalized_to_raw[key]
                break
    return resolved


def _normalize_mode(raw: object) -> str:
    mode_raw = str(raw or "").strip().upper().replace("-", "_").replace(" ", "_")
    if mode_raw == MODE_NON_TDS:
        return MODE_NON_TDS
    if mode_raw == MODE_TDS:
        return MODE_TDS
    return ""


def _normalize_gross_up(raw: object) -> str:
    value = str(raw or "").strip().upper()
    if value in {"Y", "YES", "TRUE", "1"}:
        return "Y"
    if value in {"N", "NO", "FALSE", "0"}:
        return "N"
    return ""


def parse_excel_rows(excel_bytes: bytes) -> List[Dict[str, str]]:
    if not excel_bytes:
        raise ValueError("Excel file is empty.")

    try:
        df = pd.read_excel(io.BytesIO(excel_bytes), dtype=str, engine="openpyxl")
    except Exception as exc:  # pragma: no cover - handled by caller
        raise ValueError(f"Unable to parse Excel file: {exc}") from exc

    resolved = _resolve_alias_columns(list(df.columns))
    missing = [col for col in REQUIRED_COLUMNS if col not in resolved]
    if missing:
        missing_labels = [REQUIRED_LABELS.get(col, col) for col in missing]
        raise ValueError("Excel is missing required columns: " + ", ".join(missing_labels))

    rename_map: Dict[str, str] = {}
    for canonical, raw in resolved.items():
        rename_map[raw] = canonical
    df = df.rename(columns=rename_map)

    rows: List[Dict[str, str]] = []
    for index, row in df.iterrows():
        fcy_raw = row.get("Amount in Foreign Currency")
        inr_raw = row.get("Amount in INR")
        fcy_dec = _to_decimal(fcy_raw)
        inr_dec = _to_decimal(inr_raw)
        fcy_abs = abs(fcy_dec) if fcy_dec is not None else None
        inr_abs = abs(inr_dec) if inr_dec is not None else None
        out = {
            "Reference": str(row.get("Reference") or "").strip(),
            "Document Date": _parse_date_iso(row.get("Document Date")),
            "Posting Date": _parse_date_iso(row.get("Posting Date")),
            "Amount in Foreign Currency": _format_decimal(fcy_abs, 2) if fcy_abs is not None else "",
            "Amount in INR": _format_decimal(inr_abs, 0) if inr_abs is not None else "",
            "Currency": str(row.get("Currency") or "").strip().upper(),
            "Mode": _normalize_mode(row.get("Mode")),
            "Gross Up Tax": _normalize_gross_up(row.get("Gross Up Tax")),
            "__row_number": str(index + 2),
            "__row_index": str(index),
        }
        rows.append(out)
    return rows


def match_invoice_row(rows: List[Dict[str, str]], invoice_filename: str, invoice_number: str) -> MatchResult:
    if not rows:
        return {"status": "not_found", "matched_index": None, "candidates": []}

    file_stem = os.path.splitext(os.path.basename(str(invoice_filename or "")))[0]
    file_key = _normalize_ref(file_stem)
    invoice_key = _normalize_ref(invoice_number)

    def _match(key: str) -> List[int]:
        if not key:
            return []
        out: List[int] = []
        for idx, row in enumerate(rows):
            if _normalize_ref(row.get("Reference")) == key:
                out.append(idx)
        return out

    file_matches = _match(file_key)
    if file_matches:
        return {
            "status": "matched",
            "matched_index": file_matches[0],
            "candidates": file_matches,
        }

    invoice_matches = _match(invoice_key)
    if invoice_matches:
        return {
            "status": "matched",
            "matched_index": invoice_matches[0],
            "candidates": invoice_matches,
        }

    return {"status": "not_found", "matched_index": None, "candidates": list(range(len(rows)))}


def derive_single_config(row: Dict[str, str]) -> Dict[str, str]:
    mode = _normalize_mode(row.get("Mode")) or MODE_TDS
    gross_up = _normalize_gross_up(row.get("Gross Up Tax")) or "N"
    if mode == MODE_NON_TDS:
        gross_up = "N"
    currency_short = str(row.get("Currency") or "").strip().upper()
    document_date = _parse_date_iso(row.get("Document Date"))
    posting_date = _parse_date_iso(row.get("Posting Date"))

    errors: List[str] = []
    if not posting_date:
        errors.append("Posting Date is required and must be a valid date (YYYY-MM-DD).")
    if not currency_short:
        errors.append("Currency is required in the matched row.")

    fcy_dec = _to_decimal(row.get("Amount in Foreign Currency"))
    inr_dec = _to_decimal(row.get("Amount in INR"))
    if fcy_dec is None:
        errors.append("Amount FCY is invalid or empty in the matched row.")
    if inr_dec is None:
        errors.append("Amount INR is invalid or empty in the matched row.")

    fcy_abs = abs(fcy_dec) if fcy_dec is not None else None
    inr_abs = abs(inr_dec) if inr_dec is not None else None
    if fcy_abs is not None and fcy_abs == 0:
        errors.append("Amount FCY cannot be zero in the matched row.")

    if errors:
        raise ValueError(" ".join(errors))

    assert fcy_abs is not None and inr_abs is not None
    amount_fcy = _format_decimal(fcy_abs, 2)
    amount_inr = _format_decimal(inr_abs, 0)
    exchange_rate_dec = (inr_abs / fcy_abs).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    exchange_rate = _format_decimal(exchange_rate_dec, 6)

    proposed_date = (date.today() + timedelta(days=PROPOSED_DATE_OFFSET_DAYS)).isoformat()
    return {
        "mode": mode,
        "is_gross_up": gross_up,
        "exchange_rate": exchange_rate,
        "currency_short": currency_short,
        "document_date": document_date,
        "posting_date": posting_date,
        "proposed_date": proposed_date,
        "amount_fcy": amount_fcy,
        "amount_inr": amount_inr,
    }
