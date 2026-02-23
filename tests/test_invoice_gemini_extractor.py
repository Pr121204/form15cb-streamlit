from __future__ import annotations

import unittest

from modules.invoice_gemini_extractor import _extract_country_from_text, normalize_party_roles
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


if __name__ == "__main__":
    unittest.main()
