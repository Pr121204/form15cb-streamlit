from __future__ import annotations

import io
import os
import time
from typing import Dict, List

import streamlit as st

# from modules.auth import require_login, render_logout_button
#
# if not require_login():
#     st.stop()
#
# render_logout_button()   # shows user photo + Sign Out in sidebar

from modules.batch_form_ui import render_invoice_tab
from modules.currency_mapping import (
    get_upload_currency_select_options,
    is_currency_code_valid_for_xml,
    load_currency_exact_index,
    resolve_currency_selection,
)
from modules.file_manager import ensure_folders, save_uploaded_file
from modules.form15cb_constants import MODE_NON_TDS, MODE_TDS
from modules.invoice_calculator import invoice_state_to_xml_fields, recompute_invoice
from modules.invoice_gemini_extractor import (
    extract_invoice_core_fields,
    extract_invoice_core_fields_from_image,
    merge_multi_page_image_extractions,
)
from pdf2image import convert_from_bytes
from modules.invoice_state import build_invoice_state
from modules.logger import get_logger
from modules.master_data import validate_bsr_code, validate_dtaa_rate, validate_pan
from modules.ocr_engine import extract_text_from_image_file
from modules.pdf_reader import extract_text_from_pdf
from modules.xml_generator import (
    build_xml_fields_by_mode,
    generate_xml_content,
    generate_zip_from_xmls,
    validate_required_fields,
    write_xml_content,
)


MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_SCANNED_PDF_PAGES = max(1, int(os.getenv("MAX_SCANNED_PDF_PAGES", "6")))
VERSION = "3.0"
LAST_UPDATED = "February 2026"

logger = get_logger()
ensure_folders()
UPLOAD_CURRENCY_OPTIONS = get_upload_currency_select_options()
UPLOAD_CURRENCY_VALUES = [opt["value"] for opt in UPLOAD_CURRENCY_OPTIONS]
UPLOAD_CURRENCY_LABELS = {opt["value"]: opt["label"] for opt in UPLOAD_CURRENCY_OPTIONS}
CURRENCY_INDEX = load_currency_exact_index()
DEFAULT_UPLOAD_CURRENCY = next(
    (opt["value"] for opt in UPLOAD_CURRENCY_OPTIONS if str(opt.get("label", "")).upper().startswith("EUR")),
    (UPLOAD_CURRENCY_VALUES[0] if UPLOAD_CURRENCY_VALUES else ""),
)

st.set_page_config(page_title="Form 15CB Batch Generator", layout="wide", initial_sidebar_state="collapsed")
st.title("Form 15CB Batch Generator")

if "invoice_states" not in st.session_state:
    st.session_state["invoice_states"] = {}
if "uploaded_configs" not in st.session_state:
    st.session_state["uploaded_configs"] = {}


def _extract_text_for_file(uploaded) -> str:
    # Keep OCR/text extraction path unchanged.
    path = save_uploaded_file(uploaded, uploaded.name)
    logger.info("extract_start file=%s saved_path=%s", uploaded.name, path)
    uploaded.seek(0)
    text = ""
    try:
        text = extract_text_from_pdf(io.BytesIO(uploaded.read()))
        logger.info("extract_pdf_done file=%s text_len=%s", uploaded.name, len(str(text or "")))
    except Exception:
        logger.exception("extract_pdf_failed file=%s", uploaded.name)
        text = ""
    if not text or len(text.strip()) < 20:
        logger.info("extract_pdf_insufficient file=%s text_len=%s falling_back=ocr", uploaded.name, len(str(text or "")))
        text = extract_text_from_image_file(path)
        logger.info("extract_ocr_done file=%s text_len=%s", uploaded.name, len(str(text or "")))
    logger.info("extract_complete file=%s final_text_len=%s", uploaded.name, len(str(text or "")))
    return text


