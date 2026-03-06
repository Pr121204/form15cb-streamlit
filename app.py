from __future__ import annotations

import io
import os
import time
from typing import Dict, List, Optional

import streamlit as st
from pdf2image import convert_from_bytes

from modules.batch_form_ui import render_invoice_tab
from modules.currency_mapping import is_currency_code_valid_for_xml
from modules.excel_single_ingestion import derive_single_config, match_invoice_row, parse_excel_rows
from modules.file_manager import ensure_folders
from modules.form15cb_constants import MODE_NON_TDS, MODE_TDS
from modules.invoice_calculator import recompute_invoice
from modules.invoice_gemini_extractor import (
    extract_invoice_core_fields,
    extract_invoice_core_fields_from_image,
    merge_multi_page_image_extractions,
)
from modules.invoice_state import build_invoice_state
from modules.logger import get_logger
from modules.master_data import validate_bsr_code, validate_dtaa_rate, validate_pan
from modules.ocr_engine import extract_text_from_image_file
from modules.pdf_reader import extract_text_from_pdf
from modules.xml_generator import (
    build_xml_fields_by_mode,
    generate_xml_content,
    write_xml_content,
)


MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_SCANNED_PDF_PAGES = max(1, int(os.getenv("MAX_SCANNED_PDF_PAGES", "6")))
VERSION = "3.1"
LAST_UPDATED = "March 2026"
SINGLE_STATE_KEY = "single_invoice_state"
PENDING_MATCH_KEY = "single_match_context"
UPLOAD_SIGNATURE_KEY = "single_upload_signature"
MODE_SELECTOR_KEY = "single_mode_selector"
GROSS_UP_CHECKBOX_KEY = "single_gross_up_tax"


logger = get_logger()
ensure_folders()

st.set_page_config(page_title="Form 15CB Single Generator", layout="wide", initial_sidebar_state="collapsed")
st.title("Form 15CB Single Invoice Generator")

if SINGLE_STATE_KEY not in st.session_state:
    st.session_state[SINGLE_STATE_KEY] = None
if PENDING_MATCH_KEY not in st.session_state:
    st.session_state[PENDING_MATCH_KEY] = None
if UPLOAD_SIGNATURE_KEY not in st.session_state:
    st.session_state[UPLOAD_SIGNATURE_KEY] = ""
if MODE_SELECTOR_KEY not in st.session_state:
    st.session_state[MODE_SELECTOR_KEY] = MODE_TDS
if GROSS_UP_CHECKBOX_KEY not in st.session_state:
    st.session_state[GROSS_UP_CHECKBOX_KEY] = False


def _coerce_mode(raw: object) -> str:
    mode_raw = str(raw or "").strip().upper().replace("-", "_").replace(" ", "_")
    return MODE_NON_TDS if mode_raw == MODE_NON_TDS else MODE_TDS


def _selected_single_mode_and_gross_up() -> tuple[str, bool]:
    mode = _coerce_mode(st.session_state.get(MODE_SELECTOR_KEY))
    is_gross_up = bool(st.session_state.get(GROSS_UP_CHECKBOX_KEY, False))
    if mode == MODE_NON_TDS:
        is_gross_up = False
        st.session_state[GROSS_UP_CHECKBOX_KEY] = False
    return mode, is_gross_up


def _on_single_mode_change() -> None:
    mode = _coerce_mode(st.session_state.get(MODE_SELECTOR_KEY))
    if mode == MODE_NON_TDS:
        st.session_state[GROSS_UP_CHECKBOX_KEY] = False


def _apply_single_mode_controls_to_state(state: Dict[str, object]) -> Dict[str, object]:
    mode, is_gross_up = _selected_single_mode_and_gross_up()
    meta = state.setdefault("meta", {})
    form = state.setdefault("form", {})
    changed = False

    if str(meta.get("mode") or MODE_TDS) != mode:
        meta["mode"] = mode
        changed = True
    if bool(meta.get("is_gross_up", False)) != is_gross_up:
        meta["is_gross_up"] = is_gross_up
        changed = True

    tax_pay_gross = "Y" if is_gross_up else "N"
    if str(form.get("TaxPayGrossSecb") or "") != tax_pay_gross:
        form["TaxPayGrossSecb"] = tax_pay_gross
        changed = True

    if changed:
        logger.info(
            "single_mode_controls_applied invoice_id=%s mode=%s is_gross_up=%s",
            str(meta.get("invoice_id") or ""),
            mode,
            is_gross_up,
        )
    return state


