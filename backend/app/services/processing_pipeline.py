"""Central Document Processing Pipeline for Intelligent Document Processing.

This service acts as the orchestrator coordinating the existing services:
Uploaded Document
        ↓
File Detection
        ↓
    ┌───────────────┐
    │               │
    ▼               ▼
Digital PDF       Scanned PDF / Image
    │               │
PDF Parser          OCR
    │               │
    └───────┬───────┘
            ↓
    Field Extraction
            ↓
       AI Extraction
            ↓
    Rule + AI Reconciliation
            ↓
       Normalization
            ↓
        Validation
            ↓
 Confidence Evaluation
            ↓
         Routing
       /          \
      /            \
VERIFIED      NEEDS_REVIEW

Important Architecture Rules:
- The processing pipeline is an orchestrator; it does not duplicate the
  detailed logic of OCR, PDF parsing, field extraction, AI extraction,
  normalization, validation, or confidence calculation.
- The original uploaded file (documents.file_path) is NEVER overwritten,
  modified, or replaced. It is strictly read-only.
- Safe against partial failures and transaction-aware.
"""

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.security import sanitize_log_text
from app.database.connection import SessionLocal
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.document_record import DocumentRecord
from app.schemas.detection import FileCategory
from app.schemas.document import DocumentStatus
from app.schemas.extraction import InvoiceExtractionResult
from app.schemas.normalization import InvoiceNormalizationResult
from app.schemas.ocr import OCRResult
from app.schemas.pdf import PDFParseResult
from app.schemas.pipeline import PipelineProcessingResult, ProcessingError
from app.schemas.tabular import TabularParseResult
from app.schemas.validation import (
    RoutingDecision,
    RoutingStatus,
    ValidationResult,
)
from app.services.ai.base import AIExtractionProvider
from app.services.ai.factory import get_ai_provider
from app.services.confidence import ConfidenceRouter
from app.services.csv_excel_parser import csv_excel_parser
from app.services.detection import file_detection_service
from app.services.extraction import invoice_extractor
from app.services.normalizer import InvoiceNormalizer
from app.services.ocr_engine import ocr_engine
from app.services.pdf_parser import pdf_parser
from app.services.validator import InvoiceValidator

logger = logging.getLogger(__name__)


@dataclass
class ProcessingContext:
    """Internal processing context across document pipeline stages.

    Captures raw text, OCR bounding boxes/confidence, page data, and
    structured parser outputs into a common context for field extraction.
    """

    document_id: int
    file_path: Path
    file_type: str
    raw_text: str = ""
    text_source: str = "unknown"
    ocr_result: Optional[OCRResult] = None
    pdf_result: Optional[PDFParseResult] = None
    parsed_data: Optional[TabularParseResult] = None
    document_input: Any = None


class DocumentNotFoundError(ValueError):
    """Raised when the document ID does not exist in the database."""
    pass


