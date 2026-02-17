"""
XML Generator Module for Form 15CB

This module handles the generation of Form 15CB XML files using a template-based approach.
The template contains placeholders ({{FieldName}}) that are replaced with actual values.
"""

import os
import uuid
import re
from config.settings import OUTPUT_FOLDER


def escape_xml(value):
    """
    Escape special XML characters to prevent malformed XML and injection attacks.
    
    Args:
        value: The value to escape (any type)
        
    Returns:
        str: XML-safe string with special characters escaped
        
    Example:
        escape_xml("Smith & Sons") -> "Smith &amp; Sons"
        escape_xml("Price < $100") -> "Price &lt; $100"
    """
    if value is None:
        return ''
    
    # Convert to string and escape special XML characters
    return (str(value)
            .replace('&', '&amp;')      # Must be first to avoid double-escaping
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", "&apos;"))


def validate_required_fields(fields):
    """
    Validate that all mandatory fields are present and non-empty.
    
    Args:
        fields: Dictionary of field name -> value pairs
        
    Raises:
        ValueError: If any mandatory field is missing or empty
    """
    # Define mandatory fields based on Form 15CB requirements
    mandatory_fields = [
        'SWVersionNo',
        'FormName',
        'AssessmentYear',
        'RemitterPAN',
        'NameRemitter',
    ]
    
    missing = []
    for field in mandatory_fields:
        if field not in fields or not str(fields[field]).strip():
            missing.append(field)
    
    if missing:
        raise ValueError(
            f"Missing or empty mandatory fields: {', '.join(missing)}. "
            f"Please fill in these fields before generating XML."
        )


def generate_xml(fields, template_path='templates/form15cb_template.xml'):
    """
    Generate Form 15CB XML file from a template by replacing placeholders with actual values.
    
    This function:
    1. Loads the XML template file
    2. Replaces all {{FieldName}} placeholders with escaped field values
    3. Removes any remaining unreplaced placeholders
    4. Saves the final XML to the output folder
    
    Args:
        fields: Dictionary of field name -> value pairs
        template_path: Path to the XML template file (default: templates/form15cb_template.xml)
        
    Returns:
        str: Full path to the generated XML file
        
    Raises:
        FileNotFoundError: If template file doesn't exist
        ValueError: If mandatory fields are missing
        IOError: If unable to write output file
        
    Example:
        fields = {
            'RemitterPAN': 'ABCDE1234F',
            'NameRemitter': 'ABC Company Ltd',
            'AmtPayIndRem': '100000'
        }
        xml_path = generate_xml(fields)
        # Returns: 'data/output/generated_abc123.xml'
    """
    # Validate mandatory fields first
    try:
        validate_required_fields(fields)
    except ValueError as e:
        # Re-raise with additional context
        raise ValueError(f"XML generation failed: {str(e)}")
    
    # Load template
    try:
        with open(template_path, 'r', encoding='utf8') as f:
            xml_content = f.read()
    except FileNotFoundError:
        raise FileNotFoundError(
            f"XML template not found at: {template_path}. "
            f"Ensure the templates directory exists and contains form15cb_template.xml"
        )
    except Exception as e:
        raise IOError(f"Failed to read template file: {str(e)}")
    
    # Replace all placeholders with escaped values
    for field_name, field_value in fields.items():
        placeholder = '{{' + field_name + '}}'
        escaped_value = escape_xml(field_value)
        xml_content = xml_content.replace(placeholder, escaped_value)
    
    # Remove any unreplaced placeholders (optional fields that weren't provided)
    # This prevents {{FieldName}} from appearing in the final XML
    xml_content = re.sub(r'\{\{[^}]+\}\}', '', xml_content)
    
    # Ensure output folder exists
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    
    # Generate unique filename using UUID
    filename = f'generated_{uuid.uuid4().hex[:12]}.xml'
    output_path = os.path.join(OUTPUT_FOLDER, filename)
    
    # Write XML to file
    try:
        with open(output_path, 'w', encoding='utf8') as f:
            f.write(xml_content)
    except PermissionError:
        raise PermissionError(
            f"Permission denied: Cannot write to {output_path}. "
            f"Check folder permissions for {OUTPUT_FOLDER}"
        )
    except Exception as e:
        raise IOError(f"Failed to write XML file: {str(e)}")
    
    return output_path


def validate_xml_structure(xml_path):
    """
    Validate the generated XML file for well-formedness.
    
    This is a basic validation that checks if the XML can be parsed.
    For full schema validation, use validate_xml_against_schema() instead.
    
    Args:
        xml_path: Path to the XML file to validate
        
    Returns:
        bool: True if XML is well-formed, False otherwise
        
    Example:
        xml_path = generate_xml(fields)
        if validate_xml_structure(xml_path):
            print("XML is well-formed")
    """
    try:
        import xml.etree.ElementTree as ET
        ET.parse(xml_path)
        return True
    except ET.ParseError as e:
        print(f"XML parsing error: {str(e)}")
        return False
    except Exception as e:
        print(f"Validation error: {str(e)}")
        return False


def validate_xml_against_schema(xml_path, xsd_path='schemas/form15cb.xsd'):
    """
    Validate the generated XML against the official XSD schema.
    
    Note: This requires the lxml library and the official schema file.
    
    Args:
        xml_path: Path to the XML file to validate
        xsd_path: Path to the XSD schema file
        
    Returns:
        tuple: (is_valid: bool, errors: list of str)
        
    Example:
        xml_path = generate_xml(fields)
        is_valid, errors = validate_xml_against_schema(xml_path)
        if not is_valid:
            for error in errors:
                print(f"Validation error: {error}")
    """
    try:
        from lxml import etree
    except ImportError:
        return (False, ["lxml library not installed. Run: pip install lxml"])
    
    try:
        # Load schema
        with open(xsd_path, 'rb') as f:
            schema_root = etree.XML(f.read())
            schema = etree.XMLSchema(schema_root)
        
        # Parse XML
        with open(xml_path, 'rb') as f:
            xml_doc = etree.parse(f)
        
        # Validate
        is_valid = schema.validate(xml_doc)
        
        if not is_valid:
            errors = [str(error) for error in schema.error_log]
            return (False, errors)
        
        return (True, [])
        
    except FileNotFoundError as e:
        return (False, [f"Schema file not found: {str(e)}"])
    except etree.XMLSyntaxError as e:
        return (False, [f"XML syntax error: {str(e)}"])
    except Exception as e:
        return (False, [f"Validation error: {str(e)}"])


# Example usage (for testing)
if __name__ == "__main__":
    # Sample fields for testing
    test_fields = {
        'SWVersionNo': '1',
        'SWCreatedBy': 'DIT-EFILING-JAVA',
        'XMLCreatedBy': 'DIT-EFILING-JAVA',
        'XMLCreationDate': '2026-02-15',
        'IntermediaryCity': 'Delhi',
        'FormName': 'FORM15CB',
        'Description': 'FORM15CB',
        'AssessmentYear': '2025',
        'SchemaVer': 'Ver1.1',
        'FormVer': '1',
        'IorWe': '02',
        'RemitterHonorific': '03',
        'RemitterPAN': 'ABCDE1234F',
        'NameRemitter': 'Test Company Ltd',
        'BeneficiaryHonorific': '03',
        'NameRemittee': 'Beneficiary Company GmbH',
        'AmtPayIndRem': '100000',
        'AmtPayForgnRem': '1200',
        'PropDateRem': '2026-03-15',
        'NameAcctnt': 'CA John Doe'
    }
    
    try:
        xml_path = generate_xml(test_fields)
        print(f"✅ XML generated successfully: {xml_path}")
        
        # Validate structure
        if validate_xml_structure(xml_path):
            print("✅ XML is well-formed")
        else:
            print("❌ XML validation failed")
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")