def _validate_xml_fields(fields: Dict[str, str], mode: str = MODE_TDS) -> List[str]:
    errors: List[str] = []

    if fields.get("RemitterPAN") and not validate_pan(fields["RemitterPAN"]):
        errors.append("RemitterPAN format is invalid (expected AAAAA9999A).")
    if fields.get("BsrCode") and not validate_bsr_code(fields["BsrCode"]):
        errors.append("BsrCode must be exactly 7 digits.")
    if fields.get("RateTdsADtaa") and (fields.get("RateTdsADtaa") or "").strip() and not validate_dtaa_rate(fields["RateTdsADtaa"]):
        errors.append("RateTdsADtaa must be between 0 and 100.")
    if not is_currency_code_valid_for_xml(fields.get("CurrencySecbCode", "")):
        errors.append("Currency must be selected with a valid code before generating XML.")
    if not str(fields.get("CountryRemMadeSecb") or "").strip():
        errors.append("Country to which remittance is made must be selected.")
    if not str(fields.get("NatureRemCategory") or "").strip():
        errors.append("Nature of remittance must be selected.")

    basis = str(fields.get("BasisDeterTax") or "").strip()
    if mode == MODE_TDS and not basis:
        errors.insert(0, "Please select the Basis of TDS determination (DTAA or Income Tax Act) before generating XML.")
    elif basis == "DTAA":
        for field in ("RateTdsADtaa", "TaxIncDtaa", "TaxLiablDtaa"):
            if not str(fields.get(field) or "").strip():
                errors.append(f"{field} is required for DTAA basis.")
    elif basis == "Act":
        for field in ("RateTdsSecB", "TaxLiablIt"):
            if not str(fields.get(field) or "").strip():
                errors.append(f"{field} is required for Income Tax Act basis.")

    if mode == MODE_TDS:
        if not str(fields.get("AmtPayForgnTds") or "").strip():
            errors.append("Amount of remittance must be entered.")
        if not str(fields.get("ActlAmtTdsForgn") or "").strip():
            errors.append("Actual amount remitted must be entered.")

    return errors


def _has_non_empty(value: object) -> bool:
    return bool(str(value or "").strip())


def _vision_core_fields_empty(extracted: Dict[str, str]) -> bool:
    core_fields = ["invoice_number", "amount", "currency_short", "beneficiary_name"]
    return not any(_has_non_empty(extracted.get(field)) for field in core_fields)


def _extract_invoice_fields(file_name: str, file_bytes: bytes) -> Dict[str, str]:
    text = ""
    extracted: Dict[str, str]

    if file_name.lower().endswith(".pdf"):
        try:
            text = extract_text_from_pdf(io.BytesIO(file_bytes)) or ""
        except Exception:
            logger.exception("pdf_text_extraction_failed file=%s", file_name)
            text = ""

        if text and len(text.strip()) >= 20:
            extracted = extract_invoice_core_fields(text)
        else:
            try:
                images = convert_from_bytes(file_bytes, dpi=300)
                if images:
                    selected_pages = images[:MAX_SCANNED_PDF_PAGES]
                    page_results: List[Dict[str, str]] = []
                    page_ocr_texts: List[str] = []
                    for page_idx, page_img in enumerate(selected_pages, start=1):
                        buf = io.BytesIO()
                        page_img.save(buf, format="JPEG", quality=90)
                        image_bytes = buf.getvalue()
                        page_extracted = extract_invoice_core_fields_from_image(image_bytes)
                        try:
                            page_ocr = extract_text_from_image_file(image_bytes) or ""
                        except Exception:
                            page_ocr = ""
                        text_extracted: Dict[str, str] = {}
                        if _vision_core_fields_empty(page_extracted) and len(page_ocr.strip()) >= 50:
                            try:
                                text_extracted = extract_invoice_core_fields(page_ocr)
                            except Exception:
                                logger.exception(
                                    "pdf_image_page_text_fallback_failed file=%s page=%s",
                                    file_name,
                                    page_idx,
                                )
                        merged_page = dict(text_extracted)
                        merged_page.update({k: v for k, v in page_extracted.items() if _has_non_empty(v)})
                        merged_page["_raw_invoice_text"] = page_ocr
                        page_results.append(merged_page)
                        page_ocr_texts.append(page_ocr)
                    if len(page_results) == 1:
                        extracted = page_results[0]
                    else:
                        extracted, merge_meta = merge_multi_page_image_extractions(page_results)
                        logger.info("pdf_image_multi_page_merged file=%s meta=%s", file_name, merge_meta)
                    text = "\n".join(t for t in page_ocr_texts if t.strip())
                    if not text.strip():
                        try:
                            text = extract_text_from_image_file(file_bytes) or ""
                        except Exception:
                            logger.exception("pdf_image_ocr_fallback_failed file=%s", file_name)
                else:
                    extracted = extract_invoice_core_fields(text)
            except Exception as exc:
                logger.exception("pdf_to_image_failed file=%s error=%s", file_name, str(exc))
                extracted = extract_invoice_core_fields(text)
    else:
        extracted = extract_invoice_core_fields_from_image(file_bytes)
        try:
            text = extract_text_from_image_file(file_bytes) or ""
        except Exception:
            logger.exception("image_ocr_fallback_failed file=%s", file_name)
            text = ""

    if not extracted.get("_raw_invoice_text"):
        extracted["_raw_invoice_text"] = text
    return extracted


