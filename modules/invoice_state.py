from __future__ import annotations

from datetime import date, timedelta
from typing import Dict
import re

from modules.currency_mapping import load_currency_exact_index, resolve_currency_selection
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
    resolve_country_name,
    resolve_dtaa,
    split_dtaa_article_text,
)
from modules.text_normalizer import normalize_single_line_text

logger = get_logger()


def _split_beneficiary_address(address: str) -> tuple[str, str, str]:
    text = " ".join(str(address or "").split()).strip(" ,")
    if not text:
        return "", "", ""

    # Mexico-style fallback: "... <LOCALITY> C.P.:<ZIP> <CITY/DISTRICT>"
    # Example:
    #   CircuitoG.GonzalezCamarena333 SANTAFE ALVAROOBREGON C.P.:01210 DISTRITOFEDERAL
    cp_match = re.search(r"\bC\.?\s*P\.?\s*:?\s*\d{4,6}\b.*$", text, flags=re.IGNORECASE)
    if cp_match:
        cp_segment = cp_match.group(0).strip(" ,")
        pre_cp = text[: cp_match.start()].strip(" ,")
        pre_tokens = [tok for tok in pre_cp.split() if tok]
        street = pre_cp
        locality = ""
        if len(pre_tokens) >= 2:
            # Detect tail block of uppercase locality words.
            split_idx = None
            for i in range(1, len(pre_tokens)):
                head = pre_tokens[:i]
                tail = pre_tokens[i:]
                if not tail:
                    continue
                if all(re.fullmatch(r"[A-Z0-9][A-Z0-9.&'/-]*", t) for t in tail):
                    split_idx = i
                    break
            if split_idx is not None:
                street = " ".join(pre_tokens[:split_idx]).strip(" ,")
                locality = " ".join(pre_tokens[split_idx:]).strip(" ,")
        return street or pre_cp, locality, cp_segment

    parts = [p.strip(" ,") for p in re.split(r",|\n", text) if p.strip(" ,")]
    if not parts:
        return text, "", ""

    # Drop trailing country token if present ("Germany", "UNITED STATES OF AMERICA", etc.)
    last = parts[-1].upper()
    if len(last) >= 4 and infer_country_from_beneficiary_name(last):
        parts = parts[:-1]

    if not parts:
        return text, "", ""
    if len(parts) == 1:
        single = parts[0]
        # Handle slash-separated foreign addresses, e.g. "... Nilüfer/Bursa/16140"
        if "/" in single:
            slash_parts = [p.strip(" ,") for p in single.split("/") if p.strip(" ,")]
            if len(slash_parts) >= 3:
                street = "/".join(slash_parts[:-2]).strip(" ,")
                city = slash_parts[-2]
                locality = slash_parts[-1]
                return street or single, locality, city
            if len(slash_parts) == 2:
                street = slash_parts[0]
                city_or_zip = slash_parts[1]
                return street, city_or_zip, city_or_zip
        return single, "", ""
    if len(parts) == 2:
        return parts[0], parts[1], parts[1]

    street = parts[0]
    locality = ", ".join(parts[1:-1]).strip(" ,")
    city = parts[-1]
    return street, locality, city


