"""
Dynamic LLM Schema Discovery Service.
When an uploaded document has no pre-existing template or match in the Schema Registry,
this service analyzes the document structure and prompts the LLM to dynamically
propose sections, fields, data types, repeating tables, safe validation rules, and insights.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.schemas.universal import (
    ClassificationResult,
    InsightDefinition,
    SchemaDefinition,
    SchemaFieldDefinition,
    SchemaTableDefinition,
    UniversalDocument,
    ValidationRuleDefinition,
)
from app.services.ai.base import AIExtractionProvider
from app.services.ai.factory import get_ai_provider

logger = logging.getLogger(__name__)

DISCOVERY_SYSTEM_INSTRUCTION = """You are a Schema Architect for an Intelligent Document Processing (IDP) platform.
Your objective is to inspect a previously unseen document and infer a clean, normalized extraction schema.

Output valid JSON matching this exact structure:
{
  "sections": ["Section Name 1", "Section Name 2"],
  "fields": [
    {
      "key": "snake_case_key",
      "label": "Human Readable Label",
      "data_type": "string|number|date|money|percent|email|phone|id|text|bool",
      "section": "Section Name 1",
      "description": "Brief description of the field"
    }
  ],
  "tables": [
    {
      "key": "table_key",
      "title": "Human Title",
      "columns": ["col_1", "col_2", "col_3"]
    }
  ],
  "validation_rules": [
    {
      "rule": "sum_equals",
      "target": "target_field_key",
      "terms": ["table_key.col", "tax_key"]
    }
  ],
  "insight_definitions": [
    {
      "id": "ins_metric_id",
      "title": "Total Metric Title",
      "kind": "metric",
      "agg": "sum",
      "table": "table_key",
      "column": "col_name"
    }
  ]
}

