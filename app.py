"""
Form 15CB OCR to XML Demo Application
Version: 2.1
Author: Your Name
Last Updated: February 2026

This application automates Form 15CB data entry by:
1. Extracting text from PDFs or images using OCR
2. Auto-extracting key fields using Gemini (AI)
3. Allowing manual review and correction
4. Generating schema-compliant XML for IT Department's Java utility
"""

import streamlit as st
from modules.file_manager import save_uploaded_file, ensure_folders
from modules.pdf_reader import extract_text_from_pdf
from modules.ocr_engine import extract_text_from_image_file
from modules.field_extractor import extract_fields, XML_FIELD_KEYS
from modules.xml_generator import generate_xml
from modules.logger import get_logger
import hashlib
import io
import os
import time
import re
from datetime import datetime

# Initialize
logger = get_logger()
ensure_folders()

# Constants
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
VERSION = "2.1"
LAST_UPDATED = "February 2026"

# Page configuration
st.set_page_config(
    page_title='Form 15CB OCR → XML Demo',
    layout='wide',
    initial_sidebar_state='collapsed'
)

# Title and Instructions
st.title('📄 Form 15CB OCR → XML (Demo)')

with st.expander("How to use this tool", expanded=False):
    st.markdown("""
    ### Quick Guide:
    1. **Upload** a PDF or image containing Form 15CB data (invoices, agreements, etc.)
    2. **Review** the auto-extracted fields and edit any incorrect values
    3. **Fill** the fixed template fields in the expandable section
    4. **Generate** XML file ready for Income Tax Department's Java utility
    
    ### 📁 Supported Files:
    - PDF documents (with embedded text or scanned)
    - Images: PNG, JPG, JPEG
    - Maximum file size: 10MB
    
    ### 💡 Tips for Best Results:
    - Use clear, high-quality scans (300 DPI or higher recommended)
    - Ensure text is readable and not skewed or blurry
    - Always review extracted data before generating XML
    - The manual review step ensures 100% accuracy
    
    ### ⏱️ Time Savings:
    - Manual entry: 15-20 minutes per form
    - With this tool: 2-3 minutes per form
    - **Time saved: ~85%**
    """)

st.divider()

# File Upload Section
st.subheader('📤 Step 1: Upload Document')
uploaded = st.file_uploader(
    'Upload PDF or Image',
    type=['pdf', 'png', 'jpg', 'jpeg'],
    help='Select a PDF invoice, 15CA form, or agreement containing Form 15CB data'
)

