"""Unit and integration tests for POST /api/documents/{document_id}/process.

Covers:
1. Happy path: 200 OK returning ProcessingResult schema.
2. 404 Not Found when document does not exist.
3. Idempotency: re-calling the endpoint updates existing DocumentRecord.
4. Validation failure: returns 200 with NEEDS_REVIEW and validation_errors.
5. Error response security: zero leaked credentials, keys, or stack traces.
6. Synchronous processing flow: completed within the request lifecycle.
"""

from pathlib import Path
import tempfile
from typing import Generator
from unittest.mock import patch

from fastapi import status
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.connection import Base, get_db
from app.main import app
from app.models.document import Document
from app.models.document_record import DocumentRecord
from app.schemas.extraction import ExtractedField, InvoiceExtractionResult
from app.schemas.pdf import PDFPageData, PDFParseResult
from app.schemas.processing import ProcessingResult


# =============================================================================
# Database Fixtures (In-Memory SQLite)
# =============================================================================

@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Provides a fresh isolated in-memory SQLite database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """TestClient with get_db dependency overridden to use the test session."""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def temp_workspace() -> Generator[Path, None, None]:
    """Provides a temporary directory for dummy test files."""
    with tempfile.TemporaryDirectory(prefix="idp_test_endpoint_") as tmpdir:
        yield Path(tmpdir)


def create_sample_pdf(file_path: Path) -> Path:
    """Creates a minimal valid PDF header."""
    file_path.write_bytes(b"%PDF-1.4\n%Minimal valid test PDF\n%%EOF\n")
    return file_path


# =============================================================================
# API Endpoint Tests
# =============================================================================

