from __future__ import annotations

import unittest

from modules.batch_form_ui import _purpose_group_for_code, _selectbox_index_from_value


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


if __name__ == "__main__":
    unittest.main()
