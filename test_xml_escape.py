#!/usr/bin/env python
from modules.xml_generator import escape_xml

# Test XML escaping
test_cases = [
    ("ANAND S & ASSOCIATES", "ANAND S &amp; ASSOCIATES"),
    ("Normal Text", "Normal Text"),
    ("Text with <", "Text with &lt;"),
    ("Text with >", "Text with &gt;"),
    ("Text with \"", "Text with &quot;"),
    ("Text with '", "Text with &apos;"),
    ("Multiple & ampersands &", "Multiple &amp; ampersands &amp;"),
]

print("Testing escape_xml function:")
all_passed = True
for input_str, expected in test_cases:
    result = escape_xml(input_str)
    passed = result == expected
    all_passed = all_passed and passed
    status = "✓" if passed else "✗"
    print(f"{status} escape_xml('{input_str}') = '{result}'")
    if not passed:
        print(f"   Expected: '{expected}'")

if all_passed:
    print("\n✓ All escape_xml tests passed!")
else:
    print("\n✗ Some escape_xml tests failed!")
