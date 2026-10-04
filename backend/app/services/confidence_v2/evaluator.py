"""
Calibrated Composite Confidence Engine.
Evaluates multi-signal evidence calibration:
1. Grounding match quality (0.0 to 1.0)
2. OCR quality score from physical blocks
3. Multi-pass agreement / conflict signal
4. Data type normalization validity
5. Cross-field DSL validation rule outcomes

Never uses raw LLM self-reported confidence.
Threshold for auto-verification is calibrated to >= 0.85.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.universal import DynamicFieldResult

logger = logging.getLogger(__name__)

AUTO_VERIFY_THRESHOLD = 0.85


class CalibratedConfidenceEvaluator:
    """Computes calibrated confidence scores and routing decisions."""

    def evaluate_field(
        self,
        field: DynamicFieldResult,
        is_type_valid: bool,
        rule_failures_for_field: int = 0,
        ocr_confidence: float = 1.0,
    ) -> Tuple[float, str]:
        """
        Computes calibrated confidence score and routing status for an extracted field.
        Returns:
            (calibrated_score, status) -> status is 'verified' or 'needs_review'
        """
        # If value is empty or not grounded, confidence is strictly capped
        if field.value is None or str(field.value).strip() == "":
            return 0.0, "needs_review"

        if not field.evidence or not field.evidence.grounded:
            return 0.35, "needs_review"

        # Signal 1: Grounding match quality (weight: 0.35)
        grounding_score = field.evidence.match_score if field.evidence else 0.5

        # Signal 2: Pass agreement (weight: 0.25)
        if len(field.passes) >= 2:
            # Check if all passes agree
            val_strs = [str(p.value).strip().lower() for p in field.passes]
            if len(set(val_strs)) == 1:
                pass_score = 1.0
            else:
                pass_score = 0.55
        else:
            pass_score = 0.88  # Single pass, grounded

        # Signal 3: Data type validation (weight: 0.25)
        type_score = 1.0 if is_type_valid else 0.40

        # Signal 4: OCR quality & DSL rules (weight: 0.15)
        rule_score = max(0.0, 1.0 - (rule_failures_for_field * 0.3))
        ocr_score = max(0.5, min(1.0, ocr_confidence))
        aux_score = (rule_score * 0.6) + (ocr_score * 0.4)

        # Calibrated weighted combination
        composite = (
            (grounding_score * 0.35)
            + (pass_score * 0.25)
            + (type_score * 0.25)
            + (aux_score * 0.15)
        )
        calibrated = round(min(0.99, max(0.1, composite)), 2)

        # Routing decision
        status = "verified" if (calibrated >= AUTO_VERIFY_THRESHOLD and is_type_valid and field.evidence.grounded) else "needs_review"

        return calibrated, status

    def evaluate_document(
        self,
        fields: List[DynamicFieldResult],
        dsl_errors: List[str],
    ) -> Tuple[float, str, List[str]]:
        """
        Computes overall document confidence and routing decision.
        Returns:
            (doc_confidence, routing_status, review_reasons)
        """
        if not fields:
            return 0.0, "NEEDS_REVIEW", ["No fields extracted from document."]

        field_confs = [f.confidence for f in fields]
        avg_conf = sum(field_confs) / len(field_confs)

        review_reasons = []
        failing_fields = [f for f in fields if f.status == "needs_review"]
        ungrounded_fields = [f for f in fields if f.evidence and not f.evidence.grounded]

        if ungrounded_fields:
            review_reasons.append(f"{len(ungrounded_fields)} field(s) ungrounded in document text")

        if failing_fields:
            names = ", ".join(f.label for f in failing_fields[:4])
            review_reasons.append(f"Fields requiring human review: {names}")

        if dsl_errors:
            review_reasons.extend(dsl_errors)

        is_verified = (
            len(failing_fields) == 0
            and len(ungrounded_fields) == 0
            and len(dsl_errors) == 0
            and avg_conf >= AUTO_VERIFY_THRESHOLD
        )

        doc_status = "VERIFIED" if is_verified else "NEEDS_REVIEW"
        doc_conf = round(avg_conf, 2)

        return doc_conf, doc_status, review_reasons


# Singleton instance
confidence_evaluator_v2 = CalibratedConfidenceEvaluator()