class TestProcessDocumentEndpoint:
    """Tests for the synchronous document processing endpoint."""

    def test_process_document_success_verified(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Verify successful synchronous processing returns 200 and schema."""
        pdf_path = create_sample_pdf(temp_workspace / "valid_inv.pdf")

        doc = Document(
            file_name="valid_inv.pdf",
            file_path=str(pdf_path),
            file_type="PDF",
            file_size=pdf_path.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        invoice_text = (
            "Acme Technologies Ltd\n"
            "Invoice No: INV-2026-888\n"
            "Invoice Date: 05/09/2026\n"
            "Total Amount: Rs. 25,500.00\n"
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
            vendor_name="Acme Technologies Ltd",
            invoice_number="INV-2026-888",
            invoice_date="05/09/2026",
            total_amount="25500.00",
            extracted_fields={
                "vendor_name": ExtractedField(
                    value="Acme Technologies Ltd",
                    confidence=0.96,
                    source="rule+ai",
                ),
                "invoice_number": ExtractedField(
                    value="INV-2026-888",
                    confidence=0.94,
                    source="rule+ai",
                ),
                "invoice_date": ExtractedField(
                    value="05/09/2026",
                    confidence=0.91,
                    source="rule",
                ),
                "total_amount": ExtractedField(
                    value="25500.00",
                    confidence=0.97,
                    source="rule+ai",
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

        with patch(
            "app.services.processing_pipeline.pdf_parser.parse_pdf",
            return_value=mock_pdf_result,
        ), patch(
            "app.services.processing_pipeline.invoice_extractor.extract",
            return_value=mock_extraction,
        ):
            response = client.post(f"/api/documents/{doc.id}/process")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Validate with Pydantic model
        result = ProcessingResult(**data)
        assert result.document_id == doc.id
        assert result.status == "VERIFIED"
        assert len(result.validation_errors) == 0
        assert len(result.processing_errors) == 0

        # Field validation
        fields = result.fields
        assert "vendor_name" in fields
        assert fields["vendor_name"].original_value == "Acme Technologies Ltd"
        assert fields["vendor_name"].confidence == 0.96

        assert "invoice_number" in fields
        assert fields["invoice_number"].normalized_value == "INV-2026-888"

        assert "invoice_date" in fields
        assert fields["invoice_date"].original_value == "05/09/2026"
        assert fields["invoice_date"].normalized_value == "2026-09-05"

        assert "total_amount" in fields
        assert fields["total_amount"].normalized_value == "25500.00"

        # Direct confidence mapping
        assert result.confidence["vendor_name"] == 0.96
        assert result.confidence["total_amount"] == 0.97

    def test_process_document_not_found_returns_404(
        self,
        client: TestClient,
    ):
        """Verify requesting non-existent document returns 404."""
        response = client.post("/api/documents/999999/process")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_reprocessing_idempotency_via_api(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Verify re-calling endpoint updates the existing record."""
        pdf_path = create_sample_pdf(temp_workspace / "idempotent.pdf")

        doc = Document(
            file_name="idempotent.pdf",
            file_path=str(pdf_path),
            file_type="PDF",
            file_size=pdf_path.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        invoice_text = "Acme Corp INV-001 Date: 2026-09-05 Total: 1000.00"
        mock_pdf = PDFParseResult(
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

        mock_ext = InvoiceExtractionResult(
            success=True,
            vendor_name="Acme Corp",
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

        with patch(
            "app.services.processing_pipeline.pdf_parser.parse_pdf",
            return_value=mock_pdf,
        ), patch(
            "app.services.processing_pipeline.invoice_extractor.extract",
            return_value=mock_ext,
        ):
            resp1 = client.post(f"/api/documents/{doc.id}/process")
            assert resp1.status_code == status.HTTP_200_OK

            resp2 = client.post(f"/api/documents/{doc.id}/process")
            assert resp2.status_code == status.HTTP_200_OK

        # Verify only 1 DocumentRecord exists in the database
        records = (
            db_session.query(DocumentRecord)
            .filter(DocumentRecord.document_id == doc.id)
            .all()
        )
        assert len(records) == 1

    def test_validation_failure_returns_needs_review(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Verify validation errors route to NEEDS_REVIEW via API."""
        pdf_path = create_sample_pdf(temp_workspace / "bad_amount.pdf")

        doc = Document(
            file_name="bad_amount.pdf",
            file_path=str(pdf_path),
            file_type="PDF",
            file_size=pdf_path.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        invoice_text = "Acme Corp INV-001 Date: 2026-09-05 Total: 0.00"
        mock_pdf = PDFParseResult(
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

        mock_ext = InvoiceExtractionResult(
            success=True,
            vendor_name="Acme Corp",
            invoice_number="INV-001",
            invoice_date="2026-09-05",
            total_amount="0.00",
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

        with patch(
            "app.services.processing_pipeline.pdf_parser.parse_pdf",
            return_value=mock_pdf,
        ), patch(
            "app.services.processing_pipeline.invoice_extractor.extract",
            return_value=mock_ext,
        ):
            response = client.post(f"/api/documents/{doc.id}/process")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "NEEDS_REVIEW"
        assert len(data["validation_errors"]) > 0
        assert any(
            "greater than 0" in err for err in data["validation_errors"]
        )

    def test_error_responses_contain_no_secrets(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Verify API response never leaks stack traces or system secrets."""
        pdf_path = create_sample_pdf(temp_workspace / "secret_leak_test.pdf")

        doc = Document(
            file_name="secret_leak_test.pdf",
            file_path=str(pdf_path),
            file_type="PDF",
            file_size=pdf_path.stat().st_size,
            status="UPLOADED",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        err_msg = "Database connection error password=super_secret"
        with patch(
            "app.services.processing_pipeline.pdf_parser.parse_pdf",
            side_effect=RuntimeError(err_msg),
        ):
            response = client.post(f"/api/documents/{doc.id}/process")

        assert response.status_code == status.HTTP_200_OK
        raw_text = response.text.lower()
        # Verify no stack traces or raw secret leaks
        assert "traceback" not in raw_text
        assert "super_secret" not in raw_text
        data = response.json()
        assert data["status"] == "FAILED"
        assert len(data["processing_errors"]) > 0