SAFETY RULES:
- Never execute or generate code.
- Validation rules must only use safe built-in keywords: "sum_equals", "running_balance", "date_order", "in_range", "regex_match".
- All field keys MUST be lowercase snake_case (e.g., "candidate_name", "total_amount").
- Respond ONLY with the JSON object.
"""


class DynamicSchemaDiscovery:
    """Discovers structured schemas for unseen document types using LLM inference."""

    def __init__(self, ai_provider: Optional[AIExtractionProvider] = None):
        self._ai_provider = ai_provider

    def discover_schema(
        self,
        udoc: UniversalDocument,
        classification: ClassificationResult,
        ai_provider: Optional[AIExtractionProvider] = None,
    ) -> SchemaDefinition:
        """
        Infers an extraction schema from the physical document content and classification.
        """
        provider = ai_provider or self._ai_provider or get_ai_provider()

        # Build context from blocks and tables
        headings = [b.text for b in udoc.blocks if b.type == "heading"][:10]
        sample_text = udoc.page_text(1)[:3000] if udoc.pages else udoc.full_text[:3000]

        table_info = []
        for idx, tbl in enumerate(udoc.tables[:3]):
            if tbl.headers:
                table_info.append(f"Detected Table {idx + 1}: Columns = {tbl.headers}")

        sheet_info = []
        for s in udoc.sheets[:3]:
            sheet_info.append(f"Spreadsheet Sheet '{s.name}': Columns = {s.columns}")

        prompt_parts = [
            f"Document Classified Type: {classification.primary_type} (Family: {classification.family})",
            f"File Name: {udoc.document.file_name}",
            f"Total Pages: {udoc.document.page_count}",
        ]
        if headings:
            prompt_parts.append(f"Major Headings: {' | '.join(headings)}")
        if table_info:
            prompt_parts.extend(table_info)
        if sheet_info:
            prompt_parts.extend(sheet_info)

        prompt_parts.append("\n--- Document Text Excerpt ---")
        prompt_parts.append(sample_text)
        prompt_parts.append("\nGenerate the complete JSON extraction schema for this document.")

        user_content = "\n".join(prompt_parts)

        try:
            raw_result = provider.complete_json(
                messages=[{"role": "user", "content": user_content}],
                system_instruction=DISCOVERY_SYSTEM_INSTRUCTION,
                temperature=0.0,
            )
        except Exception as exc:
            logger.warning(f"Schema discovery LLM error ({exc}). Using degraded schema fallback.")
            raw_result = {
                "sections": ["Overview", "Details"],
                "fields": [
                    {"key": "title", "label": "Document Title", "data_type": "string", "section": "Overview"},
                    {"key": "date", "label": "Document Date", "data_type": "date", "section": "Overview"},
                    {"key": "summary", "label": "Summary", "data_type": "text", "section": "Details"},
                ],
                "tables": [],
                "validation_rules": [],
                "insight_definitions": [],
            }

        return self._parse_discovered_schema(raw_result, classification)

    def _parse_discovered_schema(
        self,
        data: Dict[str, Any],
        classification: ClassificationResult,
    ) -> SchemaDefinition:
        """Parses and sanitizes LLM JSON into a validated SchemaDefinition object."""
        sections: List[str] = data.get("sections", [])
        if not sections:
            sections = ["General Information", "Details"]

        fields: List[SchemaFieldDefinition] = []
        raw_fields = data.get("fields", [])
        for f in raw_fields:
            if not isinstance(f, dict):
                continue
            key = str(f.get("key", "")).strip().lower()
            key = re.sub(r"[^a-z0-9_]+", "_", key).strip("_")
            if not key:
                continue

            label = f.get("label", key.replace("_", " ").title())
            dtype = str(f.get("data_type", "string")).lower()
            valid_dtypes = {
                "string", "number", "date", "money", "percent",
                "email", "phone", "id", "text", "bool"
            }
            if dtype not in valid_dtypes:
                dtype = "string"

            sec = f.get("section", sections[0])
            if sec not in sections:
                sections.append(sec)

            fields.append(
                SchemaFieldDefinition(
                    key=key,
                    label=label,
                    section=sec,
                    data_type=dtype,
                    description=f.get("description"),
                )
            )

        tables: List[SchemaTableDefinition] = []
        raw_tables = data.get("tables", [])
        for t in raw_tables:
            if not isinstance(t, dict):
                continue
            t_key = str(t.get("key", "")).strip().lower()
            t_key = re.sub(r"[^a-z0-9_]+", "_", t_key).strip("_")
            if not t_key:
                continue
            title = t.get("title", t_key.replace("_", " ").title())
            cols = [str(c).strip().lower() for c in t.get("columns", []) if str(c).strip()]
            tables.append(
                SchemaTableDefinition(
                    key=t_key,
                    title=title,
                    columns=cols,
                )
            )

        rules: List[ValidationRuleDefinition] = []
        raw_rules = data.get("validation_rules", [])
        valid_rule_names = {"sum_equals", "running_balance", "date_order", "in_range", "regex_match"}
        for r in raw_rules:
            if not isinstance(r, dict):
                continue
            rule_name = str(r.get("rule", "")).strip()
            if rule_name not in valid_rule_names:
                continue
            rules.append(
                ValidationRuleDefinition(
                    rule=rule_name,
                    target=r.get("target"),
                    terms=r.get("terms"),
                    tolerance=float(r.get("tolerance", 0.05)),
                    table=r.get("table"),
                    opening=r.get("opening"),
                    debit=r.get("debit"),
                    credit=r.get("credit"),
                    balance=r.get("balance"),
                    earlier=r.get("earlier"),
                    later=r.get("later"),
                )
            )

        insights: List[InsightDefinition] = []
        raw_insights = data.get("insight_definitions", [])
        for i_data in raw_insights:
            if not isinstance(i_data, dict):
                continue
            i_id = str(i_data.get("id", f"ins_{len(insights)}"))
            title = i_data.get("title", "Document Metric")
            kind = i_data.get("kind", "metric")
            agg = i_data.get("agg")
            insights.append(
                InsightDefinition(
                    id=i_id,
                    title=title,
                    kind=kind if kind in ("metric", "chart", "flag", "text") else "metric",
                    agg=agg if agg in ("sum", "avg", "min", "max", "count", "trend") else None,
                    table=i_data.get("table"),
                    column=i_data.get("column"),
                )
            )

        return SchemaDefinition(
            sections=sections,
            fields=fields,
            tables=tables,
            validation_rules=rules,
            insight_definitions=insights,
        )


# Singleton instance
schema_discovery = DynamicSchemaDiscovery()