def build_invoice_state(invoice_id: str, file_name: str, extracted: Dict[str, str], config: Dict[str, str]) -> Dict[str, object]:
    mode = config.get("mode", MODE_TDS)
    source_short = config.get("currency_short", "")
    resolved_currency = resolve_currency_selection(source_short, load_currency_exact_index())
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

    # Infer country from beneficiary name/country text/address combined.
    beneficiary_country_text = normalize_single_line_text(str(extracted.get("beneficiary_country_text") or ""))
    beneficiary_address = normalize_single_line_text(str(extracted.get("beneficiary_address") or ""))
    beneficiary_name = normalize_single_line_text(str(extracted.get("beneficiary_name") or ""))
    extraction_core_empty = not any(
        str(extracted.get(k) or "").strip()
        for k in ("remitter_name", "beneficiary_name", "invoice_number", "amount", "currency_short")
    )
    country_probe = " ".join([beneficiary_country_text, beneficiary_address, beneficiary_name]).strip()
    inferred_country_code = infer_country_from_beneficiary_name(
        country_probe,
        beneficiary_address,
    )
    logger.info(
        "state_country_inference invoice_id=%s beneficiary=%s country_text=%s inferred_country_code=%s",
        invoice_id,
        beneficiary_name,
        beneficiary_country_text,
        inferred_country_code,
    )
    if inferred_country_code == "91" and mode == MODE_TDS:
        # Outward remittance guard: beneficiary must be foreign for this workflow.
        # If beneficiary resolves to India, retry from remitter side first.
        remitter_probe = " ".join(
            [
                str(extracted.get("remitter_country_text") or ""),
                str(extracted.get("remitter_address") or ""),
                str(extracted.get("remitter_name") or ""),
            ]
        )
        alternate_country_code = infer_country_from_beneficiary_name(
            remitter_probe,
            str(extracted.get("remitter_address") or ""),
        )
        if alternate_country_code and alternate_country_code != "91":
            logger.warning(
                "state_country_india_safeguard invoice_id=%s old_country=%s alternate_country=%s",
                invoice_id,
                inferred_country_code,
                alternate_country_code,
            )
            inferred_country_code = alternate_country_code
        else:
            # Keep country foreign-only: never finalize India here.
            logger.warning(
                "state_country_india_disallowed invoice_id=%s old_country=%s fallback=9999",
                invoice_id,
                inferred_country_code,
            )
            inferred_country_code = ""

    if inferred_country_code:
        form["RemitteeCountryCode"] = inferred_country_code
        form["CountryRemMadeSecb"] = inferred_country_code
        # Seed DTAA fields so tax values can auto-calculate before manual country selection.
        country_hint = resolve_country_name(inferred_country_code) or beneficiary_country_text
        if extraction_core_empty:
            logger.warning(
                "state_dtaa_seed_skipped invoice_id=%s reason=core_extraction_empty country_hint=%s",
                invoice_id,
                country_hint,
            )
        else:
            dtaa = resolve_dtaa(country_hint) or None
            if dtaa:
                dtaa_without_article, dtaa_with_article = split_dtaa_article_text(str(dtaa.get("dtaa_applicable") or ""))
                form["RelevantDtaa"] = dtaa_without_article
                form["RelevantArtDtaa"] = dtaa_with_article
                try:
                    resolved["dtaa_rate_percent"] = str(float(str(dtaa.get("percentage"))) * 100).rstrip("0").rstrip(".")
                    form["RateTdsADtaa"] = resolved["dtaa_rate_percent"]
                    form["ArtDtaa"] = dtaa_with_article
                except Exception:
                    pass
            else:
                logger.warning("state_dtaa_not_found invoice_id=%s country_hint=%s", invoice_id, country_hint)
    else:
        # Never leave country blank; use OTHERS so user can still proceed and correct in UI.
        form["RemitteeCountryCode"] = "9999"
        form["CountryRemMadeSecb"] = "9999"
        logger.warning(
            "state_country_fallback_others invoice_id=%s beneficiary=%s country_text=%s",
            invoice_id,
            beneficiary_name,
            beneficiary_country_text,
        )

    # Seed remittee address fields from OCR/Gemini enrichment when available.
    if extracted.get("beneficiary_street"):
        form.setdefault("RemitteeFlatDoorBuilding", str(extracted.get("beneficiary_street") or ""))
    if extracted.get("beneficiary_zip_text"):
        form.setdefault("RemitteeAreaLocality", str(extracted.get("beneficiary_zip_text") or ""))
    if extracted.get("beneficiary_city"):
        form.setdefault("RemitteeTownCityDistrict", str(extracted.get("beneficiary_city") or ""))
    # Fallback split from full beneficiary_address when granular components are missing.
    if beneficiary_address and (
        not form.get("RemitteeFlatDoorBuilding")
        or not form.get("RemitteeAreaLocality")
        or not form.get("RemitteeTownCityDistrict")
    ):
        flat, area, city = _split_beneficiary_address(beneficiary_address)
        if flat and not form.get("RemitteeFlatDoorBuilding"):
            form["RemitteeFlatDoorBuilding"] = flat
        if area and not form.get("RemitteeAreaLocality"):
            form["RemitteeAreaLocality"] = area
        if city and not form.get("RemitteeTownCityDistrict"):
            form["RemitteeTownCityDistrict"] = city
    # Final fallback for area/locality from zip text if available.
    if not form.get("RemitteeAreaLocality") and extracted.get("beneficiary_zip_text"):
        form["RemitteeAreaLocality"] = str(extracted.get("beneficiary_zip_text") or "")

    if extracted.get("beneficiary_country_text") and str(form.get("RemitteeCountryCode") or "") in {"", "9999"}:
        inferred_by_text = infer_country_from_beneficiary_name(
            str(extracted.get("beneficiary_country_text") or ""),
            str(extracted.get("beneficiary_address") or "")  # Also scan address
        )
        if mode == MODE_TDS and inferred_by_text == "91":
            inferred_by_text = ""
        if inferred_by_text:
            form["RemitteeCountryCode"] = inferred_by_text
            form["CountryRemMadeSecb"] = inferred_by_text
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
