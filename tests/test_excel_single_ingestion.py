from __future__ import annotations

import io
import unittest
from datetime import date, timedelta

import pandas as pd

from modules.excel_single_ingestion import (
    derive_single_config,
    match_invoice_row,
    parse_excel_rows,
)
from modules.form15cb_constants import MODE_NON_TDS, MODE_TDS, PROPOSED_DATE_OFFSET_DAYS


class TestExcelSingleIngestion(unittest.TestCase):
    def _to_excel_bytes(self, rows):
        df = pd.DataFrame(rows)
        buf = io.BytesIO()
        df.to_excel(buf, index=False, engine="openpyxl")
        return buf.getvalue()

    def test_parse_excel_rows_requires_posting_date_and_finance_columns(self) -> None:
        excel_bytes = self._to_excel_bytes(
            [
                {
                    "Reference": "INV123",
                    "Document Date": "2026-03-01",
                    "Amount in Foreign Currency": "100",
                    "Currency": "USD",
                }
            ]
        )
        with self.assertRaises(ValueError) as ctx:
            parse_excel_rows(excel_bytes)
        self.assertIn("Posting Date", str(ctx.exception))
        self.assertIn("Amount INR", str(ctx.exception))

    def test_parse_excel_rows_supports_sap_alias_headers(self) -> None:
        excel_bytes = self._to_excel_bytes(
            [
                {
                    "Reference": " INV123 ",
                    "Document Date": "01/03/2026",
                    "Posting Date": "05/03/2026",
                    "Amount in doc. curr.": "-1850.567",
                    "Amount in local currency": "-198394.6",
                    "Document currency": "usd",
                    "Mode": "non-tds",
                    "Gross Up Tax": "yes",
                }
            ]
        )
        rows = parse_excel_rows(excel_bytes)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["Reference"], "INV123")
        self.assertEqual(row["Document Date"], "2026-03-01")
        self.assertEqual(row["Posting Date"], "2026-03-05")
        self.assertEqual(row["Amount in Foreign Currency"], "1850.57")
        self.assertEqual(row["Amount in INR"], "198395")
        self.assertEqual(row["Currency"], "USD")
        self.assertEqual(row["Mode"], MODE_NON_TDS)
        self.assertEqual(row["Gross Up Tax"], "Y")

    def test_match_invoice_row_filename_reference(self) -> None:
        rows = [
            {"Reference": "INV001"},
            {"Reference": "INV002"},
        ]
        out = match_invoice_row(rows, "INV002.pdf", "")
        self.assertEqual(out["status"], "matched")
        self.assertEqual(out["matched_index"], 1)

    def test_match_invoice_row_invoice_number_fallback(self) -> None:
        rows = [
            {"Reference": "ABC123"},
            {"Reference": "INV-88"},
        ]
        out = match_invoice_row(rows, "NO_MATCH.pdf", "INV 88")
        self.assertEqual(out["status"], "matched")
        self.assertEqual(out["matched_index"], 1)

    def test_match_invoice_row_duplicate_auto_selects_first(self) -> None:
        rows = [
            {"Reference": "INV001"},
            {"Reference": "INV-001"},
            {"Reference": "INV003"},
        ]
        out = match_invoice_row(rows, "INV001.pdf", "")
        self.assertEqual(out["status"], "matched")
        self.assertEqual(out["matched_index"], 0)
        self.assertEqual(out["candidates"], [0, 1])

    def test_match_invoice_row_hyphen_and_slash_patterns(self) -> None:
        rows = [
            {"Reference": "4716/0002025028B"},
            {"Reference": "65/2024"},
            {"Reference": "FTFA.2024/55"},
        ]
        out_1 = match_invoice_row(rows, "4716-0002025028B.pdf", "")
        out_2 = match_invoice_row(rows, "65-2024.pdf", "")
        out_3 = match_invoice_row(rows, "FT FA.2024-55.pdf", "")
        self.assertEqual(out_1["matched_index"], 0)
        self.assertEqual(out_2["matched_index"], 1)
        self.assertEqual(out_3["matched_index"], 2)

    def test_match_invoice_row_not_found_returns_all_candidates(self) -> None:
        rows = [
            {"Reference": "A"},
            {"Reference": "B"},
        ]
        out = match_invoice_row(rows, "C.pdf", "D")
        self.assertEqual(out["status"], "not_found")
        self.assertEqual(out["matched_index"], None)
        self.assertEqual(out["candidates"], [0, 1])

    def test_derive_single_config_uses_posting_date_and_today_plus_offset(self) -> None:
        out = derive_single_config(
            {
                "Mode": "TDS",
                "Gross Up Tax": "N",
                "Amount in Foreign Currency": "-1850.567",
                "Amount in INR": "-198394.6",
                "Currency": "EUR",
                "Document Date": "2026-02-01",
                "Posting Date": "2026-02-10",
            }
        )
        self.assertEqual(out["mode"], MODE_TDS)
        self.assertEqual(out["is_gross_up"], "N")
        self.assertEqual(out["currency_short"], "EUR")
        self.assertEqual(out["exchange_rate"], "107.207467")
        self.assertEqual(out["document_date"], "2026-02-01")
        self.assertEqual(out["posting_date"], "2026-02-10")
        self.assertEqual(out["proposed_date"], (date.today() + timedelta(days=PROPOSED_DATE_OFFSET_DAYS)).isoformat())
        self.assertEqual(out["amount_fcy"], "1850.57")
        self.assertEqual(out["amount_inr"], "198395")

    def test_derive_single_config_blocks_invalid_posting_date(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            derive_single_config(
                {
                    "Amount in Foreign Currency": "100",
                    "Amount in INR": "8000",
                    "Currency": "USD",
                    "Posting Date": "",
                }
            )
        self.assertIn("Posting Date", str(ctx.exception))

    def test_derive_single_config_blocks_zero_fcy(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            derive_single_config(
                {
                    "Amount in Foreign Currency": "0",
                    "Amount in INR": "8000",
                    "Currency": "USD",
                    "Posting Date": "2026-03-01",
                }
            )
        self.assertIn("Amount FCY cannot be zero", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
