# IT Act Section 195 Dynamic TDS Rate Implementation

## Overview
Implemented dynamic TDS rate calculation for Income Tax Act Section 195, replacing the hardcoded 21.84% rate with surcharge-based slabs based on remittance amount.

## Changes Made

### 1. Constants (modules/form15cb_constants.py)
Added three new rate constants for IT Act surcharge slabs:
- **IT_ACT_RATE_SLAB_LOW = 20.80%** - Up to ₹1 crore (0% surcharge)
- **IT_ACT_RATE_SLAB_MID = 21.22%** - ₹1 crore to ₹10 crore (2% surcharge)
- **IT_ACT_RATE_SLAB_HIGH = 21.84%** - Above ₹10 crore (5% surcharge)

Added amount thresholds:
- **IT_ACT_AMOUNT_SLAB_LOW = 10,000,000** (₹1 crore = 10 million)
- **IT_ACT_AMOUNT_SLAB_HIGH = 100,000,000** (₹10 crore = 100 million)

Added basis text strings for each slab:
- **BASIS_ACT_LOW** - "...AT 20.80 PERCENTAGE..."
- **BASIS_ACT_MID** - "...AT 21.22 PERCENTAGE..."
- **BASIS_ACT_HIGH** - "...AT 21.84 PERCENTAGE..."

### 2. New Function (modules/invoice_calculator.py)
```python
def get_effective_it_rate(inr_amount: float) -> tuple[float, str]:
    """
    Returns (effective_rate_percent, basis_text) based on INR remittance amount.
    
    Formula: Income Tax 20% + Surcharge + Cess 4%
    - Up to ₹1 crore: 20% + 0% surcharge + 4% cess = 20.80%
    - ₹1 crore to ₹10 crore: 20% + 2% surcharge + 4% cess = 21.22%
    - Above ₹10 crore: 20% + 5% surcharge + 4% cess = 21.84%
    """
```

### 3. Updated recompute_invoice Function
Added new path for IT Act basis:
```python
elif mode == MODE_TDS and str(form.get("BasisDeterTax") or "").strip() == "Act":
    # Income Tax Act Section 195 path
    effective_rate, basis_text = get_effective_it_rate(inr)
    tax_liable_it = _round_to_int(inr * (effective_rate / 100.0))
    form["TaxLiablIt"] = _fmt_num(tax_liable_it)
    form["BasisDeterTax"] = basis_text
    form["RateTdsSecB"] = _fmt_num(effective_rate)
    # ... other fields
```

## Rate Calculation Examples

### Example 1: ₹1 crore remittance
- **INR Amount:** ₹10,000,000
- **Rate:** 20.80% (0% surcharge)
- **Calculation:** 10,000,000 × 0.2080 = ₹2,080,000

### Example 2: ₹5 crore remittance
- **INR Amount:** ₹50,000,000
- **Rate:** 21.22% (2% surcharge)
- **Calculation:** 50,000,000 × 0.2122 = ₹10,610,000

### Example 3: ₹15 crore remittance
- **INR Amount:** ₹150,000,000
- **Rate:** 21.84% (5% surcharge)
- **Calculation:** 150,000,000 × 0.2184 = ₹32,760,000

## Integration with Existing Code

The implementation seamlessly integrates with the existing codebase:

1. **DTAA Path (unchanged):** When `dtaa_rate_percent` is set, uses DTAA calculation with existing BASIS_LOW/BASIS_HIGH
2. **IT Act Path (new):** When `BasisDeterTax == "Act"`, uses dynamic IT Act calculation
3. **Skip Path (unchanged):** When neither DTAA nor Act basis is set, logs warning

## Verification Tests

Created comprehensive test suite:
- `test_it_act_rates.py` - Tests `get_effective_it_rate()` function directly
- `test_recompute_it_act.py` - Tests `recompute_invoice()` with IT Act basis
- `test_it_act_comprehensive.py` - Full integration tests with all three slabs

All tests pass ✓

## Key Features

✓ Dynamic rate selection based on remittance amount
✓ Automatic basis text generation with correct percentage
✓ Proper handling of DTAA vs IT Act paths
✓ Clean separation of concerns with dedicated function
✓ Maintains backward compatibility with existing DTAA logic
✓ Full test coverage with multiple amount scenarios
