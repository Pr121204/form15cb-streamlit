from __future__ import annotations

import unittest
from unittest.mock import patch

from modules.master_lookups import load_purpose_grouped
from modules.invoice_gemini_extractor import (
    _finalize_extracted_fields,
    _enrich_addresses_from_text,
    _extract_country_from_text,
    _detect_country_signals_from_text,
    _fallback_invoice_fields_from_text,
    _infer_nature_from_text,
    _is_valid_purpose_code,
    _purpose_group_for_code,
    merge_multi_page_image_extractions,
    normalize_party_roles,
    parse_invoice_date,
    keyword_fallback,
)
from modules.invoice_gemini_extractor import extract_invoice_core_fields
from modules.text_normalizer import is_ascii_clean


class TestInvoiceGeminiExtractor(unittest.TestCase):
    def test_swaps_when_foreign_is_remitter_and_indian_is_beneficiary(self) -> None:
        raw = {
            "remitter_name": "Bosch IO GmbH",
            "remitter_address": "Berlin, Germany",
            "beneficiary_name": "Bosch Global Software Technologies Private Limited",
            "invoice_number": "7057441295",
        }
        out = normalize_party_roles(raw)
        self.assertEqual(out["remitter_name"], "BOSCH GLOBAL SOFTWARE TECHNOLOGIES PRIVATE LIMITED")
        self.assertEqual(out["beneficiary_name"], "BOSCH IO GMBH")
        self.assertEqual(out["remitter_address"], "")

    def test_does_not_swap_when_remitter_already_indian(self) -> None:
        raw = {
            "remitter_name": "Myntra Jabong India Private Limited",
            "remitter_address": "Bengaluru",
            "beneficiary_name": "Kaimen Global Partners, S.L",
        }
        out = normalize_party_roles(raw)
        self.assertEqual(out["remitter_name"], "MYNTRA JABONG INDIA PRIVATE LIMITED")
        self.assertEqual(out["beneficiary_name"], "KAIMEN GLOBAL PARTNERS, S.L")
        self.assertEqual(out["remitter_address"], raw["remitter_address"])

    def test_swaps_using_country_signals_and_swaps_country_fields(self) -> None:
        raw = {
            "remitter_name": "Bosch Sanayi ve Ticaret Anonim Sirketi",
            "remitter_address": "Bursa, Turkey",
            "remitter_country_text": "Turkey",
            "beneficiary_name": "Bosch Limited",
            "beneficiary_address": "3000 Hosur Road, Adugodi, Bangalore, India",
            "beneficiary_country_text": "India",
        }
        out = normalize_party_roles(raw)
        self.assertEqual(out["remitter_name"], "BOSCH LIMITED")
        self.assertEqual(out["beneficiary_name"], "BOSCH SANAYI VE TICARET ANONIM SIRKETI")
        self.assertEqual(out.get("remitter_country_text", ""), "India")
        self.assertEqual(out.get("beneficiary_country_text", ""), "Turkey")

    def test_normalizes_bosch_lio_typo(self) -> None:
        text = "Company address Bosch.IO GmbH, Ullsteinstra3e 128, 12109 Berlin, Germany"
        # Force no API path by using short text and direct helper behavior through extraction defaults.
        # We validate name normalization through role normalization helper.
        out = normalize_party_roles(
            {
                "remitter_name": "Bosch.lIO GmbH",
                "beneficiary_name": "Bosch Global Software Technologies Private Limited",
                "remitter_address": "Berlin",
            }
        )
        self.assertEqual(out["beneficiary_name"], "BOSCH.IO GMBH")

    def test_normalizes_no_space_company_names_to_spaced_uppercase(self) -> None:
        out = normalize_party_roles(
            {
                "remitter_name": "BoschGlobalSoftwareTechnologiesPrivateLimited",
                "beneficiary_name": "RobertBoschMexico",
            }
        )
        self.assertEqual(out["remitter_name"], "BOSCH GLOBAL SOFTWARE TECHNOLOGIES PRIVATE LIMITED")
        self.assertEqual(out["beneficiary_name"], "ROBERT BOSCH MEXICO")
        self.assertTrue(is_ascii_clean(out["remitter_name"]))
        self.assertTrue(is_ascii_clean(out["beneficiary_name"]))

    def test_normalizes_accents_in_party_fields(self) -> None:
        out = normalize_party_roles(
            {
                "remitter_name": "Bosch São Paulo Ltda",
                "beneficiary_name": "Bosch Sanayi ve Ticaret AnonimŞirketi",
            }
        )
        self.assertEqual(out["remitter_name"], "BOSCH SAO PAULO LTDA")
        self.assertEqual(out["beneficiary_name"], "BOSCH SANAYI VE TICARET ANONIM SIRKETI")
        self.assertTrue(is_ascii_clean(out["beneficiary_name"]))

    def test_extract_country_from_country_label(self) -> None:
        text = "Beneficiary Address\nCountry: Singapore\nInvoice No: 123"
        self.assertEqual(_extract_country_from_text(text), "SINGAPORE")

    def test_extract_country_from_zip_city_country_tail(self) -> None:
        text = "ServiceNow Pte. Ltd., 049213 Singapore"
        self.assertEqual(_extract_country_from_text(text), "SINGAPORE")

    def test_parse_invoice_date_supports_dotted(self) -> None:
        iso, disp = parse_invoice_date("31.12.2025")
        self.assertEqual(iso, "2025-12-31")
        self.assertEqual(disp, "31.12.2025")

    def test_country_signal_fatura_alone_does_not_infer_portugal(self) -> None:
        self.assertEqual(_detect_country_signals_from_text("FATURA No. 123"), "")

    def test_country_signal_portugal_strong_markers_infer_portugal(self) -> None:
        self.assertEqual(
            _detect_country_signals_from_text("ATCUD: AB12-12345 NIPC 123456789"),
            "PORTUGAL",
        )

    @patch("modules.invoice_gemini_extractor._gemini_backend", return_value="modern")
    @patch("modules.invoice_gemini_extractor.GEMINI_API_KEY", "dummy-key")
    @patch("modules.invoice_gemini_extractor._generate_with_gemini_text")
    def test_extract_retries_on_truncated_json_and_recovers(
        self,
        mock_generate,
        _mock_backend,
    ) -> None:
        mock_generate.side_effect = [
            ('{"remitter_name":"Bosch Limited","beneficiary_name":"Bosch Sanayi', "MAX_TOKENS"),
            (
                '{"remitter_name":"Bosch Limited","beneficiary_name":"Bosch Sanayi ve Ticaret Anonim Sirketi","invoice_number":"INV-1","amount":"3574.77","currency":"USD"}',
                "STOP",
            ),
        ]
        out = extract_invoice_core_fields("Invoice text with enough length. " * 20)
        self.assertEqual(mock_generate.call_count, 2)
        self.assertEqual(out.get("remitter_name"), "BOSCH LIMITED")
        self.assertEqual(out.get("invoice_number"), "INV-1")
        self.assertEqual(out.get("currency_short"), "USD")
        self.assertTrue(is_ascii_clean(out.get("remitter_name", "")))

    @patch("modules.invoice_gemini_extractor._gemini_backend", return_value="modern")
    @patch("modules.invoice_gemini_extractor.GEMINI_API_KEY", "dummy-key")
    @patch("modules.invoice_gemini_extractor._generate_with_gemini_text")
    def test_extract_fallback_after_retry_failure_recovers_invoice_fields(
        self,
        mock_generate,
        _mock_backend,
    ) -> None:
        mock_generate.side_effect = [
            ('{"beneficiary_country":"Turkey"', "MAX_TOKENS"),
            ('{"beneficiary_country":"Turkey"', "MAX_TOKENS"),
        ]
        text = "INVOICE NO: RA22025000000271 DATE: 24/10/2025 services rendered"
        out = extract_invoice_core_fields(text * 4)
        self.assertEqual(mock_generate.call_count, 2)
        self.assertEqual(out.get("invoice_number"), "RA22025000000271")
        self.assertEqual(out.get("invoice_date_iso"), "2025-10-24")

    def test_fallback_extracts_invoice_number_and_date(self) -> None:
        text = "ROBERT BOSCH GMBH INVOICE NO. 19003645 DT 31.12.2025"
        out = _fallback_invoice_fields_from_text(text)
        self.assertEqual(out["invoice_number"], "19003645")
        self.assertEqual(out["invoice_date_raw"], "31.12.2025")

    def test_enrich_address_parses_de_prefixed_city(self) -> None:
        text = "Robert-Bosch-Platz 1, DE-70839 Gerlingen-Schillerhoehe"
        out = _enrich_addresses_from_text(text, {})
        self.assertEqual(out.get("beneficiary_street"), "Robert-Bosch-Platz 1")
        self.assertEqual(out.get("beneficiary_zip_text"), "70839")
        self.assertEqual(out.get("beneficiary_city"), "Gerlingen-Schillerhoehe")
        self.assertEqual(out.get("beneficiary_country_text"), "Germany")

    def test_enrich_address_uses_postfach_as_fallback(self) -> None:
        text = "Postfach 10 60 50, DE-70049 Stuttgart"
        out = _enrich_addresses_from_text(text, {})
        self.assertEqual(out.get("beneficiary_street"), "Postfach 10 60 50")
        self.assertEqual(out.get("beneficiary_zip_text"), "70049")
        self.assertEqual(out.get("beneficiary_city"), "Stuttgart")

    def test_keyword_fallback_detects_training_and_variants(self) -> None:
        text = "Invoice for SWE-RE English training workshop and trainer fees"
        nat, grp, cd = keyword_fallback(text)
        self.assertEqual(nat, "FEES FOR TECHNICAL SERVICES")
        self.assertEqual(grp, "Other Business Services")
        self.assertEqual(cd, "S1023")

    def test_purpose_code_validation_and_group_derivation(self) -> None:
        grouped = load_purpose_grouped()
        sample_group = next(iter(grouped.keys()))
        sample_code = str(grouped[sample_group][0]["purpose_code"])
        self.assertTrue(_is_valid_purpose_code(sample_code))
        self.assertFalse(_is_valid_purpose_code("S9999"))
        self.assertEqual(_purpose_group_for_code(sample_code), sample_group)

    def test_finalize_fills_beneficiary_address_from_labeled_block(self) -> None:
        text = """Bill To:
Tech Solutions India Pvt Ltd
Cyber Park, No. 76, 77, Bangalore, 560001, India
Invoice No: INV-10"""
        out = _finalize_extracted_fields({"beneficiary_name": "Tech Solutions India Pvt Ltd"}, text)
        self.assertIn("Cyber Park", out.get("beneficiary_address", ""))

    def test_finalize_sets_remitter_country_india_for_indian_entity(self) -> None:
        out = _finalize_extracted_fields({"remitter_name": "Myntra Jabong India Private Limited"}, "")
        self.assertEqual(out.get("remitter_country_text", ""), "India")

    def test_normalize_company_name_strips_domains_and_spaces_suffix(self) -> None:
        # domain suffix should be removed and GROUP split
        from modules.invoice_gemini_extractor import _normalize_company_name

        self.assertEqual(_normalize_company_name("EXPLEOGROUP.COM"), "EXPLEO GROUP")
        self.assertEqual(_normalize_company_name("foo.bar.NET"), "FOO BAR")
        self.assertEqual(_normalize_company_name("ACMEINC"), "ACME INC")

    def test_finalize_cleans_domain_name_and_infers_country(self) -> None:
        text = "Some header line\n+49 3581 76726\nDE-50968\n"
        out = _finalize_extracted_fields({"beneficiary_name": "EXPLEOGROUP.COM"}, text)
        self.assertEqual(out.get("beneficiary_name"), "EXPLEO GROUP")
        # context contains german indicators so country should be set
        self.assertEqual(out.get("beneficiary_country_text"), "Germany")

    def test_infer_nature_from_text_consulting(self) -> None:
        inferred = _infer_nature_from_text("Consulting services rendered for product implementation")
        self.assertTrue(bool(inferred))

    def test_multi_page_merge_picks_amount_from_second_page(self) -> None:
        page1 = {
            "remitter_name": "BOSCH GLOBAL SOFTWARE TECHNOLOGIES PRIVATE LIMITED",
            "beneficiary_name": "BOSCH GLOBAL SOFTWARE TECHNOLOGIES GMBH",
            "invoice_number": "299997708",
            "amount": "",
            "currency_short": "",
        }
        page2 = {
            "invoice_number": "299997708",
            "amount": "178269.98",
            "currency_short": "EUR",
        }
        merged, meta = merge_multi_page_image_extractions([page1, page2])
        self.assertEqual(merged.get("amount"), "178269.98")
        self.assertEqual(merged.get("currency_short"), "EUR")
        self.assertEqual(meta.get("amount_selected_page"), 2)
        self.assertEqual(meta.get("currency_selected_page"), 2)

    def test_multi_page_merge_preserves_page1_names_and_uses_page2_amount(self) -> None:
        page1 = {
            "remitter_name": "BOSCH GLOBAL SOFTWARE TECHNOLOGIES PRIVATE LIMITED",
            "beneficiary_name": "BOSCH GLOBAL SOFTWARE TECHNOLOGIES GMBH",
            "remitter_address": "123 INDUSTRIAL LAYOUT HOSUR ROAD BANGALORE INDIA",
            "invoice_number": "299997708",
        }
        page2 = {
            "amount": "178269.98",
            "currency_short": "EUR",
        }
        merged, _ = merge_multi_page_image_extractions([page1, page2])
        self.assertEqual(merged.get("remitter_name"), page1["remitter_name"])
        self.assertEqual(merged.get("beneficiary_name"), page1["beneficiary_name"])
        self.assertEqual(merged.get("amount"), "178269.98")
        self.assertEqual(merged.get("currency_short"), "EUR")

    def test_multi_page_merge_conflicting_amounts_flags_conflict_and_selects_best(self) -> None:
        page1 = {
            "invoice_number": "INV-1",
            "amount": "100.00",
            "currency_short": "",
        }
        page2 = {
            "invoice_number": "INV-1",
            "amount": "200.00",
            "currency_short": "EUR",
        }
        merged, meta = merge_multi_page_image_extractions([page1, page2])
        self.assertTrue(bool(meta.get("amount_conflict")))
        self.assertEqual(merged.get("amount"), "200.00")
        self.assertEqual(meta.get("amount_selected_page"), 2)


if __name__ == "__main__":
    unittest.main()