def _validate_xml_fields(fields: Dict[str, str], mode: str = MODE_TDS) -> List[str]:
    """CHANGE 3: Validate XML fields conditionally based on BasisDeterTax.
    If BasisDeterTax is empty, return early with a clear message.
    Otherwise, validate only the fields relevant to the selected basis.
    """
    errors: List[str] = []
    
    # Preliminary field validations (always needed)
    if fields.get("RemitterPAN") and not validate_pan(fields["RemitterPAN"]):
        errors.append("RemitterPAN format is invalid (expected AAAAA9999A).")
    if fields.get("BsrCode") and not validate_bsr_code(fields["BsrCode"]):
        errors.append("BsrCode must be exactly 7 digits.")
    if fields.get("RateTdsADtaa") and fields.get("RateTdsADtaa").strip() and not validate_dtaa_rate(fields["RateTdsADtaa"]):
        errors.append("RateTdsADtaa must be between 0 and 100.")
    if not is_currency_code_valid_for_xml(fields.get("CurrencySecbCode", "")):
        errors.append("Currency must be selected with a valid code before generating XML.")
    if not str(fields.get("CountryRemMadeSecb") or "").strip():
        errors.append("Country to which remittance is made must be selected.")
    if not str(fields.get("NatureRemCategory") or "").strip():
        errors.append("Nature of remittance must be selected.")
    
    # CHANGE 3: Check BasisDeterTax and validate conditionally
    basis = str(fields.get("BasisDeterTax") or "").strip()
    
    if not basis:
        # User hasn't selected DTAA or Act yet - this is the root cause
        errors.insert(0, "Please select the Basis of TDS determination (DTAA or Income Tax Act) before generating XML.")
    elif basis == "DTAA":
        # DTAA basis: check only DTAA-specific fields
        dtaa_fields = ["RateTdsADtaa", "TaxIncDtaa", "TaxLiablDtaa"]
        for field in dtaa_fields:
            if not str(fields.get(field) or "").strip():
                errors.append(f"{field} is required for DTAA basis.")
    elif basis == "Act":
        # Act basis: check Act-specific fields
        act_fields = ["RateTdsSecB", "TaxLiablIt"]
        for field in act_fields:
            if not str(fields.get(field) or "").strip():
                errors.append(f"{field} is required for Income Tax Act basis.")
    
    # Always required in TDS mode (regardless of basis)
    if mode == MODE_TDS:
        if not str(fields.get("AmtPayForgnTds") or "").strip():
            errors.append("Amount of remittance must be entered.")
        if not str(fields.get("ActlAmtTdsForgn") or "").strip():
            errors.append("Actual amount remitted must be entered.")
    
    if errors:
        logger.warning(
            "xml_validation_failed mode=%s basis=%s errors=%s key_fields=%s",
            mode,
            basis,
            errors,
            {
                "RemitterPAN": str(fields.get("RemitterPAN") or ""),
                "BasisDeterTax": basis,
                "CountryRemMadeSecb": str(fields.get("CountryRemMadeSecb") or ""),
                "NatureRemCategory": str(fields.get("NatureRemCategory") or ""),
            },
        )
    else:
        logger.info(
            "xml_validation_ok mode=%s basis=%s key_fields=%s",
            mode,
            basis,
            {
                "RemitterPAN": str(fields.get("RemitterPAN") or ""),
                "BasisDeterTax": basis,
                "CountryRemMadeSecb": str(fields.get("CountryRemMadeSecb") or ""),
                "NatureRemCategory": str(fields.get("NatureRemCategory") or ""),
            },
        )
    return errors


st.subheader("Step 1 - Upload Invoices")
uploaded_files = st.file_uploader(
    "Upload one or more invoice files (PDF/JPG/PNG)",
    type=["pdf", "png", "jpg", "jpeg"],
    accept_multiple_files=True,
    key="batch_invoice_uploader",
)

