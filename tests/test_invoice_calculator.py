from __future__ import annotations

import unittest

from modules.form15cb_constants import MODE_NON_TDS, MODE_TDS, REMITTEE_ZIP_CODE
from modules.invoice_calculator import format_dotted_date, invoice_state_to_xml_fields, recompute_invoice


class TestInvoiceCalculator(unittest.TestCase):
    def test_format_dotted_date(self) -> None:
        self.assertEqual(format_dotted_date("2023-05-15"), "15.05.2023")
        self.assertEqual(format_dotted_date("15/05/2023"), "15.05.2023")
        self.assertEqual(format_dotted_date("15.05.2023"), "15.05.2023")

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

    def test_inr_amount_is_rounded_integer(self) -> None:
        state = {
            "meta": {"mode": MODE_TDS, "exchange_rate": "90"},
            "extracted": {"amount": "100.51", "invoice_date_iso": "2026-02-10"},
            "resolved": {"dtaa_rate_percent": "10"},
            "form": {"AmtPayForgnRem": "100.51"},
            "computed": {},
        }
        out = recompute_invoice(state)
        self.assertEqual(out["form"]["AmtPayIndRem"], "9046")

    def test_xml_fields_hardcoded_zip(self) -> None:
        state = {
            "meta": {"mode": MODE_TDS},
            "extracted": {
                "remitter_name": "A",
                "remitter_address": "B",
                "beneficiary_name": "bosch io gmbh",
                "invoice_number": "1",
                "invoice_date_iso": "2023-05-15",
            },
            "resolved": {},
            "form": {"RemitterPAN": "ABCDE1234F", "CurrencySecbCode": "50"},
            "computed": {},
        }
        xmlf = invoice_state_to_xml_fields(state)
        self.assertEqual(xmlf["RemitteeZipCode"], REMITTEE_ZIP_CODE)
        self.assertTrue(xmlf["NameRemittee"].startswith("BOSCH IO GMBH"))
        self.assertIn("INVOICE NO. 1", xmlf["NameRemittee"])
        self.assertIn("DT 15.05.2023", xmlf["NameRemittee"])

    def test_xml_fields_split_dtaa_variants(self) -> None:
        state = {
            "meta": {"mode": MODE_TDS},
            "extracted": {},
            "resolved": {},
            "form": {
                "RemitterPAN": "ABCDE1234F",
                "RelevantDtaa": "ARTICLE 12 OF DTAA BTWN INDIA AND GERMANY",
                "CurrencySecbCode": "50",
            },
            "computed": {},
        }
        xmlf = invoice_state_to_xml_fields(state)
        self.assertEqual(xmlf["RelevantDtaa"], "DTAA BTWN INDIA AND GERMANY")
        self.assertEqual(xmlf["RelevantArtDtaa"], "ARTICLE 12 OF DTAA BTWN INDIA AND GERMANY")
        self.assertEqual(xmlf["ArtDtaa"], "ARTICLE 12 OF DTAA BTWN INDIA AND GERMANY")

    def test_recompute_gross_up_tds(self) -> None:
        state = {
            "meta": {"mode": MODE_TDS, "exchange_rate": "107.24", "is_gross_up": True},
            "extracted": {"amount": "1850", "invoice_date_iso": "2026-02-10"},
            "resolved": {},
            "form": {"AmtPayForgnRem": "1850"},
            "computed": {},
        }
        # Math: Net INR = 1850 * 107.24 = 198394
        # R = 20.80. Gross = 198394 * 100 / (100 - 20.80) = 250497.4747 -> round to 250497
        # TDS INR = 250497 * 0.208 = 52103.376 -> round to 52103
        # TDS FCY = 52103.376 / 107.24 = 485.8576 -> round to 485.86
        out = recompute_invoice(state)
        f = out["form"]
        self.assertEqual(f["AmtPayIndRem"], "198394")
        self.assertEqual(f["AmtIncChrgIt"], "250497")
        self.assertEqual(f["TaxLiablIt"], "52103")
        self.assertEqual(f["AmtPayIndianTds"], "52103")
        self.assertEqual(f["AmtPayForgnTds"], "485.86")
        self.assertEqual(f["RateTdsSecB"], "20.80")
        self.assertTrue("GROSS AMOUNT" in f["BasisDeterTax"])
        self.assertEqual(f["ActlAmtTdsForgn"], "1850")

    def test_recompute_it_act_non_gross_up_tds(self) -> None:
        state = {
            "meta": {"mode": MODE_TDS, "exchange_rate": "107.24", "is_gross_up": False},
            "extracted": {"amount": "1850", "invoice_date_iso": "2026-02-10"},
            "resolved": {},
            "form": {"AmtPayForgnRem": "1850", "BasisDeterTax": "Act"},
            "computed": {},
        }
        # Math: Net INR = 1850 * 107.24 = 198394
        # R = 20.80. TDS INR = 198394 * 0.208 = 41265.952 -> round to 41266
        # TDS FCY = 41265.952 / 107.24 = 384.799... -> round to 384.80
        out = recompute_invoice(state)
        f = out["form"]
        self.assertEqual(f["AmtPayIndRem"], "198394")
        self.assertEqual(f["TaxLiablIt"], "41266")
        self.assertEqual(f["AmtPayIndianTds"], "41266")
        self.assertEqual(f["AmtPayForgnTds"], "384.80")


if __name__ == "__main__":
    unittest.main()
