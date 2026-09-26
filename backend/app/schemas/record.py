from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ExtractionStatus(str, Enum):
    """Extraction status indicating the outcome of parsing/OCR."""
    PENDING = "pending"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class DocumentRecordBase(BaseModel):
    """
    Base schema for extracted document data.
    All extracted fields are intentionally OPTIONAL with None defaults
    because extraction can be pending, partially successful, or fail.
    """
    document_id: int = Field(..., description="ID of the parent document")
    document_type: Optional[str] = Field(
        default=None,
        description="Classified document type (e.g., 'invoice', 'receipt', 'contract', 'id_card')",
    )
    extraction_status: ExtractionStatus = Field(
        default=ExtractionStatus.PENDING,
        description="Current extraction status",
    )
    raw_text: Optional[str] = Field(
        default=None,
        description="Full raw OCR/extracted text content",
    )
    extracted_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Structured key-value pairs extracted from document (e.g. invoice_number, total, dates)",
    )
    confidence_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Overall model extraction confidence score between 0.0 and 1.0",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error description if extraction failed or was incomplete",
    )


class DocumentRecordCreate(DocumentRecordBase):
    """Schema used when saving new extraction results."""
    pass


class DocumentRecordUpdate(BaseModel):
    """Schema used when updating extraction status or human-reviewed edits."""
    document_type: Optional[str] = None
    extraction_status: Optional[ExtractionStatus] = None
    extracted_data: Optional[Dict[str, Any]] = None
    confidence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    error_message: Optional[str] = None


class DocumentRecordResponse(DocumentRecordBase):
    """
    Standard response schema returned by the API for a document record.
    Maps directly from SQLAlchemy DocumentRecord model using from_attributes=True.
    """
    id: int = Field(..., description="Unique record database ID")
    created_at: datetime = Field(..., description="Timestamp when the record was created")
    updated_at: Optional[datetime] = Field(default=None, description="Timestamp of the latest update")

    # Pydantic v2 configuration to map from SQLAlchemy ORM models
    model_config = ConfigDict(from_attributes=True)


class DocumentWithRecordResponse(BaseModel):
    """Composite response showing document info together with its extracted record (if available)."""
    document_id: int
    filename: str
    status: str
    record: Optional[DocumentRecordResponse] = Field(
        default=None,
        description="Extracted record data, or None if extraction is not yet complete or failed",
    )

    model_config = ConfigDict(from_attributes=True)
