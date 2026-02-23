from __future__ import annotations

from datetime import date, timedelta
from typing import Dict

from modules.currency_mapping import load_currency_exact_index, resolve_short_code_currency
from modules.form15cb_constants import (
    MODE_NON_TDS,
    MODE_TDS,
    PROPOSED_DATE_OFFSET_DAYS,
)
from modules.invoice_calculator import recompute_invoice
from modules.logger import get_logger
from modules.master_lookups import (
    infer_country_from_beneficiary_name,
    load_nature_options,
    load_purpose_grouped,
    match_remitter,
    resolve_bank_code,
    resolve_dtaa,
)

logger = get_logger()


def build_invoice_state(invoice_id: str, file_name: str, extracted: Dict[str, str], config: Dict[str, str]) -> Dict[str, object]:
    mode = config.get("mode", MODE_TDS)
    source_short = config.get("currency_short", "")
    resolved_currency = resolve_short_code_currency(source_short, load_currency_exact_index())
    state: Dict[str, object] = {
        "meta": {
            "invoice_id": invoice_id,
            "file_name": file_name,
            "mode": MODE_NON_TDS if mode == MODE_NON_TDS else MODE_TDS,
            "exchange_rate": str(config.get("exchange_rate", "")),
            "source_currency_short": source_short,
        },
        "extracted": extracted,
        "resolved": {},
        "form": {},
        "computed": {},
        "xml_fields": {},
    }

    form = state["form"]
    resolved = state["resolved"]
    logger.info(
        "state_build_start invoice_id=%s file=%s mode=%s source_currency=%s extracted_summary=%s",
        invoice_id,
        file_name,
        state["meta"]["mode"],
        source_short,
        {
            "remitter_name": extracted.get("remitter_name", ""),
            "beneficiary_name": extracted.get("beneficiary_name", ""),
            "amount": extracted.get("amount", ""),
            "invoice_date_iso": extracted.get("invoice_date_iso", ""),
        },
    )
    form["AmtPayForgnRem"] = extracted.get("amount", "")
    form["CurrencySecbCode"] = resolved_currency.get("code", "")
    form["RemitteeZipCode"] = "999999"
    form["RemitteeState"] = "OUTSIDE INDIA"
    form["TaxPayGrossSecb"] = "N"
    form["DednDateTds"] = date.today().isoformat()
    form["PropDateRem"] = (date.today() + timedelta(days=PROPOSED_DATE_OFFSET_DAYS)).isoformat()

    inferred_country_code = infer_country_from_beneficiary_name(extracted.get("beneficiary_name", ""))
    logger.info(
        "state_country_inference invoice_id=%s beneficiary=%s inferred_country_code=%s",
        invoice_id,
        extracted.get("beneficiary_name", ""),
        inferred_country_code,
    )
    if inferred_country_code:
        form["RemitteeCountryCode"] = inferred_country_code
        form["CountryRemMadeSecb"] = inferred_country_code
        # Seed DTAA fields so tax values can auto-calculate before manual country selection.
        country_hint = extracted.get("beneficiary_name", "")
        dtaa = resolve_dtaa(country_hint) or None
        if not dtaa and inferred_country_code == "49":
            dtaa = resolve_dtaa("Germany")
        if dtaa:
            form["RelevantDtaa"] = str(dtaa.get("dtaa_applicable") or "")
            form["RelevantArtDtaa"] = str(dtaa.get("dtaa_applicable") or "")
            try:
                resolved["dtaa_rate_percent"] = str(float(str(dtaa.get("percentage"))) * 100).rstrip("0").rstrip(".")
                form["RateTdsADtaa"] = resolved["dtaa_rate_percent"]
                form["ArtDtaa"] = form["RelevantArtDtaa"]
            except Exception:
                pass
        else:
            logger.warning("state_dtaa_not_found invoice_id=%s country_hint=%s", invoice_id, country_hint)

    # Seed remittee address fields from OCR/Gemini enrichment when available.
    if extracted.get("beneficiary_street"):
        form.setdefault("RemitteeFlatDoorBuilding", str(extracted.get("beneficiary_street") or ""))
    if extracted.get("beneficiary_zip_text"):
        form.setdefault("RemitteeAreaLocality", str(extracted.get("beneficiary_zip_text") or ""))
    if extracted.get("beneficiary_city"):
        form.setdefault("RemitteeTownCityDistrict", str(extracted.get("beneficiary_city") or ""))
    if extracted.get("beneficiary_country_text") and not form.get("RemitteeCountryCode"):
        inferred_by_text = infer_country_from_beneficiary_name(str(extracted.get("beneficiary_country_text") or ""))
        if inferred_by_text:
            form["RemitteeCountryCode"] = inferred_by_text
            logger.info(
                "state_remittee_country_from_text invoice_id=%s beneficiary_country_text=%s inferred_code=%s",
                invoice_id,
                extracted.get("beneficiary_country_text", ""),
                inferred_by_text,
            )

    # Wire Gemini-extracted nature_of_remittance, purpose_group, purpose_code into form state
    if extracted.get("nature_of_remittance"):
        nature_label = str(extracted.get("nature_of_remittance", "")).strip()
        # Find the matching nature code from master data
        nature_opts = load_nature_options()
        for opt in nature_opts:
            if str(opt.get("label", "")).strip() == nature_label:
                form["NatureRemCategory"] = str(opt.get("code", ""))
                logger.info(
                    "state_nature_set invoice_id=%s label=%s code=%s",
                    invoice_id,
                    nature_label,
                    form.get("NatureRemCategory", ""),
                )
                break

    if extracted.get("purpose_code"):
        purpose_code = str(extracted.get("purpose_code", "")).strip().upper()

        # Look up the code in Purpose_code_List and derive group_name + gr_no from same record
        purpose_grouped = load_purpose_grouped()
        matched_code = False
        for group_name, codes in purpose_grouped.items():
            for code_record in codes:
                if str(code_record.get("purpose_code", "")).strip().upper() == purpose_code:
                    gr_no = str(code_record.get("gr_no", "00") or "00").strip()
                    form["_purpose_group"] = group_name
                    form["_purpose_code"] = purpose_code
                    form["RevPurCategory"] = f"RB-{gr_no}.1"
                    form["RevPurCode"] = f"RB-{gr_no}.1-{purpose_code}"
                    matched_code = True
                    logger.info(
                        "state_purpose_set invoice_id=%s group=%s code=%s gr_no=%s",
                        invoice_id,
                        group_name,
                        purpose_code,
                        gr_no,
                    )
                    break
            else:
                continue
            break
        if not matched_code:
            logger.warning("state_purpose_code_not_found invoice_id=%s code=%s", invoice_id, purpose_code)

    rem = match_remitter(extracted.get("remitter_name", ""))
    if rem:
        resolved["remitter_match"] = "1"
        resolved["pan"] = rem.get("pan", "")
        resolved["bank_name"] = rem.get("bank_name", "")
        resolved["branch"] = rem.get("branch", "")
        resolved["bsr"] = rem.get("bsr", "")
        resolved["bank_code"] = resolve_bank_code(rem.get("bank_name", ""))
        form["RemitterPAN"] = rem.get("pan", "")
        form["NameBankDisplay"] = rem.get("bank_name", "")
        form["NameBankCode"] = resolved["bank_code"]
        form["BranchName"] = rem.get("branch", "")
        form["BsrCode"] = rem.get("bsr", "")
        form["_lock_pan_bank_branch_bsr"] = "1"
        logger.info(
            "state_remitter_match invoice_id=%s remitter_name=%s pan=%s bank=%s",
            invoice_id,
            extracted.get("remitter_name", ""),
            rem.get("pan", ""),
            rem.get("bank_name", ""),
        )
    else:
        form["_lock_pan_bank_branch_bsr"] = "0"
        logger.warning(
            "state_remitter_not_matched invoice_id=%s remitter_name=%s",
            invoice_id,
            extracted.get("remitter_name", ""),
        )
    state = recompute_invoice(state)
    logger.info(
        "state_build_done invoice_id=%s form_snapshot=%s",
        invoice_id,
        {
            "RemitterPAN": form.get("RemitterPAN", ""),
            "CountryRemMadeSecb": form.get("CountryRemMadeSecb", ""),
            "RateTdsADtaa": form.get("RateTdsADtaa", ""),
            "TaxLiablIt": form.get("TaxLiablIt", ""),
            "AmtPayForgnTds": form.get("AmtPayForgnTds", ""),
        },
    )
    return state

