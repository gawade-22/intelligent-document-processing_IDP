"""Invoice validation service for Intelligent Document Processing (IDP).

This service performs deterministic, rule-based validation on core invoice fields:
1. Vendor Name: Required, non-empty.
2. Invoice Number: Required, non-empty.
3. Invoice Date: Required, valid calendar date (YYYY-MM-DD).
4. Total Amount: Required, numeric, strictly greater than 0.

Independent of OCR, LLM, database persistence, and FastAPI routes.
"""

import datetime
from decimal import Decimal, InvalidOperation
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from app.schemas.validation import ValidationResult

logger = logging.getLogger(__name__)


class InvoiceValidator:
    """Service to validate extracted and normalized invoice fields against core business rules."""

    @classmethod
    def validate_vendor_name(cls, value: Optional[str]) -> Tuple[bool, Optional[str]]:
        """Validate that Vendor Name is present and non-empty.

        Rule 1:
        - Must be present (not None).
        - Must contain non-whitespace characters.
        """
        if value is None or not str(value).strip():
            return False, "Vendor Name is required"
        return True, None

    @classmethod
    def validate_invoice_number(cls, value: Optional[str]) -> Tuple[bool, Optional[str]]:
        """Validate that Invoice Number is present and non-empty.

        Rule 2:
        - Must be present (not None).
        - Must contain non-whitespace characters.
        """
        if value is None or not str(value).strip():
            return False, "Invoice Number is required"
        return True, None

    @classmethod
    def validate_invoice_date(cls, value: Optional[Union[str, datetime.date]]) -> Tuple[bool, Optional[str]]:
        """Validate that Invoice Date is present and represents a valid calendar date.

        Rule 3:
        - Must be present.
        - Must be a valid ISO format date (YYYY-MM-DD) or valid datetime.date object.
        - Rejects invalid dates such as 2026-02-30 or non-date strings.
        """
        if value is None:
            return False, "Invoice Date is required"

        if isinstance(value, datetime.date):
            return True, None

        trimmed = str(value).strip()
        if not trimmed:
            return False, "Invoice Date is required"

        try:
            # Parse ISO formatted date string (YYYY-MM-DD)
            datetime.date.fromisoformat(trimmed)
            return True, None
        except ValueError:
            pass

        # Try alternative standard parsing if not strictly ISO
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                datetime.datetime.strptime(trimmed, fmt).date()
                return True, None
            except ValueError:
                continue

        # Also attempt normalization check for textual / international dates
        try:
            from app.services.normalizer import InvoiceNormalizer
            norm = InvoiceNormalizer.normalize_date(trimmed)
            if norm.success and norm.normalized_value:
                return True, None
        except Exception:
            pass

        return False, f"Invoice Date is invalid: '{value}'"

    @classmethod
    def validate_total_amount(cls, value: Any) -> Tuple[bool, Optional[str]]:
        """Validate that Total Amount is present, numeric, and strictly greater than 0.

        Rule 4:
        - Must be present (not None).
        - Must be numeric.
        - Must be strictly greater than 0 (> 0).
        """
        if value is None:
            return False, "Total Amount is required"

        trimmed = str(value).strip()
        if not trimmed:
            return False, "Total Amount is required"

        # Safely convert to Decimal for exact numeric checking
        cleaned_num = trimmed.replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "").strip()
        try:
            amount_decimal = Decimal(cleaned_num)
        except (InvalidOperation, ValueError):
            return False, f"Total Amount must be a valid number: '{value}'"

        if amount_decimal <= Decimal("0"):
            return False, "Total Amount must be greater than 0"

        return True, None

    @classmethod
    def _extract_field_value(cls, field: Any) -> Any:
        """Extract underlying primitive value from string, ExtractedField, or NormalizedField."""
        if field is None:
            return None
        if isinstance(field, (str, int, float, Decimal, datetime.date)):
            return field
        if hasattr(field, "normalized_value") and getattr(field, "normalized_value") is not None:
            return getattr(field, "normalized_value")
        if hasattr(field, "value"):
            return getattr(field, "value")
        if hasattr(field, "original_value"):
            return getattr(field, "original_value")
        if isinstance(field, dict):
            if "normalized_value" in field and field["normalized_value"] is not None:
                return field["normalized_value"]
            if "value" in field and field["value"] is not None:
                return field["value"]
            if "original_value" in field:
                return field["original_value"]
        return field

    @classmethod
    def validate_invoice(
        cls,
        data: Optional[Union[dict, Any]] = None,
        *,
        vendor_name: Optional[Any] = None,
        invoice_number: Optional[Any] = None,
        invoice_date: Optional[Any] = None,
        total_amount: Optional[Any] = None,
        **kwargs,
    ) -> ValidationResult:
        """Validate an invoice across all four core business rules.

        Accepts either:
        1. A dictionary: `validate_invoice({"vendor_name": "...", "total_amount": "..."})`
        2. An extraction / normalization result object.
        3. Direct keyword arguments: `validate_invoice(vendor_name="...", ...)`
        """
        val_vendor = vendor_name
        val_number = invoice_number
        val_date = invoice_date
        val_amount = total_amount

        if isinstance(data, dict):
            if val_vendor is None:
                val_vendor = data.get("vendor_name")
            if val_number is None:
                val_number = data.get("invoice_number")
            if val_date is None:
                val_date = data.get("invoice_date")
            if val_amount is None:
                val_amount = data.get("total_amount")
        elif data is not None and not isinstance(data, str):
            if val_vendor is None and hasattr(data, "vendor_name"):
                val_vendor = getattr(data, "vendor_name")
            if val_number is None and hasattr(data, "invoice_number"):
                val_number = getattr(data, "invoice_number")
            if val_date is None and hasattr(data, "invoice_date"):
                val_date = getattr(data, "invoice_date")
            if val_amount is None and hasattr(data, "total_amount"):
                val_amount = getattr(data, "total_amount")

        # Extract unwrapped values
        clean_vendor = cls._extract_field_value(val_vendor)
        clean_number = cls._extract_field_value(val_number)
        clean_date = cls._extract_field_value(val_date)
        clean_amount = cls._extract_field_value(val_amount)

        errors: List[str] = []
        field_errors: Dict[str, str] = {}

        # 1. Vendor Name
        v_ok, v_err = cls.validate_vendor_name(clean_vendor)
        if not v_ok and v_err:
            errors.append(v_err)
            field_errors["vendor_name"] = v_err

        # 2. Invoice Number
        n_ok, n_err = cls.validate_invoice_number(clean_number)
        if not n_ok and n_err:
            errors.append(n_err)
            field_errors["invoice_number"] = n_err

        # 3. Invoice Date
        d_ok, d_err = cls.validate_invoice_date(clean_date)
        if not d_ok and d_err:
            errors.append(d_err)
            field_errors["invoice_date"] = d_err

        # 4. Total Amount
        a_ok, a_err = cls.validate_total_amount(clean_amount)
        if not a_ok and a_err:
            errors.append(a_err)
            field_errors["total_amount"] = a_err

        is_valid = len(errors) == 0

        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            field_errors=field_errors,
        )


# Module-level convenience functions
validate_vendor_name = InvoiceValidator.validate_vendor_name
validate_invoice_number = InvoiceValidator.validate_invoice_number
validate_invoice_date = InvoiceValidator.validate_invoice_date
validate_total_amount = InvoiceValidator.validate_total_amount
validate_invoice = InvoiceValidator.validate_invoice
