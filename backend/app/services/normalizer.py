"""Data normalization service for Intelligent Document Processing (IDP).

This service converts extracted invoice values (specifically `invoice_date` and `total_amount`)
into standardized, machine-readable formats while strictly preserving original extracted values.

Design Principles:
1. Field Isolation: Only normalizes `invoice_date` and `total_amount`. All other fields
   (vendor_name, invoice_number, GSTIN, line items, etc.) are left untouched.
2. Separation of Concerns: Independent of OCR, LLM, DB persistence, HITL, or validation.
3. Date Ambiguity Policy: Strictly interprets ambiguous numeric dates (e.g. `05/09/2026`) as
   `DD/MM/YYYY` (`2026-09-05`) unless explicitly formatted as US textual month (e.g. `September 5, 2026`).
4. Financial Precision: Uses Python's `Decimal` module with half-up rounding to 2 decimal places,
   avoiding binary floating-point inaccuracies.
5. No Over-Cleaning: Validates structural integrity and refuses to guess or silently accept
   malformed values (e.g., `₹abc`, `12.34.56`, `31/02/2026`).
"""

import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import logging
import re
from typing import Any, Optional, Union

from app.schemas.normalization import InvoiceNormalizationResult, NormalizedField

logger = logging.getLogger(__name__)

# Month name mapping for English textual dates
MONTH_NAME_MAP = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

# Regex patterns for date extraction & cleaning
DATE_LABEL_PREFIX = re.compile(
    r"^(?:invoice\s*date|inv\s*date|bill\s*date|date)\s*[:\-]?\s*",
    re.IGNORECASE,
)
TRAILING_TIMESTAMP = re.compile(
    r"[T\s]+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap][Mm])?(?:\s*Z|[+-]\d{2}:?\d{2})?$"
)

# 1. ISO: YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD
ISO_DATE_PATTERN = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$")

# 2. Textual month with day first: 5 September 2026, 05-Sep-2026, 5th Sep 2026, 05.Sep.2026
DAY_TEXT_MONTH_PATTERN = re.compile(
    r"^(\d{1,2})(?:st|nd|rd|th)?[-/.\s]+([a-zA-Z]+)[,-/.\s]+(\d{4}|\d{2})$"
)

# 3. Textual month with month first: September 5, 2026, Sep 5, 2026, September 05 2026
MONTH_TEXT_DAY_PATTERN = re.compile(
    r"^([a-zA-Z]+)[-/.\s]+(\d{1,2})(?:st|nd|rd|th)?(?:,)?[-/.\s]+(\d{4}|\d{2})$"
)

# 4. Strict Day-first numeric: DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY, D/M/YYYY
# Per project specification: 05/09/2026 MUST be interpreted as DD/MM/YYYY -> 2026-09-05.
DAY_FIRST_NUMERIC_PATTERN = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})$")

# Regex patterns for currency and total amount
AMOUNT_LABEL_PREFIX = re.compile(
    r"^(?:grand\s+total|total\s+amount|total|net\s+amount|amount)\s*[:\-]?\s*",
    re.IGNORECASE,
)
CURRENCY_PREFIX = re.compile(
    r"^(?:₹|rs\.?|inr|usd|\$|eur|€|gbp|£)\s*",
    re.IGNORECASE,
)
CURRENCY_SUFFIX = re.compile(
    r"\s*(?:/[-–—]|(?:₹|rs\.?|inr|usd|\$|eur|€|gbp|£))(?:\s*/[-–—])?$",
    re.IGNORECASE,
)

# Numeric format patterns (validating comma groupings and decimal places):
# Western: 123,456,789.00 or 1,234.50 or 25,500.00
WESTERN_AMOUNT_PATTERN = re.compile(r"^[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?$")
# Indian: 12,34,56,789.00 or 1,23,456.00 or 25,500.00
INDIAN_AMOUNT_PATTERN = re.compile(r"^[+-]?\d{1,2}(?:,\d{2})*,\d{3}(?:\.\d+)?$")
# Plain integer or decimal without commas: 25500 or 25500.00
PLAIN_AMOUNT_PATTERN = re.compile(r"^[+-]?\d+(?:\.\d+)?$")


