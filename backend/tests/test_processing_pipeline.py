"""Unit and integration tests for Central Document Processing Pipeline.

Covers:
1. Orchestration of existing services:
   Uploaded Document -> Detection -> Digital / Scanned PDF / Image / Tabular
   -> Field Extraction -> AI Extraction -> Reconciliation -> Normalization
   -> Validation -> Confidence Evaluation -> Routing.

2. Database persistence into Document, DocumentRecord, and AuditLog.
3. Verification checks: document exists, original file exists.
4. Integrity guarantee: original uploaded file is NEVER modified/overwritten.
5. Error handling and safe failure isolation (FAILED status on missing file,
   unsupported format, or unexpected exceptions).
6. Idempotency: re-processing updates existing DocumentRecord.
"""

import hashlib
from pathlib import Path
import shutil
import tempfile
from typing import Generator
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database.connection import Base
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.document_record import DocumentRecord
from app.schemas.extraction import ExtractedField, InvoiceExtractionResult
from app.schemas.ocr import OCRResult
from app.schemas.pdf import PDFPageData, PDFParseResult
from app.schemas.pipeline import PipelineProcessingResult
from app.schemas.tabular import SheetData, TabularParseResult
from app.schemas.validation import RoutingStatus
from app.services.ai.base import MockAIExtractionProvider
from app.services.extraction import invoice_extractor
from app.services.processing_pipeline import (
    DocumentNotFoundError,
    DocumentProcessingPipeline,
    pipeline,
    process_document,
)


# =============================================================================
# Test Database Fixtures (In-Memory SQLite)
# =============================================================================

@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Create an isolated, in-memory SQLite database session for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def temp_workspace() -> Generator[Path, None, None]:
    """Create a temporary directory for file processing tests."""
    temp_dir = tempfile.mkdtemp(prefix="idp_test_pipeline_")
    path = Path(temp_dir)
    try:
        yield path
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# =============================================================================
# Helper Utilities
# =============================================================================

def create_sample_pdf(
    file_path: Path,
    content_bytes: bytes = b"%PDF-1.4 sample pdf content",
) -> Path:
    """Write dummy PDF bytes with valid %PDF- magic header."""
    file_path.write_bytes(content_bytes)
    return file_path


