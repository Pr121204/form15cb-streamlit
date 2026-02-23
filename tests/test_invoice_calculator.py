from __future__ import annotations

import unittest

from modules.form15cb_constants import MODE_NON_TDS, MODE_TDS, REMITTEE_ZIP_CODE
from modules.invoice_calculator import format_dotted_date, invoice_state_to_xml_fields, recompute_invoice


class TestInvoiceCalculator(unittest.TestCase):
    def test_format_dotted_date(self) -> None:
        self.assertEqual(format_dotted_date("2023-05-15"), "15.05.2023")
        self.assertEqual(format_dotted_date("15/05/2023"), "15.05.2023")

    def test_recompute_tds(self) -> None:
        state = {
            "meta": {"mode": MODE_TDS, "exchange_rate": "80"},
            "extracted": {"amount": "100", "invoice_date_iso": "2026-02-10"},
            "resolved": {"dtaa_rate_percent": "10"},
            "form": {"AmtPayForgnRem": "100"},
            "computed": {},
        }
        out = recompute_invoice(state)
        self.assertEqual(out["form"]["AmtPayIndRem"], "8000")
        self.assertEqual(out["form"]["AmtPayForgnTds"], "10")

    def test_non_tds_zero_tds(self) -> None:
        state = {
            "meta": {"mode": MODE_NON_TDS, "exchange_rate": "80"},
            "extracted": {"amount": "100", "invoice_date_iso": "2026-02-10"},
            "resolved": {},
            "form": {"AmtPayForgnRem": "100"},
            "computed": {},
        }
        out = recompute_invoice(state)
        self.assertEqual(out["form"]["AmtPayForgnTds"], "0")
        self.assertEqual(out["form"]["AmtPayIndianTds"], "0")

    def test_xml_fields_hardcoded_zip(self) -> None:
        state = {
            "meta": {"mode": MODE_TDS},
            "extracted": {
                "remitter_name": "A",
                "remitter_address": "B",
                "beneficiary_name": "C",
                "invoice_number": "1",
                "invoice_date_iso": "2023-05-15",
            },
            "resolved": {},
            "form": {"RemitterPAN": "ABCDE1234F", "CurrencySecbCode": "50"},
            "computed": {},
        }
        xmlf = invoice_state_to_xml_fields(state)
        self.assertEqual(xmlf["RemitteeZipCode"], REMITTEE_ZIP_CODE)
        self.assertIn("DT 15.05.2023", xmlf["NameRemittee"])


if __name__ == "__main__":
    unittest.main()