def _build_single_state(
    file_name: str,
    extracted: Dict[str, str],
    excel_row: Dict[str, str],
    selected_mode: str,
    selected_is_gross_up: bool,
) -> Dict[str, object]:
    derived = derive_single_config(excel_row)
    mode = MODE_NON_TDS if str(selected_mode or MODE_TDS) == MODE_NON_TDS else MODE_TDS
    is_gross_up = bool(selected_is_gross_up) if mode == MODE_TDS else False
    config: Dict[str, object] = {
        "mode": mode,
        "exchange_rate": derived.get("exchange_rate") or "1",
        "currency_short": derived.get("currency_short") or str(extracted.get("currency_short") or ""),
        "is_gross_up": is_gross_up,
    }
    excel_seed = {
        "mode": mode,
        "is_gross_up": "Y" if is_gross_up else "N",
        "exchange_rate": str(derived.get("exchange_rate") or ""),
        "currency_short": str(derived.get("currency_short") or ""),
        "document_date": str(derived.get("document_date") or ""),
        "deduction_date": str(derived.get("posting_date") or ""),
        "proposed_date": str(derived.get("proposed_date") or ""),
        "amount_fcy": str(derived.get("amount_fcy") or ""),
        "amount_inr": str(derived.get("amount_inr") or ""),
    }
    invoice_id = f"inv_single_{int(time.time() * 1000) % 1000000}"
    return build_invoice_state(invoice_id, file_name, extracted, config, excel_seed=excel_seed)


def _excel_row_label(row: Dict[str, str]) -> str:
    return (
        f"Row {row.get('__row_number', '?')} | "
        f"Reference={row.get('Reference', '')} | "
        f"Posting Date={row.get('Posting Date', '')} | "
        f"FCY={row.get('Amount in Foreign Currency', '')} | "
        f"INR={row.get('Amount in INR', '')}"
    )


def _reset_states_if_upload_changed(invoice_file, excel_file) -> None:
    if not invoice_file or not excel_file:
        return
    signature = f"{invoice_file.name}:{invoice_file.size}:{excel_file.name}:{excel_file.size}"
    previous = str(st.session_state.get(UPLOAD_SIGNATURE_KEY) or "")
    if signature != previous:
        st.session_state[UPLOAD_SIGNATURE_KEY] = signature
        st.session_state[PENDING_MATCH_KEY] = None
        st.session_state[SINGLE_STATE_KEY] = None


st.subheader("Step 1 - Upload Files")
invoice_file = st.file_uploader(
    "Upload invoice file (PDF/JPG/PNG)",
    type=["pdf", "png", "jpg", "jpeg"],
    accept_multiple_files=False,
    key="single_invoice_uploader",
)
excel_file = st.file_uploader(
    "Upload matching Excel file (.xlsx)",
    type=["xlsx"],
    accept_multiple_files=False,
    key="single_excel_uploader",
)

