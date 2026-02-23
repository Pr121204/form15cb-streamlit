from __future__ import annotations

import unittest

from modules.currency_mapping import (
    CONFIRMED_SHORT_CODE_TO_CODE,
    is_currency_code_valid_for_xml,
    load_currency_exact_index,
    preselect_currency_code,
    validate_short_code_targets,
)


class TestCurrencyMapping(unittest.TestCase):
    def test_confirmed_mappings_match_master_file(self) -> None:
        index = load_currency_exact_index()
        resolved, missing = validate_short_code_targets(index)
        self.assertFalse(missing)
        for short_code, expected_code in CONFIRMED_SHORT_CODE_TO_CODE.items():
            self.assertIn(short_code, resolved)
            self.assertEqual(resolved[short_code]["code"], expected_code)

    def test_preselection_requires_exact_json_backed_mapping(self) -> None:
        index = {"EURO": "50", "US DOLLAR": "167"}
        code, requires_manual = preselect_currency_code("", "EUR", index)
        self.assertEqual(code, "50")
        self.assertFalse(requires_manual)

        code2, requires_manual2 = preselect_currency_code("", "GBP", index)
        self.assertEqual(code2, "")
        self.assertTrue(requires_manual2)

    def test_unresolved_or_placeholder_currency_is_invalid_for_xml(self) -> None:
        self.assertFalse(is_currency_code_valid_for_xml(""))
        self.assertFalse(is_currency_code_valid_for_xml("-1"))
        self.assertTrue(is_currency_code_valid_for_xml("50"))


if __name__ == "__main__":
    unittest.main()
