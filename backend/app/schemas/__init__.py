"""Pydantic validation and serialization schemas package."""

from app.schemas.audit import (
    AuditLogBase,
    AuditLogCreate,
    AuditLogListResponse,
    AuditLogResponse,
)
from app.schemas.common import ErrorResponse, MessageResponse
from app.schemas.detection import DetectionResult, FileCategory
from app.schemas.document import (
    DocumentBase,
    DocumentCreate,
    DocumentListResponse,
    DocumentResponse,
    DocumentStatus,
    DocumentUpdate,
    DocumentUploadResponse,
)
from app.schemas.record import (
    DocumentRecordBase,
    DocumentRecordCreate,
    DocumentRecordResponse,
    DocumentRecordUpdate,
    DocumentWithRecordResponse,
    ExtractionStatus,
)
from app.schemas.ocr import (
    OCRBoundingBox,
    OCRPageData,
    OCRResult,
    OCRWordData,
)
from app.schemas.pdf import PDFPageData, PDFParseResult
from app.schemas.tabular import SheetData, TabularParseResult
from app.schemas.extraction import (
    ExtractedField,
    FieldCandidate,
    InvoiceExtractionResult,
)
from app.schemas.llm import (
    DocumentTypeConfig,
    FieldExtractionValue,
    FieldSpecification,
    LLMExtractionResult,
    LLMExtractionStatus,
)
from app.schemas.normalization import (
    InvoiceNormalizationResult,
    NormalizedField,
)
from app.schemas.validation import (
    ConfidenceEvaluationResult,
    FieldConfidenceInfo,
    RoutingDecision,
    RoutingStatus,
    ValidationResult,
)
from app.schemas.pipeline import PipelineProcessingResult, ProcessingError
from app.schemas.processing import (
    ProcessingFieldResult,
    ProcessingResult,
    to_processing_result,
)

from app.schemas.review import (
    DocumentViewerInfo,
    FieldCorrectionAudit,
    ReviewDocumentDetailResponse,
    ReviewDocumentSummary,
    ReviewFieldItem,
    ReviewListResponse,
    VerifyDocumentRequest,
    VerifyDocumentResponse,
)
from app.schemas.dashboard import (
    DashboardDocumentItem,
    DashboardDocumentListResponse,
    DashboardStatsResponse,
    DocumentListItem,
    DocumentStatsResponse,
)

__all__ = [
    # Common
    "ErrorResponse",
    "MessageResponse",
    # Detection
    "FileCategory",
    "DetectionResult",
    # Document
    "DocumentStatus",
    "DocumentBase",
    "DocumentCreate",
    "DocumentUpdate",
    "DocumentResponse",
    "DocumentUploadResponse",
    "DocumentListResponse",
    # Record
    "ExtractionStatus",
    "DocumentRecordBase",
    "DocumentRecordCreate",
    "DocumentRecordUpdate",
    "DocumentRecordResponse",
    "DocumentWithRecordResponse",
    # Tabular (CSV & Excel)
    "SheetData",
    "TabularParseResult",
    # PDF
    "PDFPageData",
    "PDFParseResult",
    # OCR
    "OCRBoundingBox",
    "OCRWordData",
    "OCRPageData",
    "OCRResult",
    # Extraction
    "ExtractedField",
    "FieldCandidate",
    "InvoiceExtractionResult",
    # LLM Multi-Document Extraction
    "FieldSpecification",
    "DocumentTypeConfig",
    "FieldExtractionValue",
    "LLMExtractionResult",
    "LLMExtractionStatus",
    # Normalization
    "NormalizedField",
    "InvoiceNormalizationResult",
    # Validation & Routing
    "ValidationResult",
    "FieldConfidenceInfo",
    "ConfidenceEvaluationResult",
    "RoutingStatus",
    "RoutingDecision",
    # Pipeline & Processing
    "PipelineProcessingResult",
    "ProcessingError",
    "ProcessingFieldResult",
    "ProcessingResult",
    "to_processing_result",
    # HITL Review & Verification
    "ReviewFieldItem",
    "ReviewDocumentSummary",
    "ReviewListResponse",
    "DocumentViewerInfo",
    "ReviewDocumentDetailResponse",
    "VerifyDocumentRequest",
    "FieldCorrectionAudit",
    "VerifyDocumentResponse",
    # Dashboard
    "DashboardDocumentItem",
    "DashboardDocumentListResponse",
    "DashboardStatsResponse",
    "DocumentListItem",
    "DocumentListResponse",
    "DocumentStatsResponse",
    # Audit
    "AuditLogBase",
    "AuditLogCreate",
    "AuditLogResponse",
    "AuditLogListResponse",
]