if uploaded_files:
    logger.info("upload_received file_count=%s files=%s", len(uploaded_files), [f.name for f in uploaded_files])
    st.caption("Configure each invoice before processing")
    for idx, file in enumerate(uploaded_files):
        cfg_key = f"cfg_{file.name}_{idx}"
        existing = st.session_state["uploaded_configs"].get(
            cfg_key,
            {"currency_short": DEFAULT_UPLOAD_CURRENCY, "exchange_rate": "1", "mode": MODE_TDS},
        )
        c1, c2, c3 = st.columns([3, 2, 2])
        with c1:
            st.text_input("Filename", value=file.name, disabled=True, key=f"{cfg_key}_file")
        with c2:
            existing_currency = str(existing.get("currency_short") or "").strip()
            resolved_existing_currency = resolve_currency_selection(existing_currency, CURRENCY_INDEX)
            selected_currency_value = resolved_existing_currency.get("code", "")
            if selected_currency_value not in UPLOAD_CURRENCY_VALUES:
                selected_currency_value = DEFAULT_UPLOAD_CURRENCY
            currency_short = st.selectbox(
                "Currency",
                UPLOAD_CURRENCY_VALUES or [""],
                index=(UPLOAD_CURRENCY_VALUES.index(selected_currency_value) if selected_currency_value in UPLOAD_CURRENCY_VALUES else 0),
                format_func=lambda code: UPLOAD_CURRENCY_LABELS.get(code, code),
                key=f"{cfg_key}_currency",
            )
            exchange_rate = st.text_input("1 unit of FCY = ₹ X", value=str(existing["exchange_rate"]), key=f"{cfg_key}_rate")
        with c3:
            mode = st.radio("Mode", [MODE_TDS, MODE_NON_TDS], index=0 if existing["mode"] == MODE_TDS else 1, key=f"{cfg_key}_mode")
        st.session_state["uploaded_configs"][cfg_key] = {
            "currency_short": currency_short,
            "exchange_rate": exchange_rate,
            "mode": mode,
            "file_name": file.name,
        }

    process = st.button("Process Invoices", type="primary")
    if process:
        logger.info("process_clicked file_count=%s", len(uploaded_files))
        states: Dict[str, Dict[str, object]] = {}
        for idx, file in enumerate(uploaded_files):
            cfg_key = f"cfg_{file.name}_{idx}"
            cfg = st.session_state["uploaded_configs"].get(cfg_key, {})
            logger.info("invoice_process_start file=%s cfg=%s", file.name, cfg)
            if file.size > MAX_FILE_SIZE:
                st.error(f"{file.name}: file too large.")
                logger.warning("invoice_skipped_file_too_large file=%s size=%s", file.name, file.size)
                continue
            try:
                if float(str(cfg.get("exchange_rate") or "0")) <= 0:
                    st.error(f"{file.name}: exchange rate must be greater than 0.")
                    logger.warning("invoice_skipped_bad_exchange file=%s exchange_rate=%s", file.name, cfg.get("exchange_rate"))
                    continue
            except ValueError:
                st.error(f"{file.name}: invalid exchange rate.")
                logger.warning("invoice_skipped_invalid_exchange file=%s exchange_rate=%s", file.name, cfg.get("exchange_rate"))
                continue

            with st.spinner(f"Processing {file.name}..."):
                start = time.time()
                # Handle PDFs differently: try text extraction first, else convert
                # the first PDF page to an image and send to Gemini vision.
                file_bytes = file.read()
                if file.name.lower().endswith('.pdf'):
                    text = ""
                    try:
                        text = extract_text_from_pdf(io.BytesIO(file_bytes))
                    except Exception:
                        logger.exception("pdf_text_extraction_failed file=%s", file.name)
                        text = ""

                    if text and len(text.strip()) >= 20:
                        # Use text-based extraction when PDF text is sufficient
                        extracted = extract_invoice_core_fields(text)
                    else:
                        # Convert scanned PDF pages to images and aggregate extraction.
                        try:
                            images = convert_from_bytes(file_bytes, dpi=300)
                            if images:
                                selected_pages = images[:MAX_SCANNED_PDF_PAGES]
                                logger.info(
                                    "pdf_image_fallback_pages file=%s total_pages=%s processed_pages=%s",
                                    file.name,
                                    len(images),
                                    len(selected_pages),
                                )
                                page_results: List[Dict[str, str]] = []
                                for page_idx, page_img in enumerate(selected_pages, start=1):
                                    buf = io.BytesIO()
                                    page_img.save(buf, format='JPEG', quality=90)
                                    image_bytes = buf.getvalue()
                                    page_extracted = extract_invoice_core_fields_from_image(image_bytes)
                                    page_results.append(page_extracted)
                                    logger.info(
                                        "pdf_image_page_extracted file=%s page=%s summary=%s",
                                        file.name,
                                        page_idx,
                                        {
                                            "invoice_number": page_extracted.get("invoice_number", ""),
                                            "amount": page_extracted.get("amount", ""),
                                            "currency_short": page_extracted.get("currency_short", ""),
                                            "remitter_name": page_extracted.get("remitter_name", ""),
                                            "beneficiary_name": page_extracted.get("beneficiary_name", ""),
                                        },
                                    )
                                if len(page_results) == 1:
                                    extracted = page_results[0]
                                else:
                                    extracted, merge_meta = merge_multi_page_image_extractions(page_results)
                                    logger.info("pdf_image_multi_page_merged file=%s meta=%s", file.name, merge_meta)
                            else:
                                extracted = extract_invoice_core_fields(text)
                        except Exception as e:
                            logger.exception("pdf_to_image_failed file=%s error=%s", file.name, str(e))
                            extracted = extract_invoice_core_fields(text)
                else:
                    # For image uploads (jpg/png/etc.), send bytes directly to image extractor
                    extracted = extract_invoice_core_fields_from_image(file_bytes)
                logger.info(
                    "invoice_extracted file=%s fields=%s",
                    file.name,
                    {
                        "remitter_name": extracted.get("remitter_name", ""),
                        "remitter_country": extracted.get("remitter_country_text", ""),
                        "beneficiary_name": extracted.get("beneficiary_name", ""),
                        "beneficiary_country": extracted.get("beneficiary_country_text", ""),
                        "invoice_number": extracted.get("invoice_number", ""),
                        "amount": extracted.get("amount", ""),
                        "currency_short": extracted.get("currency_short", ""),
                        "invoice_date_iso": extracted.get("invoice_date_iso", ""),
                    },
                )
                invoice_id = f"inv_{idx}_{int(time.time()*1000)%1000000}"
                state = build_invoice_state(invoice_id, file.name, extracted, cfg)
                states[invoice_id] = state
                logger.info(
                    "invoice_state_built invoice_id=%s file=%s form_snapshot=%s",
                    invoice_id,
                    file.name,
                    {
                        "RemitterPAN": state.get("form", {}).get("RemitterPAN", ""),
                        "CountryRemMadeSecb": state.get("form", {}).get("CountryRemMadeSecb", ""),
                        "RateTdsADtaa": state.get("form", {}).get("RateTdsADtaa", ""),
                        "NatureRemCategory": state.get("form", {}).get("NatureRemCategory", ""),
                    },
                )
                logger.info("invoice_processed file=%s elapsed=%.2fs", file.name, time.time() - start)
        st.session_state["invoice_states"] = states
        if states:
            st.success(f"Processed {len(states)} invoices.")
            logger.info("process_complete invoice_count=%s ids=%s", len(states), list(states.keys()))


