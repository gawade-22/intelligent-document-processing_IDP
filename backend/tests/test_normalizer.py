"""Unit tests for the Data Normalization service (Step 12).

Tests:
1. Invoice Date Normalization (standard, textual, and common variants)
2. Date Ambiguity Handling (verifying DD/MM/YYYY over MM/DD/YYYY)
3. Invalid Date Handling (rejects impossible calendar dates and non-dates)
4. Total Amount Normalization (currency symbols, Indian & Western groupings, decimals)
5. Financial Precision with Decimal (no binary float rounding errors)
6. Invalid Amount Handling (rejects non-numeric tokens, multiple decimals, malformed groupings)
7. Preservation of Original Values
8. Invoice-level Normalization Result & Field Isolation
"""

from decimal import Decimal
import pytest

from app.schemas.normalization import InvoiceNormalizationResult, NormalizedField
from app.services.normalizer import (
    InvoiceDataNormalizer,
    InvoiceNormalizer,
    normalize_amount,
    normalize_date,
    normalize_invoice,
)


class TestInvoiceDateNormalization:
    """Test suite for invoice date normalization."""

    @pytest.mark.parametrize(
        "raw_date,expected_normalized",
        [
            ("05/09/2026", "2026-09-05"),
            ("05-09-2026", "2026-09-05"),
            ("September 5, 2026", "2026-09-05"),
            ("5/9/2026", "2026-09-05"),
            ("5-9-2026", "2026-09-05"),
            ("05.09.2026", "2026-09-05"),
            ("2026-09-05", "2026-09-05"),
            ("Sep 5, 2026", "2026-09-05"),
            ("5 September 2026", "2026-09-05"),
            ("September 05, 2026", "2026-09-05"),
            ("05 Sep 2026", "2026-09-05"),
            ("5-Sep-2026", "2026-09-05"),
            ("5th September 2026", "2026-09-05"),
            ("2026/09/05", "2026-09-05"),
            ("2026.09.05", "2026-09-05"),
            ("Invoice Date: 05/09/2026", "2026-09-05"),
            ("Date: 05-09-2026", "2026-09-05"),
            ("05/09/2026 14:30:00", "2026-09-05"),
        ],
    )
    def test_valid_date_formats(self, raw_date: str, expected_normalized: str):
        result = normalize_date(raw_date)
        assert isinstance(result, NormalizedField)
        assert result.success is True
        assert result.normalized_value == expected_normalized
        assert result.original_value == raw_date
        assert result.error is None

    def test_date_ambiguity_strictly_dd_mm_yyyy(self):
        """Verify that ambiguous numeric formats like 05/09/2026 are parsed as DD/MM/YYYY (5th Sept),

        NOT MM/DD/YYYY (9th May).
        """
        result = normalize_date("05/09/2026")
        assert result.success is True
        assert result.normalized_value == "2026-09-05"
        assert result.normalized_value != "2026-05-09"

        result2 = normalize_date("01/02/2025")
        assert result2.success is True
        # DD/MM/YYYY -> 1st Feb, NOT 2nd Jan
        assert result2.normalized_value == "2025-02-01"

    @pytest.mark.parametrize(
        "invalid_date",
        [
            "31/02/2026",  # Feb 31 does not exist
            "29/02/2026",  # 2026 is not a leap year
            "99/99/2026",  # Invalid month and day
            "not a date",
            "Invoice Date: unknown",
            "unknown",
            "TBD",
            "12/34/2026",  # Month 34 does not exist
            "00/05/2026",  # Day 0 does not exist
            "05/00/2026",  # Month 0 does not exist
        ],
    )
    def test_invalid_date_rejection(self, invalid_date: str):
        result = normalize_date(invalid_date)
        assert result.success is False
        assert result.normalized_value is None
        assert result.original_value == invalid_date
        assert result.error is not None
        assert len(result.error) > 0

    def test_empty_and_none_date(self):
        none_result = normalize_date(None)
        assert none_result.success is True
        assert none_result.original_value is None
        assert none_result.normalized_value is None
        assert none_result.error is None

        empty_result = normalize_date("   ")
        assert empty_result.success is False
        assert empty_result.normalized_value is None
        assert empty_result.error is not None


