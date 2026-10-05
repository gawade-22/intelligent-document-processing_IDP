"""
Safe Deterministic Validation DSL Engine.
Executes declarative cross-field validation rules stored with DocumentSchema.
Guarantees deterministic execution in Python with ZERO unsafe eval or code execution.
"""

from datetime import datetime
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.universal import DynamicFieldResult, DynamicTableResult
from app.services.normalization_v2.normalizer import generic_normalizer

logger = logging.getLogger(__name__)


class DSLValidationEngine:
    """Executes safe, declarative business validation rules across fields and tables."""

    def _get_field(self, key: str, fields_map: Dict[str, DynamicFieldResult]) -> Optional[DynamicFieldResult]:
        """Looks up a field by exact key or canonical suffix."""
        if key in fields_map:
            return fields_map[key]
        for f_key, f in fields_map.items():
            if f_key.endswith(f".{key}") or f.label.lower().replace(" ", "_") == key:
                return f
        return None

    def _resolve_numeric_term(
        self,
        term: str,
        fields_map: Dict[str, DynamicFieldResult],
        tables_map: Dict[str, DynamicTableResult],
    ) -> Optional[float]:
        """Resolves a numeric term which can be a field key or a table column (e.g. 'items.amount')."""
        clean_term = term.replace("fields.", "").replace("tables.", "").strip()

        # 1. Check if the term directly matches a known field (including dotted keys like 'financial.tax_amount')
        field = self._get_field(clean_term, fields_map)
        if field is not None:
            return generic_normalizer.normalize_money(field.value) if field.value is not None else None

        # 2. Check if table column sum: "items.amount" -> table="items", col="amount"
        if "." in clean_term:
            t_name, col_name = clean_term.split(".", 1)
            tbl = tables_map.get(t_name)
            if not tbl or not tbl.headers or not tbl.rows:
                return 0.0

            # Find column index
            norm_col = col_name.lower().strip()
            col_idx = None
            for idx, h in enumerate(tbl.headers):
                if h.lower().strip() == norm_col or norm_col in h.lower():
                    col_idx = idx
                    break

            if col_idx is None:
                return 0.0

            total = 0.0
            for row in tbl.rows:
                if col_idx < len(row):
                    val_num = generic_normalizer.normalize_money(row[col_idx])
                    if val_num is not None:
                        total += val_num
            return total

        return None


    def evaluate_rules(
        self,
        rules: List[Dict[str, Any]],
        fields: List[DynamicFieldResult],
        tables: List[DynamicTableResult],
    ) -> List[Dict[str, Any]]:
        """
        Evaluates a list of validation rules across extracted fields and tables.
        Returns outcome records:
        [{"rule": "...", "target": "...", "status": "pass|fail", "severity": "fail|warn", "message": "..."}]
        """
        results: List[Dict[str, Any]] = []
        fields_map: Dict[str, DynamicFieldResult] = {f.key: f for f in fields}
        tables_map: Dict[str, DynamicTableResult] = {t.key: t for t in tables}

        for r in rules:
            if not isinstance(r, dict):
                continue
            rule_type = r.get("rule", "").strip()
            severity = r.get("severity", "fail")

            # -----------------------------------------------------------------
            # 1. sum_equals: target == sum(terms) +/- tolerance
            # -----------------------------------------------------------------
            if rule_type == "sum_equals":
                target_key = r.get("target")
                terms = r.get("terms", [])
                tolerance = float(r.get("tolerance", 0.05))

                target_field = self._get_field(target_key, fields_map)
                if not target_field or target_field.value is None:
                    continue

                target_val = generic_normalizer.normalize_money(target_field.value)
                if target_val is None:
                    continue

                term_sum = 0.0
                terms_found = False
                for t in terms:
                    term_val = self._resolve_numeric_term(t, fields_map, tables_map)
                    if term_val is not None:
                        term_sum += term_val
                        terms_found = True

                if terms_found:
                    diff = abs(target_val - term_sum)
                    passed = diff <= tolerance

                    if not passed:
                        # Check if invoice has additional components (discounts, shipping, fees, etc.)
                        adjusted_sum = term_sum
                        for f_k, f_obj in fields_map.items():
                            if f_obj.value is None:
                                continue
                            k_lower = f_k.lower()
                            lbl_lower = (f_obj.label or "").lower()
                            # Avoid double-counting terms already included in terms
                            if any(t in f_k for t in terms):
                                continue
                            val_m = generic_normalizer.normalize_money(f_obj.value)
                            if val_m is None or val_m == 0:
                                continue
                            if any(w in k_lower or w in lbl_lower for w in ("discount", "deduction", "rebate", "less")):
                                adjusted_sum -= val_m
                            elif any(w in k_lower or w in lbl_lower for w in ("shipping", "freight", "handling", "delivery", "postage", "fee", "charge")):
                                adjusted_sum += val_m
                            elif any(w in k_lower or w in lbl_lower for w in ("tax", "vat", "gst", "cess")):
                                if not any("tax" in t for t in terms):
                                    adjusted_sum += val_m

                        adj_diff = abs(target_val - adjusted_sum)
                        if adj_diff <= tolerance:
                            passed = True
                            term_sum = adjusted_sum
                            diff = adj_diff
                            msg = f"Sum check passed with invoice adjustments: total={target_val:.2f} matches net sum={term_sum:.2f} (diff={diff:.2f})"
                        else:
                            msg = f"Sum mismatch: target total={target_val:.2f} but terms sum={term_sum:.2f} (difference={diff:.2f}, tolerance={tolerance})"
                    else:
                        msg = f"Sum check passed: total={target_val:.2f} matches sum={term_sum:.2f} (diff={diff:.2f})"

                    results.append({
                        "rule": "sum_equals",
                        "target": target_key,
                        "status": "pass" if passed else "fail",
                        "severity": severity,
                        "message": msg,
                    })

            # -----------------------------------------------------------------
            # 2. running_balance: verifies ledger balance across table rows
            # -----------------------------------------------------------------
            elif rule_type == "running_balance":
                t_key = r.get("table", "transactions")
                tbl = tables_map.get(t_key)
                if not tbl or not tbl.rows:
                    continue

                # Locate columns: date, debit, credit, balance
                headers_norm = [h.lower().strip() for h in tbl.headers]
                debit_idx = next((i for i, h in enumerate(headers_norm) if "debit" in h or "withdrawal" in h), None)
                credit_idx = next((i for i, h in enumerate(headers_norm) if "credit" in h or "deposit" in h), None)
                bal_idx = next((i for i, h in enumerate(headers_norm) if "balance" in h), None)

                if bal_idx is not None and (debit_idx is not None or credit_idx is not None):
                    prev_bal = None
                    mismatches = 0
                    for row_idx, row in enumerate(tbl.rows):
                        if bal_idx < len(row):
                            cur_bal = generic_normalizer.normalize_money(row[bal_idx])
                            debit = generic_normalizer.normalize_money(row[debit_idx]) if debit_idx and debit_idx < len(row) else 0.0
                            credit = generic_normalizer.normalize_money(row[credit_idx]) if credit_idx and credit_idx < len(row) else 0.0

                            if prev_bal is not None and cur_bal is not None:
                                expected_bal = prev_bal + (credit or 0.0) - (debit or 0.0)
                                if abs(expected_bal - cur_bal) > 0.05:
                                    mismatches += 1
                            if cur_bal is not None:
                                prev_bal = cur_bal

                    passed = mismatches == 0
                    msg = (
                        f"Running balance verified across {len(tbl.rows)} transaction rows."
                        if passed
                        else f"Running balance verification found {mismatches} row mismatch(es)."
                    )
                    results.append({
                        "rule": "running_balance",
                        "target": t_key,
                        "status": "pass" if passed else "fail",
                        "severity": severity,
                        "message": msg,
                    })

            # -----------------------------------------------------------------
            # 3. date_order: earlier_date <= later_date
            # -----------------------------------------------------------------
            elif rule_type == "date_order":
                earlier_key = r.get("earlier")
                later_key = r.get("later")
                f_earlier = self._get_field(earlier_key, fields_map)
                f_later = self._get_field(later_key, fields_map)

                if f_earlier and f_later and f_earlier.value and f_later.value:
                    d_early = generic_normalizer.normalize_date(f_earlier.value)
                    d_late = generic_normalizer.normalize_date(f_later.value)

                    if d_early and d_late:
                        passed = d_early <= d_late
                        msg = (
                            f"Date sequence valid: {d_early} <= {d_late}"
                            if passed
                            else f"Chronological order violated: {earlier_key} ({d_early}) is after {later_key} ({d_late})"
                        )
                        results.append({
                            "rule": "date_order",
                            "target": earlier_key,
                            "status": "pass" if passed else "fail",
                            "severity": severity,
                            "message": msg,
                        })

            # -----------------------------------------------------------------
            # 4. in_range: min <= value <= max
            # -----------------------------------------------------------------
            elif rule_type == "in_range":
                val_key = r.get("value")
                f_target = self._get_field(val_key, fields_map)
                if f_target and f_target.value is not None:
                    target_num = generic_normalizer.normalize_number(f_target.value)
                    min_val = float(r["min"]) if "min" in r and r["min"] is not None else None
                    max_val = float(r["max"]) if "max" in r and r["max"] is not None else None

                    if target_num is not None:
                        passed = True
                        if min_val is not None and target_num < min_val:
                            passed = False
                        if max_val is not None and target_num > max_val:
                            passed = False

                        msg = (
                            f"Value {target_num} in valid range [{min_val}, {max_val}]"
                            if passed
                            else f"Value {target_num} outside range [{min_val}, {max_val}]"
                        )
                        results.append({
                            "rule": "in_range",
                            "target": val_key,
                            "status": "pass" if passed else "fail",
                            "severity": severity,
                            "message": msg,
                        })

            # -----------------------------------------------------------------
            # 5. regex_match: field matches pattern
            # -----------------------------------------------------------------
            elif rule_type == "regex_match":
                f_key = r.get("field")
                pattern = r.get("pattern")
                f_target = self._get_field(f_key, fields_map)
                if f_target and f_target.value and pattern:
                    passed = bool(re.search(pattern, str(f_target.value)))
                    msg = (
                        f"Field '{f_key}' matches pattern."
                        if passed
                        else f"Field '{f_key}' does not match pattern '{pattern}'"
                    )
                    results.append({
                        "rule": "regex_match",
                        "target": f_key,
                        "status": "pass" if passed else "fail",
                        "severity": severity,
                        "message": msg,
                    })

        return results


# Singleton instance
dsl_validation_engine = DSLValidationEngine()
