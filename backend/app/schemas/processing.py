"""Processing schemas for Intelligent Document Processing (IDP).

Defines the structured output contract returned by
POST /api/documents/{document_id}/process.
"""

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.pipeline import PipelineProcessingResult, ProcessingError


class ProcessingFieldResult(BaseModel):
    """Structured per-field result preserving original extracted value,

    normalized value, confidence, source attribution, and validation errors
    for human-in-the-loop (HITL) review.
    """

    original_value: Optional[str] = Field(
        default=None,
        description="Raw extracted value before normalization",
    )
    normalized_value: Optional[str] = Field(
        default=None,
        description="Standardized machine-readable value",
    )
    confidence: Optional[float] = Field(
        default=None,
        description="Field confidence score between 0.0 and 1.0",
    )
    source: Optional[str] = Field(
        default=None,
        description="Candidate source attribution ('rule', 'ai', 'rule+ai')",
    )
    validation_errors: List[str] = Field(
        default_factory=list,
        description="Validation error messages associated with this field",
    )

    model_config = ConfigDict(from_attributes=True)


class ProcessingResult(BaseModel):
    """Structured output contract returned by document processing API."""

    document_id: int = Field(
        ...,
        description="Database identifier of the processed document",
    )
    status: Literal[
        "PROCESSING",
        "VERIFIED",
        "NEEDS_REVIEW",
        "FAILED",
    ] = Field(
        ...,
        description="Final document processing status",
    )
    fields: Dict[str, ProcessingFieldResult] = Field(
        default_factory=dict,
        description="Detailed extracted and normalized field dictionary",
    )
    confidence: Dict[str, float] = Field(
        default_factory=dict,
        description="Reconciled field-level confidence scores",
    )
    validation_errors: List[str] = Field(
        default_factory=list,
        description="Document-level and field-level validation errors",
    )
    processing_errors: List[ProcessingError] = Field(
        default_factory=list,
        description="Technical or operational processing errors",
    )

    model_config = ConfigDict(from_attributes=True)


def sanitize_error_message(message: str) -> str:
    """Sanitize error messages to prevent exposing secrets or traces.

    Masks passwords, api keys, tokens, database connection credentials, and
    strips stack traces.
    """
    if not message:
        return ""
    import re

    # Strip stack traces if present
    if "traceback" in message.lower():
        message = message.split("\n")[0]

    # Redact common credentials/patterns
    sanitized = re.sub(
        r"(password|pwd|secret|key|token|api_key|apikey)\s*[:=]\s*\S+",
        r"\1=[REDACTED]",
        message,
        flags=re.IGNORECASE,
    )
    # Database connection URLs e.g. postgresql://user:pass@host:port/db
    sanitized = re.sub(
        r"://([^:]+):([^@]+)@",
        r"://\1:[REDACTED]@",
        sanitized,
    )
    return sanitized


def to_processing_result(res: PipelineProcessingResult) -> ProcessingResult:
    """Converts a PipelineProcessingResult into an API ProcessingResult."""
    field_results: Dict[str, ProcessingFieldResult] = {}
    extracted_fields = (res.extracted_data or {}).get("fields", {})
    field_errors_map = (
        res.validation.field_errors
        if res.validation and res.validation.field_errors
        else {}
    )

    for field_name, f_data in extracted_fields.items():
        if not isinstance(f_data, dict):
            continue
        f_errs: List[str] = []
        if field_name in field_errors_map and field_errors_map[field_name]:
            err_val = field_errors_map[field_name]
            if isinstance(err_val, list):
                f_errs.extend(err_val)
            else:
                f_errs.append(str(err_val))

        val = f_data.get("original_value") if f_data.get("original_value") is not None else f_data.get("value")
        norm = f_data.get("normalized_value")
        field_results[field_name] = ProcessingFieldResult(
            original_value=str(val) if val is not None else None,
            normalized_value=str(norm) if norm is not None else None,
            confidence=f_data.get("confidence"),
            source=f_data.get("source"),
            validation_errors=f_errs,
        )

    # Field-level confidences
    conf_map: Dict[str, float] = {}
    if res.extraction and res.extraction.field_confidence:
        conf_map = dict(res.extraction.field_confidence)
    elif res.extracted_data and "field_confidence" in res.extracted_data:
        conf_map = dict(res.extracted_data["field_confidence"])

    # Validation errors
    v_errors = (
        list(res.validation.errors)
        if res.validation and res.validation.errors
        else []
    )

    # Processing errors
    raw_p_errors = list(res.processing_errors) if res.processing_errors else []
    if res.status == "FAILED" and not raw_p_errors and res.error:
        raw_p_errors.append(
            ProcessingError(
                stage="PIPELINE",
                code="PROCESSING_FAILED",
                message=res.error,
            )
        )

    sanitized_p_errors = [
        ProcessingError(
            stage=err.stage,
            code=err.code,
            message=sanitize_error_message(err.message),
        )
        for err in raw_p_errors
    ]

    return ProcessingResult(
        document_id=res.document_id,
        status=res.status,  # type: ignore[arg-type]
        fields=field_results,
        confidence=conf_map,
        validation_errors=v_errors,
        processing_errors=sanitized_p_errors,
    )
