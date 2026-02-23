from __future__ import annotations

import unittest

from modules.form15cb_constants import MODE_TDS
from modules.invoice_state import build_invoice_state


class TestRemitterLocking(unittest.TestCase):
    def test_match_locks_pan_bank_branch_bsr_together(self) -> None:
        state = build_invoice_state(
            "x1",
            "a.pdf",
            {
                "remitter_name": "BOSCH LIMITED",
                "remitter_address": "addr",
                "beneficiary_name": "benef",
                "invoice_number": "INV1",
                "invoice_date_iso": "2026-02-20",
                "amount": "100",
                "currency_short": "EUR",
            },
            {"mode": MODE_TDS, "exchange_rate": "80", "currency_short": "EUR"},
        )
        form = state["form"]
        self.assertEqual(form.get("_lock_pan_bank_branch_bsr"), "1")
        self.assertTrue(str(form.get("RemitterPAN") or ""))
        self.assertTrue(str(form.get("NameBankCode") or ""))
        self.assertTrue(str(form.get("BranchName") or ""))
        self.assertTrue(str(form.get("BsrCode") or ""))


if __name__ == "__main__":
    unittest.main()
