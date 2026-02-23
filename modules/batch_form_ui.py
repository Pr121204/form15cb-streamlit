from __future__ import annotations

from typing import Dict, List
from datetime import date

import streamlit as st

from modules.form15cb_constants import (
    CA_FIRM_OPTIONS,
    MODE_NON_TDS,
    MODE_TDS,
    REMITTEE_STATE,
    REMITTEE_ZIP_CODE,
)
from modules.invoice_calculator import recompute_invoice
from modules.logger import get_logger
from modules.master_lookups import (
    get_bank_options,
    get_country_options,
    get_currency_options,
    load_nature_options,
    load_purpose_grouped,
    match_remitter,
    resolve_bank_code,
    resolve_country_code,
    resolve_dtaa,
)

logger = get_logger()


def _dtaa_rate_percent(raw: str) -> str:
    try:
        return str(float(str(raw)) * 100).rstrip("0").rstrip(".")
    except Exception:
        return ""


def _apply_remitter_match(state: Dict[str, object], remitter_name: str) -> None:
    invoice_id = str(state.get("meta", {}).get("invoice_id") or "")
    form = state["form"]
    resolved = state["resolved"]
    rec = match_remitter(remitter_name)
    if rec:
        resolved["remitter_match"] = "1"
        resolved["pan"] = rec.get("pan", "")
        resolved["bank_name"] = rec.get("bank_name", "")
        resolved["branch"] = rec.get("branch", "")
        resolved["bsr"] = rec.get("bsr", "")
        resolved["bank_code"] = resolve_bank_code(rec.get("bank_name", ""))
        form["RemitterPAN"] = rec.get("pan", "")
        form["NameBankDisplay"] = rec.get("bank_name", "")
        form["NameBankCode"] = resolved["bank_code"]
        form["BranchName"] = rec.get("branch", "")
        form["BsrCode"] = rec.get("bsr", "")
        form["_lock_pan_bank_branch_bsr"] = "1"
        logger.info(
            "ui_remitter_match invoice_id=%s remitter_name=%s pan=%s bank=%s",
            invoice_id,
            remitter_name,
            rec.get("pan", ""),
            rec.get("bank_name", ""),
        )
    else:
        resolved["remitter_match"] = "0"
        form["_lock_pan_bank_branch_bsr"] = "0"
        logger.warning("ui_remitter_not_matched invoice_id=%s remitter_name=%s", invoice_id, remitter_name)


