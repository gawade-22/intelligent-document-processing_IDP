"""Pydantic schemas for invoice validation and confidence-based routing."""

from enum import Enum
from typing import Any, Dict, List
from pydantic import BaseModel, ConfigDict, Field


class ValidationResult(BaseModel):
    """Schema representing the outcome of rule-based invoice validation."""

    model_config = ConfigDict(from_attributes=True)

    is_valid: bool = Field(
        default=True,
        description="Whether all invoice validation rules passed successfully",
    )
    errors: List[str] = Field(
        default_factory=list,
        description="List of all validation error messages",
    )
    field_errors: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of field name to specific validation error message",
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert validation result to standard dictionary."""
        return self.model_dump()


class FieldConfidenceInfo(BaseModel):
    """Schema representing confidence assessment for a single field against a threshold."""

    model_config = ConfigDict(from_attributes=True)

    confidence: float = Field(..., description="Actual field extraction confidence score")
    meets_threshold: bool = Field(..., description="Whether confidence >= threshold")


class ConfidenceEvaluationResult(BaseModel):
    """Schema representing the evaluation of all required fields against the configured threshold."""

    model_config = ConfigDict(from_attributes=True)

    threshold: float = Field(..., description="Configured threshold evaluated against")
    all_meet_threshold: bool = Field(..., description="True if every required field meets the threshold")
    fields: Dict[str, FieldConfidenceInfo] = Field(
        default_factory=dict,
        description="Field-level confidence information",
    )
    failing_fields: List[str] = Field(
        default_factory=list,
        description="List of fields failing the threshold",
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to standard dictionary."""
        return self.model_dump()


class RoutingStatus(str, Enum):
    """Routing destination status for an invoice in the IDP pipeline."""

    VERIFIED = "VERIFIED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class RoutingDecision(BaseModel):
    """Schema representing the confidence evaluation and routing decision for an invoice."""

    model_config = ConfigDict(from_attributes=True)

    status: RoutingStatus = Field(
        ...,
        description="Routing destination (VERIFIED for straight-through processing, NEEDS_REVIEW for HITL)",
    )
    is_valid: bool = Field(
        ...,
        description="Whether rule-based validation passed",
    )
    threshold: float = Field(
        default=0.85,
        description="Configured confidence threshold evaluated against",
    )
    overall_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Composite confidence score across invoice fields",
    )
    field_confidences: Dict[str, float] = Field(
        default_factory=dict,
        description="Individual confidence scores by field",
    )
    field_evaluations: Dict[str, FieldConfidenceInfo] = Field(
        default_factory=dict,
        description="Field-level evaluations indicating whether each field meets threshold",
    )
    validation_errors: List[str] = Field(
        default_factory=list,
        description="Errors from rule-based validation if any rule failed",
    )
    review_reasons: List[str] = Field(
        default_factory=list,
        description="Explanations why the invoice requires review (validation failure or low confidence)",
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert routing decision to standard dictionary."""
        return self.model_dump()
