from __future__ import annotations

import unittest

from modules.text_normalizer import is_ascii_clean, normalize_invoice_text, normalize_single_line_text


class TestTextNormalizer(unittest.TestCase):
    def test_transliterates_accented_letters(self) -> None:
        self.assertEqual(normalize_single_line_text("NILÃœFER/BURSA"), "NILUFER/BURSA")
        self.assertEqual(normalize_single_line_text("SÃ£o Ã§ Ãµ Ã³ Ã©"), "Sao c o o e")

    def test_transliterates_ligatures_and_specials(self) -> None:
        self.assertEqual(
            normalize_single_line_text("straÃŸe Å“uvre encyclopÃ¦dia"),
            "strasse oeuvre encyclopaedia",
        )

    def test_transliterates_stroke_d(self) -> None:
        self.assertEqual(normalize_single_line_text("Đuro đakovic"), "Duro dakovic")

    def test_keeps_non_transliterable_chars_for_manual_ui_fix(self) -> None:
        src = "INV-123 \u65e5\u672c\u8a9e 2025/10/24"
        self.assertEqual(normalize_single_line_text(src), src)

    def test_preserves_allowed_punctuation(self) -> None:
        src = "A/B-C:D;E,F.G!H?I (J) [K] {L} #M &N +O =P @Q 'R' \"S\""
        out = normalize_single_line_text(src)
        self.assertEqual(out, src)

    def test_keep_newlines_true_preserves_lines(self) -> None:
        src = "LÃ­nea 1\t\tA\n\nLinha 2  B"
        out = normalize_invoice_text(src, keep_newlines=True)
        self.assertEqual(out, "Linea 1 A\n\nLinha 2 B")

    def test_ascii_clean_helper(self) -> None:
        self.assertTrue(is_ascii_clean("ABC 123"))
        self.assertFalse(is_ascii_clean("NILÃœFER"))


if __name__ == "__main__":
    unittest.main()

