"""
Multi-Pass Reconciliation Service.
Compares candidates from multiple independent passes (Text-LLM, Deterministic Patterns, Vision-LLM).
Identifies agreements (auto-accepted with high confidence) vs conflicts (flagged as NEEDS_REVIEW).
Records full pass history in the passes array for HITL auditability.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.universal import ExtractionPass, FieldEvidence

logger = logging.getLogger(__name__)


class PatternDetector:
    """Generic, document-agnostic regex detector for standard data types."""

    EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
    PHONE_PATTERN = re.compile(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b|\+?\d{1,4}[-.\s]?\d{10}\b")
    DATE_PATTERN = re.compile(r"\b(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})\b")
    MONEY_PATTERN = re.compile(r"[$€£₹]?\s*(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?\b")

    @classmethod
    def detect_candidates(cls, text: str, data_type: str) -> List[str]:
        """Finds candidate values by generic data type pattern."""
        if not text:
            return []

        if data_type == "email":
            return cls.EMAIL_PATTERN.findall(text)
        elif data_type == "phone":
            return cls.PHONE_PATTERN.findall(text)
        elif data_type == "date":
            return cls.DATE_PATTERN.findall(text)
        elif data_type == "money":
            return [m.strip() for m in cls.MONEY_PATTERN.findall(text) if any(c.isdigit() for c in m)]
        return []


class MultiPassReconciler:
    """Reconciles candidate extractions across passes and assigns confidence/review status."""

    def _normalize_for_comparison(self, val: Any) -> str:
        """Removes spaces, lowercase, removes punctuation/currency symbols for soft match."""
        if val is None:
            return ""
        s = str(val).lower().strip()
        # Remove currency symbols and formatting commas
        s = re.sub(r"[$€£₹,\s]", "", s)
        return s

    def reconcile_field(
        self,
        key: str,
        llm_value: Any,
        data_type: str,
        evidence: FieldEvidence,
        document_text: str,
        secondary_llm_value: Optional[Any] = None,
    ) -> Tuple[Any, List[ExtractionPass], float, str, List[str]]:
        """
        Reconciles field candidates.
        Returns:
            (reconciled_value, passes_list, confidence, status, conflict_messages)
        """
        passes: List[ExtractionPass] = []
        conflict_messages: List[str] = []

        # 1. Record primary Text-LLM pass
        if llm_value is not None:
            passes.append(ExtractionPass(engine="text-llm", value=llm_value))

        # 2. Record Secondary LLM pass if present
        if secondary_llm_value is not None:
            passes.append(ExtractionPass(engine="vision-llm", value=secondary_llm_value))

        # 3. Generic Pattern Detector Pass
        pattern_matches = PatternDetector.detect_candidates(document_text, data_type)
        if pattern_matches and llm_value is not None:
            # Check if any pattern match corresponds to llm_value
            norm_llm = self._normalize_for_comparison(llm_value)
            matched_pattern = None
            for p in pattern_matches:
                if self._normalize_for_comparison(p) == norm_llm:
                    matched_pattern = p
                    break

            if matched_pattern:
                passes.append(ExtractionPass(engine="pattern-detector", value=matched_pattern))
        elif pattern_matches and llm_value is None:
            passes.append(ExtractionPass(engine="pattern-detector", value=pattern_matches[0]))

        # 4. Evaluate Reconciliation Outcome
        # Base confidence from grounding
        if not evidence.grounded:
            return (
                llm_value,
                passes,
                0.40,
                "needs_review",
                ["Ungrounded value: evidence quote not found in source text."],
            )

        if not passes:
            return None, [], 0.0, "needs_review", ["No extraction candidates produced."]

        # Check for multi-pass conflicts
        if len(passes) >= 2:
            val1_norm = self._normalize_for_comparison(passes[0].value)
            val2_norm = self._normalize_for_comparison(passes[1].value)

            if val1_norm and val2_norm and val1_norm != val2_norm:
                # Contested extraction
                msg = f"Pass disagreement: {passes[0].engine}='{passes[0].value}' vs {passes[1].engine}='{passes[1].value}'"
                conflict_messages.append(msg)
                return (
                    llm_value,
                    passes,
                    0.60,
                    "needs_review",
                    conflict_messages,
                )

        # High confidence agreement / grounded extraction
        confidence = 0.95 if len(passes) >= 2 else 0.90
        return llm_value, passes, confidence, "verified", []


# Singleton instance
multi_pass_reconciler = MultiPassReconciler()