class TestTotalAmountNormalization:
    """Test suite for total amount normalization."""

    @pytest.mark.parametrize(
        "raw_amount,expected_normalized",
        [
            ("₹25,500", "25500.00"),
            ("Rs. 25,500", "25500.00"),
            ("25,500.00", "25500.00"),
            ("₹ 25,500.00", "25500.00"),
            ("Rs 25500", "25500.00"),
            ("Rs. 25,500.50", "25500.50"),
            ("INR 25,500", "25500.00"),
            ("INR 25500.75", "25500.75"),
            ("25,500", "25500.00"),
            ("25500.00", "25500.00"),
            ("₹25,500.50", "25500.50"),
            ("25500", "25500.00"),
            ("25500.5", "25500.50"),
            ("₹ 25500/-", "25500.00"),
            ("Total: ₹25,500.00", "25500.00"),
            ("Grand Total: INR 25,500.50", "25500.50"),
            ("$1,250.00", "1250.00"),
            ("€500.25", "500.25"),
            ("£10,000", "10000.00"),
            ("-₹500.00", "-500.00"),
            ("₹-500.00", "-500.00"),
            ("-Rs. 500", "-500.00"),
            ("Rs. -500.50", "-500.50"),
            ("(₹25,500)", "-25500.00"),
            ("(500.00)", "-500.00"),
            ("  ₹25,500  ", "25500.00"),
        ],
    )
    def test_valid_amount_formats(self, raw_amount: str, expected_normalized: str):
        result = normalize_amount(raw_amount)
        assert isinstance(result, NormalizedField)
        assert result.success is True
        assert result.normalized_value == expected_normalized
        assert result.original_value == raw_amount
        assert result.error is None

    @pytest.mark.parametrize(
        "raw_amount,expected_normalized",
        [
            # Indian lakh & crore formats
            ("1,25,000", "125000.00"),
            ("12,50,000.75", "1250000.75"),
            ("Rs. 1,25,000.50", "125000.50"),
            ("1,12,50,000.00", "11250000.00"),
            ("₹ 5,00,000", "500000.00"),
            # Standard Western grouping
            ("125,000", "125000.00"),
            ("1,250,000.75", "1250000.75"),
            ("$ 1,000,000.00", "1000000.00"),
        ],
    )
    def test_number_groupings_indian_and_western(
        self, raw_amount: str, expected_normalized: str
    ):
        result = normalize_amount(raw_amount)
        assert result.success is True
        assert result.normalized_value == expected_normalized

    def test_decimal_precision(self):
        """Ensure no binary floating point rounding artifacts exist (e.g. 0.1 + 0.2 = 0.30000000000000004)."""
        result = normalize_amount("100.10")
        assert result.normalized_value == "100.10"
        # Convert to Decimal to ensure exactness
        dec = Decimal(result.normalized_value)
        assert dec == Decimal("100.10")

        # Test rounding on 3 decimal digits
        result3 = normalize_amount("25500.756")
        assert result3.normalized_value == "25500.76"

    @pytest.mark.parametrize(
        "invalid_amount",
        [
            "₹abc",
            "25,50,00,xyz",
            "12.34.56",  # Multiple decimal points
            "unknown",
            "₹",  # Bare currency symbol
            "Rs.",  # Bare currency code
            "Rs. abc",
            "N/A",
            "₹ 12,34,56",  # Malformed grouping (only 2 digits at end instead of 3)
            "123.45.67",
            "-₹-500",  # Ambiguous double negative
            "₹-abc",
        ],
    )
    def test_invalid_amount_rejection(self, invalid_amount: str):
        result = normalize_amount(invalid_amount)
        assert result.success is False
        assert result.normalized_value is None
        assert result.original_value == invalid_amount
        assert result.error is not None
        assert len(result.error) > 0

    def test_empty_and_none_amount(self):
        none_result = normalize_amount(None)
        assert none_result.success is True
        assert none_result.original_value is None
        assert none_result.normalized_value is None
        assert none_result.error is None

        empty_result = normalize_amount("   ")
        assert empty_result.success is False
        assert empty_result.normalized_value is None
        assert empty_result.error is not None


