from __future__ import annotations

import io
import os
import time
from datetime import datetime

import streamlit as st

from config.settings import PARITY_UI_ENABLED
from modules.field_extractor import XML_FIELD_KEYS, extract_fields
from modules.file_manager import ensure_folders, save_uploaded_file
from modules.form_ui import render_form
from modules.logger import get_logger
from modules.master_data import validate_bsr_code, validate_dtaa_rate, validate_pan, validate_purpose_code
from modules.ocr_engine import extract_text_from_image_file
from modules.pdf_reader import extract_text_from_pdf
from modules.xml_generator import generate_xml
from modules.xml_parser import parse_xml_to_fields


MAX_FILE_SIZE = 10 * 1024 * 1024
VERSION = "2.2"
LAST_UPDATED = "February 2026"

logger = get_logger()
ensure_folders()


st.set_page_config(page_title="Form 15CB Verification UI", layout="wide", initial_sidebar_state="collapsed")
st.title("Form 15CB Verification UI")

st.markdown(
    """
<style>
  /* Professional, readable field styling for dark/light themes */
  div[data-testid="stTextInput"] input,
  div[data-testid="stNumberInput"] input,
  div[data-testid="stDateInput"] input,
  div[data-testid="stTextArea"] textarea {
    background-color: #e6e8ee !important;
    color: #141824 !important;
    border: 1px solid #b8bfcc !important;
    font-size: 0.95rem !important;
    line-height: 1.35 !important;
  }

  div[data-testid="stTextInput"] input::placeholder,
  div[data-testid="stNumberInput"] input::placeholder,
  div[data-testid="stDateInput"] input::placeholder,
  div[data-testid="stTextArea"] textarea::placeholder {
    color: #555d6f !important;
    opacity: 1 !important;
  }

  /* Streamlit disabled fields use webkit text fill; force readable dark text */
  div[data-testid="stTextInput"] input:disabled,
  div[data-testid="stNumberInput"] input:disabled,
  div[data-testid="stDateInput"] input:disabled,
  div[data-testid="stTextArea"] textarea:disabled {
    color: #141824 !important;
    -webkit-text-fill-color: #141824 !important;
    opacity: 1 !important;
  }

  div[data-testid="stSelectbox"] div[data-baseweb="select"] input {
    color: #141824 !important;
    -webkit-text-fill-color: #141824 !important;
  }

  div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
    font-size: 0.95rem !important;
  }

  .f15cb-header-main {
    text-align: center;
    font-size: 1.05rem;
    line-height: 1.15;
    font-weight: 700;
    margin-bottom: 0.15rem;
  }
  .f15cb-header-sub {
    text-align: center;
    font-size: 0.85rem;
    line-height: 1.1;
    margin-bottom: 0.1rem;
  }
  .f15cb-header-title {
    text-align: center;
    font-size: 0.95rem;
    line-height: 1.1;
    font-weight: 600;
    margin-bottom: 0.7rem;
  }
  .f15cb-line-text {
    font-size: 0.92rem;
    line-height: 1.4;
    font-weight: 600;
    margin-top: 0.45rem;
  }
</style>
""",
    unsafe_allow_html=True,
)

input_mode = st.radio("Input Mode", ["Upload Invoice (PDF/Image)", "Upload Existing XML for Review"], horizontal=True)

if "extracted_fields" not in st.session_state:
    st.session_state["extracted_fields"] = {}


def _merge_into_session(data: dict) -> None:
    clean = {k: str(v) for k, v in data.items() if v is not None}
    st.session_state["extracted_fields"].update(clean)


def _process_invoice_upload() -> None:
    uploaded = st.file_uploader("Upload PDF or image", type=["pdf", "png", "jpg", "jpeg"], key="invoice_uploader")
    if not uploaded:
        return
    if uploaded.size > MAX_FILE_SIZE:
        st.error(f"File too large: {uploaded.size/1024/1024:.1f} MB (max 10 MB)")
        return

    path = save_uploaded_file(uploaded, uploaded.name)
    st.success(f"Uploaded: {uploaded.name}")

    with st.spinner("Extracting text..."):
        start = time.time()
        text = ""
        try:
            uploaded.seek(0)
            text = extract_text_from_pdf(io.BytesIO(uploaded.read()))
        except Exception:
            text = ""
        if not text or len(text.strip()) < 20:
            text = extract_text_from_image_file(path)
        elapsed = time.time() - start

    st.caption(f"Text extraction completed in {elapsed:.1f}s")
    with st.expander("View extracted text (preview)", expanded=False):
        st.code(text[:4000], language="text")

    with st.spinner("Extracting fields with AI..."):
        extracted = extract_fields(text)
    _merge_into_session(extracted)
    st.success(f"Loaded {len([v for v in extracted.values() if v])} populated fields from invoice")
    logger.info("invoice_extraction populated=%d", len([v for v in extracted.values() if v]))