if invoice_file and excel_file:
    st.subheader("Step 1.5 - Pre-processing Settings")
    selected_mode = st.radio(
        "Mode",
        options=[MODE_TDS, MODE_NON_TDS],
        index=0 if _coerce_mode(st.session_state.get(MODE_SELECTOR_KEY)) == MODE_TDS else 1,
        format_func=lambda value: "TDS" if value == MODE_TDS else "Non-TDS",
        horizontal=True,
        key=MODE_SELECTOR_KEY,
        on_change=_on_single_mode_change,
    )
    if str(selected_mode) == MODE_NON_TDS and st.session_state.get(GROSS_UP_CHECKBOX_KEY):
        st.session_state[GROSS_UP_CHECKBOX_KEY] = False
    st.checkbox(
        "Gross-up Tax?",
        key=GROSS_UP_CHECKBOX_KEY,
        disabled=str(selected_mode) == MODE_NON_TDS,
    )

    _reset_states_if_upload_changed(invoice_file, excel_file)
    if st.button("Process Files", type="primary"):
        if invoice_file.size > MAX_FILE_SIZE:
            st.error("Invoice file too large (max 10 MB).")
        elif excel_file.size > MAX_FILE_SIZE:
            st.error("Excel file too large (max 10 MB).")
        else:
            invoice_bytes = invoice_file.getvalue()
            excel_bytes = excel_file.getvalue()
            try:
                with st.spinner("Parsing Excel..."):
                    excel_rows = parse_excel_rows(excel_bytes)
                with st.spinner("Extracting invoice fields..."):
                    extracted = _extract_invoice_fields(invoice_file.name, invoice_bytes)
            except Exception as exc:
                logger.exception("single_processing_failed invoice=%s excel=%s", invoice_file.name, excel_file.name)
                st.error(str(exc))
            else:
                selected_mode, selected_is_gross_up = _selected_single_mode_and_gross_up()
                match_result = match_invoice_row(
                    excel_rows,
                    invoice_filename=invoice_file.name,
                    invoice_number=str(extracted.get("invoice_number") or ""),
                )
                if match_result["status"] == "matched" and match_result["matched_index"] is not None:
                    selected_row = excel_rows[match_result["matched_index"]]
                    try:
                        state = _build_single_state(
                            invoice_file.name,
                            extracted,
                            selected_row,
                            selected_mode,
                            selected_is_gross_up,
                        )
                    except ValueError as exc:
                        st.session_state[SINGLE_STATE_KEY] = None
                        st.session_state[PENDING_MATCH_KEY] = {
                            "rows": excel_rows,
                            "match_result": match_result,
                            "extracted": extracted,
                            "file_name": invoice_file.name,
                        }
                        st.error(str(exc))
                    else:
                        st.session_state[SINGLE_STATE_KEY] = state
                        st.session_state[PENDING_MATCH_KEY] = None
                        if len(match_result.get("candidates") or []) > 1:
                            st.info(
                                f"Multiple rows matched by normalized Reference; auto-selected first match (row {selected_row.get('__row_number', '?')})."
                            )
                        st.success("Invoice and Excel row matched successfully.")
                else:
                    st.session_state[SINGLE_STATE_KEY] = None
                    st.session_state[PENDING_MATCH_KEY] = {
                        "rows": excel_rows,
                        "match_result": match_result,
                        "extracted": extracted,
                        "file_name": invoice_file.name,
                    }
                    st.warning("No matching row found. Select the correct row below.")
else:
    st.caption("Upload one invoice file and one Excel file to begin.")

pending_context = st.session_state.get(PENDING_MATCH_KEY)
if isinstance(pending_context, dict) and not st.session_state.get(SINGLE_STATE_KEY):
    rows = pending_context.get("rows") or []
    match_result = pending_context.get("match_result") or {}
    candidate_indices = list(match_result.get("candidates") or list(range(len(rows))))
    if rows and candidate_indices:
        st.subheader("Step 1.1 - Select Matching Excel Row")
        selected_idx = st.selectbox(
            "Select the correct row",
            options=candidate_indices,
            format_func=lambda idx: _excel_row_label(rows[idx]),
            key="single_row_selector",
        )
        if st.button("Use Selected Row", type="primary", key="single_select_row"):
            selected_row = rows[int(selected_idx)]
            selected_mode, selected_is_gross_up = _selected_single_mode_and_gross_up()
            try:
                state = _build_single_state(
                    str(pending_context.get("file_name") or ""),
                    pending_context.get("extracted") or {},
                    selected_row,
                    selected_mode,
                    selected_is_gross_up,
                )
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state[SINGLE_STATE_KEY] = state
                st.session_state[PENDING_MATCH_KEY] = None
                st.success("Selected row applied successfully.")
                st.rerun()
    else:
        st.error("No Excel rows available to select.")

state = st.session_state.get(SINGLE_STATE_KEY)
if isinstance(state, dict):
    st.subheader("Step 2 - Review Invoice")
    logger.info("single_review_start invoice_id=%s", state.get("meta", {}).get("invoice_id", ""))
    state = _apply_single_mode_controls_to_state(state)
    state = render_invoice_tab(state)
    state = recompute_invoice(state)
    st.session_state[SINGLE_STATE_KEY] = state

    xml_fields = build_xml_fields_by_mode(state)
    mode = str(state.get("meta", {}).get("mode") or MODE_TDS)
    errors = _validate_xml_fields(xml_fields, mode=mode)
    if errors:
        for err in errors:
            st.error(err)
    else:
        try:
            xml_content = generate_xml_content(xml_fields, mode=mode)
        except Exception as exc:
            logger.exception("single_xml_generate_failed invoice_id=%s", state.get("meta", {}).get("invoice_id", ""))
            st.error(f"XML generation failed: {exc}")
        else:
            file_stub = str(state["extracted"].get("invoice_number") or state["meta"]["invoice_id"]).replace(" ", "_")
            xml_filename = f"form15cb_{file_stub}.xml"
            st.download_button(
                "Generate XML",
                data=xml_content.encode("utf8"),
                file_name=xml_filename,
                mime="application/xml",
                key="single_xml_download",
            )
            if st.button("Save XML to output folder", key="single_xml_save"):
                path = write_xml_content(xml_content, filename=xml_filename)
                st.success(f"Saved: {path}")

st.markdown("---")
st.caption(f"Version: {VERSION} | Last Updated: {LAST_UPDATED}")
