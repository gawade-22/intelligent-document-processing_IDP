"""Schemas for Universal Human-In-The-Loop (HITL) document verification.

Supports any document type (invoices, forms, marksheets, certificates,
employee records, patient reports, etc.) without hardcoding specific fields.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ReviewFieldItem(BaseModel):
    """Universal field item representation for HITL review.

    Handles arbitrary document fields (e.g., student_name, roll_number,
    employee_id, vendor_name, total_amount, tabular items, etc.).
    """

    value: Optional[Any] = Field(
        default=None,
        description="Current raw or entered value of the field (scalar or list)",
    )
    normalized_value: Optional[Any] = Field(
        default=None,
        description="Standardized machine-readable value",
    )
    confidence: Optional[float] = Field(
        default=None,
        description=(
            "Confidence score between 0.0 and 1.0 (1.0 if human-verified)"
        ),
    )
    source: Optional[str] = Field(
        default=None,
        description=(
            "Extraction source attribution ('rule', 'ai', 'ocr', 'human')"
        ),
    )
    validation_errors: List[str] = Field(
        default_factory=list,
        description="Validation error messages associated with this field",
    )

    model_config = ConfigDict(from_attributes=True)


class ReviewDocumentSummary(BaseModel):
    """Summary item for the review list API (GET /api/documents/review)."""

    document_id: int
    file_name: str
    file_type: str
    status: str
    document_type: Optional[str] = None
    document_type_label: Optional[str] = None
    uploaded_at: datetime
    updated_at: Optional[datetime] = None
    fields: Dict[str, ReviewFieldItem] = Field(default_factory=dict)
    validation_errors: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ReviewListResponse(BaseModel):
    """Response schema for GET /api/documents/review."""

    items: List[ReviewDocumentSummary]
    count: int

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "items": [
                    {
                        "document_id": 123,
                        "file_name": "certificate.pdf",
                        "file_type": "PDF",
                        "status": "NEEDS_REVIEW",
                        "uploaded_at": "2026-09-25T14:00:00Z",
                        "updated_at": "2026-09-25T14:05:00Z",
                        "fields": {
                            "student_name": {
                                "value": "Prathmesh Gawade",
                                "normalized_value": "Prathmesh Gawade",
                                "confidence": 0.96,
                                "source": "ocr",
                                "validation_errors": [],
                            },
                            "roll_number": {
                                "value": "19",
                                "normalized_value": "19",
                                "confidence": 0.61,
                                "source": "ocr",
                                "validation_errors": [
                                    "roll_number confidence is below threshold"
                                ],
                            },
                            "percentage": {
                                "value": None,
                                "normalized_value": None,
                                "confidence": None,
                                "source": None,
                                "validation_errors": [
                                    "percentage is missing"
                                ],
                            },
                        },
                        "validation_errors": [
                            "roll_number confidence is below threshold",
                            "percentage is missing",
                        ],
                    }
                ],
                "count": 1,
            }
        },
    )


class DocumentViewerInfo(BaseModel):
    """Document viewer URL schema."""

    viewer_url: str


class ReviewDocumentDetailResponse(BaseModel):
    """Response schema for GET /api/documents/{id}."""

    document_id: int
    file_name: str
    file_type: str
    status: str
    document_type: Optional[str] = None
    document_type_label: Optional[str] = None
    document: DocumentViewerInfo
    fields: Dict[str, ReviewFieldItem] = Field(default_factory=dict)
    validation_errors: List[str] = Field(default_factory=list)
    processing_errors: List[str] = Field(default_factory=list)
    raw_text: Optional[str] = None
    confidence_score: Optional[float] = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "document_id": 123,
                "file_name": "certificate.pdf",
                "file_type": "PDF",
                "status": "NEEDS_REVIEW",
                "document": {
                    "viewer_url": "/api/documents/123/file",
                },
                "fields": {
                    "student_name": {
                        "value": "Prathmesh Gawade",
                        "normalized_value": "Prathmesh Gawade",
                        "confidence": 0.96,
                        "source": "ocr",
                        "validation_errors": [],
                    },
                    "roll_number": {
                        "value": "19",
                        "normalized_value": "19",
                        "confidence": 0.61,
                        "source": "ocr",
                        "validation_errors": [],
                    },
                    "percentage": {
                        "value": None,
                        "normalized_value": None,
                        "confidence": None,
                        "source": None,
                        "validation_errors": [
                            "percentage is missing"
                        ],
                    },
                },
                "validation_errors": [
                    "percentage is missing"
                ],
                "processing_errors": [],
                "raw_text": "Name: Prathmesh Gawade\nRoll: 19",
                "confidence_score": 0.785,
            }
        },
    )


class VerifyDocumentRequest(BaseModel):
    """Request schema for POST /api/documents/{id}/verify."""

    fields: Dict[str, Any] = Field(
        description="Corrected/added fields dictionary (strings or dicts).",
    )
    reviewer_id: Optional[str] = Field(
        default="reviewer",
        description="Identifier of the human reviewer",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional reviewer notes",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "fields": {
                    "student_name": "Prathamesh Gawade",
                    "percentage": "82.5",
                },
                "reviewer_id": "reviewer_alice",
                "notes": (
                    "Corrected student name spelling and manually entered "
                    "percentage."
                ),
            }
        }
    )


class FieldCorrectionAudit(BaseModel):
    """Audit entry for a specific field correction."""

    field: str
    action: str  # "HUMAN_CORRECTION"
    old_value: Optional[str] = None
    new_value: Optional[str] = None


class VerifyDocumentResponse(BaseModel):
    """Response schema for POST /api/documents/{id}/verify."""

    document_id: int
    status: str  # "VERIFIED" or "NEEDS_REVIEW"
    fields: Dict[str, ReviewFieldItem]
    validation_errors: List[str] = Field(default_factory=list)
    corrections_made: List[FieldCorrectionAudit] = Field(default_factory=list)
    message: str

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "document_id": 123,
                "status": "VERIFIED",
                "fields": {
                    "student_name": {
                        "value": "Prathamesh Gawade",
                        "normalized_value": "Prathamesh Gawade",
                        "confidence": 1.0,
                        "source": "human",
                        "validation_errors": [],
                    },
                    "roll_number": {
                        "value": "19",
                        "normalized_value": "19",
                        "confidence": 0.61,
                        "source": "ocr",
                        "validation_errors": [],
                    },
                    "percentage": {
                        "value": "82.5",
                        "normalized_value": "82.5",
                        "confidence": 1.0,
                        "source": "human",
                        "validation_errors": [],
                    },
                },
                "validation_errors": [],
                "corrections_made": [
                    {
                        "field": "student_name",
                        "action": "HUMAN_CORRECTION",
                        "old_value": "Prathmesh Gawade",
                        "new_value": "Prathamesh Gawade",
                    },
                    {
                        "field": "percentage",
                        "action": "HUMAN_CORRECTION",
                        "old_value": None,
                        "new_value": "82.5",
                    },
                ],
                "message": (
                    "Document successfully verified and marked VERIFIED."
                ),
            }
        },
    )