def render_invoice_tab(state: Dict[str, object]) -> Dict[str, object]:
    meta = state["meta"]
    extracted = state["extracted"]
    form = state["form"]

    invoice_id = str(meta["invoice_id"])
    mode = str(meta.get("mode") or MODE_TDS)
    st.markdown("### FORM NO. 15CB")
    st.caption("Certificate of an accountant")
    st.caption(f"Mode: {'TDS' if mode == MODE_TDS else 'Non-TDS'}")
    extracted_currency = str(extracted.get("currency_short") or "").strip().upper()
    selected_currency = str(meta.get("source_currency_short") or "").strip().upper()
    if extracted_currency and selected_currency and extracted_currency != selected_currency:
        st.warning(
            f"Gemini detected {extracted_currency} from invoice but {selected_currency} was selected in Step 1. "
            "Please confirm which is correct."
        )
        logger.warning(
            "ui_currency_mismatch invoice_id=%s extracted_currency=%s selected_currency=%s",
            invoice_id,
            extracted_currency,
            selected_currency,
        )

    c1, c2 = st.columns(2)
    with c1:
        remitter_name = st.text_input(
            "Name of the Remitter",
            key=f"{invoice_id}_remitter_name",
            value=str(form.get("NameRemitterInput") or extracted.get("remitter_name") or ""),
        )
        form["NameRemitterInput"] = remitter_name
        _apply_remitter_match(state, remitter_name)
        lock = form.get("_lock_pan_bank_branch_bsr") == "1"
        form["RemitterPAN"] = st.text_input(
            "PAN/TAN",
            key=f"{invoice_id}_pan",
            value=str(form.get("RemitterPAN") or ""),
            disabled=lock,
        )
        form["RemitterAddress"] = st.text_input(
            "Remitter Address (as per invoice, appended to name in XML)",
            key=f"{invoice_id}_remitter_addr",
            value=str(form.get("RemitterAddress") or extracted.get("remitter_address") or ""),
        )
    with c2:
        form["NameRemitteeInput"] = st.text_input(
            "Name of the Beneficiary",
            key=f"{invoice_id}_benef_name",
            value=str(form.get("NameRemitteeInput") or extracted.get("beneficiary_name") or ""),
        )
        form["RemitteeFlatDoorBuilding"] = st.text_input(
            "Flat / Door / Building",
            key=f"{invoice_id}_remittee_flat",
            value=str(form.get("RemitteeFlatDoorBuilding") or ""),
        )
        form["RemitteeAreaLocality"] = st.text_input(
            "Area / Locality",
            key=f"{invoice_id}_remittee_area",
            value=str(form.get("RemitteeAreaLocality") or ""),
        )
        form["RemitteeTownCityDistrict"] = st.text_input(
            "Town / City / District",
            key=f"{invoice_id}_remittee_town",
            value=str(form.get("RemitteeTownCityDistrict") or ""),
        )
        st.text_input("State", value=REMITTEE_STATE, disabled=True, key=f"{invoice_id}_remittee_state")
        st.text_input("ZIP Code", value=REMITTEE_ZIP_CODE, disabled=True, key=f"{invoice_id}_remittee_zip")

    st.markdown("#### Section B - Remittance")
    b1, b2, b3 = st.columns(3)
    country_opts = get_country_options()
    country_labels = ["SELECT"] + [f"{k} ({v})" for k, v in country_opts]
    current_country_code = str(form.get("CountryRemMadeSecb") or "")
    country_idx = 0
    for i, (_, code) in enumerate(country_opts):
        if code == current_country_code:
            country_idx = i + 1
            break
    with b1:
        country_sel = st.selectbox("Country to which remittance is made", country_labels or [""], index=country_idx, key=f"{invoice_id}_country")
        if country_sel and country_sel != "SELECT":
            country_name, country_code = country_sel.rsplit("(", 1)
            code = country_code.replace(")", "").strip()
            form["CountryRemMadeSecb"] = code
            form["RemitteeCountryCode"] = code
            form["_manual_dtaa_rate_required"] = "0"
            dtaa = resolve_dtaa(country_name.strip())
            if dtaa:
                form["RelevantDtaa"] = dtaa.get("dtaa_applicable", "")
                form["RelevantArtDtaa"] = dtaa.get("dtaa_applicable", "")
                percent = _dtaa_rate_percent(dtaa.get("percentage", ""))
                if percent:
                    # Persist DTAA rate into canonical places used by recompute and XML
                    state["resolved"]["dtaa_rate_percent"] = percent
                    form["RateTdsADtaa"] = percent
                    form["RateTdsSecB"] = percent
                    form["dtaa_rate"] = percent
                    form["ArtDtaa"] = dtaa.get("dtaa_applicable", "")
                    # Sync to session_state so Rate field widget displays it immediately
                    st.session_state[f"{invoice_id}_rate_tds_dtaa"] = str(percent)
                    # Ensure recompute runs with updated state immediately
                    try:
                        recompute_invoice(state)
                    except Exception:
                        logger.exception("recompute_failed_after_dtaa_write invoice_id=%s", invoice_id)
                else:
                    state["resolved"]["dtaa_rate_percent"] = ""
                    form["RateTdsADtaa"] = str(form.get("RateTdsADtaa") or "")
                    form["_manual_dtaa_rate_required"] = "1"
                    st.warning("No DTAA rate found for selected country. Please enter DTAA rate manually to proceed.")
                    logger.warning("ui_dtaa_rate_missing invoice_id=%s country=%s", invoice_id, country_name.strip())
                logger.info(
                    "ui_country_selected invoice_id=%s country_code=%s dtaa_article=%s dtaa_rate=%s",
                    invoice_id,
                    code,
                    form.get("RelevantDtaa", ""),
                    form.get("RateTdsADtaa", ""),
                )
            else:
                state["resolved"]["dtaa_rate_percent"] = ""
                form["RateTdsADtaa"] = str(form.get("RateTdsADtaa") or "")
                form["_manual_dtaa_rate_required"] = "1"
                form["RelevantDtaa"] = str(form.get("RelevantDtaa") or "NOT AVAILABLE")
                form["RelevantArtDtaa"] = str(form.get("RelevantArtDtaa") or "NOT AVAILABLE")
                form["ArtDtaa"] = str(form.get("ArtDtaa") or "NOT AVAILABLE")
                st.warning("No DTAA data found for selected country. Please enter DTAA rate manually to proceed.")
                logger.warning(
                    "ui_country_selected_no_dtaa invoice_id=%s country_code=%s",
                    invoice_id,
                    code,
                )
        elif mode == MODE_TDS:
            form["_manual_dtaa_rate_required"] = "0"
            st.error("Country required - select to enable tax calculations.")
            logger.warning("ui_country_not_selected invoice_id=%s", invoice_id)
    currency_opts = get_currency_options()
    currency_labels = [f"{k} ({v})" for k, v in currency_opts]
    current_currency_code = str(form.get("CurrencySecbCode") or "")
    currency_idx = 0
    for i, (_, code) in enumerate(currency_opts):
        if code == current_currency_code:
            currency_idx = i
            break
    with b2:
        currency_sel = st.selectbox("Currency", currency_labels or [""], index=currency_idx, key=f"{invoice_id}_currency")
        if currency_sel:
            form["CurrencySecbCode"] = currency_sel.rsplit("(", 1)[1].replace(")", "").strip()
    with b3:
        form["AmtPayForgnRem"] = st.text_input(
            "Amount in Foreign Currency",
            key=f"{invoice_id}_fcy_amt",
            value=str(form.get("AmtPayForgnRem") or ""),
        )
        st.text_input(
            "Amount in Indian ₹",
            key=f"{invoice_id}_inr_amt",
            value=str(form.get("AmtPayIndRem") or ""),
            disabled=True,
        )
        try:
            # Prefer any existing form value, otherwise derive from extracted invoice date
            prop_default = date.fromisoformat(str(form.get("PropDateRem") or extracted.get("invoice_date_iso") or ""))
        except Exception:
            prop_default = date.today()
        form["PropDateRem"] = st.date_input(
            "Proposed Date of Remittance",
            value=prop_default,
            key=f"{invoice_id}_prop_date",
        ).isoformat()

    bank_lock = form.get("_lock_pan_bank_branch_bsr") == "1"
    bank_opts = get_bank_options()
    bank_labels = [f"{k} ({v})" for k, v in bank_opts] + ["OTHER BANK"]
    cur_bank_code = str(form.get("NameBankCode") or "")
    b_idx = len(bank_labels) - 1
    for i, (_, code) in enumerate(bank_opts):
        if code == cur_bank_code:
            b_idx = i
            break
    bank_sel = st.selectbox("Name of Bank", bank_labels, index=b_idx, key=f"{invoice_id}_bank_dropdown", disabled=bank_lock)
    if bank_sel != "OTHER BANK":
        bank_name, bank_code = bank_sel.rsplit("(", 1)
        form["NameBankDisplay"] = bank_name.strip()
        form["NameBankCode"] = bank_code.replace(")", "").strip()
    else:
        form["NameBankDisplay"] = st.text_input(
            "Other Bank (manual)",
            key=f"{invoice_id}_bank_display",
            value=str(form.get("NameBankDisplay") or ""),
            disabled=bank_lock,
        )
        if not bank_lock:
            form["NameBankCode"] = resolve_bank_code(str(form.get("NameBankDisplay") or ""))
    form["BranchName"] = st.text_input("Branch", key=f"{invoice_id}_branch", value=str(form.get("BranchName") or ""), disabled=bank_lock)
    form["BsrCode"] = st.text_input("BSR Code", key=f"{invoice_id}_bsr", value=str(form.get("BsrCode") or ""), disabled=bank_lock)

    nature_opts = [n for n in load_nature_options() if n.get("code") != "-1"]
    nature_labels = ["SELECT"] + [f"{n['code']} - {n['label']}" for n in nature_opts]
    n_idx = 0
    for i, n in enumerate(nature_opts):
        if str(form.get("NatureRemCategory") or "") == str(n.get("code") or ""):
            n_idx = i + 1
            break
    nature_sel = st.selectbox("Nature of Remittance", nature_labels or [""], index=n_idx if nature_labels else 0, key=f"{invoice_id}_nature")
    if nature_sel and nature_sel != "SELECT":
        form["NatureRemCategory"] = nature_sel.split(" - ", 1)[0].strip()
    if str(form.get("NatureRemCategory") or "") == "16.99":
        form["NatureRemCode"] = st.text_input(
            "Specify nature (for 16.99)",
            key=f"{invoice_id}_nature_code",
            value=str(form.get("NatureRemCode") or ""),
        )

    purpose_grouped = load_purpose_grouped()
    groups = ["SELECT"] + sorted(purpose_grouped.keys())
    g_idx = 0
    if form.get("_purpose_group") and form.get("_purpose_group") in purpose_grouped:
        g_idx = groups.index(form["_purpose_group"]) if form["_purpose_group"] in groups else 0
    group_sel = st.selectbox("Purpose Group", groups or [""], index=g_idx if groups else 0, key=f"{invoice_id}_pur_group")
    form["_purpose_group"] = group_sel if group_sel != "SELECT" else ""
    rows = purpose_grouped.get(group_sel if group_sel != "SELECT" else "", [])
    row_labels = ["SELECT"] + [f"{r['purpose_code']} - {r['description']}" for r in rows]
    r_idx = 0
    for i, r in enumerate(rows):
        if r.get("purpose_code") == form.get("_purpose_code"):
            r_idx = i + 1
            break
    row_sel = st.selectbox("Purpose Code", row_labels or [""], index=r_idx if row_labels else 0, key=f"{invoice_id}_pur_code")
    if row_sel and row_sel != "SELECT":
        p_code = row_sel.split(" - ", 1)[0]
        form["_purpose_code"] = p_code
        chosen = next((r for r in rows if r.get("purpose_code") == p_code), None)
        if chosen:
            # Preserve gr_no as-is (do not treat 0 as missing)
            gr_val = chosen.get("gr_no")
            gr = str(gr_val) if gr_val is not None else "00"
            form["RevPurCategory"] = f"RB-{gr}.1"
            form["RevPurCode"] = f"RB-{gr}.1-{p_code}"

    mode_is_tds = mode == MODE_TDS
    form["TaxPayGrossSecb"] = st.selectbox("Grossed Up Tax", ["N", "Y"], index=0 if str(form.get("TaxPayGrossSecb", "N")) != "Y" else 1, key=f"{invoice_id}_gross")
    form["RemittanceCharIndia"] = "Y" if mode_is_tds else "N"
    form["ReasonNot"] = st.text_input("Reason if not chargeable", key=f"{invoice_id}_reason_not", value=str(form.get("ReasonNot") or ""), disabled=mode_is_tds)
    form["RateTdsSecbFlg"] = "2" if mode_is_tds else ""
    form["RemForRoyFlg"] = "Y" if mode_is_tds else "N"
    form["OtherRemDtaa"] = "N" if mode_is_tds else "Y"
    form["RelArtDetlDDtaa"] = "NOT APPLICABLE" if mode_is_tds else str(form.get("RelArtDetlDDtaa") or "")
    form["NameFirmAcctnt"] = st.selectbox(
        "Firm / Proprietorship",
        CA_FIRM_OPTIONS,
        index=0 if str(form.get("NameFirmAcctnt") or CA_FIRM_OPTIONS[0]) == CA_FIRM_OPTIONS[0] else 1,
        key=f"{invoice_id}_firm",
    )

    if mode_is_tds:
        rate_key = f"{invoice_id}_rate_tds_dtaa"
        if rate_key not in st.session_state:
            st.session_state[rate_key] = str(form.get("RateTdsADtaa") or state.get("resolved", {}).get("dtaa_rate_percent") or "")
        form["RateTdsADtaa"] = st.text_input(
            "Rate of TDS per DTAA (%)",
            key=rate_key,
        )
        if str(form.get("_manual_dtaa_rate_required") or "") == "1":
            st.caption("No DTAA data/rate found for selected country. Enter DTAA rate (%) manually to compute tax fields.")
        state["resolved"]["dtaa_rate_percent"] = str(form.get("RateTdsADtaa") or "").strip()
        if state["resolved"]["dtaa_rate_percent"]:
            logger.info("ui_rate_entered invoice_id=%s rate=%s", invoice_id, state["resolved"]["dtaa_rate_percent"])
        else:
            logger.warning("ui_rate_missing invoice_id=%s", invoice_id)
        form["DednDateTds"] = st.date_input("Date of deduction of TDS", key=f"{invoice_id}_dedn_date").isoformat()
    else:
        st.caption("Non-TDS mode - TDS fields are shown but disabled and will output as zero.")

    state = recompute_invoice(state)
    logger.info(
        "ui_recompute_done invoice_id=%s snapshot=%s",
        invoice_id,
        {
            "RemitterPAN": form.get("RemitterPAN", ""),
            "CountryRemMadeSecb": form.get("CountryRemMadeSecb", ""),
            "RateTdsADtaa": form.get("RateTdsADtaa", ""),
            "TaxLiablIt": form.get("TaxLiablIt", ""),
            "AmtPayForgnTds": form.get("AmtPayForgnTds", ""),
        },
    )
    if mode_is_tds:
        # Sync computed values to session_state so display widgets read current values, not stale cache
        st.session_state[f"{invoice_id}_tax_liab_it"] = str(form.get("TaxLiablIt") or "")
        st.session_state[f"{invoice_id}_tax_inc_dtaa"] = str(form.get("TaxIncDtaa") or "")
        st.session_state[f"{invoice_id}_tax_liab_dtaa"] = str(form.get("TaxLiablDtaa") or "")
        st.session_state[f"{invoice_id}_amt_tds_fcy"] = str(form.get("AmtPayForgnTds") or "")
        st.session_state[f"{invoice_id}_amt_tds_inr"] = str(form.get("AmtPayIndianTds") or "")
        st.session_state[f"{invoice_id}_rate_tds_secb"] = str(form.get("RateTdsSecB") or "")
        st.session_state[f"{invoice_id}_actl_amt_tds_forgn"] = str(form.get("ActlAmtTdsForgn") or "")
        st.session_state[f"{invoice_id}_basis_tax"] = str(form.get("BasisDeterTax") or "")
        st.markdown("#### TDS Computation")
        d1, d2, d3 = st.columns(3)
        with d1:
            st.text_input("Tax liability under IT Act (INR)", value=str(form.get("TaxLiablIt") or ""), disabled=True, key=f"{invoice_id}_tax_liab_it")
            st.text_input("Taxable income per DTAA (INR)", value=str(form.get("TaxIncDtaa") or ""), disabled=True, key=f"{invoice_id}_tax_inc_dtaa")
            st.text_input("Tax liability per DTAA (INR)", value=str(form.get("TaxLiablDtaa") or ""), disabled=True, key=f"{invoice_id}_tax_liab_dtaa")
        with d2:
            st.text_input("TDS Amount (foreign)", value=str(form.get("AmtPayForgnTds") or ""), disabled=True, key=f"{invoice_id}_amt_tds_fcy")
            st.text_input("TDS Amount (INR)", value=str(form.get("AmtPayIndianTds") or ""), disabled=True, key=f"{invoice_id}_amt_tds_inr")
            st.text_input("TDS Rate % (Section B)", value=str(form.get("RateTdsSecB") or ""), disabled=True, key=f"{invoice_id}_rate_tds_secb")
        with d3:
            st.text_input("Actual remittance after TDS (foreign)", value=str(form.get("ActlAmtTdsForgn") or ""), disabled=True, key=f"{invoice_id}_actl_amt_tds_forgn")
            st.text_area("Basis of determining tax", value=str(form.get("BasisDeterTax") or ""), disabled=True, key=f"{invoice_id}_basis_tax", height=80)
    return state
