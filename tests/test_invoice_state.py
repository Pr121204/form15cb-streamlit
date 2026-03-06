from __future__ import annotations

from datetime import date, timedelta
import unittest

from modules.form15cb_constants import MODE_NON_TDS, MODE_TDS
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
        self.assertTrue(bool(str(form.get("RateTdsADtaa") or "").strip()))

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

    def test_applies_excel_seed_values_for_single_flow(self) -> None:
        state = build_invoice_state(
            "inv_seed",
            "INV100.pdf",
            {
                "remitter_name": "Bosch Global Software Technologies Private Limited",
                "beneficiary_name": "Bosch IO GmbH",
                "invoice_date_iso": "2026-02-08",
                "amount": "100",
                "currency_short": "EUR",
            },
            {"mode": MODE_TDS, "exchange_rate": "1", "currency_short": "EUR"},
            excel_seed={
                "mode": MODE_TDS,
                "is_gross_up": "Y",
                "exchange_rate": "107.24",
                "currency_short": "USD",
                "document_date": "2026-02-10",
                "proposed_date": "2026-02-25",
                "amount_fcy": "1850",
                "amount_inr": "198394",
            },
        )
        form = state["form"]
        meta = state["meta"]
        self.assertEqual(form.get("AmtPayForgnRem"), "1850")
        self.assertEqual(form.get("AmtPayIndRem"), "198394")
        self.assertEqual(form.get("DednDateTds"), "2026-02-10")
        self.assertEqual(form.get("PropDateRem"), "2026-02-25")
        self.assertEqual(form.get("TaxPayGrossSecb"), "Y")
        self.assertEqual(meta.get("exchange_rate"), "107.24")
        self.assertEqual(meta.get("mode"), MODE_TDS)
        self.assertTrue(bool(meta.get("is_gross_up")))

    def test_non_tds_forces_gross_up_false_even_when_seeded_yes(self) -> None:
        state = build_invoice_state(
            "inv_seed_non_tds",
            "INV101.pdf",
            {
                "remitter_name": "Bosch Global Software Technologies Private Limited",
                "beneficiary_name": "Bosch IO GmbH",
                "invoice_date_iso": "2026-02-08",
                "amount": "100",
                "currency_short": "EUR",
            },
            {"mode": MODE_NON_TDS, "exchange_rate": "1", "currency_short": "EUR", "is_gross_up": True},
            excel_seed={
                "mode": MODE_NON_TDS,
                "is_gross_up": "Y",
                "exchange_rate": "107.24",
                "currency_short": "USD",
                "posting_date": "2026-02-10",
                "amount_fcy": "1850",
                "amount_inr": "198394",
            },
        )
        form = state["form"]
        meta = state["meta"]
        self.assertEqual(meta.get("mode"), MODE_NON_TDS)
        self.assertFalse(bool(meta.get("is_gross_up")))
        self.assertEqual(form.get("TaxPayGrossSecb"), "N")

    def test_splits_beneficiary_address_into_remittee_fields(self) -> None:
        state = build_invoice_state(
            "inv3",
            "a.pdf",
            {
                "remitter_name": "Bosch Global Software Technologies Private Limited",
                "beneficiary_name": "Robert Bosch GmbH",
                "beneficiary_address": "Ullsteinstra3e 128, 12109, Berlin, Germany",
                "amount": "100",
                "currency_short": "EUR",
            },
            {"mode": MODE_TDS, "exchange_rate": "100", "currency_short": "EUR"},
        )
        form = state["form"]
        self.assertEqual(form.get("RemitteeFlatDoorBuilding"), "Ullsteinstra3e 128")
        self.assertEqual(form.get("RemitteeAreaLocality"), "12109")
        self.assertEqual(form.get("RemitteeTownCityDistrict"), "Berlin")
        self.assertEqual(form.get("CountryRemMadeSecb"), "49")

    def test_handles_bullet_separated_address(self) -> None:
        state = build_invoice_state(
            "inv7",
            "a.pdf",
            {
                "remitter_name": "Some Remitter",
                "beneficiary_name": "Planisware Deutschland GmbH",
                "beneficiary_address": "Planisware Deutschland GmbH • Leonrodstr. 52-54 • D-80636 München",
                "amount": "100",
                "currency_short": "EUR",
            },
            {"mode": MODE_TDS, "exchange_rate": "100", "currency_short": "EUR"},
        )
        form = state["form"]
        self.assertEqual(form.get("RemitteeFlatDoorBuilding"), "Leonrodstr. 52-54")
        # area/locality may be blank (None or empty string)
        self.assertFalse(form.get("RemitteeAreaLocality"))
        # city text is normalized (accents removed)
        self.assertEqual(form.get("RemitteeTownCityDistrict"), "D-80636 Munchen")
        self.assertEqual(form.get("CountryRemMadeSecb"), "49")

    def test_country_fallback_defaults_to_others_when_unknown(self) -> None:
        state = build_invoice_state(
            "inv4",
            "a.pdf",
            {
                "remitter_name": "Bosch Global Software Technologies Private Limited",
                "beneficiary_name": "Unknown Counterparty",
                "beneficiary_address": "Unknown Address",
                "amount": "100",
                "currency_short": "EUR",
            },
            {"mode": MODE_TDS, "exchange_rate": "100", "currency_short": "EUR"},
        )
        form = state["form"]
        # When no country and no phone prefix can be inferred, leave country blank
        # so the user must explicitly select it.
        self.assertEqual(form.get("CountryRemMadeSecb"), "")
        self.assertEqual(form.get("RemitteeCountryCode"), "")

    def test_splits_slash_separated_beneficiary_address(self) -> None:
        state = build_invoice_state(
            "inv6",
            "a.pdf",
            {
                "remitter_name": "Bosch Limited",
                "beneficiary_name": "Bosch Foreign Entity",
                "beneficiary_country_text": "Turkey",
                "beneficiary_address": "MinarelicavusBursaOSBMah.YesilCad. No:15 Nilüfer/Bursa/16140",
                "amount": "100",
                "currency_short": "USD",
            },
            {"mode": MODE_TDS, "exchange_rate": "100", "currency_short": "USD"},
        )
        form = state["form"]
        self.assertEqual(form.get("RemitteeTownCityDistrict"), "Bursa")
        self.assertEqual(form.get("RemitteeAreaLocality"), "16140")

    def test_india_safeguard_uses_alternate_foreign_country(self) -> None:
        state = build_invoice_state(
            "inv5",
            "a.pdf",
            {
                "remitter_name": "Bosch Sanayi ve Ticaret Anonim Sirketi",
                "remitter_country_text": "Turkey",
                "remitter_address": "Bursa, Turkey",
                "beneficiary_name": "Bosch Limited",
                "beneficiary_country_text": "India",
                "beneficiary_address": "Bangalore, India",
                "amount": "100",
                "currency_short": "USD",
            },
            {"mode": MODE_TDS, "exchange_rate": "100", "currency_short": "USD"},
        )
        form = state["form"]
        self.assertEqual(form.get("CountryRemMadeSecb"), "90")
        self.assertEqual(form.get("RemitteeCountryCode"), "90")

    def test_india_is_disallowed_in_tds_when_no_foreign_fallback(self) -> None:
        state = build_invoice_state(
            "inv7",
            "a.pdf",
            {
                "remitter_name": "Bosch Limited",
                "remitter_country_text": "India",
                "remitter_address": "Bangalore, India",
                "beneficiary_name": "Domestic Counterparty",
                "beneficiary_country_text": "India",
                "beneficiary_address": "Mumbai, India",
                "amount": "100",
                "currency_short": "USD",
            },
            {"mode": MODE_TDS, "exchange_rate": "100", "currency_short": "USD"},
        )
        form = state["form"]
        self.assertEqual(form.get("CountryRemMadeSecb"), "9999")
        self.assertEqual(form.get("RemitteeCountryCode"), "9999")

    def test_empty_core_extraction_skips_dtaa_seed_even_with_country(self) -> None:
        state = build_invoice_state(
            "inv8",
            "a.pdf",
            {
                "beneficiary_country_text": "Portugal",
            },
            {"mode": MODE_TDS, "exchange_rate": "100", "currency_short": "USD"},
        )
        form = state["form"]
        self.assertEqual(form.get("CountryRemMadeSecb"), "14")
        self.assertEqual(form.get("RateTdsADtaa", ""), "")
        self.assertEqual(form.get("RelevantDtaa", ""), "")

    def test_splits_mexico_cp_address_into_three_fields(self) -> None:
        state = build_invoice_state(
            "inv9",
            "7120002741.pdf",
            {
                "remitter_name": "Bosch Global Software Technologies Private Limited",
                "beneficiary_name": "ROBERT BOSCH MEXICO",
                "beneficiary_country_text": "Mexico",
                "beneficiary_address": "CircuitoG.GonzalezCamarena333 SANTAFE ALVAROOBREGON C.P.:01210 DISTRITOFEDERAL",
                "amount": "18900",
                "currency_short": "USD",
            },
            {"mode": MODE_TDS, "exchange_rate": "90", "currency_short": "USD"},
        )
        form = state["form"]
        self.assertEqual(form.get("RemitteeFlatDoorBuilding"), "CircuitoG.GonzalezCamarena333")
        self.assertEqual(form.get("RemitteeAreaLocality"), "SANTAFE ALVAROOBREGON")
        self.assertEqual(form.get("RemitteeTownCityDistrict"), "C.P.:01210 DISTRITOFEDERAL")

    def test_splits_accented_address_after_ascii_normalization(self) -> None:
        state = build_invoice_state(
            "inv10",
            "a.pdf",
            {
                "remitter_name": "Bosch Limited",
                "beneficiary_name": "Bosch Foreign Entity",
                "beneficiary_country_text": "Turkiye",
                "beneficiary_address": "Minarelicavus Bursa OSB Mah. Yesil Cad. No:15 Nilufer/Bursa/16140",
                "amount": "100",
                "currency_short": "USD",
            },
            {"mode": MODE_TDS, "exchange_rate": "100", "currency_short": "USD"},
        )
        form = state["form"]
        self.assertEqual(form.get("RemitteeFlatDoorBuilding"), "Minarelicavus Bursa OSB Mah. Yesil Cad. No:15 Nilufer")
        self.assertEqual(form.get("RemitteeAreaLocality"), "16140")
        self.assertEqual(form.get("RemitteeTownCityDistrict"), "Bursa")

    def test_parse_german_style_beneficiary_address_street_zip_city(self) -> None:
        state = build_invoice_state(
            "inv12",
            "a.pdf",
            {
                "remitter_name": "Bosch Limited",
                "beneficiary_name": "Back Office Associates Germany GmbH",
                "beneficiary_address": "Musterstrasse 12, 70376 Stuttgart",
                "amount": "100",
                "currency_short": "EUR",
            },
            {"mode": MODE_TDS, "exchange_rate": "100", "currency_short": "EUR"},
        )
        form = state["form"]
        self.assertEqual(form.get("RemitteeFlatDoorBuilding"), "Musterstrasse 12")
        self.assertEqual(form.get("RemitteeAreaLocality"), "70376")
        self.assertEqual(form.get("RemitteeTownCityDistrict"), "Stuttgart")

    def test_dtaa_fields_are_split_into_relevant_and_article_variants(self) -> None:
        state = build_invoice_state(
            "inv11",
            "a.pdf",
            {
                "remitter_name": "Bosch Global Software Technologies Private Limited",
                "beneficiary_name": "Robert Bosch GmbH",
                "beneficiary_country_text": "Germany",
                "amount": "100",
                "currency_short": "EUR",
            },
            {"mode": MODE_TDS, "exchange_rate": "100", "currency_short": "EUR"},
        )
        form = state["form"]
        self.assertEqual(form.get("RelevantDtaa"), "DTAA BTWN INDIA AND GERMANY")
        self.assertEqual(form.get("RelevantArtDtaa"), "ARTICLE 12 OF DTAA BTWN INDIA AND GERMANY")
        self.assertEqual(form.get("ArtDtaa"), "ARTICLE 12 OF DTAA BTWN INDIA AND GERMANY")


if __name__ == "__main__":
    unittest.main()
