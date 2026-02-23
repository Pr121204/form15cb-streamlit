from __future__ import annotations

import unittest

from modules.xml_shape_normalizer import normalize_xml_to_reference_shape, strict_shape_compare


class TestXmlShapeNormalizer(unittest.TestCase):
    def _reference(self) -> str:
        return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<FORM15CB:FORM15CB xmlns:Form="http://incometaxindiaefiling.gov.in/common" xmlns:FORM15CB="http://incometaxindiaefiling.gov.in/FORM15CAB">
  <FORM15CB:RemittanceDetails>
    <FORM15CB:A>1</FORM15CB:A>
    <FORM15CB:B>2</FORM15CB:B>
    <FORM15CB:C>3</FORM15CB:C>
  </FORM15CB:RemittanceDetails>
</FORM15CB:FORM15CB>"""

    def _generated_misaligned(self) -> str:
        return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<FORM15CB:FORM15CB xmlns:Form="http://incometaxindiaefiling.gov.in/common" xmlns:FORM15CB="http://incometaxindiaefiling.gov.in/FORM15CAB">
  <FORM15CB:RemittanceDetails>
    <FORM15CB:C>30</FORM15CB:C>
    <FORM15CB:Extra>999</FORM15CB:Extra>
    <FORM15CB:A>10</FORM15CB:A>
  </FORM15CB:RemittanceDetails>
</FORM15CB:FORM15CB>"""

    def test_normalize_matches_reference_shape(self) -> None:
        normalized = normalize_xml_to_reference_shape(self._generated_misaligned(), self._reference())
        diff = strict_shape_compare(self._reference(), normalized)
        self.assertTrue(diff["ok"])
        self.assertIn("<FORM15CB:A>10</FORM15CB:A>", normalized)
        self.assertIn("<FORM15CB:C>30</FORM15CB:C>", normalized)

    def test_declaration_preserved(self) -> None:
        normalized = normalize_xml_to_reference_shape(self._generated_misaligned(), self._reference())
        self.assertTrue(normalized.splitlines()[0].strip() == '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')


if __name__ == "__main__":
    unittest.main()
