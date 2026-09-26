"""
Pydantic schemas for the AI/LLM Invoice Extraction layer.
Defines structured response models, field confidence validations, and provider status codes.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class AIExtractionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    AI_NOT_CONFIGURED = "AI_NOT_CONFIGURED"
    RATE_LIMITED = "RATE_LIMITED"
    API_ERROR = "API_ERROR"
    TIMEOUT = "TIMEOUT"
    PARSING_ERROR = "PARSING_ERROR"


class AIExtractedFields(BaseModel):
    """
    Structured fields extracted by an AI/LLM provider.
    Confidence values represent model-reported scores clamped between 0.0 and 1.0.
    """
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    total_amount: Optional[str] = None
    confidence: Optional[Dict[str, float]] = Field(default_factory=dict)
    evidence: Optional[Dict[str, str]] = Field(default_factory=dict)

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_and_clamp_confidence(cls, val: Any) -> Dict[str, float]:
        if not val or not isinstance(val, dict):
            return {}
        clamped: Dict[str, float] = {}
        for k, v in val.items():
            try:
                f_val = float(v)
                clamped[str(k)] = round(max(0.0, min(1.0, f_val)), 2)
            except (ValueError, TypeError):
                clamped[str(k)] = 0.0
        return clamped

    @field_validator("evidence", mode="before")
    @classmethod
    def validate_evidence(cls, val: Any) -> Dict[str, str]:
        if not val or not isinstance(val, dict):
            return {}
        return {str(k): str(v) for k, v in val.items()}

    def to_dict(self) -> Dict[str, Any]:
        """Convert fields to dictionary format compatible with legacy extraction interfaces."""
        return {
            "vendor_name": self.vendor_name,
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date,
            "total_amount": self.total_amount,
            "confidence": self.confidence or {},
            "evidence": self.evidence or {},
        }


class AIExtractionResponse(BaseModel):
    """
    Encapsulates the full response from an AI extraction provider,
    including provider identification, execution status, and diagnostics.
    """
    status: str = AIExtractionStatus.AI_NOT_CONFIGURED.value
    fields: Optional[AIExtractedFields] = None
    raw_response: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    errors: List[str] = Field(default_factory=list)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, val: Any) -> str:
        if isinstance(val, AIExtractionStatus):
            return val.value
        s = str(val or "").strip().upper()
        valid = {e.value for e in AIExtractionStatus}
        return s if s in valid else AIExtractionStatus.API_ERROR.value
