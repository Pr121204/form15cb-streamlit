from __future__ import annotations

from datetime import date, timedelta
import unittest

from modules.form15cb_constants import MODE_TDS
from modules.invoice_state import build_invoice_state
from modules.master_lookups import load_purpose_grouped


class TestInvoiceState(unittest.TestCase):
    def test_infers_country_and_sets_prop_date_from_today(self) -> None:
        state = build_invoice_state(
            "inv1",
            "7057441295.pdf",
            {
                "remitter_name": "Bosch Global Software Technologies Private Limited",
                "beneficiary_name": "Bosch IO GmbH",
                "invoice_date_iso": "2023-05-15",
                "amount": "49300.00",
                "currency_short": "EUR",
                "beneficiary_street": "Ullsteinstra3e 128",
                "beneficiary_zip_text": "12109",
                "beneficiary_city": "Berlin",
            },
            {"mode": MODE_TDS, "exchange_rate": "100", "currency_short": "EUR"},
        )
        form = state["form"]
        self.assertEqual(form.get("CountryRemMadeSecb"), "49")
        self.assertEqual(form.get("RemitteeCountryCode"), "49")
        self.assertEqual(form.get("PropDateRem"), (date.today() + timedelta(days=15)).isoformat())
        self.assertEqual(form.get("RemitteeFlatDoorBuilding"), "Ullsteinstra3e 128")
        self.assertEqual(form.get("RemitteeAreaLocality"), "12109")
        self.assertEqual(form.get("RemitteeTownCityDistrict"), "Berlin")

    def test_derives_purpose_group_from_code_even_when_group_missing(self) -> None:
        grouped = load_purpose_grouped()
        sample_group = next(iter(grouped.keys()))
        sample = grouped[sample_group][0]
        sample_code = str(sample["purpose_code"])
        sample_gr = str(sample["gr_no"])
        state = build_invoice_state(
            "inv2",
            "x.pdf",
            {
                "remitter_name": "Bosch Global Software Technologies Private Limited",
                "beneficiary_name": "Robert Bosch GmbH",
                "amount": "100",
                "currency_short": "EUR",
                "purpose_group": "",
                "purpose_code": sample_code,
            },
            {"mode": MODE_TDS, "exchange_rate": "100", "currency_short": "EUR"},
        )
        form = state["form"]
        self.assertEqual(form.get("_purpose_group"), sample_group)
        self.assertEqual(form.get("_purpose_code"), sample_code)
        self.assertEqual(form.get("RevPurCategory"), f"RB-{sample_gr}.1")
        self.assertEqual(form.get("RevPurCode"), f"RB-{sample_gr}.1-{sample_code}")


if __name__ == "__main__":
    unittest.main()
