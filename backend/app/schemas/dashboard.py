"""Schemas for the Dashboard backend APIs.

Supports:
- Paginated document listing with filtering & search (GET /api/documents)
- Dashboard summary statistics (GET /api/documents/stats)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DashboardDocumentItem(BaseModel):
    """Document summary item returned in the dashboard table list."""

    document_id: int = Field(description="Unique document database ID")
    id: Optional[int] = Field(
        default=None,
        description="Alias for document_id for backwards compatibility",
    )
    file_name: str = Field(description="Original filename of the document")
    file_type: str = Field(description="File format (e.g. PDF, IMAGE, CSV)")
    file_size: Optional[int] = Field(
        default=None,
        description="File size in bytes",
    )
    status: str = Field(description="Current processing status")
    document_type: Optional[str] = Field(
        default=None,
        description="Classified document type (e.g. invoice, certificate)",
    )
    vendor_name: Optional[str] = Field(
        default=None,
        description="Extracted vendor name if available",
    )
    invoice_number: Optional[str] = Field(
        default=None,
        description="Extracted invoice number if available",
    )
    total_amount: Optional[str] = Field(
        default=None,
        description="Extracted total amount if available",
    )
    invoice_date: Optional[str] = Field(
        default=None,
        description="Extracted invoice or document date if available",
    )
    confidence: Optional[float] = Field(
        default=None,
        description="Overall model extraction confidence score",
    )
    confidence_score: Optional[float] = Field(
        default=None,
        description="Alias for confidence score",
    )
    uploaded_at: datetime = Field(
        description="Timestamp when the document was uploaded"
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of latest processing/review update",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Review reason or failure message if applicable",
    )
    fields: Dict[str, Any] = Field(
        default_factory=dict,
        description="Universal dictionary of extracted field values",
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "document_id": 123,
                "id": 123,
                "file_name": "invoice_001.pdf",
                "file_type": "PDF",
                "file_size": 245000,
                "status": "NEEDS_REVIEW",
                "document_type": "invoice",
                "vendor_name": "ABC Technologies",
                "invoice_number": "INV-1001",
                "total_amount": "25500.00",
                "invoice_date": "2026-09-05",
                "confidence": 0.82,
                "confidence_score": 0.82,
                "uploaded_at": "2026-09-25T10:30:00Z",
                "updated_at": "2026-09-25T10:35:00Z",
                "error_message": None,
                "fields": {
                    "vendor_name": "ABC Technologies",
                    "invoice_number": "INV-1001",
                    "invoice_date": "2026-09-05",
                    "total_amount": "25500.00",
                },
            }
        },
    )


class DashboardDocumentListResponse(BaseModel):
    """Paginated response schema for GET /api/documents."""

    items: List[DashboardDocumentItem] = Field(
        default_factory=list,
        description="List of document items for the current page",
    )
    page: int = Field(
        ...,
        ge=1,
        description="Current page number (1-indexed)",
    )
    page_size: int = Field(
        ...,
        ge=1,
        le=100,
        description="Number of items per page",
    )
    total: int = Field(
        ...,
        ge=0,
        description="Total count of documents matching filter criteria",
    )
    total_pages: int = Field(
        ...,
        ge=0,
        description="Total number of pages (0 if total is 0)",
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "items": [
                    {
                        "id": 101,
                        "file_name": "invoice_1001.pdf",
                        "file_type": "PDF",
                        "file_size": 245000,
                        "status": "VERIFIED",
                        "document_type": "invoice",
                        "vendor_name": "ABC Technologies",
                        "invoice_number": "INV-1001",
                        "total_amount": "25500.00",
                        "invoice_date": "2026-09-05",
                        "confidence_score": 0.945,
                        "uploaded_at": "2026-09-25T14:30:00Z",
                        "error_message": None,
                        "fields": {
                            "vendor_name": "ABC Technologies",
                            "invoice_number": "INV-1001",
                            "total_amount": "25500.00",
                        },
                    }
                ],
                "page": 1,
                "page_size": 20,
                "total": 125,
                "total_pages": 7,
            }
        },
    )


class FieldMetricItem(BaseModel):
    """Field-level extraction performance metrics."""

    field_name: str = Field(description="System identifier of the field")
    label: str = Field(description="Human-readable label for the field")
    detected_count: int = Field(default=0, description="Number of times field was extracted")
    total_evaluated: int = Field(default=0, description="Total records evaluated for this field")
    detection_rate: float = Field(default=0.0, description="Percentage of records where field was found (0-100)")
    average_confidence: float = Field(default=0.0, description="Average confidence score for this field (0-1)")
    sources: Dict[str, int] = Field(default_factory=dict, description="Counts by extraction source (e.g. rule, ai, ocr)")


class ExtractionRecordAnalytics(BaseModel):
    """Aggregated analytics computed across all files extraction records."""

    total_records: int = Field(default=0, description="Total document records in database")
    automation_rate: float = Field(default=0.0, description="Straight-Through Processing automation percentage")
    average_confidence: float = Field(default=0.0, description="Mean extraction confidence across records")
    high_confidence_count: int = Field(default=0, description="Count of extractions with confidence >= 0.85")
    review_required_count: int = Field(default=0, description="Count of extractions needing human triage")
    fields_breakdown: List[FieldMetricItem] = Field(default_factory=list, description="Performance per extracted field")
    text_sources: Dict[str, int] = Field(default_factory=dict, description="Distribution of extraction channels (OCR, PDF, etc)")
    confidence_tiers: Dict[str, int] = Field(default_factory=dict, description="Tier counts (high, medium, low)")


class DashboardStatsResponse(BaseModel):
    """Summary statistics response schema for GET /api/documents/stats.

    total_processed represents successfully processed documents:
    VERIFIED + NEEDS_REVIEW.
    """

    total_processed: int = Field(
        default=0,
        ge=0,
        description=(
            "Total number of successfully processed documents "
            "(VERIFIED + NEEDS_REVIEW)"
        ),
    )
    total_verified: int = Field(
        default=0,
        ge=0,
        description="Total number of verified documents (status = VERIFIED)",
    )
    total_needing_review: int = Field(
        default=0,
        ge=0,
        description=(
            "Total number of documents requiring human review "
            "(status = NEEDS_REVIEW)"
        ),
    )
    average_confidence: Optional[float] = Field(
        default=None,
        description=(
            "Average confidence score across processed documents "
            "(4 decimals), or null if no confidence values exist"
        ),
    )
    total_failed: int = Field(
        default=0,
        ge=0,
        description="Total number of failed documents (status = FAILED)",
    )
    total_documents: int = Field(
        default=0,
        ge=0,
        description="Total number of documents in the system",
    )
    verified_count: Optional[int] = Field(
        default=None,
        ge=0,
        description="Alias for total_verified",
    )
    needs_review_count: Optional[int] = Field(
        default=None,
        ge=0,
        description="Alias for total_needing_review",
    )
    failed_count: Optional[int] = Field(
        default=None,
        ge=0,
        description="Alias for total_failed",
    )
    processing_count: int = Field(
        default=0,
        ge=0,
        description="Number of documents currently processing",
    )
    uploaded_count: int = Field(
        default=0,
        ge=0,
        description="Number of documents waiting to be processed",
    )
    by_status: Dict[str, int] = Field(
        default_factory=dict,
        description="Count breakdown by document status",
    )
    by_document_type: Dict[str, int] = Field(
        default_factory=dict,
        description="Count breakdown by document format or classified type",
    )
    accuracy_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Percentage of processed documents successfully verified",
    )
    extraction_analytics: Optional[ExtractionRecordAnalytics] = Field(
        default=None,
        description="Comprehensive files extraction record analytics",
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "total_processed": 117,
                "total_verified": 95,
                "total_needing_review": 22,
                "average_confidence": 0.924,
                "total_failed": 5,
                "total_documents": 125,
                "verified_count": 95,
                "needs_review_count": 22,
                "failed_count": 5,
                "processing_count": 1,
                "uploaded_count": 2,
                "by_status": {
                    "VERIFIED": 95,
                    "NEEDS_REVIEW": 22,
                    "FAILED": 5,
                    "PROCESSING": 1,
                    "UPLOADED": 2,
                },
                "by_document_type": {
                    "PDF": 85,
                    "IMAGE": 25,
                    "CSV": 10,
                    "EXCEL": 5,
                },
                "accuracy_rate": 81.2,
            }
        },
    )


# Standard naming aliases matching existing project conventions
DocumentListItem = DashboardDocumentItem
DocumentListResponse = DashboardDocumentListResponse
DocumentStatsResponse = DashboardStatsResponse
