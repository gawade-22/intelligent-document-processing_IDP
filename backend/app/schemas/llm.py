"""
Pydantic schemas and configuration models for the LLM extraction environment.
Supports multi-document architectures (Invoice, Resume, Student Document, Custom),
structured field definitions, confidence validation, and seamless pipeline interoperability.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator


class LLMExtractionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    AI_NOT_CONFIGURED = "AI_NOT_CONFIGURED"
    RATE_LIMITED = "RATE_LIMITED"
    API_ERROR = "API_ERROR"
    TIMEOUT = "TIMEOUT"
    PARSING_ERROR = "PARSING_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"


class FieldSpecification(BaseModel):
    """
    Specification for a target field to be extracted by the LLM.
    Defines field name, human-readable description, expected data type, and extraction rules.
    """
    name: str = Field(..., description="Unique machine-readable field identifier (e.g. 'vendor_name', 'skills')")
    description: str = Field(..., description="Clear explanation of the field to guide LLM extraction")
    field_type: str = Field(default="string", description="Data type: 'string', 'number', 'date', 'list[string]', 'boolean'")
    required: bool = Field(default=False, description="Whether this field must be present if found in document")
    instructions: Optional[str] = Field(default=None, description="Specific extraction instructions or boundary constraints")
    examples: List[str] = Field(default_factory=list, description="Illustrative examples of valid values for this field")

    model_config = ConfigDict(from_attributes=True)


class DocumentTypeConfig(BaseModel):
    """
    Configuration definition for a specific document class.
    Enables dynamic, configurable field extraction without hardcoding invoice fields into the core LLM engine.
    """
    document_type: str = Field(..., description="Unique document type identifier (e.g. 'invoice', 'resume', 'student_document')")
    display_name: str = Field(..., description="Human-readable title (e.g. 'Commercial Invoice', 'Professional Resume')")
    description: str = Field(..., description="General description of the document domain")
    fields: List[FieldSpecification] = Field(..., description="List of fields to be extracted for this document type")
    system_instructions: Optional[str] = Field(default=None, description="Custom system-level extraction instructions for this document type")

    model_config = ConfigDict(from_attributes=True)

    def get_field_names(self) -> List[str]:
        return [f.name for f in self.fields]


class FieldExtractionValue(BaseModel):
    """
    Individual extracted field result containing value, confidence score, and contextual evidence.
    """
    value: Optional[Any] = Field(default=None, description="Extracted field value (string, number, list, or null)")
    confidence: float = Field(default=0.0, description="Model-reported confidence score clamped between 0.0 and 1.0")
    evidence: Optional[str] = Field(default=None, description="Exact textual excerpt, line number, or bounding location where found")

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_and_clamp_confidence(cls, val: Any) -> float:
        if val is None:
            return 0.0
        try:
            f = float(val)
            # If model reported percentage (e.g. 95 instead of 0.95)
            if f > 1.0 and f <= 100.0:
                f = f / 100.0
            return round(max(0.0, min(1.0, f)), 2)
        except (ValueError, TypeError):
            return 0.0

    model_config = ConfigDict(from_attributes=True)


class LLMExtractionResult(BaseModel):
    """
    Structured outcome of an LLM document extraction operation.
    Encapsulates validated field extractions, provider metadata, status, and pipeline adapters.
    """
    document_type: str = Field(default="invoice", description="Category of document processed")
    fields: Dict[str, FieldExtractionValue] = Field(default_factory=dict, description="Map of field names to extracted values")
    status: str = Field(default=LLMExtractionStatus.SUCCESS.value, description="Execution status code")
    raw_response: Optional[str] = Field(default=None, description="Original unparsed LLM completion response")
    model: Optional[str] = Field(default=None, description="LLM model identifier used for extraction")
    provider: Optional[str] = Field(default=None, description="LLM service provider name")
    errors: List[str] = Field(default_factory=list, description="Diagnostic warnings or errors encountered")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Execution diagnostics and token/character metrics")

    model_config = ConfigDict(from_attributes=True)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, val: Any) -> str:
        if isinstance(val, LLMExtractionStatus):
            return val.value
        s = str(val or "").strip().upper()
        valid = {e.value for e in LLMExtractionStatus}
        return s if s in valid else LLMExtractionStatus.API_ERROR.value

    def get_value(self, field_name: str, default: Any = None) -> Any:
        """Retrieve the raw extracted value for a specific field name."""
        if field_name in self.fields:
            val = self.fields[field_name].value
            return val if val is not None else default
        return default

    def get_confidence(self, field_name: str, default: float = 0.0) -> float:
        """Retrieve the confidence score for a specific field name."""
        if field_name in self.fields:
            return self.fields[field_name].confidence
        return default

    def get_evidence(self, field_name: str, default: Optional[str] = None) -> Optional[str]:
        """Retrieve the textual evidence for a specific field name."""
        if field_name in self.fields:
            return self.fields[field_name].evidence or default
        return default

    def to_dict(self) -> Dict[str, Any]:
        """
        Export a flattened dictionary of field names to their extracted values.
        Missing or null fields map to None.
        """
        return {name: item.value for name, item in self.fields.items()}

    def to_confidence_dict(self) -> Dict[str, float]:
        """Export a dictionary of field names to their clamped confidence values."""
        return {name: item.confidence for name, item in self.fields.items()}

    def to_evidence_dict(self) -> Dict[str, str]:
        """Export a dictionary of field names to their textual evidence strings."""
        return {name: item.evidence or "" for name, item in self.fields.items()}

    def to_ai_response(self) -> Any:
        """
        Convert to AIExtractionResponse for backward-compatible consumption
        by existing IDP services (ReconciliationEngine, processing_pipeline).
        """
        from app.services.ai.schemas import AIExtractedFields, AIExtractionResponse

        fields_dict = self.to_dict()
        conf_dict = self.to_confidence_dict()
        ev_dict = self.to_evidence_dict()

        extracted_fields = AIExtractedFields(
            vendor_name=fields_dict.get("vendor_name"),
            invoice_number=fields_dict.get("invoice_number"),
            invoice_date=fields_dict.get("invoice_date"),
            total_amount=fields_dict.get("total_amount"),
            confidence=conf_dict,
            evidence=ev_dict,
        )

        return AIExtractionResponse(
            status=self.status,
            fields=extracted_fields,
            raw_response=self.raw_response,
            model=self.model,
            provider=self.provider,
            errors=self.errors,
        )