class DocumentProcessingPipeline:
    """Central orchestrator for the IDP workflow."""

    def __init__(
        self,
        ai_provider: Optional[AIExtractionProvider] = None,
    ) -> None:
        self._ai_provider = ai_provider

    def process_document(
        self,
        document_id: int,
        db: Optional[Session] = None,
        ai_provider: Optional[AIExtractionProvider] = None,
    ) -> PipelineProcessingResult:
        """Execute the end-to-end document processing pipeline.

        Args:
            document_id: Database primary key of the Document record.
            db: Optional active SQLAlchemy Session. If omitted, a session
                is created and closed automatically.
            ai_provider: Optional AI extraction provider override.

        Returns:
            PipelineProcessingResult: Comprehensive structured outcome.

        Raises:
            DocumentNotFoundError: If the document_id is not in the database.
        """
        session: Session
        close_session: bool

        if db is None:
            session = SessionLocal()
            close_session = True
        else:
            session = db
            close_session = False

        try:
            return self._execute_pipeline(
                document_id=document_id,
                session=session,
                ai_provider_override=ai_provider,
            )
        finally:
            if close_session:
                session.close()

    def _execute_pipeline(
        self,
        document_id: int,
        session: Session,
        ai_provider_override: Optional[AIExtractionProvider] = None,
    ) -> PipelineProcessingResult:
        """Internal execution method running within a session context."""

        # ---------------------------------------------------------------------
        # 1. Load Document Record
        # ---------------------------------------------------------------------
        document: Optional[Document] = (
            session.query(Document).filter(Document.id == document_id).first()
        )
        if not document:
            err_msg = (
                f"Document with ID {document_id} does not exist in database."
            )
            logger.error(err_msg)
            raise DocumentNotFoundError(err_msg)

        logger.info(
            f"Pipeline start for document ID={document.id}, "
            f"file='{document.file_name}'"
        )

        # ---------------------------------------------------------------------
        # 2. Verify Original File Existence (Never Overwrite Original File)
        # ---------------------------------------------------------------------
        file_path = Path(document.file_path)
        if not file_path.exists() or not file_path.is_file():
            err_msg = (
                f"Original file not found on disk at '{document.file_path}'"
            )
            logger.error(err_msg)
            document.status = DocumentStatus.FAILED.value
            document.error_message = err_msg
            proc_err = ProcessingError(
                stage="STORAGE",
                code="FILE_NOT_FOUND",
                message=err_msg,
            )
            audit_fail = AuditLog(
                document_id=document.id,
                action="PROCESSING_FAILED",
                actor="pipeline",
                details={
                    "stage": "STORAGE",
                    "code": proc_err.code,
                    "message": proc_err.message,
                },
            )
            session.add(audit_fail)
            session.commit()
            return PipelineProcessingResult(
                document_id=document.id,
                file_name=document.file_name,
                file_type=document.file_type or "UNKNOWN",
                status=DocumentStatus.FAILED.value,
                success=False,
                error=err_msg,
                processing_errors=[proc_err],
            )

        # ---------------------------------------------------------------------
        # 3. Update Processing Status to PROCESSING & Log Event
        # ---------------------------------------------------------------------
        document.status = DocumentStatus.PROCESSING.value
        document.error_message = None
        audit_start = AuditLog(
            document_id=document.id,
            action="PROCESSING_STARTED",
            actor="pipeline",
            details={
                "file_name": document.file_name,
                "status": DocumentStatus.PROCESSING.value,
            },
        )
        session.add(audit_start)
        session.commit()

        processing_errors: List[ProcessingError] = []

        try:
            # -----------------------------------------------------------------
            # 4. File Detection
            # -----------------------------------------------------------------
            detection_res = file_detection_service.detect_file_type(
                file_path=str(file_path),
                original_filename=document.file_name,
            )

            is_unsupported = (
                not detection_res.is_supported
                or detection_res.category == FileCategory.UNSUPPORTED
            )
            if is_unsupported:
                err_msg = f"Unsupported file type: {detection_res.details}"
                logger.warning(
                    f"Document ID={document.id} rejected: {err_msg}"
                )
                document.status = DocumentStatus.FAILED.value
                document.error_message = err_msg
                proc_err = ProcessingError(
                    stage="DETECTION",
                    code="UNSUPPORTED_FILE_TYPE",
                    message=err_msg,
                )
                audit_fail = AuditLog(
                    document_id=document.id,
                    action="PROCESSING_FAILED",
                    actor="pipeline",
                    details={
                        "stage": "DETECTION",
                        "code": proc_err.code,
                        "message": proc_err.message,
                    },
                )
                session.add(audit_fail)
                session.commit()
                return PipelineProcessingResult(
                    document_id=document.id,
                    file_name=document.file_name,
                    file_type=detection_res.category.value,
                    status=DocumentStatus.FAILED.value,
                    success=False,
                    error=err_msg,
                    processing_errors=[proc_err],
                )

            # Update document file_type with detected category

            detected_category = detection_res.category
            document.file_type = detected_category.value
            session.commit()

            # -----------------------------------------------------------------
            # 5. Route to Text / OCR Extraction Path & Text Preparation
            # -----------------------------------------------------------------
            context = ProcessingContext(
                document_id=document.id,
                file_path=file_path,
                file_type=detected_category.value,
            )

            if detected_category == FileCategory.PDF:
                pdf_res = pdf_parser.parse_pdf(file_path)
                has_usable_digital_text = (
                    pdf_res.success
                    and pdf_res.has_extractable_text
                    and not pdf_res.likely_scanned
                )
                if has_usable_digital_text:
                    # Path: Digital PDF
                    context.pdf_result = pdf_res
                    context.raw_text = pdf_res.combined_text
                    context.document_input = pdf_res
                    context.text_source = "digital_pdf"
                    logger.info(
                        f"Doc ID={document.id} routed to Digital PDF Parser"
                    )
                else:
                    # Path: Scanned PDF -> Fallback to OCR
                    ocr_res = ocr_engine.perform_ocr(file_path)
                    context.ocr_result = ocr_res
                    context.raw_text = self._extract_doc_text(ocr_res)
                    context.document_input = ocr_res
                    context.text_source = "ocr_scanned_pdf"
                    logger.info(
                        f"Doc ID={document.id} routed to OCR (Scanned PDF)"
                    )

            elif detected_category == FileCategory.IMAGE:
                # Path: Image OCR
                ocr_res = ocr_engine.perform_ocr(file_path)
                context.ocr_result = ocr_res
                context.raw_text = self._extract_doc_text(ocr_res)
                context.document_input = ocr_res
                context.text_source = "ocr_image"
                logger.info(
                    f"Doc ID={document.id} routed to OCR Engine (Image)"
                )
            elif detected_category in (FileCategory.CSV, FileCategory.EXCEL):
                # Path: Tabular file (CSV/Excel Parser -> Structured Records)
                tabular_res = csv_excel_parser.parse_csv_or_excel(file_path)
                context.parsed_data = tabular_res
                context.raw_text = self._format_tabular_text(tabular_res)
                context.document_input = context.raw_text
                context.text_source = "tabular"
                logger.info(
                    f"Doc ID={document.id} routed to CSV/Excel Parser"
                )

            raw_text = context.raw_text
            text_source = context.text_source

            # -----------------------------------------------------------------
            # 6. Field Extraction + AI Extraction + Reconciliation
            # -----------------------------------------------------------------
            effective_ai = (
                ai_provider_override
                or self._ai_provider
                or get_ai_provider()
            )

            extraction_context: Dict[str, Any] = {
                "document_id": document.id,
                "file_name": document.file_name,
                "file_type": detected_category.value,
                "document_type": "invoice",
            }

            extraction_result: InvoiceExtractionResult = (
                invoice_extractor.extract(
                    document_input=context.document_input,
                    ai_provider=effective_ai,
                    context=extraction_context,
                )
            )

            # -----------------------------------------------------------------
            # 7. Data Normalization
            # -----------------------------------------------------------------
            normalization_result: InvoiceNormalizationResult = (
                InvoiceNormalizer.normalize_invoice(extraction_result)
            )

            # -----------------------------------------------------------------
            # 8. Business Rule Validation
            # -----------------------------------------------------------------
            date_field = normalization_result.invoice_date
            raw_date = self._get_field_value(extraction_result.invoice_date)
            norm_date = (
                date_field.normalized_value
                if date_field.success and date_field.normalized_value
                else raw_date
            )

            amt_field = normalization_result.total_amount
            raw_amount = self._get_field_value(extraction_result.total_amount)
            norm_amount = (
                amt_field.normalized_value
                if amt_field.success and amt_field.normalized_value
                else raw_amount
            )

            val_vendor = self._get_field_value(
                extraction_result.vendor_name
            )
            val_number = self._get_field_value(
                extraction_result.invoice_number
            )

            validation_result: ValidationResult = (
                InvoiceValidator.validate_invoice(
                    vendor_name=val_vendor,
                    invoice_number=val_number,
                    invoice_date=norm_date,
                    total_amount=norm_amount,
                )
            )

            # Integrate normalization failures into validation if present
            if not normalization_result.success:
                for norm_err in normalization_result.errors:
                    if norm_err not in validation_result.errors:
                        validation_result.errors.append(norm_err)
                        validation_result.is_valid = False

            # -----------------------------------------------------------------
            # 9. Confidence Evaluation and Routing
            # -----------------------------------------------------------------
            routing_decision: RoutingDecision = (
                ConfidenceRouter.evaluate_and_route(
                    validation_result=validation_result,
                    field_confidences=extraction_result.field_confidence,
                )
            )

            final_status = routing_decision.status.value
            review_reason_str = (
                "; ".join(routing_decision.review_reasons)
                if routing_decision.review_reasons
                else None
            )

            # -----------------------------------------------------------------
            # 10. Persist Results (Transaction-Aware)
            # -----------------------------------------------------------------
            # Extract values, scores, and sources safely
            v_val = val_vendor
            v_conf = extraction_result.field_confidence.get(
                "vendor_name", 0.0
            )
            v_src = self._get_field_source("vendor_name", extraction_result)

            num_val = val_number
            num_conf = extraction_result.field_confidence.get(
                "invoice_number", 0.0
            )
            num_src = self._get_field_source(
                "invoice_number", extraction_result
            )

            d_raw = (
                normalization_result.invoice_date.original_value or raw_date
            )
            d_norm = normalization_result.invoice_date.normalized_value
            d_conf = extraction_result.field_confidence.get(
                "invoice_date", 0.0
            )
            d_src = self._get_field_source("invoice_date", extraction_result)

            a_raw = (
                normalization_result.total_amount.original_value or raw_amount
            )
            a_norm = normalization_result.total_amount.normalized_value
            a_conf = extraction_result.field_confidence.get(
                "total_amount", 0.0
            )
            a_src = self._get_field_source("total_amount", extraction_result)

            structured_data: Dict[str, Any] = {
                "fields": {
                    "vendor_name": {
                        "field": "vendor_name",
                        "original_value": v_val,
                        "value": v_val,
                        "normalized_value": v_val,
                        "confidence": v_conf,
                        "source": v_src,
                    },
                    "invoice_number": {
                        "field": "invoice_number",
                        "original_value": num_val,
                        "value": num_val,
                        "normalized_value": num_val,
                        "confidence": num_conf,
                        "source": num_src,
                    },
                    "invoice_date": {
                        "field": "invoice_date",
                        "original_value": d_raw,
                        "value": d_raw,
                        "normalized_value": d_norm,
                        "confidence": d_conf,
                        "source": d_src,
                    },
                    "total_amount": {
                        "field": "total_amount",
                        "original_value": a_raw,
                        "value": a_raw,
                        "normalized_value": a_norm,
                        "confidence": a_conf,
                        "source": a_src,
                    },
                },
                "field_confidence": extraction_result.field_confidence,
                "normalization": {
                    "success": normalization_result.success,
                    "errors": normalization_result.errors,
                },
                "validation": {
                    "is_valid": validation_result.is_valid,
                    "errors": validation_result.errors,
                    "field_errors": validation_result.field_errors,
                },
                "routing": {
                    "status": final_status,
                    "overall_confidence": routing_decision.overall_confidence,
                    "threshold": routing_decision.threshold,
                    "review_reasons": routing_decision.review_reasons,
                },
                "candidates": {
                    f: [
                        c.model_dump() if hasattr(c, "model_dump") else c.dict() if hasattr(c, "dict") else dict(c)
                        for c in (cands or [])
                    ]
                    for f, cands in (extraction_result.candidates or {}).items()
                },
                "text_source": text_source,
            }

            # Update Document status
            document.status = final_status
            document.error_message = review_reason_str

            # Upsert DocumentRecord
            record: Optional[DocumentRecord] = (
                session.query(DocumentRecord)
                .filter(DocumentRecord.document_id == document.id)
                .first()
            )
            if not record:
                record = DocumentRecord(document_id=document.id)
                session.add(record)

            record.document_type = "invoice"
            record.extraction_status = final_status
            record.raw_text = raw_text
            record.confidence_score = routing_decision.overall_confidence
            record.error_message = review_reason_str
            record.extracted_data = structured_data

            # Add Audit Log entry: PROCESSING_COMPLETED or ROUTED_TO_REVIEW
            action_name = (
                "ROUTED_TO_REVIEW"
                if final_status == RoutingStatus.NEEDS_REVIEW.value
                else "PROCESSING_COMPLETED"
            )
            audit = AuditLog(
                document_id=document.id,
                action=action_name,
                actor="pipeline",
                details={
                    "status": final_status,
                    "overall_confidence": routing_decision.overall_confidence,
                    "is_valid": routing_decision.is_valid,
                    "review_reasons": routing_decision.review_reasons,
                    "text_source": text_source,
                },
            )
            session.add(audit)

            # Commit database transaction
            session.commit()
            session.refresh(document)
            session.refresh(record)

            logger.info(
                f"Doc ID={document.id} complete: status={final_status}, "
                f"conf={routing_decision.overall_confidence}"
            )

            # -----------------------------------------------------------------
            # 11. Return Structured Result
            # -----------------------------------------------------------------
            is_review = final_status == RoutingStatus.NEEDS_REVIEW.value
            return PipelineProcessingResult(
                document_id=document.id,
                file_name=document.file_name,
                file_type=document.file_type,
                status=final_status,
                success=True,
                error=review_reason_str if is_review else None,
                processing_errors=processing_errors,
                routing_decision=routing_decision,
                validation=validation_result,
                normalization=normalization_result,
                extraction=extraction_result,
                extracted_data=structured_data,
                confidence_score=routing_decision.overall_confidence,
                raw_text=raw_text,
                text_source=text_source,
                record_id=record.id,
            )

        except Exception as exc:
            raw_err_msg = str(exc)
            clean_err_msg = sanitize_log_text(raw_err_msg)
            logger.error(
                f"Pipeline error for doc ID={document.id}: {clean_err_msg}",
                exc_info=True,
            )
            session.rollback()

            tech_err = ProcessingError(
                stage="PIPELINE_EXECUTION",
                code="UNHANDLED_EXCEPTION",
                message=clean_err_msg,
            )

            try:
                document.status = DocumentStatus.FAILED.value
                document.error_message = clean_err_msg
                audit_fail = AuditLog(
                    document_id=document.id,
                    action="PROCESSING_FAILED",
                    actor="pipeline",
                    details={
                        "stage": "PIPELINE_EXECUTION",
                        "code": tech_err.code,
                        "message": tech_err.message,
                    },
                )
                session.add(audit_fail)
                session.commit()
            except Exception as commit_exc:
                logger.error(
                    f"Failed to record FAILED status on doc {document.id}: "
                    f"{commit_exc}"
                )
                session.rollback()

            return PipelineProcessingResult(
                document_id=document.id,
                file_name=document.file_name,
                file_type=document.file_type or "UNKNOWN",
                status=DocumentStatus.FAILED.value,
                success=False,
                error=clean_err_msg,
                processing_errors=[tech_err],
            )

    @classmethod
    def _format_tabular_text(cls, tabular_result: TabularParseResult) -> str:

        """Format tabular rows into clear text representations."""
        lines = []
        for sheet in tabular_result.sheets:
            if sheet.sheet_name:
                lines.append(f"Sheet: {sheet.sheet_name}")
            if sheet.columns:
                lines.append(" | ".join(sheet.columns))
            for rec in sheet.records:
                row_items = [
                    f"{k}: {v}"
                    for k, v in rec.items()
                    if v is not None and str(v).strip()
                ]
                if row_items:
                    lines.append(", ".join(row_items))
        return "\n".join(lines)

    @staticmethod
    def _extract_doc_text(doc_res: Any) -> str:
        """Extract text content from PDFParseResult, OCRResult, or string."""
        if not doc_res:
            return ""
        if isinstance(doc_res, str):
            return doc_res
        if hasattr(doc_res, "combined_text") and doc_res.combined_text:
            return str(doc_res.combined_text)
        if hasattr(doc_res, "full_text") and doc_res.full_text:
            return str(doc_res.full_text)
        if hasattr(doc_res, "raw_text") and doc_res.raw_text:
            return str(doc_res.raw_text)
        return ""

    @staticmethod
    def _get_field_value(field: Any) -> Optional[str]:
        """Safely extract underlying string value."""
        if field is None:
            return None
        if hasattr(field, "value"):
            return str(field.value) if field.value is not None else None
        return str(field)

    @staticmethod
    def _get_field_source(
        field_name: str,
        extraction_result: InvoiceExtractionResult,
    ) -> Optional[str]:
        """Extract candidate source flag ('rule', 'ai', 'rule+ai')."""
        ext_fields = getattr(extraction_result, "extracted_fields", None)
        if ext_fields and isinstance(ext_fields, dict):
            cand = ext_fields.get(field_name)
            if cand and hasattr(cand, "source") and cand.source:
                return str(cand.source)
        field_obj = getattr(extraction_result, field_name, None)
        if field_obj and hasattr(field_obj, "source") and field_obj.source:
            return str(field_obj.source)
        return None


# Global singleton instance
pipeline = DocumentProcessingPipeline()


# Module-level convenience function
process_document = pipeline.process_document

__all__ = [
    "ProcessingContext",
    "DocumentProcessingPipeline",
    "DocumentNotFoundError",
    "pipeline",
    "process_document",
]
