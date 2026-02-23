from __future__ import annotations

import os
import re
import uuid
from typing import Dict, Iterable

from config.settings import OUTPUT_FOLDER
from modules.form15cb_constants import MODE_NON_TDS, MODE_TDS


def escape_xml(value):
    if value is None:
        return ""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def validate_required_fields(fields: Dict[str, str], mode: str = MODE_TDS) -> None:
    required = ["SWVersionNo", "FormName", "AssessmentYear", "RemitterPAN", "NameRemitter", "CurrencySecbCode"]
    missing = [k for k in required if not str(fields.get(k, "")).strip()]
    if str(mode or MODE_TDS) == MODE_TDS:
        tds_required = [
            "TaxLiablIt",
            "BasisDeterTax",
            "TaxIncDtaa",
            "TaxLiablDtaa",
            "RateTdsADtaa",
            "RateTdsSecB",
            "AmtPayForgnTds",
            "AmtPayIndianTds",
            "ActlAmtTdsForgn",
        ]
        missing.extend([k for k in tds_required if not str(fields.get(k, "")).strip()])
    if missing:
        uniq_missing = sorted(set(missing))
        raise ValueError(f"Missing or empty mandatory fields: {', '.join(uniq_missing)}")


def _fill_template(fields: Dict[str, str], template_path: str) -> str:
    with open(template_path, "r", encoding="utf8") as f:
        xml_content = f.read()
    for field_name, field_value in fields.items():
        xml_content = xml_content.replace("{{" + field_name + "}}", escape_xml(field_value))
    return re.sub(r"\{\{[^}]+\}\}", "", xml_content)


def _remove_tag_block(xml_text: str, tag: str) -> str:
    pattern = rf"\s*<FORM15CB:{tag}>.*?</FORM15CB:{tag}>"
    return re.sub(pattern, "", xml_text, flags=re.DOTALL)


def _remove_empty_optional_tags(xml_text: str) -> str:
    optional_tags = [
        "ReasonNot",
        "NatureRemCode",
        "NatureRemDtaa",
        "RelevantDtaa",
        "RelevantArtDtaa",
        "TaxIncDtaa",
        "TaxLiablDtaa",
        "ArtDtaa",
        "RateTdsADtaa",
        "SecRemCovered",
        "AmtIncChrgIt",
        "TaxLiablIt",
        "BasisDeterTax",
        "PremisesBuildingVillage",  # In RemitteeAddrs: actual tag name (not RemitteePremisesBuildingVillage)
        "RoadStreet",  # In RemitteeAddrs: actual tag name (not RemitteeRoadStreet)
    ]
    for tag in optional_tags:
        pattern = rf"\s*<FORM15CB:{tag}>\s*</FORM15CB:{tag}>"
        xml_text = re.sub(pattern, "", xml_text, flags=re.DOTALL)
    return xml_text


def generate_xml_content(xml_fields: Dict[str, str], mode: str = MODE_TDS, template_path: str = "templates/form15cb_template.xml") -> str:
    validate_required_fields(xml_fields, mode=mode)
    xml_text = _fill_template(xml_fields, template_path)
    xml_text = _remove_empty_optional_tags(xml_text)
    if mode == MODE_NON_TDS:
        for tag in ("RateTdsSecbFlg", "RateTdsSecB", "DednDateTds"):
            xml_text = _remove_tag_block(xml_text, tag)
    return xml_text


def build_xml_fields_by_mode(state: Dict[str, object]) -> Dict[str, str]:
    from modules.invoice_calculator import invoice_state_to_xml_fields

    out = invoice_state_to_xml_fields(state)
    mode = str(state.get("meta", {}).get("mode") or MODE_TDS)
    if mode == MODE_NON_TDS:
        out["AmtPayForgnTds"] = "0"
        out["AmtPayIndianTds"] = "0"
        out["RateTdsSecbFlg"] = ""
        out["RateTdsSecB"] = ""
        out["DednDateTds"] = ""
    return out


def write_xml_content(xml_content: str, filename: str | None = None) -> str:
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    if not filename:
        filename = f"generated_{uuid.uuid4().hex[:12]}.xml"
    out_path = os.path.join(OUTPUT_FOLDER, filename)
    with open(out_path, "w", encoding="utf8") as f:
        f.write(xml_content)
    return out_path


def generate_xml(fields, template_path: str = "templates/form15cb_template.xml"):
    xml_content = generate_xml_content({k: str(v) for k, v in fields.items()}, mode=MODE_TDS, template_path=template_path)
    return write_xml_content(xml_content)


def generate_zip_from_xmls(xml_payloads: Iterable[tuple[str, bytes]]) -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in xml_payloads:
            zf.writestr(name, data)
    return buf.getvalue()


def validate_xml_structure(xml_path: str):
    try:
        import xml.etree.ElementTree as ET

        ET.parse(xml_path)
        return True
    except Exception:
        return False
