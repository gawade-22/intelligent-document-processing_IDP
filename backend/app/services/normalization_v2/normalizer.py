"""
Generic Typed Normalization Service.
Normalizes extracted values according to their declared schema data type:
- date: Standardized ISO YYYY-MM-DD (handles DD/MM vs MM/DD, month names, lakh dates)
- money: Clean floating-point value (handles $, €, £, ₹, lakh commas, European decimals)
- number, percent, email, phone, id, bool, string, text
Zero hardcoded per-document-type logic.
"""

from datetime import datetime
import logging
import re
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


class GenericDataNormalizer:
    """Document-agnostic data normalizer based purely on data types and locale heuristics."""

    MONTH_MAP = {
        "jan": 1, "january": 1,
        "feb": 2, "february": 2,
        "mar": 3, "march": 3,
        "apr": 4, "april": 4,
        "may": 5,
        "jun": 6, "june": 6,
        "jul": 7, "july": 7,
        "aug": 8, "august": 8,
        "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10,
        "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }

    def normalize_date(self, val: Any) -> Optional[str]:
        """Converts arbitrary date representation into ISO YYYY-MM-DD."""
        if val is None:
            return None
        s = str(val).strip()
        if not s:
            return None

        # 1. Direct ISO match: YYYY-MM-DD
        iso_match = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$", s)
        if iso_match:
            y, m, d = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
            try:
                return datetime(y, m, d).strftime("%Y-%m-%d")
            except ValueError:
                pass

        # 2. Text Month: "14 August 2024", "August 14, 2024", "14-Aug-2024"
        text_month_match = re.search(
            r"\b(\d{1,2})[-/\s]+([A-Za-z]+)[-/\s,]+(\d{2,4})\b|\b([A-Za-z]+)[-/\s]+(\d{1,2})[-/\s,]+(\d{2,4})\b",
            s,
        )
        if text_month_match:
            g = text_month_match.groups()
            if g[0]:
                d_str, m_str, y_str = g[0], g[1], g[2]
            else:
                m_str, d_str, y_str = g[3], g[4], g[5]

            m_lower = m_str.lower()
            if m_lower in self.MONTH_MAP:
                month_num = self.MONTH_MAP[m_lower]
                year_num = int(y_str)
                if year_num < 100:
                    year_num += 2000
                day_num = int(d_str)
                try:
                    return datetime(year_num, month_num, day_num).strftime("%Y-%m-%d")
                except ValueError:
                    pass

        # 3. Numeric: DD/MM/YYYY or MM/DD/YYYY
        num_match = re.search(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b", s)
        if num_match:
            p1, p2, p3 = int(num_match.group(1)), int(num_match.group(2)), int(num_match.group(3))
            year = p3 if p3 >= 100 else p3 + 2000

            # Heuristic: if p1 > 12, it must be DD/MM/YYYY
            if p1 > 12 and 1 <= p2 <= 12:
                try:
                    return datetime(year, p2, p1).strftime("%Y-%m-%d")
                except ValueError:
                    pass
            # Heuristic: if p2 > 12, it must be MM/DD/YYYY
            elif p2 > 12 and 1 <= p1 <= 12:
                try:
                    return datetime(year, p1, p2).strftime("%Y-%m-%d")
                except ValueError:
                    pass
            # Default to DD/MM/YYYY (international standard)
            elif 1 <= p1 <= 31 and 1 <= p2 <= 12:
                try:
                    return datetime(year, p2, p1).strftime("%Y-%m-%d")
                except ValueError:
                    pass

        return s

    def normalize_money(self, val: Any) -> Optional[float]:
        """Normalizes currency strings into standard float amounts."""
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return round(float(val), 2)

        s = str(val).strip()
        if not s:
            return None

        # Remove currency symbols and non-numeric characters, preserving digits, commas, dots, minus
        cleaned = re.sub(r"[^\d.,\-]", "", s).strip()
        if not cleaned:
            return None

        # Check for European format: 1.250,50 (dot as thousand, comma as decimal)
        if re.search(r"^\d{1,3}(?:\.\d{3})+,\d{2}$", cleaned) or ("," in cleaned and "." in cleaned and cleaned.rfind(",") > cleaned.rfind(".")):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            # Anglo / Indian format: 1,250.50 or 1,25,000.50
            cleaned = cleaned.replace(",", "")


        try:
            return round(float(cleaned), 2)
        except ValueError:
            return None

    def normalize_number(self, val: Any) -> Optional[float]:
        """Parses integers and floats, stripping commas."""
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).replace(",", "").strip()
        try:
            return float(s)
        except ValueError:
            return None

    def normalize_percent(self, val: Any) -> Optional[float]:
        """Extracts percentage float (e.g. '18%' or '0.18' -> 18.0)."""
        if val is None:
            return None
        s = str(val).replace("%", "").strip()
        num = self.normalize_number(s)
        if num is not None:
            # If formatted as decimal fraction 0.18 -> 18.0
            if 0 < num < 1.0:
                num = round(num * 100, 2)
            return round(num, 2)
        return None

    def normalize_email(self, val: Any) -> Optional[str]:
        """Cleans and lowercases email address."""
        if val is None:
            return None
        s = str(val).strip().lower()
        match = re.search(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", s)
        return match.group(0) if match else s

    def normalize_phone(self, val: Any) -> Optional[str]:
        """Extracts standard phone number representation."""
        if val is None:
            return None
        s = str(val).strip()
        digits = re.sub(r"[^\d+]", "", s)
        return digits if len(digits) >= 7 else s

    def normalize_bool(self, val: Any) -> Optional[bool]:
        """Normalizes boolean indicators."""
        if val is None:
            return None
        if isinstance(val, bool):
            return val
        s = str(val).strip().lower()
        if s in ("true", "yes", "1", "y", "t", "verified", "passed"):
            return True
        if s in ("false", "no", "0", "n", "f", "failed"):
            return False
        return None

    def normalize_id(self, val: Any) -> Optional[str]:
        """Normalizes identifiers while preserving leading zeros."""
        if val is None:
            return None
        s = str(val).strip()
        # Remove surrounding punctuation / quotes
        s = re.sub(r"^[\"\'#:]+|[\"\'\.]+$", "", s).strip()
        return s

    def normalize_field(
        self,
        raw_value: Any,
        data_type: str,
    ) -> Tuple[Any, bool, Optional[str]]:
        """
        Normalizes a field value according to its declared data_type.
        Returns:
            (normalized_value, is_valid, error_message)
        """
        if raw_value is None or str(raw_value).strip() == "":
            return None, True, None

        dtype = (data_type or "string").lower().strip()

        try:
            if dtype == "date":
                norm = self.normalize_date(raw_value)
                is_valid = bool(norm and re.match(r"^\d{4}-\d{2}-\d{2}$", str(norm)))
                err = None if is_valid else f"Value '{raw_value}' could not be normalized to ISO date YYYY-MM-DD"
                return norm, is_valid, err

            elif dtype == "money":
                norm = self.normalize_money(raw_value)
                is_valid = norm is not None
                err = None if is_valid else f"Value '{raw_value}' could not be parsed as currency amount"
                return norm, is_valid, err

            elif dtype == "number":
                norm = self.normalize_number(raw_value)
                is_valid = norm is not None
                err = None if is_valid else f"Value '{raw_value}' could not be parsed as a number"
                return norm, is_valid, err

            elif dtype == "percent":
                norm = self.normalize_percent(raw_value)
                is_valid = norm is not None
                err = None if is_valid else f"Value '{raw_value}' could not be parsed as a percentage"
                return norm, is_valid, err

            elif dtype == "email":
                norm = self.normalize_email(raw_value)
                is_valid = bool(norm and "@" in norm and "." in norm)
                err = None if is_valid else f"Value '{raw_value}' is not a valid email address"
                return norm, is_valid, err

            elif dtype == "phone":
                norm = self.normalize_phone(raw_value)
                is_valid = bool(norm and len(re.sub(r"\D", "", norm)) >= 7)
                err = None if is_valid else f"Value '{raw_value}' does not have sufficient phone digits"
                return norm, is_valid, err

            elif dtype == "bool":
                norm = self.normalize_bool(raw_value)
                is_valid = norm is not None
                err = None if is_valid else f"Value '{raw_value}' could not be parsed as boolean"
                return norm, is_valid, err

            elif dtype == "id":
                norm = self.normalize_id(raw_value)
                return norm, True, None

            else:
                # string, text
                return str(raw_value).strip(), True, None

        except Exception as exc:
            logger.warning(f"Normalization error for dtype={dtype}, value={raw_value}: {exc}")
            return raw_value, False, str(exc)


# Singleton instance
generic_normalizer = GenericDataNormalizer()
