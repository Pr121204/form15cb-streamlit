from __future__ import annotations

import unittest

from modules.text_normalizer import is_ascii_clean, normalize_invoice_text, normalize_single_line_text


class TestTextNormalizer(unittest.TestCase):
    def test_transliterates_accented_letters(self) -> None:
        self.assertEqual(normalize_single_line_text("NILÜFER/BURSA"), "NILUFER/BURSA")
        self.assertEqual(normalize_single_line_text("São ç õ ó é"), "Sao c o o e")

    def test_transliterates_ligatures_and_specials(self) -> None:
        self.assertEqual(
            normalize_single_line_text("straße œuvre encyclopædia"),
            "strasse oeuvre encyclopaedia",
        )

    def test_keeps_non_transliterable_chars_for_manual_ui_fix(self) -> None:
        self.assertEqual(normalize_single_line_text("INV-123 日本語 2025/10/24"), "INV-123 日本語 2025/10/24")

    def test_preserves_allowed_punctuation(self) -> None:
        src = "A/B-C:D;E,F.G!H?I (J) [K] {L} #M &N +O =P @Q 'R' \"S\""
        out = normalize_single_line_text(src)
        self.assertEqual(out, src)

    def test_keep_newlines_true_preserves_lines(self) -> None:
        src = "Línea 1\t\tA\n\nLinha 2  B"
        out = normalize_invoice_text(src, keep_newlines=True)
        self.assertEqual(out, "Linea 1 A\n\nLinha 2 B")

    def test_ascii_clean_helper(self) -> None:
        self.assertTrue(is_ascii_clean("ABC 123"))
        self.assertFalse(is_ascii_clean("NILÜFER"))


if __name__ == "__main__":
    unittest.main()
