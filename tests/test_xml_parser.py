from __future__ import annotations

import os
import tempfile
import unittest

from modules.xml_generator import generate_xml
from modules.xml_parser import parse_xml_to_fields


class TestXmlParser(unittest.TestCase):
    def test_parse_generated_xml_round_trip(self) -> None:
        fields = {
            "SWVersionNo": "1",
            "SWCreatedBy": "DIT-EFILING-JAVA",
            "XMLCreatedBy": "DIT-EFILING-JAVA",
            "XMLCreationDate": "2026-02-18",
            "IntermediaryCity": "Delhi",
            "FormName": "FORM15CB",
            "Description": "FORM15CB",
            "AssessmentYear": "2025",
            "SchemaVer": "Ver1.1",
            "FormVer": "1",
            "IorWe": "02",
            "RemitterHonorific": "03",
            "BeneficiaryHonorific": "03",
            "RemitterPAN": "ABCDE1234F",
            "NameRemitter": "Acme India Pvt Ltd",
            "NameRemittee": "Acme Global GmbH",
            "AmtPayIndRem": "100000",
            "AmtPayForgnRem": "1200",
            "PropDateRem": "2026-03-05",
            "CountryRemMadeSecb": "49",
            "CurrencySecbCode": "50",
            "NameBankCode": "41",
            "BsrCode": "1234567",
            "RateTdsSecbFlg": "1",
            "RateTdsSecB": "10",
        }
        xml_path = generate_xml(fields)
        try:
            parsed = parse_xml_to_fields(xml_path)
            self.assertEqual(parsed.get("RemitterPAN"), "ABCDE1234F")
            self.assertEqual(parsed.get("NameRemitter"), "Acme India Pvt Ltd")
            self.assertEqual(parsed.get("NameRemittee"), "Acme Global GmbH")
            self.assertEqual(parsed.get("CountryRemMadeSecb"), "49")
            self.assertEqual(parsed.get("RateTdsSecbFlg"), "1")
        finally:
            if os.path.exists(xml_path):
                os.remove(xml_path)


if __name__ == "__main__":
    unittest.main()
