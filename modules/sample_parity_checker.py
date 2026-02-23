from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

from modules.xml_shape_normalizer import (
    DECLARATION as EXPECTED_DECLARATION,
    DEFAULT_SAMPLE_ZIP_PATH,
    normalize_xml_to_reference_shape,
    select_reference_shape,
    strict_shape_compare,
)

def _local(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    if ":" in tag:
        return tag.split(":", 1)[1]
    return tag


def _first_line(text: str) -> str:
    return (text.splitlines() or [""])[0].strip()


def _root_namespace_uris(xml_text: str) -> Dict[str, str]:
    open_tag = ""
    m = re.search(r"<FORM15CB:FORM15CB[^>]*>", xml_text)
    if m:
        open_tag = m.group(0)
    out: Dict[str, str] = {}
    for prefix in ("Form", "FORM15CB"):
        m2 = re.search(rf'xmlns:{prefix}="([^"]+)"', open_tag)
        if m2:
            out[prefix] = m2.group(1).strip()
    return out


def _mode_from_xml_text(xml_text: str) -> str:
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return "NON_TDS"
    tags = {_local(n.tag) for n in root.iter()}
    return "TDS" if "RateTdsSecbFlg" in tags else "NON_TDS"


def _remittance_char_from_xml_text(xml_text: str) -> str:
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return ""
    for n in root.iter():
        if _local(n.tag) == "RemittanceCharIndia":
            return (n.text or "").strip()
    return ""


def check_xml_against_samples(
    xml_text: str,
    sample_xml_texts: Optional[List[Tuple[str, str]]] = None,  # backward compatible (unused for selection)
    sample_zip_path: str = DEFAULT_SAMPLE_ZIP_PATH,
) -> Dict[str, object]:
    issues: List[str] = []
    warnings: List[str] = []
    blocking = False

    try:
        root = ET.fromstring(xml_text)
    except Exception as exc:
        return {
            "ok": False,
            "blocking": True,
            "issues": [f"Generated XML is not parseable: {exc}"],
            "warnings": [],
            "reference_sample": "",
        }

    if _first_line(xml_text) != EXPECTED_DECLARATION:
        blocking = True
        issues.append("XML declaration line differs from approved sample declaration.")

    ns = _root_namespace_uris(xml_text)
    if ns.get("Form") != "http://incometaxindiaefiling.gov.in/common":
        blocking = True
        issues.append("Form namespace URI mismatch.")
    if ns.get("FORM15CB") != "http://incometaxindiaefiling.gov.in/FORM15CAB":
        blocking = True
        issues.append("FORM15CB namespace URI mismatch.")

    if _local(root.tag) != "FORM15CB":
        blocking = True
        issues.append("Root tag is not FORM15CB.")

    try:
        if sample_xml_texts:
            mode = _mode_from_xml_text(xml_text)
            rem_char = _remittance_char_from_xml_text(xml_text)
            candidates = [(n, t) for n, t in sample_xml_texts if _mode_from_xml_text(t) == mode] or sample_xml_texts
            if rem_char:
                rc = [(n, t) for n, t in candidates if _remittance_char_from_xml_text(t) == rem_char]
                if rc:
                    candidates = rc
            ref_name, ref_xml_text = candidates[0]
            ref = {"name": ref_name, "xml_text": ref_xml_text}
        else:
            selected = select_reference_shape(xml_text, sample_zip_path=sample_zip_path)
            ref = {"name": selected["name"], "xml_text": selected["xml_text"]}
    except Exception as exc:
        return {
            "ok": False,
            "blocking": True,
            "issues": issues + [f"Sample parity source unavailable: {exc}"],
            "warnings": warnings,
            "reference_sample": "",
        }

    normalized = normalize_xml_to_reference_shape(xml_text, ref["xml_text"])
    diff = strict_shape_compare(ref["xml_text"], normalized)
    if not diff["ok"]:
        blocking = True
        for m in diff["mismatches"][:20]:
            issues.append(
                f"{m.get('type')} at {m.get('path')}: expected={m.get('expected')} actual={m.get('actual')}"
            )
        warnings.append(f"Total structural mismatches after normalization: {len(diff['mismatches'])}")

    return {
        "ok": not blocking,
        "blocking": blocking,
        "issues": issues,
        "warnings": warnings,
        "reference_sample": str(ref["name"]),
    }
