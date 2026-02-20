from __future__ import annotations

import unittest
from datetime import date

from modules import form_ui


class TestFormUiHelpers(unittest.TestCase):
    def test_yes_no_to_yn(self) -> None:
        self.assertEqual(form_ui._yes_no_to_yn("YES"), "Y")
        self.assertEqual(form_ui._yes_no_to_yn("NO"), "N")

    def test_yn_to_yes_no(self) -> None:
        self.assertEqual(form_ui._yn_to_yes_no("Y"), "YES")
        self.assertEqual(form_ui._yn_to_yes_no("N"), "NO")

    def test_float_or_none(self) -> None:
        self.assertEqual(form_ui._float_or_none("12.5"), 12.5)
        self.assertIsNone(form_ui._float_or_none("abc"))

    def test_date_display_format(self) -> None:
        self.assertEqual(form_ui._format_dd_mmm_yyyy(date(2026, 2, 18)), "18-Feb-2026")

    def test_reset_dtaa_fields(self) -> None:
        fields = {
            "TaxResidCert": "Y",
            "RelevantDtaa": "Germany",
            "RateTdsADtaa": "10",
            "TaxIndDtaaFlg": "Y",
        }
        form_ui._reset_dtaa_fields(fields)
        self.assertEqual(fields["TaxResidCert"], "N")
        self.assertEqual(fields["RelevantDtaa"], "")
        self.assertEqual(fields["RateTdsADtaa"], "")


if __name__ == "__main__":
    unittest.main()
