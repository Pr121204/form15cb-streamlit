from __future__ import annotations

import unittest

from modules.sample_parity_checker import check_xml_against_samples
from modules.xml_shape_normalizer import normalize_xml_to_reference_shape, strict_shape_compare


class TestSampleParityChecker(unittest.TestCase):
    def _sample_xml(self) -> str:
        return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<FORM15CB:FORM15CB xmlns:Form="http://incometaxindiaefiling.gov.in/common" xmlns:FORM15CB="http://incometaxindiaefiling.gov.in/FORM15CAB">
  <FORM15CB:TDSDetails>
    <FORM15CB:AmtPayForgnTds>10</FORM15CB:AmtPayForgnTds>
    <FORM15CB:AmtPayIndianTds>800</FORM15CB:AmtPayIndianTds>
    <FORM15CB:RateTdsSecbFlg>2</FORM15CB:RateTdsSecbFlg>
    <FORM15CB:RateTdsSecB>10</FORM15CB:RateTdsSecB>
    <FORM15CB:ActlAmtTdsForgn>90</FORM15CB:ActlAmtTdsForgn>
    <FORM15CB:DednDateTds>2026-02-22</FORM15CB:DednDateTds>
  </FORM15CB:TDSDetails>
</FORM15CB:FORM15CB>"""

    def test_ok_with_matching_sample(self) -> None:
        xml = self._sample_xml()
        report = check_xml_against_samples(xml, sample_xml_texts=[("s.xml", xml)])
        self.assertTrue(report["ok"])
        self.assertFalse(report["blocking"])

    def test_blocks_bad_declaration(self) -> None:
        xml = self._sample_xml().replace('standalone="yes"', 'standalone="no"', 1)
        report = check_xml_against_samples(xml, sample_xml_texts=[("s.xml", self._sample_xml())])
        self.assertTrue(report["blocking"])
        self.assertTrue(any("declaration" in x.lower() for x in report["issues"]))

    def test_normalization_drops_extra_tag_to_match_reference(self) -> None:
        xml = self._sample_xml().replace(
            "</FORM15CB:TDSDetails>",
            "<FORM15CB:UnexpectedTag>1</FORM15CB:UnexpectedTag></FORM15CB:TDSDetails>",
        )
        ref = self._sample_xml()
        normalized = normalize_xml_to_reference_shape(xml, ref)
        diff = strict_shape_compare(ref, normalized)
        self.assertTrue(diff["ok"])
        report = check_xml_against_samples(xml, sample_xml_texts=[("s.xml", ref)])
        self.assertFalse(report["blocking"])


if __name__ == "__main__":
    unittest.main()
