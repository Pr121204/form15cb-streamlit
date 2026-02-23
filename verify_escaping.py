#!/usr/bin/env python
from modules.xml_generator import generate_xml_content

# Use the same base data from the test
test_data = {
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

# Generate XML
from modules.form15cb_constants import MODE_NON_TDS
xml = generate_xml_content(test_data, mode=MODE_NON_TDS)

# Check for proper escaping
print("Checking NameFirmAcctnt escaping in generated XML:\n")

# Find the line with NameFirmAcctnt
for line in xml.split('\n'):
    if 'NameFirmAcctnt' in line:
        print(f"Found: {line.strip()}")
        if '&amp;' in line:
            print("✓ SUCCESS: Ampersand is properly escaped as &amp;")
        else:
            print("✗ FAILURE: Ampersand is NOT properly escaped")
        break

# Also save to file for inspection
with open(r'C:\Users\HP\Downloads\15CB_final\15CB_extracted\test_output.xml', 'w', encoding='utf-8') as f:
    f.write(xml)
print("\nGenerated XML saved to: test_output.xml")
