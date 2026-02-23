from __future__ import annotations

import unittest

from modules.form15cb_constants import MODE_TDS
from modules.invoice_state import build_invoice_state


class TestInvoiceState(unittest.TestCase):
    def test_infers_country_and_sets_prop_date_from_invoice(self) -> None:
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
        self.assertEqual(form.get("PropDateRem"), "2023-05-30")
        self.assertEqual(form.get("RemitteeFlatDoorBuilding"), "Ullsteinstra3e 128")
        self.assertEqual(form.get("RemitteeAreaLocality"), "12109")
        self.assertEqual(form.get("RemitteeTownCityDistrict"), "Berlin")


if __name__ == "__main__":
    unittest.main()
