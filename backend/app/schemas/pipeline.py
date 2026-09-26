"""Pipeline schemas for Intelligent Document Processing (IDP).

Defines the structured output contract returned by
DocumentProcessingPipeline.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.extraction import InvoiceExtractionResult
from app.schemas.normalization import InvoiceNormalizationResult
from app.schemas.validation import RoutingDecision, ValidationResult


class ProcessingError(BaseModel):
    """Structured processing error detailing stage, code, and message.

    Does not expose stack traces or sensitive credentials.
    """

    stage: str = Field(
        ...,
        description="Pipeline processing stage where error occurred",
    )
    code: str = Field(
        ...,
        description="Machine-readable error code",
    )
    message: str = Field(
        ...,
        description="User-facing error description",
    )

    model_config = ConfigDict(from_attributes=True)


class PipelineProcessingResult(BaseModel):
    """Structured result returned by the central DocumentProcessingPipeline."""

    document_id: int = Field(
        ...,
        description="Database identifier of the processed document",
    )
    file_name: str = Field(
        ...,
        description="Original filename of the document",
    )
    file_type: str = Field(
        ...,
        description="Detected file category or MIME type",
    )
    status: str = Field(
        ...,
        description="Final processing status (VERIFIED, NEEDS_REVIEW, FAILED)",
    )
    success: bool = Field(
        default=True,
        description="Whether pipeline execution completed successfully",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if pipeline execution failed",
    )
    processing_errors: List[ProcessingError] = Field(
        default_factory=list,
        description="Structured processing errors across pipeline stages",
    )

    # Routing and evaluations
    routing_decision: Optional[RoutingDecision] = Field(
        default=None,
        description="Confidence evaluation and routing decision",
    )
    validation: Optional[ValidationResult] = Field(
        default=None,
        description="Rule-based invoice validation results",
    )
    normalization: Optional[InvoiceNormalizationResult] = Field(
        default=None,
        description="Normalized invoice fields and normalization status",
    )
    extraction: Optional[InvoiceExtractionResult] = Field(
        default=None,
        description="Extracted and reconciled invoice field candidates",
    )

    # Persisted data summary
    extracted_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Structured key-value payload persisted in DocumentRecord",
    )
    confidence_score: Optional[float] = Field(
        default=None,
        description="Overall composite confidence score",
    )
    raw_text: Optional[str] = Field(
        default=None,
        description="Extracted raw text from PDF, OCR, or tabular parser",
    )
    text_source: Optional[str] = Field(
        default=None,
        description="Source of extracted text (e.g. digital_pdf, ocr_image)",
    )
    record_id: Optional[int] = Field(
        default=None,
        description="ID of the persisted DocumentRecord",
    )

    model_config = ConfigDict(from_attributes=True)