def _process_xml_upload() -> None:
    uploaded = st.file_uploader("Upload existing Form 15CB XML", type=["xml"], key="xml_uploader")
    if not uploaded:
        return
    if uploaded.size > MAX_FILE_SIZE:
        st.error(f"File too large: {uploaded.size/1024/1024:.1f} MB (max 10 MB)")
        return

    path = save_uploaded_file(uploaded, uploaded.name)
    parsed = parse_xml_to_fields(path)
    _merge_into_session(parsed)
    st.success(f"Loaded {len(parsed)} fields from XML")
    logger.info("xml_review_load fields=%d", len(parsed))


def _render_legacy_flat_form() -> dict:
    st.subheader("Step 3: Review in Legacy Flat Form")
    fields = st.session_state["extracted_fields"]
    edited = {}
    for field_key in XML_FIELD_KEYS:
        edited[field_key] = st.text_input(field_key, value=fields.get(field_key, ""), key=f"legacy_{field_key}")
    fields.update(edited)
    return {k: str(v) for k, v in fields.items() if not str(k).startswith("_")}


if input_mode == "Upload Invoice (PDF/Image)":
    _process_invoice_upload()
else:
    _process_xml_upload()


has_fields = bool(st.session_state.get("extracted_fields"))
if has_fields:
    if PARITY_UI_ENABLED:
        st.caption("Parity UI mode: enabled")
        final_fields = render_form()
    else:
        st.caption("Parity UI mode: disabled (legacy fallback)")
        final_fields = _render_legacy_flat_form()

    with st.expander("Template / fixed metadata", expanded=False):
        f = st.session_state["extracted_fields"]
        f["SWVersionNo"] = st.text_input("Software Version", value=f.get("SWVersionNo", "1"))
        f["SWCreatedBy"] = st.text_input("Software Created By", value=f.get("SWCreatedBy", "DIT-EFILING-JAVA"))
        f["XMLCreatedBy"] = st.text_input("XML Created By", value=f.get("XMLCreatedBy", "DIT-EFILING-JAVA"))
        f["XMLCreationDate"] = st.text_input("XML Creation Date", value=f.get("XMLCreationDate", datetime.now().strftime("%Y-%m-%d")))
        f["IntermediaryCity"] = st.text_input("Intermediary City", value=f.get("IntermediaryCity", "Delhi"))
        f["FormName"] = st.text_input("Form Name", value=f.get("FormName", "FORM15CB"))
        f["Description"] = st.text_input("Description", value=f.get("Description", "FORM15CB"))
        f["AssessmentYear"] = st.text_input("Assessment Year", value=f.get("AssessmentYear", "2025"))
        f["SchemaVer"] = st.text_input("Schema Version", value=f.get("SchemaVer", "Ver1.1"))
        f["FormVer"] = st.text_input("Form Version", value=f.get("FormVer", "1"))
        final_fields = {k: str(v) for k, v in f.items() if not str(k).startswith("_")}

    st.divider()
    generate = st.button("Generate XML", type="primary", use_container_width=True)
    if generate:
        missing = [k for k in ["RemitterPAN", "NameRemitter", "AmtPayIndRem"] if not final_fields.get(k, "").strip()]
        errors = []
        if final_fields.get("RemitterPAN") and not validate_pan(final_fields["RemitterPAN"]):
            errors.append("RemitterPAN format is invalid (expected AAAAA9999A).")
        if final_fields.get("BsrCode") and not validate_bsr_code(final_fields["BsrCode"]):
            errors.append("BsrCode must be exactly 7 digits.")
        if final_fields.get("RevPurCode") and not validate_purpose_code(final_fields["RevPurCode"]):
            errors.append("RevPurCode format is invalid (expected RB-xx.x or RB-xx.x-Snnnn).")
        if final_fields.get("RateTdsADtaa") and not validate_dtaa_rate(final_fields["RateTdsADtaa"]):
            errors.append("RateTdsADtaa must be between 0 and 100.")

        if missing:
            st.error(f"Missing mandatory fields: {', '.join(missing)}")
        elif errors:
            for err in errors:
                st.error(err)
        else:
            try:
                xml_path = generate_xml(final_fields)
                with open(xml_path, "r", encoding="utf8") as f:
                    content = f.read()
                st.success("XML generated successfully.")
                with st.expander("Preview XML", expanded=True):
                    st.code(content, language="xml")
                with open(xml_path, "rb") as f:
                    st.download_button("Download XML", data=f, file_name=os.path.basename(xml_path), mime="application/xml")
            except Exception as exc:
                logger.exception("xml_generate_failed")
                st.error(f"XML generation failed: {exc}")

st.markdown("---")
st.caption(f"Version: {VERSION} | Last Updated: {LAST_UPDATED}")
