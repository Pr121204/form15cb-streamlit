from __future__ import annotations

import unittest

from modules.batch_form_ui import _purpose_group_for_code, _selectbox_index_from_value, _dtaa_rate_percent


class TestBatchFormUiHelpers(unittest.TestCase):
    def test_selectbox_index_from_value(self) -> None:
        options = ["SELECT", "A", "B"]
        self.assertEqual(_selectbox_index_from_value(options, "B"), 2)
        self.assertEqual(_selectbox_index_from_value(options, "X"), 0)

    def test_purpose_group_for_code(self) -> None:
        grouped = {
            "Group A": [{"purpose_code": "S1001", "description": "", "gr_no": "10"}],
            "Group B": [{"purpose_code": "S1002", "description": "", "gr_no": "11"}],
        }
        self.assertEqual(_purpose_group_for_code(grouped, "S1002"), "Group B")
        self.assertEqual(_purpose_group_for_code(grouped, "S9999"), "")

    def test_dtaa_rate_percent(self) -> None:
        # fractional input should be converted to percentage string without trailing zeros
        self.assertEqual(_dtaa_rate_percent("0.1"), "10")
        self.assertEqual(_dtaa_rate_percent("0.1575"), "15.75")
        self.assertEqual(_dtaa_rate_percent(""), "")


if __name__ == "__main__":
    unittest.main()
