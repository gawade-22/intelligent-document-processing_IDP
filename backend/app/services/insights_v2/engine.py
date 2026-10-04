"""
Dynamic Schema-Driven Insights Engine.
Executes exact mathematical aggregations (sum, avg, min, max, count, trend)
over extracted tables and fields according to Schema Registry insight definitions.
Guarantees mathematical precision in code (never hallucinated LLM arithmetic).
Generates high-level analytic cards and business flags for the frontend dashboard.
"""

import logging
from typing import Any, Dict, List, Optional

from app.schemas.universal import DynamicFieldResult, DynamicInsightResult, DynamicTableResult
from app.services.normalization_v2.normalizer import generic_normalizer

logger = logging.getLogger(__name__)


class DynamicInsightsEngine:
    """Computes exact schema-driven and document-wide analytics and insights."""

    def _extract_column_numbers(
        self,
        table: DynamicTableResult,
        column_name: str,
    ) -> List[float]:
        """Extracts and parses float numbers from a specific column of a table."""
        if not table or not table.headers or not table.rows:
            return []

        col_norm = column_name.lower().strip()
        col_idx = None
        for idx, h in enumerate(table.headers):
            if h.lower().strip() == col_norm or col_norm in h.lower().strip():
                col_idx = idx
                break

        if col_idx is None:
            return []

        numbers: List[float] = []
        for row in table.rows:
            if col_idx < len(row):
                val = generic_normalizer.normalize_money(row[col_idx])
                if val is not None:
                    numbers.append(val)
        return numbers

    def generate_insights(
        self,
        definitions: List[Dict[str, Any]],
        fields: List[DynamicFieldResult],
        tables: List[DynamicTableResult],
        validation_results: List[Dict[str, Any]],
    ) -> List[DynamicInsightResult]:
        """
        Executes aggregations defined in the schema and appends generic document metrics and flags.
        """
        insights: List[DynamicInsightResult] = []
        tables_map = {t.key: t for t in tables}

        # ---------------------------------------------------------------------
        # 1. Schema-Driven Analytical Aggregations
        # ---------------------------------------------------------------------
        for d in definitions:
            if not isinstance(d, dict):
                continue
            ins_id = d.get("id", f"ins_{len(insights)}")
            title = d.get("title", "Insight Metric")
            kind = d.get("kind", "metric")
            agg = d.get("agg", "sum")
            t_key = d.get("table")
            col_name = d.get("column")

            computed_val = None

            if t_key and t_key in tables_map:
                tbl = tables_map[t_key]
                if agg == "count":
                    computed_val = len(tbl.rows)
                elif col_name:
                    nums = self._extract_column_numbers(tbl, col_name)
                    if nums:
                        if agg == "sum":
                            computed_val = round(sum(nums), 2)
                        elif agg == "avg":
                            computed_val = round(sum(nums) / len(nums), 2)
                        elif agg == "min":
                            computed_val = min(nums)
                        elif agg == "max":
                            computed_val = max(nums)

            if computed_val is not None:
                insights.append(
                    DynamicInsightResult(
                        id=ins_id,
                        title=title,
                        kind=kind,
                        definition=d,
                        value=computed_val,
                    )
                )

        # ---------------------------------------------------------------------
        # 2. Generic Always-On Insights
        # ---------------------------------------------------------------------
        total_fields = len(fields)
        grounded_fields = sum(1 for f in fields if f.evidence and f.evidence.grounded)
        verified_fields = sum(1 for f in fields if f.status == "verified")

        insights.append(
            DynamicInsightResult(
                id="ins_field_coverage",
                title="Grounding & Coverage",
                kind="metric",
                definition={"type": "system_metric"},
                value=f"{grounded_fields}/{total_fields} grounded ({verified_fields} verified)",
            )
        )

        # 3. Validation Flags
        failed_rules = [r for r in validation_results if r.get("status") == "fail"]
        for idx, r in enumerate(failed_rules):
            insights.append(
                DynamicInsightResult(
                    id=f"ins_flag_rule_{idx}",
                    title=f"Rule Warning: {r.get('rule')}",
                    kind="flag",
                    definition=r,
                    value=r.get("message"),
                )
            )

        return insights


# Singleton instance
insights_engine_v2 = DynamicInsightsEngine()
