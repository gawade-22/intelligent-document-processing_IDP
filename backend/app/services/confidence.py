"""Confidence evaluation and routing service for Intelligent Document Processing (IDP).

This service evaluates extraction confidence scores and rule-based validation results
to make routing decisions:
- VERIFIED: All validation rules passed and confidence scores meet/exceed configured threshold.
- NEEDS_REVIEW: One or more validation rules failed or confidence is below configured threshold.

Independent of OCR, LLM, database persistence, and FastAPI routes.
"""

import logging
from typing import Any, Dict, List, Optional, Union

from app.core.config import settings
from app.schemas.validation import (
    ConfidenceEvaluationResult,
    FieldConfidenceInfo,
    RoutingDecision,
    RoutingStatus,
    ValidationResult,
)

logger = logging.getLogger(__name__)

# Required core invoice fields evaluated for confidence
REQUIRED_INVOICE_FIELDS = ("vendor_name", "invoice_number", "invoice_date", "total_amount")

# Default field weights for overall composite confidence computation
DEFAULT_FIELD_WEIGHTS: Dict[str, float] = {
    "vendor_name": 0.25,
    "invoice_number": 0.25,
    "invoice_date": 0.25,
    "total_amount": 0.25,
}


class ConfidenceRouter:
    """Service to evaluate document confidence against configured thresholds and route invoices."""

    REQUIRED_FIELDS = REQUIRED_INVOICE_FIELDS

    @classmethod
    def get_configured_threshold(cls) -> float:
        """Retrieve the configured confidence threshold from application settings.

        Default is 0.85 if not explicitly configured in environment.
        """
        try:
            return float(getattr(settings, "CONFIDENCE_THRESHOLD", 0.85))
        except (TypeError, ValueError):
            return 0.85

    @classmethod
    def compute_overall_confidence(
        cls,
        field_confidences: Dict[str, float],
        weights: Optional[Dict[str, float]] = None,
    ) -> float:
        """Compute normalized, weighted overall document confidence score.

        If custom weights are provided, they are normalized. Missing field confidences
        default to 0.0.
        """
        if not field_confidences:
            return 0.0

        applied_weights = weights or DEFAULT_FIELD_WEIGHTS

        total_weight = 0.0
        weighted_sum = 0.0

        for field_name, weight in applied_weights.items():
            conf = field_confidences.get(field_name, 0.0)
            # Clamp individual confidence between 0.0 and 1.0
            clamped_conf = max(0.0, min(1.0, float(conf)))
            weighted_sum += clamped_conf * weight
            total_weight += weight

        if total_weight <= 0:
            return 0.0

        raw_score = weighted_sum / total_weight
        return round(max(0.0, min(1.0, raw_score)), 4)

    @classmethod
    def extract_field_confidences(cls, source: Any) -> Dict[str, float]:
        """Extract field confidence mapping from a dict or an InvoiceExtractionResult object."""
        confidences: Dict[str, float] = {}

        if isinstance(source, dict):
            for field in cls.REQUIRED_FIELDS:
                val = source.get(field)
                if isinstance(val, (int, float)):
                    confidences[field] = float(val)
                elif hasattr(val, "confidence") and getattr(val, "confidence") is not None:
                    confidences[field] = float(getattr(val, "confidence"))
                elif isinstance(val, dict) and "confidence" in val and val["confidence"] is not None:
                    confidences[field] = float(val["confidence"])
        elif source is not None:
            # Pydantic model or object
            for field in cls.REQUIRED_FIELDS:
                if hasattr(source, field):
                    attr = getattr(source, field)
                    if hasattr(attr, "confidence") and getattr(attr, "confidence") is not None:
                        confidences[field] = float(getattr(attr, "confidence"))
                    elif isinstance(attr, (int, float)):
                        confidences[field] = float(attr)

        return confidences

    @classmethod
    def evaluate_field_confidences(
        cls,
        field_confidences: Any,
        threshold: Optional[float] = None,
    ) -> ConfidenceEvaluationResult:
        """Evaluate individual required fields against the confidence threshold.

        Confidence Boundary:
        -------------------
        The comparison is strictly: `confidence >= threshold`
        - 0.85 >= 0.85 PASSES
        - 0.849 < 0.85 FAILS
        - Exactly 0.85 PASSES (not >)
        """
        applied_threshold = (
            cls.get_configured_threshold() if threshold is None else float(threshold)
        )
        scores = cls.extract_field_confidences(field_confidences)

        field_evals: Dict[str, FieldConfidenceInfo] = {}
        failing_fields: List[str] = []

        for field_name in cls.REQUIRED_FIELDS:
            raw_conf = scores.get(field_name, 0.0)
            conf = round(float(raw_conf), 4)
            # Boundary rule: confidence >= threshold
            meets = conf >= applied_threshold
            field_evals[field_name] = FieldConfidenceInfo(
                confidence=conf,
                meets_threshold=meets,
            )
            if not meets:
                failing_fields.append(field_name)

        all_meet = len(failing_fields) == 0

        return ConfidenceEvaluationResult(
            threshold=applied_threshold,
            all_meet_threshold=all_meet,
            fields=field_evals,
            failing_fields=failing_fields,
        )

    @classmethod
    def evaluate_and_route(
        cls,
        validation_result: ValidationResult,
        field_confidences: Optional[Union[Dict[str, float], Any]] = None,
        *,
        threshold: Optional[float] = None,
        overall_threshold: Optional[float] = None,
        min_field_threshold: Optional[float] = None,
        weights: Optional[Dict[str, float]] = None,
    ) -> RoutingDecision:
        """Evaluate invoice confidence against thresholds and validation results.

        Routing Logic:
        1. If validation failed (any rule violated) -> NEEDS_REVIEW with validation errors.
        2. If any core field confidence < threshold -> NEEDS_REVIEW with low-confidence field details.
        3. If overall confidence < threshold -> NEEDS_REVIEW with overall confidence explanation.
        4. If all validation rules pass AND all field confidences >= threshold -> VERIFIED.
        """
        # Determine effective threshold from arguments or application config
        effective_threshold = (
            threshold
            if threshold is not None
            else (
                overall_threshold
                if overall_threshold is not None
                else cls.get_configured_threshold()
            )
        )

        effective_field_floor = (
            min_field_threshold
            if min_field_threshold is not None
            else effective_threshold
        )

        scores = cls.extract_field_confidences(field_confidences)

        # 1. Field-level confidence evaluations
        conf_eval = cls.evaluate_field_confidences(scores, threshold=effective_field_floor)

        # 2. Compute overall composite confidence
        overall_conf = cls.compute_overall_confidence(scores, weights=weights)

        review_reasons: List[str] = []

        # 3. Check validation outcome
        if not validation_result.is_valid:
            for err in validation_result.errors:
                review_reasons.append(err)

        # 4. Check field-level confidence threshold failures
        field_display_names = {
            "vendor_name": "Vendor Name",
            "invoice_number": "Invoice Number",
            "invoice_date": "Invoice Date",
            "total_amount": "Total Amount",
        }
        for failing_field in conf_eval.failing_fields:
            field_score = conf_eval.fields[failing_field].confidence
            display_name = field_display_names.get(
                failing_field, failing_field.replace("_", " ").title()
            )
            review_reasons.append(
                f"{display_name} confidence {field_score:.2f} is below threshold {effective_field_floor:.2f}"
            )

        # 5. Check overall confidence threshold
        if overall_conf < effective_threshold and not any("Overall confidence" in r for r in review_reasons):
            review_reasons.append(
                f"Overall confidence {overall_conf:.2f} is below threshold {effective_threshold:.2f}"
            )

        # Exact Routing Rule:
        # IF validation passes AND every required field confidence >= configured threshold
        # THEN VERIFIED
        # ELSE NEEDS_REVIEW
        if validation_result.is_valid and conf_eval.all_meet_threshold and overall_conf >= effective_threshold:
            status = RoutingStatus.VERIFIED
        else:
            status = RoutingStatus.NEEDS_REVIEW

        return RoutingDecision(
            status=status,
            is_valid=validation_result.is_valid,
            threshold=effective_threshold,
            overall_confidence=overall_conf,
            field_confidences=scores,
            field_evaluations=conf_eval.fields,
            validation_errors=validation_result.errors,
            review_reasons=review_reasons,
        )

    @classmethod
    def route_invoice(
        cls,
        invoice_data: Any,
        field_confidences: Any,
        threshold: Optional[float] = None,
    ) -> RoutingDecision:
        """Convenience method to validate and route an invoice in one step."""
        from app.services.validator import InvoiceValidator

        val_result = InvoiceValidator.validate_invoice(invoice_data)
        return cls.evaluate_and_route(val_result, field_confidences, threshold=threshold)


# Backward compatibility and alternative naming aliases
ConfidenceService = ConfidenceRouter

# Module-level convenience functions
evaluate_field_confidences = ConfidenceRouter.evaluate_field_confidences
evaluate_confidence = ConfidenceRouter.evaluate_field_confidences
compute_overall_confidence = ConfidenceRouter.compute_overall_confidence
evaluate_and_route = ConfidenceRouter.evaluate_and_route
route_invoice = ConfidenceRouter.route_invoice