class InvoiceNormalizer:
    """Service to normalize extracted invoice values into clean machine-readable representations."""

    @classmethod
    def normalize_date(cls, date_str: Optional[str]) -> NormalizedField:
        """Normalize invoice date into standard ISO YYYY-MM-DD format.

        Date Ambiguity Policy:
        ----------------------
        Ambiguous numeric date formats (e.g. `05/09/2026` or `05-09-2026`) are strictly
        parsed as `DD/MM/YYYY` (Day: 05, Month: 09, Year: 2026) -> `2026-09-05`.
        They are NEVER interpreted as `MM/DD/YYYY` unless explicitly written with US textual
        month naming (e.g. `September 5, 2026`).

        Invalid dates (e.g. `31/02/2026`, `99/99/2026`, `not a date`) are rejected with
        success=False and an informative error message.
        """
        if date_str is None:
            return NormalizedField(
                original_value=None,
                normalized_value=None,
                success=True,
                error=None,
            )

        trimmed = date_str.strip()
        if not trimmed:
            return NormalizedField(
                original_value=date_str,
                normalized_value=None,
                success=False,
                error="Date value is empty",
            )

        # Remove common label prefix if present, e.g., "Invoice Date: 05/09/2026"
        cleaned = DATE_LABEL_PREFIX.sub("", trimmed).strip()
        # Remove trailing timestamp if present, e.g., "05/09/2026 14:30:00"
        cleaned = TRAILING_TIMESTAMP.sub("", cleaned).strip()

        if not cleaned:
            return NormalizedField(
                original_value=date_str,
                normalized_value=None,
                success=False,
                error="Date value contains no date digits or tokens",
            )

        year: Optional[int] = None
        month: Optional[int] = None
        day: Optional[int] = None

        # Pattern 1: ISO format (YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD)
        iso_match = ISO_DATE_PATTERN.match(cleaned)
        if iso_match:
            year = int(iso_match.group(1))
            month = int(iso_match.group(2))
            day = int(iso_match.group(3))

        # Pattern 2: Day-first text month (e.g. 5 September 2026, 05-Sep-2026, 5th Sep 2026)
        if year is None:
            day_text_match = DAY_TEXT_MONTH_PATTERN.match(cleaned)
            if day_text_match:
                day_val = int(day_text_match.group(1))
                month_name = day_text_match.group(2).lower()
                year_val = int(day_text_match.group(3))
                if month_name in MONTH_NAME_MAP:
                    day = day_val
                    month = MONTH_NAME_MAP[month_name]
                    year = year_val + 2000 if year_val < 100 else year_val
                else:
                    return NormalizedField(
                        original_value=date_str,
                        normalized_value=None,
                        success=False,
                        error=f"Unrecognized month name: '{day_text_match.group(2)}'",
                    )

        # Pattern 3: Month-first text month (e.g. September 5, 2026, Sep 5 2026)
        if year is None:
            month_text_match = MONTH_TEXT_DAY_PATTERN.match(cleaned)
            if month_text_match:
                month_name = month_text_match.group(1).lower()
                day_val = int(month_text_match.group(2))
                year_val = int(month_text_match.group(3))
                if month_name in MONTH_NAME_MAP:
                    month = MONTH_NAME_MAP[month_name]
                    day = day_val
                    year = year_val + 2000 if year_val < 100 else year_val
                else:
                    return NormalizedField(
                        original_value=date_str,
                        normalized_value=None,
                        success=False,
                        error=f"Unrecognized month name: '{month_text_match.group(1)}'",
                    )

        # Pattern 4: Strict Day-first numeric format (DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY)
        if year is None:
            day_first_match = DAY_FIRST_NUMERIC_PATTERN.match(cleaned)
            if day_first_match:
                day = int(day_first_match.group(1))
                month = int(day_first_match.group(2))
                year_val = int(day_first_match.group(3))
                year = year_val + 2000 if year_val < 100 else year_val

        # If no pattern matched, fail safely
        if year is None or month is None or day is None:
            return NormalizedField(
                original_value=date_str,
                normalized_value=None,
                success=False,
                error=f"Unrecognized or unsupported date format: '{date_str}'",
            )

        # Validate calendar reality using datetime.date
        try:
            parsed_date = datetime.date(year, month, day)
        except ValueError as err:
            return NormalizedField(
                original_value=date_str,
                normalized_value=None,
                success=False,
                error=f"Invalid calendar date: {err}",
            )

        normalized_iso = parsed_date.strftime("%Y-%m-%d")
        return NormalizedField(
            original_value=date_str,
            normalized_value=normalized_iso,
            success=True,
            error=None,
        )

    @classmethod
    def normalize_amount(cls, amount_str: Optional[str]) -> NormalizedField:
        """Normalize extracted total amount into standard 2-decimal financial string.

        Financial Precision Policy:
        --------------------------
        Uses Python's `Decimal` module with `ROUND_HALF_UP` quantized to `0.01`
        to eliminate binary floating-point rounding errors.

        Supports:
        - Currency symbols and codes: `₹`, `Rs.`, `Rs`, `INR`, `$`, `€`, `£`, etc.
        - Western thousands groupings: `125,000`, `1,250,000.75`
        - Indian lakh/crore groupings: `1,25,000`, `12,50,000.75`
        - Grouping-free numbers: `25500`, `25500.00`
        - Trailing payment markers: `25500/-`

        Safeguards:
        - Does NOT blindly strip all non-numeric characters.
        - Rejects malformed values (e.g. `₹abc`, `25,50,00,xyz`, `12.34.56`, `unknown`, `₹`).
        """
        if amount_str is None:
            return NormalizedField(
                original_value=None,
                normalized_value=None,
                success=True,
                error=None,
            )

        trimmed = amount_str.strip()
        if not trimmed:
            return NormalizedField(
                original_value=amount_str,
                normalized_value=None,
                success=False,
                error="Amount value is empty",
            )

        # Remove label prefixes like "Grand Total:", "Total Amount:", "Total:"
        cleaned = AMOUNT_LABEL_PREFIX.sub("", trimmed).strip()

        # Handle accounting parentheses format: (500.00) or (₹25,500)
        is_negative = False
        if cleaned.startswith("(") and cleaned.endswith(")"):
            is_negative = True
            cleaned = cleaned[1:-1].strip()

        # Track explicit negative signs (before and/or after currency symbol)
        minus_count = 0
        if cleaned.startswith("-"):
            minus_count += 1
            cleaned = cleaned[1:].strip()
        elif cleaned.startswith("+"):
            cleaned = cleaned[1:].strip()

        # Remove currency markers from prefix (e.g. "₹", "Rs.", "INR")
        cleaned = CURRENCY_PREFIX.sub("", cleaned).strip()

        # Check for negative sign after currency symbol (e.g. ₹-500.00 or Rs. -500.50)
        if cleaned.startswith("-"):
            minus_count += 1
            cleaned = cleaned[1:].strip()
        elif cleaned.startswith("+"):
            cleaned = cleaned[1:].strip()

        # Remove currency markers or "/-" from suffix (e.g. "/-", "INR")
        cleaned = CURRENCY_SUFFIX.sub("", cleaned).strip()

        # Reject ambiguous or malformed formats like -₹-500 (multiple minus signs)
        if minus_count > 1:
            return NormalizedField(
                original_value=amount_str,
                normalized_value=None,
                success=False,
                error=f"Ambiguous or malformed negative format: '{amount_str}'",
            )
        if minus_count == 1:
            is_negative = True

        if not cleaned:
            return NormalizedField(
                original_value=amount_str,
                normalized_value=None,
                success=False,
                error="Invalid numeric amount: missing numeric digits",
            )

        # Validate structural integrity against valid numeric patterns
        is_western = WESTERN_AMOUNT_PATTERN.match(cleaned)
        is_indian = INDIAN_AMOUNT_PATTERN.match(cleaned)
        is_plain = PLAIN_AMOUNT_PATTERN.match(cleaned)

        if not (is_western or is_indian or is_plain):
            return NormalizedField(
                original_value=amount_str,
                normalized_value=None,
                success=False,
                error=f"Invalid numeric amount: '{amount_str}' does not conform to a valid numeric format",
            )

        # Safely remove thousands separators (commas)
        numeric_str = cleaned.replace(",", "")

        try:
            decimal_val = Decimal(numeric_str).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if is_negative and decimal_val > 0:
                decimal_val = -decimal_val
            normalized_str = f"{decimal_val:.2f}"
            return NormalizedField(
                original_value=amount_str,
                normalized_value=normalized_str,
                success=True,
                error=None,
            )
        except (InvalidOperation, ValueError) as err:
            return NormalizedField(
                original_value=amount_str,
                normalized_value=None,
                success=False,
                error=f"Decimal conversion failed: {err}",
            )

    @classmethod
    def _extract_raw_str(cls, val: Any) -> Optional[str]:
        """Extract underlying string value from a string, ExtractedField, or dictionary."""
        if val is None:
            return None
        if isinstance(val, str):
            return val
        if hasattr(val, "value"):
            inner = getattr(val, "value")
            return str(inner) if inner is not None else None
        if isinstance(val, dict):
            if "value" in val:
                inner = val["value"]
                return str(inner) if inner is not None else None
            if "original_value" in val:
                inner = val["original_value"]
                return str(inner) if inner is not None else None
            if "normalized_value" in val:
                inner = val["normalized_value"]
                return str(inner) if inner is not None else None
        return str(val)

    @classmethod
    def normalize_invoice(
        cls,
        data: Optional[Union[dict, Any]] = None,
        *,
        invoice_date: Optional[Union[str, Any]] = None,
        total_amount: Optional[Union[str, Any]] = None,
        **kwargs,
    ) -> InvoiceNormalizationResult:
        """Normalize invoice date and total amount fields.

        Input Contract:
        Accepts:
        1. A dictionary matching extraction/reconciliation outputs:
           e.g. `normalize_invoice({"invoice_date": "05/09/2026", "total_amount": "₹25,500"})`
        2. Direct keyword arguments:
           e.g. `normalize_invoice(invoice_date="05/09/2026", total_amount="₹25,500")`
        3. Extraction result objects (e.g. InvoiceExtractionResult) containing fields with `.value`.

        Explicitly ignores any other fields (vendor_name, invoice_number, GSTIN, etc.)
        as per normalization isolation requirements.
        """
        raw_date: Optional[str] = None
        raw_amount: Optional[str] = None

        if isinstance(data, dict):
            raw_date = cls._extract_raw_str(data.get("invoice_date"))
            raw_amount = cls._extract_raw_str(data.get("total_amount"))
        elif data is not None and not isinstance(data, str):
            if hasattr(data, "invoice_date"):
                raw_date = cls._extract_raw_str(getattr(data, "invoice_date"))
            if hasattr(data, "total_amount"):
                raw_amount = cls._extract_raw_str(getattr(data, "total_amount"))
        elif isinstance(data, str) and invoice_date is None:
            raw_date = data

        if invoice_date is not None:
            raw_date = cls._extract_raw_str(invoice_date)
        if total_amount is not None:
            raw_amount = cls._extract_raw_str(total_amount)

        norm_date = cls.normalize_date(raw_date)
        norm_amount = cls.normalize_amount(raw_amount)

        errors: list[str] = []
        if not norm_date.success and norm_date.error:
            errors.append(f"invoice_date: {norm_date.error}")
        if not norm_amount.success and norm_amount.error:
            errors.append(f"total_amount: {norm_amount.error}")

        overall_success = norm_date.success and norm_amount.success

        return InvoiceNormalizationResult(
            success=overall_success,
            invoice_date=norm_date,
            total_amount=norm_amount,
            errors=errors,
        )


# Backward compatibility alias
InvoiceDataNormalizer = InvoiceNormalizer

# Module-level convenience functions
normalize_date = InvoiceNormalizer.normalize_date
normalize_amount = InvoiceNormalizer.normalize_amount
normalize_invoice = InvoiceNormalizer.normalize_invoice