class TestInvoiceNormalizationResult:
    """Test suite for full invoice-level normalization result."""

    def test_successful_invoice_normalization(self):
        res = normalize_invoice(
            invoice_date="05/09/2026",
            total_amount="₹25,500.50",
        )
        assert isinstance(res, InvoiceNormalizationResult)
        assert res.success is True
        assert res.invoice_date.success is True
        assert res.invoice_date.normalized_value == "2026-09-05"
        assert res.invoice_date.original_value == "05/09/2026"
        assert res.total_amount.success is True
        assert res.total_amount.normalized_value == "25500.50"
        assert res.total_amount.original_value == "₹25,500.50"
        assert len(res.errors) == 0

    def test_partial_failure_invoice_normalization(self):
        res = normalize_invoice(
            invoice_date="31/02/2026",  # Invalid date
            total_amount="₹25,500.50",  # Valid amount
        )
        assert res.success is False
        assert res.invoice_date.success is False
        assert res.invoice_date.normalized_value is None
        assert res.total_amount.success is True
        assert res.total_amount.normalized_value == "25500.50"
        assert len(res.errors) == 1
        assert "invoice_date" in res.errors[0]

    def test_both_failure_invoice_normalization(self):
        res = normalize_invoice(
            invoice_date="not a date",
            total_amount="₹abc",
        )
        assert res.success is False
        assert res.invoice_date.success is False
        assert res.total_amount.success is False
        assert len(res.errors) == 2

    def test_field_isolation_ignores_other_fields(self):
        """Verify that other fields (vendor_name, invoice_number, etc.) are ignored and not normalized."""
        res = InvoiceDataNormalizer.normalize_invoice(
            invoice_date="05/09/2026",
            total_amount="25500.00",
            vendor_name="Acme Corp",
            invoice_number="INV-2026-001",
            gstin="27AAPFU0939F1ZV",
        )
        assert res.success is True
        # Verify schema only exposes invoice_date and total_amount
        assert hasattr(res, "invoice_date")
        assert hasattr(res, "total_amount")
        assert not hasattr(res, "vendor_name")
        assert not hasattr(res, "invoice_number")

    def test_dict_input_contract_and_dict_output(self):
        """Verify the exact input and output contract specified for Step 12:

        Input:
        {
            "invoice_date": "05/09/2026",
            "total_amount": "₹25,500"
        }
        Output:
        {
            "invoice_date": {
                "original_value": "05/09/2026",
                "normalized_value": "2026-09-05",
                "success": True,
                "error": None
            },
            "total_amount": {
                "original_value": "₹25,500",
                "normalized_value": "25500.00",
                "success": True,
                "error": None
            },
            "success": True,
            "errors": []
        }
        """
        extracted_input = {
            "invoice_date": "05/09/2026",
            "total_amount": "₹25,500",
        }
        res = InvoiceNormalizer.normalize_invoice(extracted_input)
        assert res.success is True

        output_dict = res.to_dict()
        expected_output = {
            "invoice_date": {
                "original_value": "05/09/2026",
                "normalized_value": "2026-09-05",
                "success": True,
                "error": None,
            },
            "total_amount": {
                "original_value": "₹25,500",
                "normalized_value": "25500.00",
                "success": True,
                "error": None,
            },
            "success": True,
            "errors": [],
        }
        assert output_dict == expected_output

    def test_class_instance_and_classmethod_invocations(self):
        """Verify InvoiceNormalizer works both via classmethods and as an instantiated service."""
        # Classmethod invocation
        res1 = InvoiceNormalizer.normalize_invoice(
            {"invoice_date": "05/09/2026", "total_amount": "₹25,500"}
        )
        assert res1.success is True

        # Instance invocation
        normalizer = InvoiceNormalizer()
        res2 = normalizer.normalize_invoice(
            {"invoice_date": "05/09/2026", "total_amount": "₹25,500"}
        )
        assert res2.success is True
        assert res2.invoice_date.normalized_value == "2026-09-05"
        assert res2.total_amount.normalized_value == "25500.00"

    def test_reconciliation_field_objects_input(self):
        """Verify acceptance of objects containing ExtractedField-like structures (with .value)."""
        class DummyField:
            def __init__(self, value):
                self.value = value

        class DummyExtractionResult:
            def __init__(self, date_val, amount_val):
                self.invoice_date = DummyField(date_val)
                self.total_amount = DummyField(amount_val)

        obj = DummyExtractionResult("05/09/2026", "Rs. 25,500")
        res = InvoiceNormalizer.normalize_invoice(obj)
        assert res.success is True
        assert res.invoice_date.normalized_value == "2026-09-05"
        assert res.total_amount.normalized_value == "25500.00"

    def test_null_missing_values_handled_explicitly(self):
        """Verify that missing fields (None) succeed without error:

        {
            "original_value": None,
            "normalized_value": None,
            "success": True,
            "error": None
        }
        while malformed values fail with success=False.
        """
        res = InvoiceNormalizer.normalize_invoice(
            {"invoice_date": None, "total_amount": "25,500.00"}
        )
        assert res.success is True
        assert res.invoice_date.original_value is None
        assert res.invoice_date.normalized_value is None
        assert res.invoice_date.success is True
        assert res.invoice_date.error is None
        assert res.total_amount.normalized_value == "25500.00"

        # Both missing
        res_both_none = InvoiceNormalizer.normalize_invoice(
            {"invoice_date": None, "total_amount": None}
        )
        assert res_both_none.success is True
        assert res_both_none.invoice_date.original_value is None
        assert res_both_none.invoice_date.normalized_value is None
        assert res_both_none.total_amount.original_value is None
        assert res_both_none.total_amount.normalized_value is None
        assert len(res_both_none.errors) == 0