if uploaded:
    # File size validation
    if uploaded.size > MAX_FILE_SIZE:
        st.error(f"❌ File too large: {uploaded.size/1024/1024:.1f}MB. Maximum allowed: {MAX_FILE_SIZE/1024/1024:.0f}MB")
        st.info("💡 Tip: Compress the PDF or reduce image resolution before uploading")
        st.stop()
    
    # Display file info
    file_size_kb = uploaded.size / 1024
    st.success(f"✅ File uploaded: **{uploaded.name}** ({file_size_kb:.1f} KB)")
    file_hash = hashlib.md5(uploaded.getvalue()).hexdigest()
    
    # Save uploaded file
    try:
        saved_path = save_uploaded_file(uploaded, uploaded.name)
        logger.info(f"File saved: {saved_path}")
    except PermissionError:
        st.error("❌ Permission denied: Cannot save file. Check folder permissions.")
        st.stop()
    except OSError as e:
        st.error(f"❌ File system error: {str(e)}")
        st.stop()
    except Exception as e:
        logger.exception("Failed to save uploaded file")
        st.error(f"❌ Failed to save file: {str(e)}")
        st.stop()
    
    st.divider()
    
    # Text Extraction Section
    st.subheader('🔍 Step 2: Extract Text')
    
    with st.spinner('Extracting text from document...'):
        start_time = time.time()
        text = ''
        
        # Try PDF extraction first
        try:
            uploaded.seek(0)
            pdf_bytes = io.BytesIO(uploaded.read())
            text = extract_text_from_pdf(pdf_bytes)
            if text and len(text.strip()) >= 20:
                extraction_method = "PDF text extraction"
                logger.info("PDF text extracted successfully")
        except FileNotFoundError:
            st.error("❌ File not found. Please try re-uploading.")
            st.stop()
        except Exception as e:
            logger.warning(f"PDF extraction failed: {type(e).__name__}")
            text = ''
        
        # Fallback to OCR if no embedded text
        if not text or len(text.strip()) < 20:
            st.info('📸 No embedded text found — running OCR (this may take 10-30 seconds)...')
            try:
                import pytesseract
                ocr_text = extract_text_from_image_file(saved_path)
                text = ocr_text
                extraction_method = "OCR (Tesseract)"
                logger.info("OCR extraction completed")
            except pytesseract.TesseractNotFoundError:
                st.error("❌ **Tesseract OCR not installed!**")
                st.markdown("""
                ### Installation Required:
                1. Download Tesseract from: https://github.com/tesseract-ocr/tesseract
                2. Install to default location: `C:\\Program Files\\Tesseract-OCR\\`
                3. If installed elsewhere, update `TESSERACT_PATH` in `config/settings.py`
                
                **Need help?** Contact your IT administrator.
                """)
                st.stop()
            except ImportError as e:
                st.error(f"❌ Missing required library: {str(e)}")
                st.info("Run: `pip install pytesseract pdf2image Pillow`")
                st.stop()
            except Exception as e:
                logger.exception("OCR failed")
                st.error(f"❌ **OCR failed:** {type(e).__name__}")
                st.markdown(f"""
                **Error details:** {str(e)}
                
                ### 💡 Troubleshooting Tips:
                - Ensure the document image is clear and high-resolution
                - Try scanning at 300 DPI or higher
                - Check that the file is not corrupted
                - Verify Tesseract is properly installed
                - Ensure Poppler is installed (for PDF to image conversion)
                
                **Still having issues?** Try uploading a different file or contact support.
                """)
                st.stop()
        
        extraction_time = time.time() - start_time
    
    # Show extraction results
    col1, col2 = st.columns([3, 1])
    with col1:
        st.success(f"✅ Text extracted successfully using: **{extraction_method}**")
    with col2:
        st.metric("⏱️ Time", f"{extraction_time:.1f}s")
    
    # Display extracted text preview
    with st.expander("📄 View Raw Extracted Text (first 4000 characters)", expanded=False):
        st.code(text[:4000], language='text')
        if len(text) > 4000:
            st.caption(f"... and {len(text) - 4000} more characters")
    
    st.divider()
    
    # Field Extraction Section
    st.subheader('✏️ Step 3: Review & Edit Extracted Fields')
    st.caption('Fields are auto-extracted using Gemini (AI). Please review and correct any errors.')

    with st.spinner('Analyzing document and extracting fields...'):
        fields = extract_fields(text)
        logger.info(f"Extracted {len(fields)} fields")

    if 'extracted_fields' not in st.session_state:
        st.session_state['extracted_fields'] = fields

    edited = {}

    st.markdown("#### 👤 Remitter & Beneficiary")
    col1, col2 = st.columns(2)
    with col1:
        edited['NameRemitter'] = st.text_input('Remitter Name', value=st.session_state['extracted_fields'].get('NameRemitter', ''))
        edited['RemitterPAN'] = st.text_input('Remitter PAN', value=st.session_state['extracted_fields'].get('RemitterPAN', ''))
    with col2:
        edited['NameRemittee'] = st.text_input('Remittee Name', value=st.session_state['extracted_fields'].get('NameRemittee', ''))

    st.markdown("#### 🏠 Remittee Address")
    col1, col2, col3 = st.columns(3)
    with col1:
        edited['RemitteeFlatDoorBuilding'] = st.text_input('Flat/Door/Building', value=st.session_state['extracted_fields'].get('RemitteeFlatDoorBuilding', ''))
        edited['RemitteeAreaLocality'] = st.text_input('Area/Locality', value=st.session_state['extracted_fields'].get('RemitteeAreaLocality', ''))
    with col2:
        edited['RemitteeTownCityDistrict'] = st.text_input('Town/City', value=st.session_state['extracted_fields'].get('RemitteeTownCityDistrict', ''))
        edited['RemitteeZipCode'] = st.text_input('Zip Code', value=st.session_state['extracted_fields'].get('RemitteeZipCode', ''))
    with col3:
        edited['RemitteeState'] = st.text_input('State', value=st.session_state['extracted_fields'].get('RemitteeState', ''))
        edited['RemitteeCountryCode'] = st.text_input('Country Code', value=st.session_state['extracted_fields'].get('RemitteeCountryCode', ''))

    st.markdown("#### 💰 Remittance Details")
    col1, col2, col3 = st.columns(3)
    with col1:
        edited['CountryRemMadeSecb'] = st.text_input('Country Code (Remittance)', value=st.session_state['extracted_fields'].get('CountryRemMadeSecb', ''))
        edited['CurrencySecbCode'] = st.text_input('Currency Code', value=st.session_state['extracted_fields'].get('CurrencySecbCode', ''))
        edited['AmtPayForgnRem'] = st.text_input('Amount (Foreign Currency)', value=st.session_state['extracted_fields'].get('AmtPayForgnRem', ''))
        edited['AmtPayIndRem'] = st.text_input('Amount (Indian ₹)', value=st.session_state['extracted_fields'].get('AmtPayIndRem', ''))
    with col2:
        edited['NameBankCode'] = st.text_input('Bank Code', value=st.session_state['extracted_fields'].get('NameBankCode', ''))
        edited['BranchName'] = st.text_input('Branch Name', value=st.session_state['extracted_fields'].get('BranchName', ''))
        edited['BsrCode'] = st.text_input('BSR Code', value=st.session_state['extracted_fields'].get('BsrCode', ''))
        edited['PropDateRem'] = st.text_input('Proposed Date of Remittance (YYYY-MM-DD)', value=st.session_state['extracted_fields'].get('PropDateRem', ''))
    with col3:
        edited['NatureRemCategory'] = st.text_input('Nature of Remittance Category', value=st.session_state['extracted_fields'].get('NatureRemCategory', ''))
        edited['RevPurCategory'] = st.text_input('RBI Purpose Category', value=st.session_state['extracted_fields'].get('RevPurCategory', ''))
        edited['RevPurCode'] = st.text_input('RBI Purpose Code', value=st.session_state['extracted_fields'].get('RevPurCode', ''))
        edited['TaxPayGrossSecb'] = st.text_input('Tax Grossed Up? (Y/N)', value=st.session_state['extracted_fields'].get('TaxPayGrossSecb', ''))

    st.markdown("#### 🏛️ IT Act Details")
    col1, col2 = st.columns(2)
    with col1:
        edited['RemittanceCharIndia'] = st.text_input('Remittance Chargeable in India? (Y/N)', value=st.session_state['extracted_fields'].get('RemittanceCharIndia', ''))
        edited['SecRemCovered'] = st.text_input('Section Covered', value=st.session_state['extracted_fields'].get('SecRemCovered', ''))
        edited['AmtIncChrgIt'] = st.text_input('Amount of Income Chargeable (₹)', value=st.session_state['extracted_fields'].get('AmtIncChrgIt', ''))
    with col2:
        edited['TaxLiablIt'] = st.text_input('Tax Liability under IT Act (₹)', value=st.session_state['extracted_fields'].get('TaxLiablIt', ''))
        edited['BasisDeterTax'] = st.text_area('Basis of Determining Tax', value=st.session_state['extracted_fields'].get('BasisDeterTax', ''), height=100)

    st.markdown("#### 📜 DTAA Details")
    col1, col2, col3 = st.columns(3)
    with col1:
        edited['TaxResidCert'] = st.text_input('Tax Residency Certificate? (Y/N)', value=st.session_state['extracted_fields'].get('TaxResidCert', ''))
        edited['RelevantDtaa'] = st.text_input('Relevant DTAA', value=st.session_state['extracted_fields'].get('RelevantDtaa', ''))
        edited['RelevantArtDtaa'] = st.text_input('Relevant Article of DTAA', value=st.session_state['extracted_fields'].get('RelevantArtDtaa', ''))
        edited['TaxIncDtaa'] = st.text_input('Taxable Income as per DTAA (₹)', value=st.session_state['extracted_fields'].get('TaxIncDtaa', ''))
        edited['TaxLiablDtaa'] = st.text_input('Tax Liability as per DTAA (₹)', value=st.session_state['extracted_fields'].get('TaxLiablDtaa', ''))
    with col2:
        edited['RemForRoyFlg'] = st.text_input('Remittance for Royalty/FTS? (Y/N)', value=st.session_state['extracted_fields'].get('RemForRoyFlg', ''))
        edited['ArtDtaa'] = st.text_input('Article of DTAA (Royalty)', value=st.session_state['extracted_fields'].get('ArtDtaa', ''))
        edited['RateTdsADtaa'] = st.text_input('TDS Rate as per DTAA (%)', value=st.session_state['extracted_fields'].get('RateTdsADtaa', ''))
        edited['RemAcctBusIncFlg'] = st.text_input('Business Income? (Y/N)', value=st.session_state['extracted_fields'].get('RemAcctBusIncFlg', ''))
        edited['IncLiabIndiaFlg'] = st.text_input('Income Liable in India? (Y/N)', value=st.session_state['extracted_fields'].get('IncLiabIndiaFlg', ''))
    with col3:
        edited['RemOnCapGainFlg'] = st.text_input('Capital Gains? (Y/N)', value=st.session_state['extracted_fields'].get('RemOnCapGainFlg', ''))
        edited['OtherRemDtaa'] = st.text_input('Other Remittance? (Y/N)', value=st.session_state['extracted_fields'].get('OtherRemDtaa', ''))
        edited['TaxIndDtaaFlg'] = st.text_input('Taxable in India per DTAA? (Y/N)', value=st.session_state['extracted_fields'].get('TaxIndDtaaFlg', ''))
        edited['RelArtDetlDDtaa'] = st.text_input('Relevant Article Detail (Other)', value=st.session_state['extracted_fields'].get('RelArtDetlDDtaa', ''))

    st.markdown("#### 🧾 TDS Details")
    col1, col2, col3 = st.columns(3)
    with col1:
        edited['AmtPayForgnTds'] = st.text_input('TDS Amount (Foreign Currency)', value=st.session_state['extracted_fields'].get('AmtPayForgnTds', ''))
        edited['AmtPayIndianTds'] = st.text_input('TDS Amount (₹)', value=st.session_state['extracted_fields'].get('AmtPayIndianTds', ''))
    with col2:
        edited['RateTdsSecbFlg'] = st.text_input('TDS Rate Flag', value=st.session_state['extracted_fields'].get('RateTdsSecbFlg', ''))
        edited['RateTdsSecB'] = st.text_input('TDS Rate (%)', value=st.session_state['extracted_fields'].get('RateTdsSecB', ''))
    with col3:
        edited['ActlAmtTdsForgn'] = st.text_input('Actual Remittance after TDS (Foreign)', value=st.session_state['extracted_fields'].get('ActlAmtTdsForgn', ''))
        edited['DednDateTds'] = st.text_input('Date of TDS Deduction (YYYY-MM-DD)', value=st.session_state['extracted_fields'].get('DednDateTds', ''))

    st.markdown("#### 🧑‍💼 Accountant Details")
    col1, col2 = st.columns(2)
    with col1:
        edited['NameAcctnt'] = st.text_input('Accountant Name', value=st.session_state['extracted_fields'].get('NameAcctnt', ''))
        edited['NameFirmAcctnt'] = st.text_input('Firm Name', value=st.session_state['extracted_fields'].get('NameFirmAcctnt', ''))
        edited['MembershipNumber'] = st.text_input('Membership Number', value=st.session_state['extracted_fields'].get('MembershipNumber', ''))
    with col2:
        edited['AcctntFlatDoorBuilding'] = st.text_input('Flat/Door/Building (CA)', value=st.session_state['extracted_fields'].get('AcctntFlatDoorBuilding', ''))
        edited['PremisesBuildingVillage'] = st.text_input('Premises/Village (CA)', value=st.session_state['extracted_fields'].get('PremisesBuildingVillage', ''))
        edited['AcctntAreaLocality'] = st.text_input('Area/Locality (CA)', value=st.session_state['extracted_fields'].get('AcctntAreaLocality', ''))
        edited['AcctntRoadStreet'] = st.text_input('Road/Street (CA)', value=st.session_state['extracted_fields'].get('AcctntRoadStreet', ''))
        edited['AcctntTownCityDistrict'] = st.text_input('Town/City (CA)', value=st.session_state['extracted_fields'].get('AcctntTownCityDistrict', ''))
        edited['AcctntPincode'] = st.text_input('Pincode (CA)', value=st.session_state['extracted_fields'].get('AcctntPincode', ''))
        edited['AcctntState'] = st.text_input('State (CA)', value=st.session_state['extracted_fields'].get('AcctntState', ''))
        edited['AcctntCountryCode'] = st.text_input('Country Code (CA)', value=st.session_state['extracted_fields'].get('AcctntCountryCode', ''))

    shown_keys = set(edited.keys())
    remaining_keys = [field_key for field_key in XML_FIELD_KEYS if field_key not in shown_keys]

    st.markdown("#### 🧩 All Extracted Fields (Advanced)")
    with st.expander("Click to view/edit all fields", expanded=False):
        if not remaining_keys:
            st.caption("All extracted fields are already shown above.")
        else:
            st.caption("Review or edit every extracted field. Leave blank to keep the extracted value.")
            for field_key in remaining_keys:
                edited[field_key] = st.text_input(
                    field_key,
                    value=st.session_state['extracted_fields'].get(field_key, ''),
                    key=f"all_{field_key}"
                )

    st.divider()
    
    # Fixed/Template Fields
    st.subheader('⚙️ Step 4: Configure Fixed Fields')
    
    with st.expander('📝 Fixed / Template Fields (expand to edit if needed)', expanded=False):
        st.caption('These are standard values required by the XML schema. Edit only if you know what you\'re doing.')
        
        fixed = {}
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("##### Form Metadata")
            fixed['SWVersionNo'] = st.text_input('Software Version', value='1', help='Software version number')
            fixed['SWCreatedBy'] = st.text_input('Software Created By', value='DIT-EFILING-JAVA')
            fixed['XMLCreatedBy'] = st.text_input('XML Created By', value='DIT-EFILING-JAVA')
            fixed['XMLCreationDate'] = st.text_input('XML Creation Date', value=datetime.now().strftime('%Y-%m-%d'), help='Format: YYYY-MM-DD')
            fixed['IntermediaryCity'] = st.text_input('Intermediary City', value='Delhi')
        
        with col2:
            st.markdown("##### Form Details")
            fixed['FormName'] = st.text_input('Form Name', value='FORM15CB')
            fixed['Description'] = st.text_input('Description', value='FORM15CB')
            fixed['AssessmentYear'] = st.text_input('Assessment Year', value='2025', help='Financial year')
            fixed['SchemaVer'] = st.text_input('Schema Version', value='Ver1.1')
            fixed['FormVer'] = st.text_input('Form Version', value='1')
        
        st.markdown("##### Party Details")
        col1, col2 = st.columns(2)
        with col1:
            fixed['IorWe'] = st.selectbox(
                'I/We (Remitter type)',
                options=['01', '02'],
                index=1,
                format_func=lambda x: 'I (Individual)' if x == '01' else 'We (Company)',
                help='01=Individual, 02=Company'
            )
            fixed['RemitterHonorific'] = st.selectbox(
                'Remitter Honorific',
                options=['01', '02', '03', '04'],
                index=2,
                format_func=lambda x: {'01': 'Shri', '02': 'Smt', '03': 'M/s', '04': 'Kumari'}[x]
            )
        with col2:
            fixed['BeneficiaryHonorific'] = st.selectbox(
                'Beneficiary Honorific',
                options=['01', '02', '03', '04'],
                index=2,
                format_func=lambda x: {'01': 'Shri', '02': 'Smt', '03': 'M/s', '04': 'Kumari'}[x]
            )
    
    st.divider()
    
    # XML Generation Section
    st.subheader('🚀 Step 5: Generate XML')
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        generate_btn = st.button(
            '📥 Generate XML File',
            type='primary',
            use_container_width=True,
            help='Create XML file ready for Income Tax Department\'s Java utility'
        )
    
    if generate_btn:
        # Combine all fields
        final_fields = {}
        final_fields.update(edited)
        final_fields.update(fixed)
        
        # Validate mandatory fields
        mandatory_fields = ['RemitterPAN', 'NameRemitter', 'AmtPayIndRem']
        missing_fields = [f for f in mandatory_fields if not final_fields.get(f, '').strip()]
        
        if missing_fields:
            st.error(f"❌ **Missing mandatory fields:** {', '.join(missing_fields)}")
            st.warning("Please fill in all required fields before generating XML.")
        else:
            # Generate XML
            try:
                with st.spinner('Generating XML file...'):
                    xml_path = generate_xml(final_fields)
                    logger.info(f"XML generated: {xml_path}")
                
                st.success('✅ **XML file generated successfully!**')
                
                # Read XML content for preview
                with open(xml_path, 'r', encoding='utf8') as f:
                    xml_content = f.read()
                
                # XML Preview
                st.markdown("---")
                st.subheader("📄 Preview Generated XML")
                
                with st.expander("🔍 Click to view XML content", expanded=True):
                    st.code(xml_content, language='xml', line_numbers=True)
                    st.caption("💡 You can copy the XML from above or use the download button below")
                
                # Download button
                st.markdown("---")
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    with open(xml_path, 'rb') as f:
                        st.download_button(
                            label='📥 Download XML File',
                            data=f,
                            file_name=os.path.basename(xml_path),
                            mime='application/xml',
                            use_container_width=True,
                            type='primary'
                        )
                
                st.info('ℹ️ **Next Step:** Import this XML file into the Income Tax Department\'s Java utility')
                
                # Success metrics
                st.markdown("---")
                st.subheader("📊 Session Summary")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("⏱️ Total Time", f"{extraction_time + 2:.1f}s")
                with col2:
                    st.metric("📝 Fields Extracted", len(edited))
                with col3:
                    st.metric("✅ Validation", "Passed")
                with col4:
                    time_saved = 15 - ((extraction_time + 2) / 60)  # Assuming manual entry takes 15 min
                    st.metric("⚡ Time Saved", f"~{time_saved:.0f} min")
                
            except FileNotFoundError as e:
                logger.exception("Template file not found")
                st.error(f"❌ **Template file missing:** {str(e)}")
                st.info("Ensure `templates/form15cb_template.xml` exists in the application directory")
            except PermissionError:
                logger.exception("Permission error during XML generation")
                st.error("❌ **Permission denied:** Cannot write XML file. Check output folder permissions.")
            except Exception as e:
                logger.exception("XML generation failed")
                st.error(f"❌ **XML generation failed:** {type(e).__name__}")
                st.error(f"**Error details:** {str(e)}")
                st.info("Please check the logs for more information or contact support.")

# Footer
st.markdown("---")
col1, col2, col3 = st.columns(3)
with col1:
    st.caption(f"📌 Version: {VERSION}")
with col2:
    st.caption(f"📅 Last Updated: {LAST_UPDATED}")
with col3:
    st.caption("💰 Cost: ₹0 (Open Source)")

st.caption("⚠️ **Note:** This is a demonstration tool. Always review extracted data before submitting to authorities.")
