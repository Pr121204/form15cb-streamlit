from __future__ import annotations

import unittest

from modules.master_lookups import load_purpose_grouped
from modules.invoice_gemini_extractor import (
    _enrich_addresses_from_text,
    _extract_country_from_text,
    _fallback_invoice_fields_from_text,
    _is_valid_purpose_code,
    _purpose_group_for_code,
    normalize_party_roles,
    parse_invoice_date,
)
from modules.invoice_gemini_extractor import extract_invoice_core_fields


class TestInvoiceGeminiExtractor(unittest.TestCase):
    def test_swaps_when_foreign_is_remitter_and_indian_is_beneficiary(self) -> None:
        raw = {
            "remitter_name": "Bosch IO GmbH",
            "remitter_address": "Berlin, Germany",
            "beneficiary_name": "Bosch Global Software Technologies Private Limited",
            "invoice_number": "7057441295",
        }
        out = normalize_party_roles(raw)
        self.assertEqual(out["remitter_name"], "Bosch Global Software Technologies Private Limited")
        self.assertEqual(out["beneficiary_name"], "Bosch IO GmbH")
        self.assertEqual(out["remitter_address"], "")

    def test_does_not_swap_when_remitter_already_indian(self) -> None:
        raw = {
            "remitter_name": "Myntra Jabong India Private Limited",
            "remitter_address": "Bengaluru",
            "beneficiary_name": "Kaimen Global Partners, S.L",
        }
        out = normalize_party_roles(raw)
        self.assertEqual(out["remitter_name"], raw["remitter_name"])
        self.assertEqual(out["beneficiary_name"], raw["beneficiary_name"])
        self.assertEqual(out["remitter_address"], raw["remitter_address"])

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
        self.assertEqual(out["beneficiary_name"], "Bosch.IO GmbH")

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

    def test_purpose_code_validation_and_group_derivation(self) -> None:
        grouped = load_purpose_grouped()
        sample_group = next(iter(grouped.keys()))
        sample_code = str(grouped[sample_group][0]["purpose_code"])
        self.assertTrue(_is_valid_purpose_code(sample_code))
        self.assertFalse(_is_valid_purpose_code("S9999"))
        self.assertEqual(_purpose_group_for_code(sample_code), sample_group)


if __name__ == "__main__":
    unittest.main()
