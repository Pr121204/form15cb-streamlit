#!/usr/bin/env python
import os
import tempfile
from modules.xml_generator import generate_xml_content

# Create a sample xml_fields dict with an ampersand in NameFirmAcctnt
xml_fields = {
    "RefId": "TEST001",
    "FileRefNo": "FILE001",
    "DispatchDt": "2024-01-15",
    "NameFirmAcctnt": "ANAND S & ASSOCIATES",
    "AadhaarNum": "123456789012",
    "PanNum": "AAAPA5055K",
    "PassportNum": "",
    "VisaNum": "",
    "ForeignAccNo": "",
    "CountryCode": "IN",
    "CityCode": "560001",
    "MailStreet": "Test Street",
    "MailCity": "Bangalore",
    "MailState": "KA",
    "MailCntryCd": "IN",
    "PrincipalAmtInr": "100000",
    "PaymentCurrency": "USD",
    "PaymentAmount": "1200",
    "TdsAmtForgn": "0",
    "TdsAmtIndian": "0",
    "ChargeForgn": "0",
    "ChargeIndian": "0",
    "ExchangeRate": "83.25",
    "BeneficiaryName": "TEST BENEFICIARY",
    "BeneficiaryAcctNum": "123456789",
    "BeneficiaryBankCode": "TESTBK",
    "BeneficiaryCountryCode": "US",
    "BeneficiaryCity": "New York",
    "PurpCodeNot": "",
    "NatureRemCategory": "16.21",
    "RevPurCategory": "S1023",
    "RevPurCode": "RB-10.1-S1023",
    "PaymentMode": "T",
    "PaymentRefNo": "REF001",
    "PaymentDt": "2024-01-15",
    "RmtrDtaa": "",
    "BnfDtaa": "",
    "RateTdsSecB": "0",
    "AmtPayForgnTds": "0",
    "AmtPayIndianTds": "0",
    "ActlAmtTdsForgn": "0",
    "PremisesBuildingVillage": "",
    "RoadStreet": "",
}

# Generate XML
try:
    xml_output = generate_xml_content(xml_fields)
    
    # Check if ampersand is properly escaped
    if "ANAND S &amp; ASSOCIATES" in xml_output:
        print("✓ SUCCESS: Ampersand is properly escaped as &amp;")
    elif "ANAND S & ASSOCIATES" in xml_output:
        print("✗ FAILURE: Ampersand is NOT escaped in final XML")
        # Find and print the relevant line
        for line in xml_output.split('\n'):
            if "ANAND S" in line:
                print(f"  Found: {line.strip()}")
    else:
        print("? WARNING: NameFirmAcctnt not found in output")
    
    # Write output to temp file for inspection
    with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
        f.write(xml_output)
        temp_path = f.name
    
    print(f"\nGenerated XML written to: {temp_path}")
    print("You can inspect this file to verify the escaping.")
    
except Exception as e:
    print(f"✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
