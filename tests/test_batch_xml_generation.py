from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from modules.form15cb_constants import MODE_NON_TDS, MODE_TDS
from modules.xml_generator import generate_xml_content


class TestBatchXmlGeneration(unittest.TestCase):
    def _base(self):
        return {
            "SWVersionNo": "1",
            "SWCreatedBy": "DIT-EFILING-JAVA",
            "XMLCreatedBy": "DIT-EFILING-JAVA",
            "XMLCreationDate": "2026-02-22",
            "IntermediaryCity": "Delhi",
            "FormName": "FORM15CB",
            "Description": "FORM15CB",
            "AssessmentYear": "2017",
            "SchemaVer": "Ver1.1",
            "FormVer": "1",
            "IorWe": "02",
            "RemitterHonorific": "03",
            "BeneficiaryHonorific": "03",
            "NameRemitter": "A. B",
            "RemitterPAN": "ABCDE1234F",
            "NameRemittee": "C INVOICE NO. 1 DT 15.05.2023",
            "RemitteeTownCityDistrict": "GERMANY",
            "RemitteeFlatDoorBuilding": "x",
            "RemitteeAreaLocality": "y",
            "RemitteeZipCode": "999999",
            "RemitteeState": "OUTSIDE INDIA",
            "RemitteeCountryCode": "49",
            "CountryRemMadeSecb": "49",
            "CurrencySecbCode": "50",
            "AmtPayForgnRem": "100",
            "AmtPayIndRem": "8000",
            "NameBankCode": "41",
            "BranchName": "MG ROAD",
            "BsrCode": "6550003",
            "PropDateRem": "2026-03-01",
            "NatureRemCategory": "16.21",
            "NatureRemCode": "",
            "RevPurCategory": "RB-10.1",
            "RevPurCode": "RB-10.1-S1023",
            "TaxPayGrossSecb": "N",
            "RemittanceCharIndia": "Y",
            "ReasonNot": "",
            "SecRemCovered": "SEC. 195 READ WITH SEC. 115A",
            "AmtIncChrgIt": "8000",
            "TaxLiablIt": "1747.2",
            "BasisDeterTax": "x",
            "TaxResidCert": "Y",
            "RelevantDtaa": "ARTICLE 12 OF DTAA BTWN INDIA AND GERMANY",
            "RelevantArtDtaa": "ARTICLE 12 OF DTAA BTWN INDIA AND GERMANY",
            "TaxIncDtaa": "8000",
            "TaxLiablDtaa": "800",
            "RemForRoyFlg": "Y",
            "ArtDtaa": "ARTICLE 12 OF DTAA BTWN INDIA AND GERMANY",
            "RateTdsADtaa": "10",
            "RemAcctBusIncFlg": "N",
            "IncLiabIndiaFlg": "-1",
            "RemOnCapGainFlg": "N",
            "OtherRemDtaa": "N",
            "NatureRemDtaa": "",
            "TaxIndDtaaFlg": "N",
            "RelArtDetlDDtaa": "NOT APPLICABLE",
            "AmtPayForgnTds": "10",
            "AmtPayIndianTds": "800",
            "RateTdsSecbFlg": "2",
            "RateTdsSecB": "10",
            "ActlAmtTdsForgn": "90",
            "DednDateTds": "2026-02-22",
            "NameAcctnt": "SONDUR ANAND",
            "NameFirmAcctnt": "ANAND S & ASSOCIATES",
            "PremisesBuildingVillage": "S.V. COMPLEX",
            "AcctntTownCityDistrict": "BENGALURU",
            "AcctntFlatDoorBuilding": "NO. 55, SECOND FLOOR",
            "AcctntAreaLocality": "BASAVANAGUDI",
            "AcctntPincode": "560004",
            "AcctntState": "15",
            "AcctntRoadStreet": "K.R. ROAD",
            "AcctntCountryCode": "91",
            "MembershipNumber": "216066",
        }

    def test_non_tds_omits_rate_tags(self):
        xml = generate_xml_content(self._base(), mode=MODE_NON_TDS)
        self.assertTrue(xml.lstrip().startswith("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"))
        root = ET.fromstring(xml)
        ns = {"f": "http://incometaxindiaefiling.gov.in/FORM15CAB"}
        self.assertIsNone(root.find(".//f:TDSDetails/f:RateTdsSecbFlg", ns))
        self.assertIsNone(root.find(".//f:TDSDetails/f:RateTdsSecB", ns))
        self.assertIsNone(root.find(".//f:TDSDetails/f:DednDateTds", ns))

    def test_empty_optional_tags_are_omitted(self):
        data = self._base()
        data["ReasonNot"] = ""
        data["NatureRemCode"] = ""
        data["NatureRemDtaa"] = ""
        xml = generate_xml_content(data, mode=MODE_TDS)
        self.assertNotIn("<FORM15CB:ReasonNot></FORM15CB:ReasonNot>", xml)
        self.assertNotIn("<FORM15CB:NatureRemCode></FORM15CB:NatureRemCode>", xml)
        self.assertNotIn("<FORM15CB:NatureRemDtaa></FORM15CB:NatureRemDtaa>", xml)

    def test_tds_keeps_rate_tags(self):
        xml = generate_xml_content(self._base(), mode=MODE_TDS)
        root = ET.fromstring(xml)
        ns = {"f": "http://incometaxindiaefiling.gov.in/FORM15CAB"}
        self.assertIsNotNone(root.find(".//f:TDSDetails/f:RateTdsSecbFlg", ns))

    def test_preserves_leading_zero_codes_and_escapes_firm_name(self):
        xml = generate_xml_content(self._base(), mode=MODE_TDS)
        self.assertIn("<FORM15CB:IorWe>02</FORM15CB:IorWe>", xml)
        self.assertIn("<FORM15CB:RemitterHonorific>03</FORM15CB:RemitterHonorific>", xml)
        self.assertIn("<FORM15CB:BeneficiaryHonorific>03</FORM15CB:BeneficiaryHonorific>", xml)
        self.assertIn("<FORM15CB:NameFirmAcctnt>ANAND S &amp; ASSOCIATES</FORM15CB:NameFirmAcctnt>", xml)

    def test_tds_blocks_when_mandatory_tax_fields_missing(self):
        data = self._base()
        data["TaxLiablIt"] = ""
        with self.assertRaises(ValueError):
            generate_xml_content(data, mode=MODE_TDS)


if __name__ == "__main__":
    unittest.main()
