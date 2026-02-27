from __future__ import annotations

import unittest

from modules.master_lookups import (
    infer_country_from_beneficiary_name,
    load_bank_code_map,
    load_country_code_map,
    load_currency_code_map,
    load_dtaa_map,
    load_purpose_grouped,
    match_remitter,
    resolve_country_name,
)


class TestMasterLookups(unittest.TestCase):
    def test_loaders_have_data(self) -> None:
        self.assertTrue(len(load_bank_code_map()) > 0)
        self.assertTrue(len(load_country_code_map()) > 0)
        self.assertTrue(len(load_currency_code_map()) > 0)
        self.assertTrue(len(load_dtaa_map()) > 0)
        self.assertTrue(len(load_purpose_grouped()) > 0)

    def test_match_remitter_fuzzy(self) -> None:
        rec = match_remitter("BOSCH LIMITED")
        self.assertIsNotNone(rec)
        self.assertTrue(str(rec.get("pan") or "").startswith("AAA"))

    def test_match_remitter_compact_spacing_variant(self) -> None:
        rec = match_remitter("Bosch Global Software Technologies Private Limited")
        self.assertIsNotNone(rec)
        self.assertEqual(str(rec.get("pan") or "").strip().upper(), "AAACR7108R")

    def test_match_remitter_pvt_ltd_variant(self) -> None:
        rec = match_remitter("Bosch Global Software Technologies Pvt Ltd")
        self.assertIsNotNone(rec)
        self.assertEqual(str(rec.get("pan") or "").strip().upper(), "AAACR7108R")

    def test_match_remitter_techn_abbreviation_variant(self) -> None:
        rec = match_remitter("BOSCH GLOBAL SOFTWARE TECHN. PVT LTD")
        self.assertIsNotNone(rec)
        self.assertEqual(str(rec.get("pan") or "").strip().upper(), "AAACR7108R")

    def test_match_remitter_soln_abbreviation_variant(self) -> None:
        rec = match_remitter("BOSCH MOBILITY PLATFORM AND SOLN INDIA PVT LTD")
        self.assertIsNotNone(rec)
        self.assertEqual(str(rec.get("pan") or "").strip().upper(), "AAOCA2522L")

    def test_infer_country_from_gmbh(self) -> None:
        code = infer_country_from_beneficiary_name("Bosch IO GmbH")
        self.assertEqual(code, "49")

    def test_infer_country_from_postal_prefix(self) -> None:
        code = infer_country_from_beneficiary_name("Hans Muller", "DE-12207 Berlin")
        self.assertEqual(code, "49")

    def test_infer_country_from_alias_usa(self) -> None:
        code = infer_country_from_beneficiary_name("Acme LLC", "New York, USA")
        self.assertEqual(code, "2")

    def test_infer_country_from_alias_us_dotted(self) -> None:
        code = infer_country_from_beneficiary_name("Robert Bosch LLC", "Farmington Hills, U.S.")
        self.assertEqual(code, "2")

    def test_infer_country_from_vat_id(self) -> None:
        code = infer_country_from_beneficiary_name("Some Co", "USt-Id: DE123456789")
        self.assertEqual(code, "49")

    def test_infer_country_from_phone_code(self) -> None:
        code = infer_country_from_beneficiary_name("Some Co", "+49 3581 76726")
        self.assertEqual(code, "49")

    def test_infer_country_from_us_state_zip(self) -> None:
        code = infer_country_from_beneficiary_name(
            "Robert Bosch LLC",
            "38000 Hills Tech Drive, Farmington Hills, MI 48331-3417",
        )
        self.assertEqual(code, "2")

    def test_resolve_country_name_from_code(self) -> None:
        self.assertEqual(resolve_country_name("49"), "GERMANY")


if __name__ == "__main__":
    unittest.main()
