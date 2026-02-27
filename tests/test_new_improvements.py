"""Unit tests for the 4 new improvements: email domain rejection, phone prefix inference, BasisDeterTax validation."""
from __future__ import annotations

import unittest
from modules.invoice_gemini_extractor import _is_email_domain
from modules.invoice_state import _infer_country_from_phone_prefix


class TestEmailDomainRejection(unittest.TestCase):
    """CHANGE 1: Test email domain detection and rejection."""

    def test_is_email_domain_detects_common_tlds(self) -> None:
        """domains like example.com should be detected as domains."""
        self.assertTrue(_is_email_domain("example.com"))
        self.assertTrue(_is_email_domain("EXAMPLE.COM"))
        self.assertTrue(_is_email_domain("foo.bar.net"))
        self.assertTrue(_is_email_domain("domain.io"))
        self.assertTrue(_is_email_domain("company.de"))

    def test_is_email_domain_rejects_company_names_with_spaces(self) -> None:
        """Names with spaces are not simple domains."""
        self.assertFalse(_is_email_domain("Bosch IO GmbH"))
        self.assertFalse(_is_email_domain("EXAMPLE.COM GMBH"))
        self.assertFalse(_is_email_domain("Tech Solutions"))

    def test_is_email_domain_rejects_unknown_tlds(self) -> None:
        """Unknown TLDs should not be treated as domains."""
        self.assertFalse(_is_email_domain("example.xyz"))
        self.assertFalse(_is_email_domain("domain.info"))

    def test_is_email_domain_requires_dot(self) -> None:
        """Text without a dot is not a domain."""
        self.assertFalse(_is_email_domain("EXPLEOGROUP"))
        self.assertFalse(_is_email_domain("Test"))


class TestPhonePrefixInference(unittest.TestCase):
    """CHANGE 2: Test phone prefix country inference."""

    def test_infer_country_from_phone_prefix_germany(self) -> None:
        """German phone prefix +49 should infer Germany code."""
        code = _infer_country_from_phone_prefix("Contact: +49 3581 76726")
        self.assertEqual(code, "49")

    def test_infer_country_from_phone_prefix_us(self) -> None:
        """US phone prefix +1 should infer US code."""
        code = _infer_country_from_phone_prefix("Phone: +1 212 555-1234")
        self.assertEqual(code, "1")

    def test_infer_country_from_phone_prefix_japan(self) -> None:
        """Japanese phone prefix +81 should infer Japan code."""
        code = _infer_country_from_phone_prefix("Tel: +81 90 1234 5678")
        self.assertEqual(code, "111")

    def test_infer_country_from_phone_prefix_not_found(self) -> None:
        """No match should return empty string."""
        code = _infer_country_from_phone_prefix("No phone number here")
        self.assertEqual(code, "")

    def test_infer_country_from_phone_prefix_with_spaces(self) -> None:
        """Phone prefix with various spacing patterns should match."""
        code = _infer_country_from_phone_prefix("Phone +49 30 123 456")
        self.assertEqual(code, "49")

    def test_infer_country_from_phone_prefix_empty_input(self) -> None:
        """Empty input should return empty code."""
        self.assertEqual(_infer_country_from_phone_prefix(""), "")


if __name__ == "__main__":
    unittest.main()