invoice_states = st.session_state.get("invoice_states", {})
if invoice_states:
    st.subheader("Step 2 - Review Invoices")
    ordered_ids = list(invoice_states.keys())
    tabs = st.tabs([invoice_states[i]["meta"]["file_name"] for i in ordered_ids])

    all_xml_payloads: List[tuple[str, bytes]] = []
    for tab, invoice_id in zip(tabs, ordered_ids):
        with tab:
            state = invoice_states[invoice_id]
            logger.info("review_start invoice_id=%s file=%s", invoice_id, state.get("meta", {}).get("file_name"))
            state = render_invoice_tab(state)
            state = recompute_invoice(state)
            st.session_state["invoice_states"][invoice_id] = state
            logger.info(
                "review_recomputed invoice_id=%s computed=%s",
                invoice_id,
                {
                    "RemitterPAN": state.get("form", {}).get("RemitterPAN", ""),
                    "CountryRemMadeSecb": state.get("form", {}).get("CountryRemMadeSecb", ""),
                    "RateTdsADtaa": state.get("form", {}).get("RateTdsADtaa", ""),
                    "TaxLiablIt": state.get("form", {}).get("TaxLiablIt", ""),
                    "AmtPayForgnTds": state.get("form", {}).get("AmtPayForgnTds", ""),
                },
            )

            xml_fields = build_xml_fields_by_mode(state)
            mode = str(state.get("meta", {}).get("mode") or MODE_TDS)
            logger.info(
                "xml_fields_built invoice_id=%s mode=%s snapshot=%s",
                invoice_id,
                mode,
                {
                    "RemitterPAN": xml_fields.get("RemitterPAN", ""),
                    "CountryRemMadeSecb": xml_fields.get("CountryRemMadeSecb", ""),
                    "RateTdsADtaa": xml_fields.get("RateTdsADtaa", ""),
                    "RateTdsSecB": xml_fields.get("RateTdsSecB", ""),
                    "TaxLiablIt": xml_fields.get("TaxLiablIt", ""),
                },
            )
            errors = _validate_xml_fields(xml_fields, mode=mode)
            if errors:
                logger.warning("review_blocked invoice_id=%s errors=%s", invoice_id, errors)
                for err in errors:
                    st.error(err)
            else:
                try:
                    xml_content = generate_xml_content(xml_fields, mode=mode)
                    logger.info("xml_generate_ok invoice_id=%s bytes=%s", invoice_id, len(xml_content.encode("utf8")))
                except Exception as exc:
                    logger.exception("xml_generate_failed invoice_id=%s", invoice_id)
                    st.error(f"XML generation failed: {exc}")
                    continue
                file_stub = str(state["extracted"].get("invoice_number") or state["meta"]["invoice_id"]).replace(" ", "_")
                xml_filename = f"form15cb_{file_stub}.xml"
                st.download_button(
                    "Generate XML",
                    data=xml_content.encode("utf8"),
                    file_name=xml_filename,
                    mime="application/xml",
                    key=f"dl_{invoice_id}",
                )
                if st.button("Save XML to output folder", key=f"save_{invoice_id}"):
                    path = write_xml_content(xml_content, filename=xml_filename)
                    st.success(f"Saved: {path}")
                all_xml_payloads.append((xml_filename, xml_content.encode("utf8")))

    st.divider()
    st.subheader("Batch Output")
    if all_xml_payloads:
        zip_bytes = generate_zip_from_xmls(all_xml_payloads)
        st.download_button(
            "Generate All XMLs as ZIP",
            data=zip_bytes,
            file_name="form15cb_batch.zip",
            mime="application/zip",
        )

st.markdown("---")
st.caption(f"Version: {VERSION} | Last Updated: {LAST_UPDATED}")
