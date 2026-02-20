from __future__ import annotations

import unittest
from unittest.mock import patch

from modules.master_data import find_bank_by_name


class TestBankLookup(unittest.TestCase):
    @patch("modules.master_data.find_party_banks")
    @patch("modules.master_data.load_master")
    def test_exact_match_prefers_party_rows(self, mock_load_master, mock_find_party_banks) -> None:
        mock_find_party_banks.return_value = [
            {"bank_name": "State Bank of India", "bsr_code": "1234567", "branch": "Delhi"}
        ]
        mock_load_master.return_value = {}
        out = find_bank_by_name("State Bank of India", "Acme")
        self.assertIsNotNone(out)
        self.assertEqual(out.get("bsr_code"), "1234567")

    @patch("modules.master_data.find_party_banks")
    @patch("modules.master_data.load_master")
    def test_partial_match_global_fallback(self, mock_load_master, mock_find_party_banks) -> None:
        mock_find_party_banks.return_value = []
        mock_load_master.return_value = {
            "banks_by_party": {
                "Other": [{"bank_name": "Deutsche Bank AG", "bsr_code": "7654321"}]
            }
        }
        out = find_bank_by_name("Deutsche", "Unknown Party")
        self.assertIsNotNone(out)
        self.assertEqual(out.get("bsr_code"), "7654321")

    @patch("modules.master_data.find_party_banks")
    @patch("modules.master_data.load_master")
    def test_not_found(self, mock_load_master, mock_find_party_banks) -> None:
        mock_find_party_banks.return_value = []
        mock_load_master.return_value = {"banks_by_party": {}}
        out = find_bank_by_name("Nonexistent Bank", "Unknown Party")
        self.assertIsNone(out)


if __name__ == "__main__":
    unittest.main()