def create_sample_image(file_path: Path) -> Path:
    """Write dummy PNG bytes with valid PNG magic header."""
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01"
    )
    file_path.write_bytes(png_bytes)
    return file_path


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 digest of a file to verify zero alteration."""
    hasher = hashlib.sha256()
    hasher.update(file_path.read_bytes())
    return hasher.hexdigest()


# =============================================================================
# Test Suite: Central Document Processing Pipeline
# =============================================================================

class TestDocumentProcessingPipeline:
    """Test suite for DocumentProcessingPipeline orchestrator."""

    def test_pipeline_instance_and_convenience_function(self):
        """Verify singleton instance and top-level process_document."""
        assert isinstance(pipeline, DocumentProcessingPipeline)

        assert callable(process_document)

    def test_document_not_found_raises_error(self, db_session: Session):
        """Verify querying non-existent document ID raises error."""
        pipe = DocumentProcessingPipeline()
        with pytest.raises(DocumentNotFoundError) as exc_info:
            pipe.process_document(document_id=999999, db=db_session)
        assert "999999" in str(exc_info.value)

    def test_original_file_missing_marks_failed(self, db_session: Session):
        """Verify pipeline handles missing file on disk safely."""
        doc = Document(
            file_name="missing_invoice.pdf",
            file_path="c:/non_existent_folder/missing_invoice.pdf",
            file_type="PDF",
            file_size=1024,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        pipe = DocumentProcessingPipeline()
        res: PipelineProcessingResult = pipe.process_document(
            doc.id, db=db_session
        )

        assert res.success is False
        assert res.status == "FAILED"
        assert "not found on disk" in res.error

        # Verify DB document status
        db_session.refresh(doc)
        assert doc.status == "FAILED"
        assert "not found on disk" in doc.error_message

    def test_unsupported_file_type_marks_failed(
        self,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Verify unsupported file type results in clean FAILED status."""
        bad_file = temp_workspace / "archive.zip"
        bad_file.write_bytes(b"PK\x03\x04random unsupported bytes")

        doc = Document(
            file_name="archive.zip",
            file_path=str(bad_file),
            file_type="UNSUPPORTED",
            file_size=bad_file.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        pipe = DocumentProcessingPipeline()
        res = pipe.process_document(doc.id, db=db_session)

        assert res.success is False
        assert res.status == "FAILED"
        assert "Unsupported file type" in res.error

        db_session.refresh(doc)
        assert doc.status == "FAILED"

    def test_digital_pdf_verified_workflow(
        self,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test happy-path: Digital PDF -> PDF Parser -> VERIFIED."""
        pdf_path = create_sample_pdf(temp_workspace / "digital_invoice.pdf")

        doc = Document(
            file_name="digital_invoice.pdf",
            file_path=str(pdf_path),
            file_type="PDF",
            file_size=pdf_path.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        invoice_text = (
            "Acme Corp Invoice INV-2026-001 "
            "Date: 05/09/2026 Total: Rs. 25,500.00"
        )
        mock_pdf_result = PDFParseResult(
            success=True,
            status="TEXT_EXTRACTED",
            file_type="PDF",
            page_count=1,
            total_pages=1,
            combined_text=invoice_text,
            full_text=invoice_text,
            has_extractable_text=True,
            likely_scanned=False,
            pages=[
                PDFPageData(
                    page_number=1,
                    text=invoice_text,
                    has_text=True,
                )
            ],
        )

        mock_extraction = InvoiceExtractionResult(
            success=True,
            vendor_name="Acme Corp",
            invoice_number="INV-2026-001",
            invoice_date="05/09/2026",
            total_amount="Rs. 25,500.00",
            extracted_fields={
                "vendor_name": ExtractedField(
                    value="Acme Corp", confidence=0.96, source="rule+ai"
                ),
                "invoice_number": ExtractedField(
                    value="INV-2026-001", confidence=0.94, source="rule+ai"
                ),
                "invoice_date": ExtractedField(
                    value="05/09/2026", confidence=0.91, source="rule"
                ),
                "total_amount": ExtractedField(
                    value="Rs. 25,500.00", confidence=0.97, source="ai"
                ),
            },
            field_confidence={
                "vendor_name": 0.96,
                "invoice_number": 0.94,
                "invoice_date": 0.91,
                "total_amount": 0.97,
            },
            fields_found=[
                "vendor_name",
                "invoice_number",
                "invoice_date",
                "total_amount",
            ],
            missing_fields=[],
            errors=[],
        )

        pipe = DocumentProcessingPipeline()

        with patch(
            "app.services.processing_pipeline.pdf_parser.parse_pdf",
            return_value=mock_pdf_result,
        ), patch(
            "app.services.processing_pipeline.invoice_extractor.extract",
            return_value=mock_extraction,
        ):
            res = pipe.process_document(doc.id, db=db_session)

        # Assert Pipeline Result
        assert res.success is True
        assert res.status == RoutingStatus.VERIFIED.value
        assert res.routing_decision.status == RoutingStatus.VERIFIED
        assert res.routing_decision.overall_confidence >= 0.85
        assert res.text_source == "digital_pdf"

        # Assert Normalization was executed
        assert res.normalization is not None
        assert res.normalization.success is True
        assert res.normalization.invoice_date.normalized_value == "2026-09-05"
        assert res.normalization.total_amount.normalized_value == "25500.00"

        # Assert Validation passed
        assert res.validation is not None
        assert res.validation.is_valid is True
        assert len(res.validation.errors) == 0

        # Assert DB Document record updated
        db_session.refresh(doc)
        assert doc.status == RoutingStatus.VERIFIED.value
        assert doc.error_message is None

        # Assert DocumentRecord in DB
        record = (
            db_session.query(DocumentRecord)
            .filter(DocumentRecord.document_id == doc.id)
            .first()
        )
        assert record is not None
        assert record.document_type == "invoice"
        assert record.extraction_status == RoutingStatus.VERIFIED.value
        assert record.confidence_score >= 0.85
        assert record.extracted_data is not None
        fields_payload = record.extracted_data["fields"]
        assert fields_payload["vendor_name"]["value"] == "Acme Corp"
        assert fields_payload["total_amount"]["normalized_value"] == "25500.00"

        # Assert AuditLog entry created
        audits = (
            db_session.query(AuditLog)
            .filter(AuditLog.document_id == doc.id)
            .all()
        )
        assert len(audits) >= 2
        actions = [a.action for a in audits]
        assert "PROCESSING_STARTED" in actions
        assert "PROCESSING_COMPLETED" in actions

    def test_scanned_pdf_routes_to_ocr_engine(
        self,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Verify scanned PDF automatically falls back to OCR."""
        pdf_path = create_sample_pdf(temp_workspace / "scanned_doc.pdf")

        doc = Document(
            file_name="scanned_doc.pdf",
            file_path=str(pdf_path),
            file_type="PDF",
            file_size=pdf_path.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        mock_pdf_result = PDFParseResult(
            success=True,
            status="NO_USABLE_TEXT",
            file_type="PDF",
            page_count=1,
            total_pages=1,
            combined_text="",
            has_extractable_text=False,
            likely_scanned=True,
            pages=[],
        )

        mock_ocr_result = OCRResult(
            success=True,
            status="OCR_SUCCESS",
            file_type="PDF",
            page_count=1,
            combined_text=(
                "Vendor: Global Tech Invoice # 9988 "
                "Date: 2026-08-10 Total: 12500.00"
            ),
            pages=[],
        )

        mock_extraction = InvoiceExtractionResult(
            success=True,
            vendor_name="Global Tech",
            invoice_number="9988",
            invoice_date="2026-08-10",
            total_amount="12500.00",
            field_confidence={
                "vendor_name": 0.90,
                "invoice_number": 0.88,
                "invoice_date": 0.87,
                "total_amount": 0.92,
            },
            fields_found=[
                "vendor_name",
                "invoice_number",
                "invoice_date",
                "total_amount",
            ],
            missing_fields=[],
            errors=[],
        )

        pipe = DocumentProcessingPipeline()

        with patch(
            "app.services.processing_pipeline.pdf_parser.parse_pdf",
            return_value=mock_pdf_result,
        ), patch(
            "app.services.processing_pipeline.ocr_engine.perform_ocr",
            return_value=mock_ocr_result,
        ) as mock_ocr, patch(
            "app.services.processing_pipeline.invoice_extractor.extract",
            return_value=mock_extraction,
        ):
            res = pipe.process_document(doc.id, db=db_session)

        mock_ocr.assert_called_once()
        assert res.text_source == "ocr_scanned_pdf"
        assert res.status == RoutingStatus.VERIFIED.value

    def test_image_file_routes_to_ocr_engine(
        self,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Verify image document routes directly to OCR engine."""
        img_path = create_sample_image(temp_workspace / "receipt.png")

        doc = Document(
            file_name="receipt.png",
            file_path=str(img_path),
            file_type="IMAGE",
            file_size=img_path.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        mock_ocr_result = OCRResult(
            success=True,
            status="OCR_SUCCESS",
            file_type="IMAGE",
            page_count=1,
            combined_text=(
                "Vendor: Quick Mart Invoice No: QM-101 "
                "Date: 2026-01-15 Total: 550.00"
            ),
            pages=[],
        )

        mock_extraction = InvoiceExtractionResult(
            success=True,
            vendor_name="Quick Mart",
            invoice_number="QM-101",
            invoice_date="2026-01-15",
            total_amount="550.00",
            field_confidence={
                "vendor_name": 0.90,
                "invoice_number": 0.89,
                "invoice_date": 0.88,
                "total_amount": 0.93,
            },
            fields_found=[
                "vendor_name",
                "invoice_number",
                "invoice_date",
                "total_amount",
            ],
            missing_fields=[],
            errors=[],
        )

        pipe = DocumentProcessingPipeline()

        with patch(
            "app.services.processing_pipeline.ocr_engine.perform_ocr",
            return_value=mock_ocr_result,
        ) as mock_ocr, patch(
            "app.services.processing_pipeline.invoice_extractor.extract",
            return_value=mock_extraction,
        ):
            res = pipe.process_document(doc.id, db=db_session)

        mock_ocr.assert_called_once()
        assert res.text_source == "ocr_image"
        assert res.status == RoutingStatus.VERIFIED.value

    def test_validation_failure_routes_to_needs_review(
        self,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Scenario: Total amount is 0.00.
        Validation fails -> NEEDS_REVIEW.
        """
        pdf_path = create_sample_pdf(temp_workspace / "invalid_amount.pdf")

        doc = Document(

            file_name="invalid_amount.pdf",
            file_path=str(pdf_path),
            file_type="PDF",
            file_size=pdf_path.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        mock_pdf_result = PDFParseResult(
            success=True,
            status="TEXT_EXTRACTED",
            file_type="PDF",
            page_count=1,
            total_pages=1,
            combined_text="Acme Corp INV-001 Date: 2026-09-05 Total: 0.00",
            has_extractable_text=True,
            likely_scanned=False,
            pages=[],
        )

        mock_extraction = InvoiceExtractionResult(
            success=True,
            vendor_name="Acme Corp",
            invoice_number="INV-001",
            invoice_date="2026-09-05",
            total_amount="0.00",
            field_confidence={
                "vendor_name": 0.95,
                "invoice_number": 0.91,
                "invoice_date": 0.89,
                "total_amount": 0.97,
            },
            fields_found=[
                "vendor_name",
                "invoice_number",
                "invoice_date",
                "total_amount",
            ],
            missing_fields=[],
            errors=[],
        )

        pipe = DocumentProcessingPipeline()

        with patch(
            "app.services.processing_pipeline.pdf_parser.parse_pdf",
            return_value=mock_pdf_result,
        ), patch(
            "app.services.processing_pipeline.invoice_extractor.extract",
            return_value=mock_extraction,
        ):
            res = pipe.process_document(doc.id, db=db_session)

        assert res.status == RoutingStatus.NEEDS_REVIEW.value
        assert res.validation.is_valid is False
        expected_msg = "Total Amount must be greater than 0"
        assert expected_msg in res.routing_decision.review_reasons

        # Verify DB status
        db_session.refresh(doc)
        assert doc.status == RoutingStatus.NEEDS_REVIEW.value
        assert expected_msg in doc.error_message

        record = (
            db_session.query(DocumentRecord)
            .filter(DocumentRecord.document_id == doc.id)
            .first()
        )
        assert record.extraction_status == RoutingStatus.NEEDS_REVIEW.value
        assert expected_msg in record.error_message

    def test_confidence_below_threshold_routes_to_needs_review(
        self,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Scenario: Vendor Name confidence 0.72 (< 0.85) -> NEEDS_REVIEW."""
        pdf_path = create_sample_pdf(temp_workspace / "low_conf.pdf")

        doc = Document(
            file_name="low_conf.pdf",
            file_path=str(pdf_path),
            file_type="PDF",
            file_size=pdf_path.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        invoice_text = (
            "Ambiguous Vendor INV-001 Date: 2026-09-05 Total: 25500.00"
        )
        mock_pdf_result = PDFParseResult(
            success=True,
            status="TEXT_EXTRACTED",
            file_type="PDF",
            page_count=1,
            total_pages=1,
            combined_text=invoice_text,
            has_extractable_text=True,
            likely_scanned=False,
            pages=[],
        )

        mock_extraction = InvoiceExtractionResult(
            success=True,
            vendor_name="Ambiguous Vendor",
            invoice_number="INV-001",
            invoice_date="2026-09-05",
            total_amount="25500.00",
            field_confidence={
                "vendor_name": 0.72,
                "invoice_number": 0.91,
                "invoice_date": 0.89,
                "total_amount": 0.97,
            },
            fields_found=[
                "vendor_name",
                "invoice_number",
                "invoice_date",
                "total_amount",
            ],
            missing_fields=[],
            errors=[],
        )

        pipe = DocumentProcessingPipeline()

        with patch(
            "app.services.processing_pipeline.pdf_parser.parse_pdf",
            return_value=mock_pdf_result,
        ), patch(
            "app.services.processing_pipeline.invoice_extractor.extract",
            return_value=mock_extraction,
        ):
            res = pipe.process_document(doc.id, db=db_session)

        assert res.status == RoutingStatus.NEEDS_REVIEW.value
        assert res.validation.is_valid is True
        assert any(
            "Vendor Name confidence" in r and "below threshold" in r
            for r in res.routing_decision.review_reasons
        )

        db_session.refresh(doc)
        assert doc.status == RoutingStatus.NEEDS_REVIEW.value
        assert "Vendor Name confidence" in doc.error_message

    def test_original_file_never_modified_or_overwritten(
        self,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Rule 5: Verify original uploaded file is NEVER overwritten."""
        original_bytes = (
            b"%PDF-1.4\nOriginal Unmodified Invoice Content 12345\n%%EOF"
        )
        pdf_path = temp_workspace / "original_invoice.pdf"
        pdf_path.write_bytes(original_bytes)

        initial_sha = compute_sha256(pdf_path)
        initial_size = pdf_path.stat().st_size
        initial_mtime = pdf_path.stat().st_mtime

        doc = Document(
            file_name="original_invoice.pdf",
            file_path=str(pdf_path),
            file_type="PDF",
            file_size=initial_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        invoice_text = (
            "Original Vendor INV-001 Date: 2026-09-05 Total: 1000.00"
        )
        mock_pdf_result = PDFParseResult(

            success=True,
            status="TEXT_EXTRACTED",
            file_type="PDF",
            page_count=1,
            total_pages=1,
            combined_text=invoice_text,
            has_extractable_text=True,
            likely_scanned=False,
            pages=[],
        )

        mock_extraction = InvoiceExtractionResult(
            success=True,
            vendor_name="Original Vendor",
            invoice_number="INV-001",
            invoice_date="2026-09-05",
            total_amount="1000.00",
            field_confidence={
                "vendor_name": 0.95,
                "invoice_number": 0.95,
                "invoice_date": 0.95,
                "total_amount": 0.95,
            },
            fields_found=[
                "vendor_name",
                "invoice_number",
                "invoice_date",
                "total_amount",
            ],
            missing_fields=[],
            errors=[],
        )

        pipe = DocumentProcessingPipeline()

        with patch(
            "app.services.processing_pipeline.pdf_parser.parse_pdf",
            return_value=mock_pdf_result,
        ), patch(
            "app.services.processing_pipeline.invoice_extractor.extract",
            return_value=mock_extraction,
        ):
            res = pipe.process_document(doc.id, db=db_session)

        assert res.success is True

        # STRICT VERIFICATION: File on disk MUST be byte-for-byte identical
        assert pdf_path.exists()
        assert pdf_path.read_bytes() == original_bytes
        assert compute_sha256(pdf_path) == initial_sha
        assert pdf_path.stat().st_size == initial_size
        assert pdf_path.stat().st_mtime == initial_mtime

        # Verify documents.file_path in database still points to original path
        db_session.refresh(doc)
        assert doc.file_path == str(pdf_path)

    def test_reprocessing_idempotency(
        self,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Verify re-processing updates existing DocumentRecord."""
        pdf_path = create_sample_pdf(temp_workspace / "reprocess_invoice.pdf")

        doc = Document(
            file_name="reprocess_invoice.pdf",
            file_path=str(pdf_path),
            file_type="PDF",
            file_size=pdf_path.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        mock_pdf_result = PDFParseResult(
            success=True,
            status="TEXT_EXTRACTED",
            file_type="PDF",
            page_count=1,
            total_pages=1,
            combined_text="Vendor A INV-100 Date: 2026-09-05 Total: 500.00",
            has_extractable_text=True,
            likely_scanned=False,
            pages=[],
        )

        mock_extraction = InvoiceExtractionResult(
            success=True,
            vendor_name="Vendor A",
            invoice_number="INV-100",
            invoice_date="2026-09-05",
            total_amount="500.00",
            field_confidence={
                "vendor_name": 0.90,
                "invoice_number": 0.90,
                "invoice_date": 0.90,
                "total_amount": 0.90,
            },
            fields_found=[
                "vendor_name",
                "invoice_number",
                "invoice_date",
                "total_amount",
            ],
            missing_fields=[],
            errors=[],
        )

        pipe = DocumentProcessingPipeline()

        with patch(
            "app.services.processing_pipeline.pdf_parser.parse_pdf",
            return_value=mock_pdf_result,
        ), patch(
            "app.services.processing_pipeline.invoice_extractor.extract",
            return_value=mock_extraction,
        ):
            res1 = pipe.process_document(doc.id, db=db_session)
            assert res1.success is True

            res2 = pipe.process_document(doc.id, db=db_session)
            assert res2.success is True

        # Exactly 1 DocumentRecord should exist for this document
        records = (
            db_session.query(DocumentRecord)
            .filter(DocumentRecord.document_id == doc.id)
            .all()
        )
        assert len(records) == 1
        assert records[0].id == res1.record_id
        assert records[0].id == res2.record_id

    def test_pipeline_with_mock_ai_provider(
        self,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Verify pipeline accepts and utilizes custom mock AI provider."""
        pdf_path = create_sample_pdf(temp_workspace / "ai_invoice.pdf")

        doc = Document(
            file_name="ai_invoice.pdf",
            file_path=str(pdf_path),
            file_type="PDF",
            file_size=pdf_path.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        mock_ai = MockAIExtractionProvider(
            fields={
                "vendor_name": "AI Vendor Inc",
                "invoice_number": "AI-999",
                "invoice_date": "2026-07-20",
                "total_amount": "75000.00",
                "confidence": {
                    "vendor_name": 0.95,
                    "invoice_number": 0.95,
                    "invoice_date": 0.95,
                    "total_amount": 0.95,
                },
            }
        )

        mock_pdf_result = PDFParseResult(
            success=True,
            status="TEXT_EXTRACTED",
            file_type="PDF",
            page_count=1,
            total_pages=1,
            combined_text="Raw invoice text for AI Vendor Inc",
            has_extractable_text=True,
            likely_scanned=False,
            pages=[],
        )

        pipe = DocumentProcessingPipeline(ai_provider=mock_ai)

        with patch(
            "app.services.processing_pipeline.pdf_parser.parse_pdf",
            return_value=mock_pdf_result,
        ):
            res = pipe.process_document(doc.id, db=db_session)

        assert res.success is True
        assert res.status == RoutingStatus.VERIFIED.value
        fields_payload = res.extracted_data["fields"]
        assert fields_payload["vendor_name"]["value"] == "AI Vendor Inc"

    def test_vendor_ai_context_reconciliation_normalization_and_confidence(
        self,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Verify full flow: context to AI, reconciliation, normalization,

        validation, and dynamic threshold evaluation without hardcoded 0.85.
        """
        pdf_path = create_sample_pdf(temp_workspace / "vendor_full_test.pdf")

        doc = Document(
            file_name="vendor_full_test.pdf",
            file_path=str(pdf_path),
            file_type="PDF",
            file_size=pdf_path.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        invoice_text = (
            "Vendor: Acme Global Inc.\n"
            "Invoice No: INV-2026-999\n"
            "Invoice Date: 05/09/2026\n"
            "Total Amount: ₹25,500\n"
        )
        mock_pdf_result = PDFParseResult(
            success=True,
            status="TEXT_EXTRACTED",
            file_type="PDF",
            page_count=1,
            total_pages=1,
            combined_text=invoice_text,
            has_extractable_text=True,
            likely_scanned=False,
            pages=[],
        )

        pipe = DocumentProcessingPipeline()

        with patch(
            "app.services.processing_pipeline.pdf_parser.parse_pdf",
            return_value=mock_pdf_result,
        ), patch(
            "app.services.processing_pipeline.invoice_extractor.extract",
            wraps=invoice_extractor.extract,
        ) as spy_extract:
            res = pipe.process_document(doc.id, db=db_session)

        # 1. Extraction context was passed to extraction service
        spy_extract.assert_called_once()
        passed_kwargs = spy_extract.call_args[1]
        assert "context" in passed_kwargs
        assert passed_kwargs["context"]["document_type"] == "invoice"
        assert passed_kwargs["context"]["document_id"] == doc.id

        # 2. Normalization verified:
        # 05/09/2026 -> 2026-09-05, ₹25,500 -> 25500.00
        assert res.normalization is not None
        assert res.normalization.success is True
        assert res.normalization.invoice_date.normalized_value == "2026-09-05"
        assert res.normalization.invoice_date.original_value == "05/09/2026"
        assert res.normalization.total_amount.normalized_value == "25500.00"

        # 3. Validation passed: vendor, invoice_no, valid date, total > 0
        assert res.validation is not None
        assert res.validation.is_valid is True
        assert len(res.validation.errors) == 0

        # 4. Routing decision was computed via ConfidenceRouter
        assert res.routing_decision is not None
        assert res.status == RoutingStatus.VERIFIED.value

        # 5. Database persistence into document_records
        db_session.refresh(doc)
        assert doc.status == "VERIFIED"
        record = (
            db_session.query(DocumentRecord)
            .filter(DocumentRecord.document_id == doc.id)
            .first()
        )
        assert record is not None
        assert record.extraction_status == "VERIFIED"
        assert record.confidence_score is not None
        assert record.confidence_score > 0.0

        # 6. Preserve Original Values for HITL (Section 25 contract)
        fields = record.extracted_data["fields"]
        assert fields["total_amount"]["original_value"] in (
            "₹25,500", "25500.00", "25,500"
        )
        assert fields["total_amount"]["normalized_value"] == "25500.00"
        assert fields["total_amount"]["confidence"] > 0.0
        assert "source" in fields["total_amount"]
        assert fields["invoice_date"]["original_value"] == "05/09/2026"
        assert fields["invoice_date"]["normalized_value"] == "2026-09-05"
        assert fields["vendor_name"]["value"] == "Acme Global Inc."
        assert fields["invoice_number"]["value"] == "INV-2026-999"

    def test_unexpected_exception_marks_failed_and_rolls_back(
        self,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Verify unhandled error rolls back and marks document FAILED."""
        pdf_path = create_sample_pdf(temp_workspace / "crash_test.pdf")

        doc = Document(
            file_name="crash_test.pdf",
            file_path=str(pdf_path),
            file_type="PDF",
            file_size=pdf_path.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        pipe = DocumentProcessingPipeline()

        # Simulate unexpected crash in extraction
        with patch(
            "app.services.processing_pipeline.pdf_parser.parse_pdf",
            side_effect=RuntimeError("Unexpected GPU crash"),
        ):
            res = pipe.process_document(doc.id, db=db_session)

        assert res.success is False
        assert res.status == "FAILED"
        assert "Unexpected GPU crash" in res.error

        db_session.refresh(doc)
        assert doc.status == "FAILED"
        assert "Unexpected GPU crash" in doc.error_message

        # Verify structured processing_errors (Section 28)
        assert len(res.processing_errors) > 0
        err0 = res.processing_errors[0]
        assert err0.stage == "PIPELINE_EXECUTION"
        assert err0.code == "UNHANDLED_EXCEPTION"
        assert "Unexpected GPU crash" in err0.message

        # Verify PROCESSING_FAILED audit log created
        audits = (
            db_session.query(AuditLog)
            .filter(AuditLog.document_id == doc.id)
            .all()
        )
        actions = [a.action for a in audits]
        assert "PROCESSING_FAILED" in actions

        # Verify original file NEVER deleted on failure (Section 30)
        assert pdf_path.exists()
        assert pdf_path.is_file()

    def test_audit_logs_routed_to_review_and_no_credentials_stored(
        self,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Verify ROUTED_TO_REVIEW in audit logs and no sensitive data."""
        pdf_path = create_sample_pdf(temp_workspace / "review_audit.pdf")

        doc = Document(
            file_name="review_audit.pdf",
            file_path=str(pdf_path),
            file_type="PDF",
            file_size=pdf_path.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        invoice_text = (
            "Acme Corp INV-001 Date: 2026-09-05 Total: 0.00"
        )
        mock_pdf_result = PDFParseResult(
            success=True,
            status="TEXT_EXTRACTED",
            file_type="PDF",
            page_count=1,
            total_pages=1,
            combined_text=invoice_text,
            has_extractable_text=True,
            likely_scanned=False,
            pages=[],
        )

        mock_extraction = InvoiceExtractionResult(
            success=True,
            vendor_name="Acme Corp",
            invoice_number="INV-001",
            invoice_date="2026-09-05",
            total_amount="0.00",
            field_confidence={
                "vendor_name": 0.95,
                "invoice_number": 0.91,
                "invoice_date": 0.89,
                "total_amount": 0.97,
            },
            fields_found=["vendor_name", "invoice_number", "invoice_date"],
            missing_fields=[],
            errors=[],
        )

        pipe = DocumentProcessingPipeline()

        with patch(
            "app.services.processing_pipeline.pdf_parser.parse_pdf",
            return_value=mock_pdf_result,
        ), patch(
            "app.services.processing_pipeline.invoice_extractor.extract",
            return_value=mock_extraction,
        ):
            res = pipe.process_document(doc.id, db=db_session)

        assert res.status == RoutingStatus.NEEDS_REVIEW.value

        audits = (
            db_session.query(AuditLog)
            .filter(AuditLog.document_id == doc.id)
            .all()
        )
        actions = [a.action for a in audits]
        assert "PROCESSING_STARTED" in actions
        assert "ROUTED_TO_REVIEW" in actions

        # Verify no credentials or API keys leaked into audit logs
        for a in audits:
            if a.details:
                details_str = str(a.details).lower()
                assert "api_key" not in details_str
                assert "bearer" not in details_str
                assert "secret" not in details_str


# =============================================================================
# Explicit Numbered Scenarios (Tests 2 - 11)
# =============================================================================

class TestNumberedPipelineScenarios:
    """Explicit test suite covering Tests 2 through 11."""

    def test_2_scanned_pdf(
        self,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 2 — Scanned PDF.

        Flow:
        PDF -> Detection -> PDF Parser identifies scanned document
        -> OCR -> Extraction -> AI -> Reconciliation -> Normalization
        -> Validation -> Confidence.

        Verify that OCR is called.
        Verify that digital-text path is not incorrectly used as final source.
        """
        pdf_path = create_sample_pdf(temp_workspace / "scanned_invoice.pdf")
        doc = Document(
            file_name="scanned_invoice.pdf",
            file_path=str(pdf_path),
            file_type="PDF",
            file_size=pdf_path.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        # Scanned PDF: no usable digital text, likely_scanned=True
        digital_junk_text = ""
        mock_pdf_result = PDFParseResult(
            success=True,
            status="NO_USABLE_TEXT",
            file_type="PDF",
            page_count=1,
            total_pages=1,
            combined_text=digital_junk_text,
            has_extractable_text=False,
            likely_scanned=True,
            pages=[],
        )

        ocr_invoice_text = (
            "Acme Scanned Corp\n"
            "Invoice Number: SCAN-2026-001\n"
            "Invoice Date: 2026-09-05\n"
            "Total Amount: 25500.00\n"
        )
        mock_ocr_result = OCRResult(
            success=True,
            status="OCR_SUCCESS",
            file_type="PDF",
            page_count=1,
            combined_text=ocr_invoice_text,
            pages=[],
        )

        mock_extraction = InvoiceExtractionResult(
            success=True,
            vendor_name="Acme Scanned Corp",
            invoice_number="SCAN-2026-001",
            invoice_date="2026-09-05",
            total_amount="25500.00",
            field_confidence={
                "vendor_name": 0.94,
                "invoice_number": 0.91,
                "invoice_date": 0.88,
                "total_amount": 0.96,
            },
            fields_found=[
                "vendor_name",
                "invoice_number",
                "invoice_date",
                "total_amount",
            ],
            missing_fields=[],
            errors=[],
        )

        pipe = DocumentProcessingPipeline()

        with patch(
            "app.services.processing_pipeline.pdf_parser.parse_pdf",
            return_value=mock_pdf_result,
        ), patch(
            "app.services.processing_pipeline.ocr_engine.perform_ocr",
            return_value=mock_ocr_result,
        ) as mock_ocr, patch(
            "app.services.processing_pipeline.invoice_extractor.extract",
            return_value=mock_extraction,
        ):
            res = pipe.process_document(doc.id, db=db_session)

        # 1. Verify OCR was called
        mock_ocr.assert_called_once()

        # 2. Verify digital-text path was NOT used as final extraction source
        assert res.text_source == "ocr_scanned_pdf"
        assert res.text_source != "digital_pdf"
        assert res.raw_text == ocr_invoice_text
        assert res.raw_text != digital_junk_text

        # 3. Verify successful progression through pipeline
        assert res.status == RoutingStatus.VERIFIED.value
        assert res.success is True

    def test_3_image(
        self,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 3 — Image.

        Flow:
        IMAGE -> OCR -> Extraction -> ...
        Verify OCR is called.
        """
        img_path = create_sample_image(temp_workspace / "invoice_photo.png")
        doc = Document(
            file_name="invoice_photo.png",
            file_path=str(img_path),
            file_type="IMAGE",
            file_size=img_path.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        mock_ocr_result = OCRResult(
            success=True,
            status="OCR_SUCCESS",
            file_type="IMAGE",
            page_count=1,
            combined_text="Acme Photo Vendor INV-777 2026-09-05 1000.00",
            pages=[],
        )

        mock_extraction = InvoiceExtractionResult(
            success=True,
            vendor_name="Acme Photo Vendor",
            invoice_number="INV-777",
            invoice_date="2026-09-05",
            total_amount="1000.00",
            field_confidence={
                "vendor_name": 0.90,
                "invoice_number": 0.90,
                "invoice_date": 0.90,
                "total_amount": 0.90,
            },
            fields_found=[
                "vendor_name",
                "invoice_number",
                "invoice_date",
                "total_amount",
            ],
            missing_fields=[],
            errors=[],
        )

        pipe = DocumentProcessingPipeline()

        with patch(
            "app.services.processing_pipeline.ocr_engine.perform_ocr",
            return_value=mock_ocr_result,
        ) as mock_ocr, patch(
            "app.services.processing_pipeline.invoice_extractor.extract",
            return_value=mock_extraction,
        ):
            res = pipe.process_document(doc.id, db=db_session)

        # Verify OCR is called
        mock_ocr.assert_called_once()
        assert res.text_source == "ocr_image"
        assert res.status == RoutingStatus.VERIFIED.value

    def test_4_csv(
        self,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 4 — CSV.

        Flow:
        CSV -> CSV/Excel Parser -> Extraction / structured processing.
        Do not call OCR for CSV.
        """
        csv_file = temp_workspace / "invoice_data.csv"
        csv_file.write_text(
            "Vendor,Invoice Number,Invoice Date,Total Amount\n"
            "CSV Supplier,CSV-101,2026-09-05,15000.00\n",
            encoding="utf-8",
        )

        doc = Document(
            file_name="invoice_data.csv",
            file_path=str(csv_file),
            file_type="CSV",
            file_size=csv_file.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        mock_tabular_result = TabularParseResult(
            success=True,
            file_type="CSV",
            columns=[
                "Vendor", "Invoice Number", "Invoice Date", "Total Amount"
            ],
            row_count=1,
            records=[{
                "Vendor": "CSV Supplier",
                "Invoice Number": "CSV-101",
                "Invoice Date": "2026-09-05",
                "Total Amount": "15000.00",
            }],
            sheets=[
                SheetData(
                    sheet_name="CSV",
                    columns=[
                        "Vendor",
                        "Invoice Number",
                        "Invoice Date",
                        "Total Amount",
                    ],
                    row_count=1,
                    records=[{
                        "Vendor": "CSV Supplier",
                        "Invoice Number": "CSV-101",
                        "Invoice Date": "2026-09-05",
                        "Total Amount": "15000.00",
                    }],
                    is_empty=False,
                )
            ],
            total_sheets=1,
            total_rows=1,
        )

        mock_extraction = InvoiceExtractionResult(
            success=True,
            vendor_name="CSV Supplier",
            invoice_number="CSV-101",
            invoice_date="2026-09-05",
            total_amount="15000.00",
            field_confidence={
                "vendor_name": 0.95,
                "invoice_number": 0.95,
                "invoice_date": 0.95,
                "total_amount": 0.95,
            },
            fields_found=[
                "vendor_name",
                "invoice_number",
                "invoice_date",
                "total_amount",
            ],
            missing_fields=[],
            errors=[],
        )

        pipe = DocumentProcessingPipeline()

        with patch(
            "app.services.processing_pipeline.csv_excel_parser."
            "parse_csv_or_excel",
            return_value=mock_tabular_result,
        ) as mock_tabular, patch(
            "app.services.processing_pipeline.ocr_engine.perform_ocr",
        ) as mock_ocr, patch(
            "app.services.processing_pipeline.invoice_extractor.extract",
            return_value=mock_extraction,
        ):
            res = pipe.process_document(doc.id, db=db_session)

        # Tabular parser called
        mock_tabular.assert_called_once()
        # Strictly DO NOT call OCR for CSV
        mock_ocr.assert_not_called()
        assert res.text_source == "tabular"
        assert res.status == RoutingStatus.VERIFIED.value

    def test_5_excel(
        self,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 5 — Excel.

        Flow:
        XLSX -> CSV/Excel Parser.
        Do not call OCR.
        """
        xlsx_file = temp_workspace / "invoice_data.xlsx"
        import pandas as pd
        df = pd.DataFrame([{
            "Vendor": "Excel Supplier Ltd",
            "Invoice Number": "XL-2002",
            "Invoice Date": "2026-09-05",
            "Total Amount": "35000.00",
        }])
        df.to_excel(xlsx_file, index=False)

        doc = Document(
            file_name="invoice_data.xlsx",
            file_path=str(xlsx_file),
            file_type="EXCEL",
            file_size=xlsx_file.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        mock_tabular_result = TabularParseResult(
            success=True,
            file_type="XLSX",
            sheet_name="Invoices",
            columns=[
                "Vendor", "Invoice Number", "Invoice Date", "Total Amount"
            ],
            row_count=1,
            records=[{
                "Vendor": "Excel Supplier Ltd",
                "Invoice Number": "XL-2002",
                "Invoice Date": "2026-09-05",
                "Total Amount": "35000.00",
            }],
            sheets=[
                SheetData(
                    sheet_name="Invoices",
                    columns=[
                        "Vendor",
                        "Invoice Number",
                        "Invoice Date",
                        "Total Amount",
                    ],
                    row_count=1,
                    records=[{
                        "Vendor": "Excel Supplier Ltd",
                        "Invoice Number": "XL-2002",
                        "Invoice Date": "2026-09-05",
                        "Total Amount": "35000.00",
                    }],
                    is_empty=False,
                )
            ],
            total_sheets=1,
            total_rows=1,
        )

        mock_extraction = InvoiceExtractionResult(
            success=True,
            vendor_name="Excel Supplier Ltd",
            invoice_number="XL-2002",
            invoice_date="2026-09-05",
            total_amount="35000.00",
            field_confidence={
                "vendor_name": 0.95,
                "invoice_number": 0.95,
                "invoice_date": 0.95,
                "total_amount": 0.95,
            },
            fields_found=[
                "vendor_name",
                "invoice_number",
                "invoice_date",
                "total_amount",
            ],
            missing_fields=[],
            errors=[],
        )

        pipe = DocumentProcessingPipeline()

        with patch(
            "app.services.processing_pipeline.csv_excel_parser."
            "parse_csv_or_excel",
            return_value=mock_tabular_result,
        ) as mock_tabular, patch(
            "app.services.processing_pipeline.ocr_engine.perform_ocr",
        ) as mock_ocr, patch(
            "app.services.processing_pipeline.invoice_extractor.extract",
            return_value=mock_extraction,
        ):
            res = pipe.process_document(doc.id, db=db_session)

        # Tabular parser called
        mock_tabular.assert_called_once()
        # Strictly DO NOT call OCR for Excel
        mock_ocr.assert_not_called()
        assert res.text_source == "tabular"
        assert res.status == RoutingStatus.VERIFIED.value

    def test_6_validation_failure(
        self,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 6 — Validation Failure.

        Use: Total Amount = 0.
        All confidence values pass (>= 0.85).
        Expected: NEEDS_REVIEW.
        Verify that this is NOT marked FAILED.
        """
        pdf_path = create_sample_pdf(temp_workspace / "val_fail_invoice.pdf")
        doc = Document(
            file_name="val_fail_invoice.pdf",
            file_path=str(pdf_path),
            file_type="PDF",
            file_size=pdf_path.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        mock_pdf_result = PDFParseResult(
            success=True,
            status="TEXT_EXTRACTED",
            file_type="PDF",
            page_count=1,
            total_pages=1,
            combined_text="ABC Corp INV-001 2026-09-05 Total: 0.00",
            has_extractable_text=True,
            likely_scanned=False,
            pages=[],
        )

        # All confidence values comfortably pass (>= 0.85)
        mock_extraction = InvoiceExtractionResult(
            success=True,
            vendor_name="ABC Corp",
            invoice_number="INV-001",
            invoice_date="2026-09-05",
            total_amount="0.00",
            field_confidence={
                "vendor_name": 0.95,
                "invoice_number": 0.91,
                "invoice_date": 0.89,
                "total_amount": 0.97,
            },
            fields_found=[
                "vendor_name",
                "invoice_number",
                "invoice_date",
                "total_amount",
            ],
            missing_fields=[],
            errors=[],
        )

        pipe = DocumentProcessingPipeline()

        with patch(
            "app.services.processing_pipeline.pdf_parser.parse_pdf",
            return_value=mock_pdf_result,
        ), patch(
            "app.services.processing_pipeline.invoice_extractor.extract",
            return_value=mock_extraction,
        ):
            res = pipe.process_document(doc.id, db=db_session)

        # Expected: NEEDS_REVIEW
        assert res.status == RoutingStatus.NEEDS_REVIEW.value
        # Verify that this is NOT marked FAILED
        assert res.status != "FAILED"
        assert res.success is True

        db_session.refresh(doc)
        assert doc.status == RoutingStatus.NEEDS_REVIEW.value
        assert doc.status != "FAILED"

    def test_7_confidence_failure(
        self,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 7 — Confidence Failure.

        Use: Invoice Date confidence = 0.72.
        Validation passes.
        Expected: NEEDS_REVIEW.
        Verify that this is NOT marked FAILED.
        """
        pdf_path = create_sample_pdf(temp_workspace / "conf_fail_invoice.pdf")
        doc = Document(
            file_name="conf_fail_invoice.pdf",
            file_path=str(pdf_path),
            file_type="PDF",
            file_size=pdf_path.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        mock_pdf_result = PDFParseResult(
            success=True,
            status="TEXT_EXTRACTED",
            file_type="PDF",
            page_count=1,
            total_pages=1,
            combined_text="ABC Technologies INV-001 2026-09-05 25500.00",
            has_extractable_text=True,
            likely_scanned=False,
            pages=[],
        )

        # Validation passes, but Invoice Date confidence is 0.72 (< 0.85)
        mock_extraction = InvoiceExtractionResult(
            success=True,
            vendor_name="ABC Technologies",
            invoice_number="INV-001",
            invoice_date="2026-09-05",
            total_amount="25500.00",
            field_confidence={
                "vendor_name": 0.95,
                "invoice_number": 0.91,
                "invoice_date": 0.72,
                "total_amount": 0.97,
            },
            fields_found=[
                "vendor_name",
                "invoice_number",
                "invoice_date",
                "total_amount",
            ],
            missing_fields=[],
            errors=[],
        )

        pipe = DocumentProcessingPipeline()

        with patch(
            "app.services.processing_pipeline.pdf_parser.parse_pdf",
            return_value=mock_pdf_result,
        ), patch(
            "app.services.processing_pipeline.invoice_extractor.extract",
            return_value=mock_extraction,
        ):
            res = pipe.process_document(doc.id, db=db_session)

        # Expected: NEEDS_REVIEW
        assert res.status == RoutingStatus.NEEDS_REVIEW.value
        # Verify that this is NOT marked FAILED
        assert res.status != "FAILED"
        assert res.success is True

        db_session.refresh(doc)
        assert doc.status == RoutingStatus.NEEDS_REVIEW.value
        assert doc.status != "FAILED"
        assert "Invoice Date confidence" in str(doc.error_message)

    def test_8_processing_failure(
        self,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 8 — Processing Failure.

        Mock OCR or PDF parsing to fail.
        Expected: FAILED.
        Verify:
        - processing error contains stage;
        - original file path remains unchanged;
        - database transaction is handled safely.
        """
        pdf_path = create_sample_pdf(temp_workspace / "failing_doc.pdf")
        doc = Document(
            file_name="failing_doc.pdf",
            file_path=str(pdf_path),
            file_type="PDF",
            file_size=pdf_path.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        pipe = DocumentProcessingPipeline()

        # Mock PDF parser to raise a fatal unrecoverable exception
        with patch(
            "app.services.processing_pipeline.pdf_parser.parse_pdf",
            side_effect=RuntimeError("Corrupt PDF stream error"),
        ):
            res = pipe.process_document(doc.id, db=db_session)

        # Expected: FAILED
        assert res.status == "FAILED"
        assert res.success is False

        # Verify processing error contains stage
        assert len(res.processing_errors) > 0
        stages = [e.stage for e in res.processing_errors]
        assert any(
            s in ("PDF_PARSING", "PIPELINE_EXECUTION") for s in stages
        )

        # Verify original file path remains unchanged
        db_session.refresh(doc)
        assert doc.file_path == str(pdf_path)
        assert pdf_path.exists()

        # Verify database transaction is handled safely
        # (status FAILED, error logged)
        assert doc.status == "FAILED"
        assert "Corrupt PDF stream error" in doc.error_message

    def test_9_ai_failure(
        self,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 9 — AI Failure.

        Mock AI extraction failure.
        Verify:
        AI failure -> Rule extraction continues -> Pipeline completes.
        Verify pipeline follows existing AI fallback behavior.
        """
        pdf_path = create_sample_pdf(temp_workspace / "ai_fail_invoice.pdf")
        doc = Document(
            file_name="ai_fail_invoice.pdf",
            file_path=str(pdf_path),
            file_type="PDF",
            file_size=pdf_path.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        invoice_text = (
            "Vendor: Acme Fallback Supplies\n"
            "Invoice No: FB-8888\n"
            "Date: 2026-09-05\n"
            "Total Amount: 25500.00\n"
        )
        mock_pdf_result = PDFParseResult(
            success=True,
            status="TEXT_EXTRACTED",
            file_type="PDF",
            page_count=1,
            total_pages=1,
            combined_text=invoice_text,
            has_extractable_text=True,
            likely_scanned=False,
            pages=[],
        )

        # Faulty AI Provider that raises an exception
        class CrashingAIProvider(MockAIExtractionProvider):
            def extract_invoice(self, text: str, context=None):
                raise RuntimeError("LLM Service 503 Unavailable / Timeout")

        pipe = DocumentProcessingPipeline(ai_provider=CrashingAIProvider())

        with patch(
            "app.services.processing_pipeline.pdf_parser.parse_pdf",
            return_value=mock_pdf_result,
        ):
            res = pipe.process_document(doc.id, db=db_session)

        # Verify pipeline completes despite AI failure (rule fallback works)
        assert res.success is True
        assert res.status in ("VERIFIED", "NEEDS_REVIEW")
        assert res.extracted_data is not None
        fields = res.extracted_data["fields"]
        assert fields["vendor_name"]["value"] is not None
        assert fields["invoice_number"]["value"] is not None

    def test_10_original_file_preservation(
        self,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 10 — Original File Preservation.

        After successful processing:
        Verify documents.file_path still points to original uploaded document.

        After failed processing:
        Verify the same.

        The pipeline must never delete or overwrite it.
        """
        original_bytes = (
            b"%PDF-1.4\nPreservation Test Byte Exact Content 9999\n%%EOF"
        )
        pdf_path = temp_workspace / "preservation_invoice.pdf"
        pdf_path.write_bytes(original_bytes)

        initial_sha = compute_sha256(pdf_path)
        initial_size = pdf_path.stat().st_size
        initial_mtime = pdf_path.stat().st_mtime

        # 1. Successful processing preservation
        doc_success = Document(
            file_name="preservation_invoice.pdf",
            file_path=str(pdf_path),
            file_type="PDF",
            file_size=initial_size,
            status="UPLOADED",
        )
        db_session.add(doc_success)
        db_session.commit()
        db_session.refresh(doc_success)

        mock_pdf_result = PDFParseResult(
            success=True,
            status="TEXT_EXTRACTED",
            file_type="PDF",
            page_count=1,
            total_pages=1,
            combined_text="Vendor X INV-001 Date: 2026-09-05 Total: 100.00",
            has_extractable_text=True,
            likely_scanned=False,
            pages=[],
        )
        mock_extraction = InvoiceExtractionResult(
            success=True,
            vendor_name="Vendor X",
            invoice_number="INV-001",
            invoice_date="2026-09-05",
            total_amount="100.00",
            field_confidence={
                "vendor_name": 0.95,
                "invoice_number": 0.95,
                "invoice_date": 0.95,
                "total_amount": 0.95,
            },
            fields_found=[
                "vendor_name", "invoice_number", "invoice_date", "total_amount"
            ],
            missing_fields=[],
            errors=[],
        )

        pipe = DocumentProcessingPipeline()

        with patch(
            "app.services.processing_pipeline.pdf_parser.parse_pdf",
            return_value=mock_pdf_result,
        ), patch(
            "app.services.processing_pipeline.invoice_extractor.extract",
            return_value=mock_extraction,
        ):
            pipe.process_document(doc_success.id, db=db_session)

        # Verify after successful processing
        db_session.refresh(doc_success)
        assert doc_success.file_path == str(pdf_path)
        assert pdf_path.exists()
        assert pdf_path.read_bytes() == original_bytes
        assert compute_sha256(pdf_path) == initial_sha
        assert pdf_path.stat().st_size == initial_size
        assert pdf_path.stat().st_mtime == initial_mtime

        # 2. Failed processing preservation
        doc_failed = Document(
            file_name="preservation_invoice.pdf",
            file_path=str(pdf_path),
            file_type="PDF",
            file_size=initial_size,
            status="UPLOADED",
        )
        db_session.add(doc_failed)
        db_session.commit()
        db_session.refresh(doc_failed)

        with patch(
            "app.services.processing_pipeline.pdf_parser.parse_pdf",
            side_effect=RuntimeError("Intentional failure for test"),
        ):
            pipe.process_document(doc_failed.id, db=db_session)

        # Verify after failed processing
        db_session.refresh(doc_failed)
        assert doc_failed.file_path == str(pdf_path)
        assert pdf_path.exists()
        assert pdf_path.read_bytes() == original_bytes
        assert compute_sha256(pdf_path) == initial_sha
        assert pdf_path.stat().st_size == initial_size
        assert pdf_path.stat().st_mtime == initial_mtime

    def test_11_persistence(
        self,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 11 — Persistence.

        Verify that after successful processing:
        - document_records contains appropriate final invoice fields according
          to existing schema.
        - Verify document status is VERIFIED or NEEDS_REVIEW depending on
          scenario.
        """
        pdf_path = create_sample_pdf(temp_workspace / "persist_test.pdf")
        doc = Document(
            file_name="persist_test.pdf",
            file_path=str(pdf_path),
            file_type="PDF",
            file_size=pdf_path.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        invoice_text = (
            "Persistence Vendor Ltd INV-9999 2026-09-05 45000.00"
        )
        mock_pdf_result = PDFParseResult(
            success=True,
            status="TEXT_EXTRACTED",
            file_type="PDF",
            page_count=1,
            total_pages=1,
            combined_text=invoice_text,
            has_extractable_text=True,
            likely_scanned=False,
            pages=[],
        )
        mock_extraction = InvoiceExtractionResult(
            success=True,
            vendor_name="Persistence Vendor Ltd",
            invoice_number="INV-9999",
            invoice_date="2026-09-05",
            total_amount="45000.00",
            field_confidence={
                "vendor_name": 0.96,
                "invoice_number": 0.94,
                "invoice_date": 0.92,
                "total_amount": 0.98,
            },
            fields_found=[
                "vendor_name", "invoice_number", "invoice_date", "total_amount"
            ],
            missing_fields=[],
            errors=[],
        )

        pipe = DocumentProcessingPipeline()

        with patch(
            "app.services.processing_pipeline.pdf_parser.parse_pdf",
            return_value=mock_pdf_result,
        ), patch(
            "app.services.processing_pipeline.invoice_extractor.extract",
            return_value=mock_extraction,
        ):
            res = pipe.process_document(doc.id, db=db_session)

        # Verify execution and document status
        assert res.success is True
        db_session.refresh(doc)
        assert doc.status == RoutingStatus.VERIFIED.value
        assert doc.status in ("VERIFIED", "NEEDS_REVIEW")

        # Verify document_records schema and content
        record = (
            db_session.query(DocumentRecord)
            .filter(DocumentRecord.document_id == doc.id)
            .first()
        )
        assert record is not None
        assert record.document_id == doc.id
        assert record.document_type == "invoice"
        assert record.extraction_status == "VERIFIED"
        assert record.confidence_score is not None
        assert record.confidence_score >= 0.85
        assert record.raw_text == invoice_text

        # Verify extracted_data JSON payload structure
        assert record.extracted_data is not None
        fields = record.extracted_data["fields"]
        assert fields["vendor_name"]["value"] == "Persistence Vendor Ltd"
        assert fields["invoice_number"]["value"] == "INV-9999"
        assert fields["invoice_date"]["normalized_value"] == "2026-09-05"
        assert fields["total_amount"]["normalized_value"] == "45000.00"
