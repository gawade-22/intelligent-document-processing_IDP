"""Comprehensive test suite for Universal HITL Verification.

Covers:
1. Universal document support (forms, marksheets, certificates, records, etc.)
2. GET  /api/documents/review: lists documents in NEEDS_REVIEW status.
3. GET  /api/documents/{id}: complete document review detail & viewer URL.
4. GET  /api/documents/{id}/file: safe original file streaming & 404 handling.
5. POST /api/documents/{id}/verify:
   - human corrections recorded in audit_logs (FIELD_CORRECTED, FIELD_ADDED)
   - confidence updated to 1.0 and source to 'human' for edited fields
   - re-normalization of dates and amounts
   - re-validation marking VERIFIED when valid or keeping NEEDS_REVIEW
   - database persistence without duplicates
"""

from pathlib import Path
import tempfile
from typing import Generator

from fastapi import status
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.connection import Base, get_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.document_record import DocumentRecord
from app.schemas.review import VerifyDocumentRequest
from app.services.hitl_service import HITLVerificationService


# =============================================================================
# Database Fixture (In-Memory SQLite with StaticPool)
# =============================================================================

@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Provides an isolated in-memory SQLite database session."""
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
    """TestClient with get_db dependency overridden to use test session."""
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
    with tempfile.TemporaryDirectory(prefix="idp_test_hitl_") as tmpdir:
        yield Path(tmpdir)


def create_sample_file(
    file_path: Path,
    content: bytes = b"%PDF-1.4 sample document content",
) -> Path:
    """Helper to write test file on disk."""
    file_path.write_bytes(content)
    return file_path


# =============================================================================
# Test Suite: Universal HITL Verification
# =============================================================================

class TestHITLReviewAndVerification:
    """Test suite for review, file viewer, and verification."""

    def test_review_list_endpoint_filters_needs_review(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """GET /api/documents/review returns only NEEDS_REVIEW documents."""
        f1 = create_sample_file(temp_workspace / "doc1.pdf")
        f2 = create_sample_file(temp_workspace / "doc2.pdf")
        f3 = create_sample_file(temp_workspace / "doc3.pdf")

        # 1. NEEDS_REVIEW document (Invoice)
        doc1 = Document(
            file_name="invoice_review.pdf",
            file_path=str(f1),
            file_type="PDF",
            file_size=f1.stat().st_size,
            status="NEEDS_REVIEW",
            error_message="Total Amount must be greater than 0",
        )
        # 2. NEEDS_REVIEW document (Student Marksheet)
        doc2 = Document(
            file_name="marksheet_famt.pdf",
            file_path=str(f2),
            file_type="PDF",
            file_size=f2.stat().st_size,
            status="NEEDS_REVIEW",
            error_message="roll_number confidence is below threshold",
        )
        # 3. VERIFIED document (should be excluded)
        doc3 = Document(
            file_name="verified_doc.pdf",
            file_path=str(f3),
            file_type="PDF",
            file_size=f3.stat().st_size,
            status="VERIFIED",
        )
        db_session.add_all([doc1, doc2, doc3])
        db_session.commit()

        # Add records
        rec1 = DocumentRecord(
            document_id=doc1.id,
            document_type="invoice",
            extraction_status="NEEDS_REVIEW",
            extracted_data={
                "fields": {
                    "vendor_name": {
                        "value": "ABC Corp",
                        "normalized_value": "ABC Corp",
                        "confidence": 0.95,
                        "source": "rule",
                    },
                    "total_amount": {
                        "value": "0.00",
                        "normalized_value": "0.00",
                        "confidence": 0.95,
                        "source": "ai",
                        "validation_errors": [
                            "Total Amount must be greater than 0"
                        ],
                    },
                }
            },
        )
        rec2 = DocumentRecord(
            document_id=doc2.id,
            document_type="marksheet",
            extraction_status="NEEDS_REVIEW",
            extracted_data={
                "fields": {
                    "student_name": {
                        "value": "Prathamesh Gawade",
                        "normalized_value": "Prathamesh Gawade",
                        "confidence": 0.96,
                        "source": "ocr",
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
                }
            },
        )
        db_session.add_all([rec1, rec2])
        db_session.commit()

        response = client.get("/api/documents/review")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["count"] == 2
        assert len(data["items"]) == 2

        doc_ids = [item["document_id"] for item in data["items"]]
        assert doc1.id in doc_ids
        assert doc2.id in doc_ids
        assert doc3.id not in doc_ids

        # Check universal field extraction in list item
        marksheet_item = next(
            i for i in data["items"] if i["document_id"] == doc2.id
        )
        assert "student_name" in marksheet_item["fields"]
        assert (
            marksheet_item["fields"]["student_name"]["value"]
            == "Prathamesh Gawade"
        )
        assert "roll_number" in marksheet_item["fields"]
        assert (
            "roll_number confidence is below threshold"
            in marksheet_item["validation_errors"]
        )

    def test_get_document_detail_universal_fields(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """GET /api/documents/{id} returns metadata and viewer URL."""
        pdf_file = create_sample_file(temp_workspace / "certificate.pdf")
        doc = Document(
            file_name="certificate.pdf",
            file_path=str(pdf_file),
            file_type="PDF",
            file_size=pdf_file.stat().st_size,
            status="NEEDS_REVIEW",
        )
        db_session.add(doc)
        db_session.commit()

        rec = DocumentRecord(
            document_id=doc.id,
            document_type="certificate",
            extraction_status="NEEDS_REVIEW",
            raw_text="FAMT Certificate: Prathamesh Gawade Roll 19",
            confidence_score=0.78,
            extracted_data={
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
                        "validation_errors": ["Low confidence"],
                    },
                    "percentage": {
                        "value": None,
                        "normalized_value": None,
                        "confidence": None,
                        "source": None,
                        "validation_errors": ["Value not detected"],
                    },
                }
            },
        )
        db_session.add(rec)
        db_session.commit()

        response = client.get(f"/api/documents/{doc.id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["document_id"] == doc.id
        assert data["file_name"] == "certificate.pdf"
        assert data["status"] == "NEEDS_REVIEW"
        assert (
            data["document"]["viewer_url"] == f"/api/documents/{doc.id}/file"
        )
        assert data["raw_text"] == (
            "FAMT Certificate: Prathamesh Gawade Roll 19"
        )

        # Verify universal fields
        fields = data["fields"]
        assert fields["student_name"]["value"] == "Prathmesh Gawade"
        assert fields["student_name"]["confidence"] == 0.96
        assert fields["roll_number"]["value"] == "19"
        assert fields["roll_number"]["confidence"] == 0.61
        assert "Low confidence" in fields["roll_number"]["validation_errors"]
        assert fields["percentage"]["value"] is None

    def test_get_document_detail_not_found(self, client: TestClient):
        """GET /api/documents/{id} returns 404 for nonexistent document."""
        response = client.get("/api/documents/999999")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"]

    def test_document_file_viewer_streams_original_file(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """GET /api/documents/{id}/file streams original uploaded file."""
        original_bytes = b"%PDF-1.4\nOriginal Unmodified Document Stream 12345"
        pdf_file = create_sample_file(
            temp_workspace / "viewer_doc.pdf",
            content=original_bytes,
        )
        doc = Document(
            file_name="viewer_doc.pdf",
            file_path=str(pdf_file),
            file_type="PDF",
            file_size=len(original_bytes),
            status="NEEDS_REVIEW",
        )
        db_session.add(doc)
        db_session.commit()

        response = client.get(f"/api/documents/{doc.id}/file")
        assert response.status_code == status.HTTP_200_OK
        assert response.content == original_bytes
        assert "application/pdf" in response.headers.get("content-type", "")

        # Verify filesystem path was not exposed in headers
        for h_val in response.headers.values():
            assert str(temp_workspace).lower() not in h_val.lower()

    def test_document_file_viewer_not_found_on_disk(
        self,
        client: TestClient,
        db_session: Session,
    ):
        """GET /api/documents/{id}/file returns 404 if file missing on disk."""
        doc = Document(
            file_name="missing.pdf",
            file_path="c:/non_existent_folder/missing.pdf",
            file_type="PDF",
            file_size=1024,
            status="NEEDS_REVIEW",
        )
        db_session.add(doc)
        db_session.commit()

        response = client.get(f"/api/documents/{doc.id}/file")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()

    def test_verify_document_correct_and_add_fields_with_audit(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """POST /api/documents/{id}/verify records corrections, adds fields,

        sets confidence=1.0 and source='human', re-normalizes and verifies.
        """
        pdf_file = create_sample_file(temp_workspace / "student_marksheet.pdf")
        doc = Document(
            file_name="student_marksheet.pdf",
            file_path=str(pdf_file),
            file_type="PDF",
            file_size=pdf_file.stat().st_size,
            status="NEEDS_REVIEW",
        )
        db_session.add(doc)
        db_session.commit()

        rec = DocumentRecord(
            document_id=doc.id,
            document_type="marksheet",
            extraction_status="NEEDS_REVIEW",
            extracted_data={
                "fields": {
                    "student_name": {
                        "value": "Prathmesh G",
                        "normalized_value": "Prathmesh G",
                        "confidence": 0.80,
                        "source": "ocr",
                    },
                    "roll_number": {
                        "value": "19",
                        "normalized_value": "19",
                        "confidence": 0.60,
                        "source": "ocr",
                    },
                }
            },
        )
        db_session.add(rec)
        db_session.commit()

        # Human submits:
        # 1. Corrected student_name -> "Prathamesh Gawade"
        # 2. Added college_name -> "FAMT"
        # 3. Added percentage -> "82.5"
        # 4. Unchanged roll_number -> "19"
        payload = {
            "fields": {
                "student_name": "Prathamesh Gawade",
                "roll_number": "19",
                "college_name": "FAMT",
                "percentage": "82.5",
            },
            "reviewer_id": "reviewer_alice",
            "notes": "Verified against original university physical sheet",
        }

        response = client.post(f"/api/documents/{doc.id}/verify", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["status"] == "VERIFIED"
        fields = data["fields"]

        # 1. Corrected field gets confidence 1.0 and source 'human'
        assert fields["student_name"]["value"] == "Prathamesh Gawade"
        assert fields["student_name"]["confidence"] == 1.0
        assert fields["student_name"]["source"] == "human"

        # 2. Added fields get confidence 1.0 and source 'human'
        assert fields["college_name"]["value"] == "FAMT"
        assert fields["college_name"]["confidence"] == 1.0
        assert fields["college_name"]["source"] == "human"
        assert fields["percentage"]["value"] == "82.5"
        assert fields["percentage"]["confidence"] == 1.0
        assert fields["percentage"]["source"] == "human"

        # 3. Unchanged field retains previous confidence (0.60) & source
        assert fields["roll_number"]["value"] == "19"
        assert fields["roll_number"]["confidence"] == 0.60
        assert fields["roll_number"]["source"] == "ocr"

        # 4. Verify Document DB status updated to VERIFIED
        db_session.refresh(doc)
        assert doc.status == "VERIFIED"
        assert doc.error_message is None

        # 5. Verify DocumentRecord in DB updated
        db_session.refresh(rec)
        assert rec.extraction_status == "VERIFIED"
        assert rec.extracted_data["fields"]["college_name"]["value"] == "FAMT"

        # 6. Verify Audit Logs recorded in DB
        audits = (
            db_session.query(AuditLog)
            .filter(AuditLog.document_id == doc.id)
            .all()
        )
        actions = [a.action for a in audits]
        assert "HUMAN_CORRECTION" in actions
        assert "DOCUMENT_VERIFIED" in actions

        human_audits = [a for a in audits if a.action == "HUMAN_CORRECTION"]
        assert len(human_audits) == 3

        # Verify student_name correction details
        corr_audit = next(
            a for a in human_audits
            if a.details["field_name"] == "student_name"
        )
        assert corr_audit.actor == "reviewer_alice"
        assert corr_audit.details["old_value"] == "Prathmesh G"
        assert corr_audit.details["new_value"] == "Prathamesh Gawade"

        # Verify college_name addition details
        added_audit = next(
            a for a in human_audits
            if a.details["field_name"] == "college_name"
        )
        assert added_audit.actor == "reviewer_alice"
        assert added_audit.details["old_value"] is None
        assert added_audit.details["new_value"] == "FAMT"

    def test_verify_invoice_renormalizes_and_validates(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """POST /api/documents/{id}/verify re-normalizes dates and amounts.

        If amount is corrected to 0.00, document remains in NEEDS_REVIEW.
        When corrected to valid positive amount, transitions to VERIFIED.
        """
        pdf_file = create_sample_file(temp_workspace / "inv_re_review.pdf")
        doc = Document(
            file_name="inv_re_review.pdf",
            file_path=str(pdf_file),
            file_type="PDF",
            file_size=pdf_file.stat().st_size,
            status="NEEDS_REVIEW",
            error_message="Total Amount must be greater than 0",
        )
        db_session.add(doc)
        db_session.commit()

        rec = DocumentRecord(
            document_id=doc.id,
            document_type="invoice",
            extraction_status="NEEDS_REVIEW",
            extracted_data={
                "fields": {
                    "vendor_name": {
                        "value": "ABC Technologies",
                        "confidence": 0.95,
                    },
                    "invoice_number": {
                        "value": "INV-1001",
                        "confidence": 0.95,
                    },
                    "invoice_date": {
                        "value": "05/09/2026",
                        "confidence": 0.90,
                    },
                    "total_amount": {
                        "value": "0.00",
                        "confidence": 0.95,
                    },
                }
            },
        )
        db_session.add(rec)
        db_session.commit()

        # 1. First attempt: human enters Total Amount = "0.00" -> still invalid
        invalid_payload = {
            "fields": {
                "vendor_name": "ABC Technologies",
                "invoice_number": "INV-1001",
                "invoice_date": "05/09/2026",
                "total_amount": "0.00",
            },
            "reviewer_id": "bob",
        }
        res1 = client.post(
            f"/api/documents/{doc.id}/verify", json=invalid_payload
        )
        assert res1.status_code == status.HTTP_200_OK
        data1 = res1.json()
        assert data1["status"] == "NEEDS_REVIEW"
        assert any(
            "Total Amount must be greater than 0" in e
            for e in data1["validation_errors"]
        )

        db_session.refresh(doc)
        assert doc.status == "NEEDS_REVIEW"

        # 2. Second attempt: human corrects Total Amount -> "₹25,500.00"
        # and date format -> "05/09/2026"
        valid_payload = {
            "fields": {
                "vendor_name": "ABC Technologies",
                "invoice_number": "INV-1001",
                "invoice_date": "05/09/2026",
                "total_amount": "₹25,500.00",
            },
            "reviewer_id": "bob",
        }
        res2 = client.post(
            f"/api/documents/{doc.id}/verify", json=valid_payload
        )
        assert res2.status_code == status.HTTP_200_OK
        data2 = res2.json()
        assert data2["status"] == "VERIFIED"

        fields = data2["fields"]
        # Verify re-normalization occurred
        assert fields["invoice_date"]["normalized_value"] == "2026-09-05"
        assert fields["total_amount"]["normalized_value"] == "25500.00"
        assert fields["total_amount"]["confidence"] == 1.0
        assert fields["total_amount"]["source"] == "human"

        db_session.refresh(doc)
        assert doc.status == "VERIFIED"
        assert doc.error_message is None

    def test_verify_employee_record_universal(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Universal test: verify employee record with custom fields."""
        f_name = "employee_onboarding.pdf"
        doc_file = create_sample_file(temp_workspace / f_name)
        doc = Document(
            file_name="employee_onboarding.pdf",
            file_path=str(doc_file),
            file_type="PDF",
            file_size=doc_file.stat().st_size,
            status="NEEDS_REVIEW",
        )
        db_session.add(doc)
        db_session.commit()

        rec = DocumentRecord(
            document_id=doc.id,
            document_type="employee_record",
            extraction_status="NEEDS_REVIEW",
            extracted_data={
                "employee_name": "John Doe",
                "employee_id": "EMP-102",
                "department": "IT",
            },
        )
        db_session.add(rec)
        db_session.commit()

        payload = {
            "fields": {
                "employee_name": "John Doe",
                "employee_id": "EMP-102",
                "department": "Engineering",
                "joining_date": "01/08/2026",
            },
            "reviewer_id": "hr_manager",
        }

        response = client.post(f"/api/documents/{doc.id}/verify", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["status"] == "VERIFIED"
        fields = data["fields"]
        assert fields["department"]["value"] == "Engineering"
        assert fields["department"]["source"] == "human"
        assert fields["joining_date"]["normalized_value"] == "2026-08-01"

        # Verify database record updated
        db_session.refresh(doc)
        assert doc.status == "VERIFIED"

    def test_verify_preserves_existing_unspecified_fields(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Preserve existing fields when only a subset is submitted."""
        f_name = "famt_college_record.pdf"
        doc_file = create_sample_file(temp_workspace / f_name)
        doc = Document(
            file_name=f_name,
            file_path=str(doc_file),
            file_type="PDF",
            file_size=doc_file.stat().st_size,
            status="NEEDS_REVIEW",
        )
        db_session.add(doc)
        db_session.commit()

        rec = DocumentRecord(
            document_id=doc.id,
            document_type="marksheet",
            extraction_status="NEEDS_REVIEW",
            extracted_data={
                "fields": {
                    "student_name": {
                        "value": "Prathmesh",
                        "normalized_value": "Prathmesh",
                        "confidence": 0.85,
                        "source": "ocr",
                    },
                    "roll_number": {
                        "value": "19",
                        "normalized_value": "19",
                        "confidence": 0.90,
                        "source": "ocr",
                    },
                    "college": {
                        "value": "FAMT",
                        "normalized_value": "FAMT",
                        "confidence": 0.95,
                        "source": "ai",
                    },
                }
            },
        )
        db_session.add(rec)
        db_session.commit()

        # Reviewer submits ONLY student_name
        payload = {
            "fields": {
                "student_name": "Prathamesh",
            }
        }

        response = client.post(f"/api/documents/{doc.id}/verify", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["status"] == "VERIFIED"
        fields = data["fields"]

        # student_name is corrected
        assert fields["student_name"]["value"] == "Prathamesh"
        assert fields["student_name"]["source"] == "human"
        assert fields["student_name"]["confidence"] == 1.0

        # roll_number and college are preserved and NOT null
        assert fields["roll_number"]["value"] == "19"
        assert fields["roll_number"]["confidence"] == 0.90
        assert fields["roll_number"]["source"] == "ocr"

        assert fields["college"]["value"] == "FAMT"
        assert fields["college"]["confidence"] == 0.95
        assert fields["college"]["source"] == "ai"

        # Check DB persistence
        db_session.refresh(rec)
        db_fields = rec.extracted_data["fields"]
        assert db_fields["student_name"]["value"] == "Prathamesh"
        assert db_fields["roll_number"]["value"] == "19"
        assert db_fields["college"]["value"] == "FAMT"

    def test_verify_manual_data_entry_for_null_extracted_field(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Allow manual entry when a field extraction completely failed."""
        f_name = "report_card.pdf"
        doc_file = create_sample_file(temp_workspace / f_name)
        doc = Document(
            file_name=f_name,
            file_path=str(doc_file),
            file_type="PDF",
            file_size=doc_file.stat().st_size,
            status="NEEDS_REVIEW",
        )
        db_session.add(doc)
        db_session.commit()

        rec = DocumentRecord(
            document_id=doc.id,
            document_type="report_card",
            extraction_status="NEEDS_REVIEW",
            extracted_data={
                "fields": {
                    "student_name": {
                        "value": "Prathamesh Gawade",
                        "normalized_value": "Prathamesh Gawade",
                        "confidence": 0.95,
                        "source": "ocr",
                    },
                    "percentage": {
                        "value": None,
                        "normalized_value": None,
                        "confidence": None,
                        "source": None,
                    },
                }
            },
        )
        db_session.add(rec)
        db_session.commit()

        # Reviewer manually enters missing percentage
        payload = {
            "fields": {
                "percentage": "82.5",
            }
        }

        response = client.post(f"/api/documents/{doc.id}/verify", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["status"] == "VERIFIED"
        fields = data["fields"]
        assert fields["student_name"]["value"] == "Prathamesh Gawade"
        assert fields["percentage"]["value"] == "82.5"
        assert fields["percentage"]["confidence"] == 1.0
        assert fields["percentage"]["source"] == "human"

        # Check audit log recorded HUMAN_CORRECTION
        audits = (
            db_session.query(AuditLog)
            .filter(AuditLog.document_id == doc.id)
            .all()
        )
        added_audits = [a for a in audits if a.action == "HUMAN_CORRECTION"]
        assert len(added_audits) == 1
        assert added_audits[0].details["field_name"] == "percentage"
        assert added_audits[0].details["old_value"] is None
        assert added_audits[0].details["new_value"] == "82.5"
        assert added_audits[0].details["action"] == "HUMAN_CORRECTION"
        assert added_audits[0].details["document_id"] == doc.id

    def test_verify_correct_and_add_new_fields_together(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Allow correcting existing and adding new fields simultaneously."""
        f_name = "student_details.pdf"
        doc_file = create_sample_file(temp_workspace / f_name)
        doc = Document(
            file_name=f_name,
            file_path=str(doc_file),
            file_type="PDF",
            file_size=doc_file.stat().st_size,
            status="NEEDS_REVIEW",
        )
        db_session.add(doc)
        db_session.commit()

        rec = DocumentRecord(
            document_id=doc.id,
            document_type="student_record",
            extraction_status="NEEDS_REVIEW",
            extracted_data={
                "student_name": "Prathmesh",
                "roll_number": "19",
            },
        )
        db_session.add(rec)
        db_session.commit()

        # Reviewer corrects student_name and adds department + percentage
        payload = {
            "fields": {
                "student_name": "Prathamesh Gawade",
                "roll_number": "19",
                "percentage": "82.5",
                "department": "Information Technology",
            }
        }

        response = client.post(f"/api/documents/{doc.id}/verify", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["status"] == "VERIFIED"
        fields = data["fields"]
        assert fields["student_name"]["value"] == "Prathamesh Gawade"
        assert fields["student_name"]["source"] == "human"

        assert fields["roll_number"]["value"] == "19"
        assert fields["percentage"]["value"] == "82.5"
        assert fields["percentage"]["source"] == "human"

        assert fields["department"]["value"] == "Information Technology"
        assert fields["department"]["source"] == "human"

    def test_verify_no_audit_log_when_normalized_value_unchanged(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Actual changes only: no audit if old == new normalized."""
        f_name = "sample_invoice.pdf"
        doc_file = create_sample_file(temp_workspace / f_name)
        doc = Document(
            file_name=f_name,
            file_path=str(doc_file),
            file_type="PDF",
            file_size=doc_file.stat().st_size,
            status="NEEDS_REVIEW",
        )
        db_session.add(doc)
        db_session.commit()

        rec = DocumentRecord(
            document_id=doc.id,
            document_type="invoice",
            extraction_status="NEEDS_REVIEW",
            extracted_data={
                "fields": {
                    "vendor_name": {
                        "value": "ABC Technologies",
                        "normalized_value": "ABC Technologies",
                        "confidence": 0.95,
                        "source": "rule",
                    },
                    "invoice_number": {
                        "value": "INV-1001",
                        "normalized_value": "INV-1001",
                        "confidence": 0.92,
                        "source": "rule",
                    },
                    "invoice_date": {
                        "value": "2026-09-05",
                        "normalized_value": "2026-09-05",
                        "confidence": 0.90,
                        "source": "rule",
                    },
                    "total_amount": {
                        "value": "25500.00",
                        "normalized_value": "25500.00",
                        "confidence": 0.94,
                        "source": "rule",
                    },
                }
            },
        )
        db_session.add(rec)
        db_session.commit()

        # Reviewer submits ₹25,500 (normalizes to 25500.00)
        payload = {
            "fields": {
                "total_amount": "₹25,500",
            }
        }

        response = client.post(f"/api/documents/{doc.id}/verify", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["status"] == "VERIFIED"
        # No actual change occurred -> no HUMAN_CORRECTION in audit_trail
        corr_actions = [
            a["action"]
            for a in data.get("audit_trail", [])
            if a["action"] == "HUMAN_CORRECTION"
        ]
        assert len(corr_actions) == 0

        # In DB audit_logs, verify no HUMAN_CORRECTION entry was created
        audits = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.document_id == doc.id,
                AuditLog.action == "HUMAN_CORRECTION",
            )
            .all()
        )
        assert len(audits) == 0

        # Extraction metadata should be preserved
        fields = data["fields"]
        assert fields["total_amount"]["normalized_value"] == "25500.00"
        assert fields["total_amount"]["confidence"] == 0.94
        assert fields["total_amount"]["source"] == "rule"

    def test_verify_transaction_safety_rollback_on_db_error(
        self,
        db_session: Session,
        temp_workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Transaction safety: rollback on DB failure."""
        f_name = "test_rollback.pdf"
        doc_file = create_sample_file(temp_workspace / f_name)
        doc = Document(
            file_name=f_name,
            file_path=str(doc_file),
            file_type="PDF",
            file_size=doc_file.stat().st_size,
            status="NEEDS_REVIEW",
            error_message="Initial review needed",
        )
        db_session.add(doc)
        db_session.commit()

        rec = DocumentRecord(
            document_id=doc.id,
            document_type="document",
            extraction_status="NEEDS_REVIEW",
            extracted_data={
                "fields": {
                    "title": {
                        "value": "Initial Title",
                        "normalized_value": "Initial Title",
                    }
                }
            },
        )
        db_session.add(rec)
        db_session.commit()

        # Mock db.commit to raise an exception simulating a database failure
        def mock_commit():
            raise RuntimeError("Simulated DB failure during verification")

        monkeypatch.setattr(db_session, "commit", mock_commit)

        req = VerifyDocumentRequest(
            fields={"title": "Proposed New Title"},
            reviewer_id="tester",
        )

        with pytest.raises(
            RuntimeError, match="Simulated DB failure during verification"
        ):
            HITLVerificationService.verify_document(
                db=db_session,
                document_id=doc.id,
                request=req,
            )

        # Verify document remains in original NEEDS_REVIEW state
        db_session.rollback()
        db_doc = (
            db_session.query(Document)
            .filter(Document.id == doc.id)
            .first()
        )
        assert db_doc.status == "NEEDS_REVIEW"
        assert db_doc.error_message == "Initial review needed"

    def test_get_document_detail_certificate_with_null_percentage(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """GET /api/documents/{id} returns universal document review data."""
        f_name = "certificate.pdf"
        doc_file = create_sample_file(temp_workspace / f_name)
        doc = Document(
            file_name=f_name,
            file_path=str(doc_file),
            file_type="PDF",
            file_size=doc_file.stat().st_size,
            status="NEEDS_REVIEW",
            error_message="percentage is missing",
        )
        db_session.add(doc)
        db_session.commit()

        rec = DocumentRecord(
            document_id=doc.id,
            document_type="certificate",
            extraction_status="NEEDS_REVIEW",
            extracted_data={
                "fields": {
                    "student_name": {
                        "value": "Prathmesh Gawade",
                        "normalized_value": "Prathmesh Gawade",
                        "confidence": 0.96,
                        "source": "ocr",
                    },
                    "roll_number": {
                        "value": "19",
                        "normalized_value": "19",
                        "confidence": 0.61,
                        "source": "ocr",
                    },
                    "percentage": {
                        "value": None,
                        "normalized_value": None,
                        "confidence": None,
                        "source": None,
                    },
                }
            },
        )
        db_session.add(rec)
        db_session.commit()

        response = client.get(f"/api/documents/{doc.id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["document_id"] == doc.id
        assert data["file_name"] == "certificate.pdf"
        assert data["file_type"] == "PDF"
        assert (
            data["document"]["viewer_url"] == f"/api/documents/{doc.id}/file"
        )

        fields = data["fields"]
        assert fields["student_name"]["value"] == "Prathmesh Gawade"
        assert fields["student_name"]["confidence"] == 0.96
        assert fields["student_name"]["source"] == "ocr"

        assert fields["roll_number"]["value"] == "19"
        assert fields["roll_number"]["confidence"] == 0.61
        assert fields["roll_number"]["source"] == "ocr"

        assert fields["percentage"]["value"] is None
        assert fields["percentage"]["confidence"] is None
        assert fields["percentage"]["source"] is None

        assert "percentage is missing" in data["validation_errors"]

    def test_verify_example_completely_missing_extraction(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Reviewer adds fields when extraction returned empty fields."""
        f_name = "blank_extraction.pdf"
        doc_file = create_sample_file(temp_workspace / f_name)
        doc = Document(
            file_name=f_name,
            file_path=str(doc_file),
            file_type="PDF",
            file_size=doc_file.stat().st_size,
            status="NEEDS_REVIEW",
        )
        db_session.add(doc)
        db_session.commit()

        # Document extraction returned completely empty fields
        rec = DocumentRecord(
            document_id=doc.id,
            document_type="certificate",
            extraction_status="NEEDS_REVIEW",
            extracted_data={"fields": {}},
        )
        db_session.add(rec)
        db_session.commit()

        # Reviewer submits manually entered fields
        payload = {
            "fields": {
                "student_name": "Prathamesh Gawade",
                "roll_number": "19",
                "college_name": "FAMT",
            }
        }

        response = client.post(f"/api/documents/{doc.id}/verify", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["status"] == "VERIFIED"
        fields = data["fields"]
        assert fields["student_name"]["value"] == "Prathamesh Gawade"
        assert fields["student_name"]["source"] == "human"
        assert fields["roll_number"]["value"] == "19"
        assert fields["college_name"]["value"] == "FAMT"

        # Check DB audit logs: 3 HUMAN_CORRECTION entries
        audits = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.document_id == doc.id,
                AuditLog.action == "HUMAN_CORRECTION",
            )
            .all()
        )
        assert len(audits) == 3

    def test_verify_example_mixed_correction(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Mixed correction: edit existing, preserve other, enter missing."""
        f_name = "mixed_doc.pdf"
        doc_file = create_sample_file(temp_workspace / f_name)
        doc = Document(
            file_name=f_name,
            file_path=str(doc_file),
            file_type="PDF",
            file_size=doc_file.stat().st_size,
            status="NEEDS_REVIEW",
        )
        db_session.add(doc)
        db_session.commit()

        # Existing: student_name=Prathmesh, roll_number=19, college_name=null
        rec = DocumentRecord(
            document_id=doc.id,
            document_type="student_record",
            extraction_status="NEEDS_REVIEW",
            extracted_data={
                "fields": {
                    "student_name": {
                        "value": "Prathmesh",
                        "normalized_value": "Prathmesh",
                        "confidence": 0.85,
                        "source": "ocr",
                    },
                    "roll_number": {
                        "value": "19",
                        "normalized_value": "19",
                        "confidence": 0.90,
                        "source": "ocr",
                    },
                    "college_name": {
                        "value": None,
                        "normalized_value": None,
                        "confidence": None,
                        "source": None,
                    },
                }
            },
        )
        db_session.add(rec)
        db_session.commit()

        # Reviewer submits student_name and college_name
        payload = {
            "fields": {
                "student_name": "Prathamesh",
                "college_name": (
                    "Finolex Academy of Management and Technology"
                ),
            }
        }

        response = client.post(f"/api/documents/{doc.id}/verify", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["status"] == "VERIFIED"
        fields = data["fields"]

        # 1. student_name was corrected
        assert fields["student_name"]["value"] == "Prathamesh"
        assert fields["student_name"]["source"] == "human"

        # 2. roll_number was preserved (not null!)
        assert fields["roll_number"]["value"] == "19"
        assert fields["roll_number"]["confidence"] == 0.90
        assert fields["roll_number"]["source"] == "ocr"

        # 3. college_name was populated
        expected_college = "Finolex Academy of Management and Technology"
        assert fields["college_name"]["value"] == expected_college
        assert fields["college_name"]["source"] == "human"

        # 4. Audit trail checks
        audits = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.document_id == doc.id,
                AuditLog.action == "HUMAN_CORRECTION",
            )
            .all()
        )
        assert len(audits) == 2

        stud_audit = next(
            a for a in audits
            if a.details["field_name"] == "student_name"
        )
        assert stud_audit.details["old_value"] == "Prathmesh"
        assert stud_audit.details["new_value"] == "Prathamesh"

        coll_audit = next(
            a for a in audits
            if a.details["field_name"] == "college_name"
        )
        assert coll_audit.details["old_value"] is None
        assert coll_audit.details["new_value"] == expected_college
