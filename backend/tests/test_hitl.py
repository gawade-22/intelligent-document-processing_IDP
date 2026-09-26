"""Universal Human-in-the-Loop (HITL) Verification Test Suite.

Covers all 19 required HITL tests:
Test 1  — Review List (GET /api/documents/review filters NEEDS_REVIEW only)
Test 2  — Get Document (GET /api/documents/{id} complete metadata/errors)
Test 3  — Correct Existing Field (Change student_name and verify persistence)
Test 4  — Add Missing Field (Existing student_name, add roll_number)
Test 5  — Add Completely New Field (Unextracted field manually added)
Test 6  — Empty Extraction (Start with {}, manually submit multiple fields)
Test 7  — Partial Correction (Change one field, other fields unchanged)
Test 8  — Normalization (06/09/2026 -> 2026-09-05, ₹25,500 -> 25500.00)
Test 9  — Invalid Data (Validation error, not marked VERIFIED)
Test 10 — Human Source (Corrected/added fields have source='human')
Test 11 — Audit Correction (old, new, field, doc_id, action, timestamp)
Test 12 — New Field Audit (old_value=None, new_value=val for added field)
Test 13 — No False Audit (Equivalent after normalization creates no audit)
Test 14 — Successful Verification (NEEDS_REVIEW -> VERIFIED)
Test 15 — Still Invalid (Incomplete data: NEEDS_REVIEW -> NEEDS_REVIEW)
Test 16 — Verified Document (Reject modifying an already VERIFIED doc)
Test 17 — Failed Document (Reject verifying a FAILED document)
Test 18 — Transaction Rollback (Force DB failure, verify no partial state)
Test 19 — Original File Preservation (Original file_path and content)
"""

import hashlib
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
# Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Provides an isolated in-memory SQLite database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Provides a TestClient overriding the get_db dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def temp_workspace() -> Generator[Path, None, None]:
    """Temporary workspace directory for test document files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def create_sample_file(
    path: Path, content: bytes = b"%PDF-1.4 sample"
) -> Path:
    """Helper to create a sample file with dummy content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def file_sha256(path: Path) -> str:
    """Helper to compute sha256 of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


# =============================================================================
# Test Suite: Universal HITL Workflow (Tests 1 - 19)
# =============================================================================

class TestUniversalHITL:
    """Complete 19-test suite for Universal Human-in-the-Loop verification."""

    def test_01_review_list_returns_only_needs_review(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 1: Verify only NEEDS_REVIEW documents are returned."""
        f1 = create_sample_file(temp_workspace / "doc1.pdf")
        f2 = create_sample_file(temp_workspace / "doc2.pdf")
        f3 = create_sample_file(temp_workspace / "doc3.pdf")

        d_review = Document(
            file_name="doc1.pdf",
            file_path=str(f1),
            file_type="PDF",
            file_size=100,
            status="NEEDS_REVIEW",
            error_message="Missing percentage",
        )
        d_verified = Document(
            file_name="doc2.pdf",
            file_path=str(f2),
            file_type="PDF",
            file_size=100,
            status="VERIFIED",
        )
        d_failed = Document(
            file_name="doc3.pdf",
            file_path=str(f3),
            file_type="PDF",
            file_size=100,
            status="FAILED",
            error_message="Corrupt file",
        )
        db_session.add_all([d_review, d_verified, d_failed])
        db_session.commit()

        # Add record for review document
        rec = DocumentRecord(
            document_id=d_review.id,
            document_type="certificate",
            extraction_status="NEEDS_REVIEW",
            extracted_data={
                "fields": {
                    "student_name": {
                        "value": "Prathamesh",
                        "confidence": 0.95,
                        "source": "ocr",
                    }
                }
            },
        )
        db_session.add(rec)
        db_session.commit()

        response = client.get("/api/documents/review")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["count"] == 1
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["document_id"] == d_review.id
        assert item["status"] == "NEEDS_REVIEW"
        assert "student_name" in item["fields"]

    def test_02_get_document_universal_detail(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 2: Verify GET /api/documents/{id} returns universal detail."""
        f_name = "certificate.pdf"
        doc_file = create_sample_file(temp_workspace / f_name)
        doc = Document(
            file_name=f_name,
            file_path=str(doc_file),
            file_type="PDF",
            file_size=200,
            status="NEEDS_REVIEW",
            error_message="percentage is missing",
        )
        db_session.add(doc)
        db_session.commit()

        rec = DocumentRecord(
            document_id=doc.id,
            document_type="certificate",
            extraction_status="NEEDS_REVIEW",
            raw_text="Name: Prathmesh\nRoll: 19",
            confidence_score=0.785,
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
        assert data["status"] == "NEEDS_REVIEW"
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

        assert "percentage is missing" in data["validation_errors"]

    def test_03_correct_existing_field_persisted(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 3: Change student_name and verify it is persisted in DB."""
        doc_file = create_sample_file(temp_workspace / "student.pdf")
        doc = Document(
            file_name="student.pdf",
            file_path=str(doc_file),
            file_type="PDF",
            file_size=150,
            status="NEEDS_REVIEW",
        )
        db_session.add(doc)
        db_session.commit()

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
                    }
                }
            },
        )
        db_session.add(rec)
        db_session.commit()

        payload = {"fields": {"student_name": "Prathamesh Gawade"}}
        response = client.post(f"/api/documents/{doc.id}/verify", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["fields"]["student_name"]["value"] == "Prathamesh Gawade"

        # Verify DB persistence
        db_session.refresh(rec)
        persisted = rec.extracted_data["fields"]["student_name"]["value"]
        assert persisted == "Prathamesh Gawade"

    def test_04_add_missing_field(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 4: Existing student_name, submit roll_number -> persisted."""
        doc_file = create_sample_file(temp_workspace / "student_add.pdf")
        doc = Document(
            file_name="student_add.pdf",
            file_path=str(doc_file),
            file_type="PDF",
            file_size=150,
            status="NEEDS_REVIEW",
        )
        db_session.add(doc)
        db_session.commit()

        rec = DocumentRecord(
            document_id=doc.id,
            document_type="student_record",
            extraction_status="NEEDS_REVIEW",
            extracted_data={
                "fields": {
                    "student_name": {
                        "value": "Prathamesh",
                        "normalized_value": "Prathamesh",
                        "confidence": 0.95,
                        "source": "ocr",
                    }
                }
            },
        )
        db_session.add(rec)
        db_session.commit()

        # Submit roll_number
        payload = {"fields": {"roll_number": "19"}}
        response = client.post(f"/api/documents/{doc.id}/verify", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["fields"]["student_name"]["value"] == "Prathamesh"
        assert data["fields"]["roll_number"]["value"] == "19"

        # Check DB
        db_session.refresh(rec)
        assert rec.extracted_data["fields"]["roll_number"]["value"] == "19"

    def test_05_add_completely_new_field(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 5: Manually add field not originally in extraction schema."""
        doc_file = create_sample_file(temp_workspace / "new_field.pdf")
        doc = Document(
            file_name="new_field.pdf",
            file_path=str(doc_file),
            file_type="PDF",
            file_size=150,
            status="NEEDS_REVIEW",
        )
        db_session.add(doc)
        db_session.commit()

        rec = DocumentRecord(
            document_id=doc.id,
            document_type="generic_doc",
            extraction_status="NEEDS_REVIEW",
            extracted_data={
                "fields": {
                    "title": {
                        "value": "Sample Document",
                        "confidence": 0.90,
                        "source": "ocr",
                    }
                }
            },
        )
        db_session.add(rec)
        db_session.commit()

        payload = {"fields": {"department": "Information Technology"}}
        response = client.post(f"/api/documents/{doc.id}/verify", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert (
            data["fields"]["department"]["value"] == "Information Technology"
        )
        assert data["fields"]["title"]["value"] == "Sample Document"

        db_session.refresh(rec)
        assert (
            rec.extracted_data["fields"]["department"]["value"]
            == "Information Technology"
        )

    def test_06_empty_extraction_manual_submit(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 6: Start with {} extraction, submit multiple fields."""
        doc_file = create_sample_file(temp_workspace / "empty.pdf")
        doc = Document(
            file_name="empty.pdf",
            file_path=str(doc_file),
            file_type="PDF",
            file_size=150,
            status="NEEDS_REVIEW",
        )
        db_session.add(doc)
        db_session.commit()

        rec = DocumentRecord(
            document_id=doc.id,
            document_type="certificate",
            extraction_status="NEEDS_REVIEW",
            extracted_data={"fields": {}},
        )
        db_session.add(rec)
        db_session.commit()

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
        assert len(data["fields"]) == 3
        assert data["fields"]["student_name"]["value"] == "Prathamesh Gawade"
        assert data["fields"]["roll_number"]["value"] == "19"
        assert data["fields"]["college_name"]["value"] == "FAMT"

    def test_07_partial_correction_preserves_other_fields(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 7: Change only one field, all other fields remain unchanged."""
        doc_file = create_sample_file(temp_workspace / "partial.pdf")
        doc = Document(
            file_name="partial.pdf",
            file_path=str(doc_file),
            file_type="PDF",
            file_size=150,
            status="NEEDS_REVIEW",
        )
        db_session.add(doc)
        db_session.commit()

        rec = DocumentRecord(
            document_id=doc.id,
            document_type="record",
            extraction_status="NEEDS_REVIEW",
            extracted_data={
                "fields": {
                    "field_a": {
                        "value": "Alpha",
                        "confidence": 0.88,
                        "source": "ocr",
                    },
                    "field_b": {
                        "value": "Beta",
                        "confidence": 0.92,
                        "source": "ai",
                    },
                    "field_c": {
                        "value": "Gamma",
                        "confidence": 0.95,
                        "source": "rule",
                    },
                }
            },
        )
        db_session.add(rec)
        db_session.commit()

        # Correct only field_a
        payload = {"fields": {"field_a": "Alpha Corrected"}}
        response = client.post(f"/api/documents/{doc.id}/verify", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        fields = data["fields"]
        assert fields["field_a"]["value"] == "Alpha Corrected"
        assert fields["field_a"]["source"] == "human"

        # field_b and field_c remain unchanged
        assert fields["field_b"]["value"] == "Beta"
        assert fields["field_b"]["confidence"] == 0.92
        assert fields["field_b"]["source"] == "ai"

        assert fields["field_c"]["value"] == "Gamma"
        assert fields["field_c"]["confidence"] == 0.95
        assert fields["field_c"]["source"] == "rule"

    def test_08_normalization_date_and_amount(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 8: Verify normalization service normalizes date and amount."""
        doc_file = create_sample_file(temp_workspace / "invoice_norm.pdf")
        doc = Document(
            file_name="invoice_norm.pdf",
            file_path=str(doc_file),
            file_type="PDF",
            file_size=150,
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
                    "vendor_name": {"value": "Acme Corp"},
                    "invoice_number": {"value": "INV-100"},
                    "invoice_date": {"value": "unparseable-date"},
                    "total_amount": {"value": "0"},
                }
            },
        )
        db_session.add(rec)
        db_session.commit()

        payload = {
            "fields": {
                "vendor_name": "Acme Corp",
                "invoice_number": "INV-100",
                "invoice_date": "06/09/2026",
                "total_amount": "₹25,500",
            }
        }
        response = client.post(f"/api/documents/{doc.id}/verify", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["status"] == "VERIFIED"
        fields = data["fields"]
        assert fields["invoice_date"]["normalized_value"] == "2026-09-06"
        assert fields["total_amount"]["normalized_value"] == "25500.00"

    def test_09_invalid_data_fails_validation_and_not_verified(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 9: Submit invalid values -> validation error, not VERIFIED."""
        doc_file = create_sample_file(temp_workspace / "inv_invalid.pdf")
        doc = Document(
            file_name="inv_invalid.pdf",
            file_path=str(doc_file),
            file_type="PDF",
            file_size=150,
            status="NEEDS_REVIEW",
            error_message="Initial error",
        )
        db_session.add(doc)
        db_session.commit()

        rec = DocumentRecord(
            document_id=doc.id,
            document_type="invoice",
            extraction_status="NEEDS_REVIEW",
            extracted_data={
                "fields": {
                    "vendor_name": {"value": "Acme Corp"},
                    "invoice_number": {"value": "INV-101"},
                    "invoice_date": {"value": "2026-09-01"},
                    "total_amount": {"value": "100.00"},
                }
            },
        )
        db_session.add(rec)
        db_session.commit()

        # Submit invalid negative/zero amount
        payload = {
            "fields": {
                "total_amount": "-500",
            }
        }
        response = client.post(f"/api/documents/{doc.id}/verify", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Document must NOT be marked VERIFIED
        assert data["status"] == "NEEDS_REVIEW"
        assert len(data["validation_errors"]) > 0

        # DB must still show NEEDS_REVIEW
        db_session.refresh(doc)
        assert doc.status == "NEEDS_REVIEW"

    def test_10_human_source_attribution(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 10: Verify corrected/added fields marked source='human'."""
        doc_file = create_sample_file(temp_workspace / "human_src.pdf")
        doc = Document(
            file_name="human_src.pdf",
            file_path=str(doc_file),
            file_type="PDF",
            file_size=150,
            status="NEEDS_REVIEW",
        )
        db_session.add(doc)
        db_session.commit()

        rec = DocumentRecord(
            document_id=doc.id,
            document_type="report",
            extraction_status="NEEDS_REVIEW",
            extracted_data={
                "fields": {
                    "field_1": {
                        "value": "Old",
                        "confidence": 0.5,
                        "source": "ocr",
                    }
                }
            },
        )
        db_session.add(rec)
        db_session.commit()

        # Correct field_1 and add field_2
        payload = {
            "fields": {
                "field_1": "Corrected",
                "field_2": "Newly Added",
            }
        }
        response = client.post(f"/api/documents/{doc.id}/verify", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["fields"]["field_1"]["source"] == "human"
        assert data["fields"]["field_2"]["source"] == "human"
        assert data["fields"]["field_1"]["confidence"] == 1.0
        assert data["fields"]["field_2"]["confidence"] == 1.0

    def test_11_audit_correction_records_all_fields(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 11: Verify old, new, field, doc_id, action, timestamp."""
        doc_file = create_sample_file(temp_workspace / "audit.pdf")
        doc = Document(
            file_name="audit.pdf",
            file_path=str(doc_file),
            file_type="PDF",
            file_size=150,
            status="NEEDS_REVIEW",
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
                        "value": "Prathmesh",
                        "normalized_value": "Prathmesh",
                    }
                }
            },
        )
        db_session.add(rec)
        db_session.commit()

        payload = {"fields": {"student_name": "Prathamesh Gawade"}}
        response = client.post(f"/api/documents/{doc.id}/verify", json=payload)
        assert response.status_code == status.HTTP_200_OK

        audit = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.document_id == doc.id,
                AuditLog.action == "HUMAN_CORRECTION",
            )
            .first()
        )
        assert audit is not None
        assert audit.document_id == doc.id
        assert audit.action == "HUMAN_CORRECTION"
        assert audit.created_at is not None

        details = audit.details
        assert details["field_name"] == "student_name"
        assert details["old_value"] == "Prathmesh"
        assert details["new_value"] == "Prathamesh Gawade"
        assert details["document_id"] == doc.id
        assert details["action"] == "HUMAN_CORRECTION"

    def test_12_new_field_audit_has_null_old_value(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 12: Verify old_value=None, new_value=val for added field."""
        doc_file = create_sample_file(temp_workspace / "new_audit.pdf")
        doc = Document(
            file_name="new_audit.pdf",
            file_path=str(doc_file),
            file_type="PDF",
            file_size=150,
            status="NEEDS_REVIEW",
        )
        db_session.add(doc)
        db_session.commit()

        rec = DocumentRecord(
            document_id=doc.id,
            document_type="student_record",
            extraction_status="NEEDS_REVIEW",
            extracted_data={"fields": {}},
        )
        db_session.add(rec)
        db_session.commit()

        payload = {"fields": {"percentage": "82.5"}}
        response = client.post(f"/api/documents/{doc.id}/verify", json=payload)
        assert response.status_code == status.HTTP_200_OK

        audit = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.document_id == doc.id,
                AuditLog.action == "HUMAN_CORRECTION",
            )
            .first()
        )
        assert audit is not None
        assert audit.details["old_value"] is None
        assert audit.details["new_value"] == "82.5"
        assert audit.details["field_name"] == "percentage"

    def test_13_no_false_audit_for_normalized_equivalence(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 13: Submit value equivalent after normalization -> no audit."""
        doc_file = create_sample_file(temp_workspace / "no_false.pdf")
        doc = Document(
            file_name="no_false.pdf",
            file_path=str(doc_file),
            file_type="PDF",
            file_size=150,
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
                    "total_amount": {
                        "value": "25500.00",
                        "normalized_value": "25500.00",
                        "confidence": 0.95,
                        "source": "rule",
                    }
                }
            },
        )
        db_session.add(rec)
        db_session.commit()

        # Submit formatted currency string equivalent to 25500.00
        payload = {"fields": {"total_amount": "₹25,500"}}
        response = client.post(f"/api/documents/{doc.id}/verify", json=payload)
        assert response.status_code == status.HTTP_200_OK

        audits = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.document_id == doc.id,
                AuditLog.action == "HUMAN_CORRECTION",
            )
            .all()
        )
        assert len(audits) == 0

    def test_14_successful_verification_needs_review_to_verified(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 14: Valid corrected data: NEEDS_REVIEW -> VERIFIED."""
        doc_file = create_sample_file(temp_workspace / "success_v.pdf")
        doc = Document(
            file_name="success_v.pdf",
            file_path=str(doc_file),
            file_type="PDF",
            file_size=150,
            status="NEEDS_REVIEW",
        )
        db_session.add(doc)
        db_session.commit()

        rec = DocumentRecord(
            document_id=doc.id,
            document_type="certificate",
            extraction_status="NEEDS_REVIEW",
            extracted_data={"fields": {}},
        )
        db_session.add(rec)
        db_session.commit()

        payload = {
            "fields": {
                "student_name": "Prathamesh Gawade",
                "roll_number": "19",
            }
        }
        response = client.post(f"/api/documents/{doc.id}/verify", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["status"] == "VERIFIED"

        db_session.refresh(doc)
        assert doc.status == "VERIFIED"

    def test_15_still_invalid_remains_needs_review(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 15: Incomplete/invalid data remains NEEDS_REVIEW."""
        doc_file = create_sample_file(temp_workspace / "still_inv.pdf")
        doc = Document(
            file_name="still_inv.pdf",
            file_path=str(doc_file),
            file_type="PDF",
            file_size=150,
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
                    "vendor_name": {"value": "Acme Corp"},
                    "invoice_number": {"value": ""},  # empty -> invalid
                    "invoice_date": {"value": "2026-09-01"},
                    "total_amount": {"value": "100.00"},
                }
            },
        )
        db_session.add(rec)
        db_session.commit()

        payload = {"fields": {"vendor_name": "Acme Corp Updated"}}
        response = client.post(f"/api/documents/{doc.id}/verify", json=payload)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["status"] == "NEEDS_REVIEW"
        assert len(data["validation_errors"]) > 0

        db_session.refresh(doc)
        assert doc.status == "NEEDS_REVIEW"

    def test_16_verified_document_rejects_modification(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 16: Reject modifying an already VERIFIED document."""
        doc_file = create_sample_file(temp_workspace / "already_verified.pdf")
        doc = Document(
            file_name="already_verified.pdf",
            file_path=str(doc_file),
            file_type="PDF",
            file_size=150,
            status="VERIFIED",
        )
        db_session.add(doc)
        db_session.commit()

        rec = DocumentRecord(
            document_id=doc.id,
            document_type="certificate",
            extraction_status="VERIFIED",
            extracted_data={
                "fields": {"student_name": {"value": "Prathamesh"}}
            },
        )
        db_session.add(rec)
        db_session.commit()

        payload = {"fields": {"student_name": "New Name"}}
        response = client.post(f"/api/documents/{doc.id}/verify", json=payload)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already verified" in response.json()["detail"].lower()

        # Database record must remain untouched
        db_session.refresh(rec)
        assert (
            rec.extracted_data["fields"]["student_name"]["value"]
            == "Prathamesh"
        )

    def test_17_failed_document_rejected_from_hitl(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
    ):
        """Test 17: FAILED document cannot be verified and is excluded."""
        doc_file = create_sample_file(temp_workspace / "failed.pdf")
        doc = Document(
            file_name="failed.pdf",
            file_path=str(doc_file),
            file_type="PDF",
            file_size=150,
            status="FAILED",
            error_message="OCR execution failed",
        )
        db_session.add(doc)
        db_session.commit()

        # 1. Excluded from GET /api/documents/review
        resp_list = client.get("/api/documents/review")
        assert resp_list.status_code == status.HTTP_200_OK
        ids = [item["document_id"] for item in resp_list.json()["items"]]
        assert doc.id not in ids

        # 2. Rejected by POST /api/documents/{id}/verify
        payload = {"fields": {"student_name": "Prathamesh"}}
        resp_verify = client.post(
            f"/api/documents/{doc.id}/verify", json=payload
        )
        assert resp_verify.status_code == status.HTTP_400_BAD_REQUEST
        assert "failed" in resp_verify.json()["detail"].lower()

    def test_18_transaction_rollback_on_database_error(
        self,
        db_session: Session,
        temp_workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Test 18: Forced DB failure rolls back, no partial state."""
        doc_file = create_sample_file(temp_workspace / "rollback.pdf")
        doc = Document(
            file_name="rollback.pdf",
            file_path=str(doc_file),
            file_type="PDF",
            file_size=150,
            status="NEEDS_REVIEW",
            error_message="Initial need review",
        )
        db_session.add(doc)
        db_session.commit()

        rec = DocumentRecord(
            document_id=doc.id,
            document_type="document",
            extraction_status="NEEDS_REVIEW",
            extracted_data={"fields": {"title": {"value": "Original Title"}}},
        )
        db_session.add(rec)
        db_session.commit()

        def mock_commit():
            raise RuntimeError("Database connection lost during commit")

        monkeypatch.setattr(db_session, "commit", mock_commit)

        req = VerifyDocumentRequest(fields={"title": "Altered Title"})
        with pytest.raises(
            RuntimeError, match="Database connection lost during commit"
        ):
            HITLVerificationService.verify_document(
                db=db_session,
                document_id=doc.id,
                request=req,
            )

        db_session.rollback()
        db_doc = (
            db_session.query(Document)
            .filter(Document.id == doc.id)
            .first()
        )
        assert db_doc.status == "NEEDS_REVIEW"
        assert db_doc.error_message == "Initial need review"

    def test_19_original_file_preservation_across_all_states(
        self,
        client: TestClient,
        db_session: Session,
        temp_workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Test 19: Original file and content remain strictly unchanged."""
        original_bytes = b"%PDF-1.4 sample original document binary stream"
        doc_file = create_sample_file(
            temp_workspace / "immutable_original.pdf", content=original_bytes
        )
        original_hash = file_sha256(doc_file)
        original_path_str = str(doc_file)

        doc = Document(
            file_name="immutable_original.pdf",
            file_path=original_path_str,
            file_type="PDF",
            file_size=len(original_bytes),
            status="NEEDS_REVIEW",
        )
        db_session.add(doc)
        db_session.commit()

        rec = DocumentRecord(
            document_id=doc.id,
            document_type="certificate",
            extraction_status="NEEDS_REVIEW",
            extracted_data={"fields": {"title": {"value": "Cert"}}},
        )
        db_session.add(rec)
        db_session.commit()

        # 1. After successful verification
        client.post(
            f"/api/documents/{doc.id}/verify",
            json={"fields": {"title": "Verified Cert"}},
        )
        db_session.refresh(doc)
        assert doc.file_path == original_path_str
        assert doc_file.exists()
        assert file_sha256(doc_file) == original_hash

        # 2. File viewer serves the exact binary content
        view_resp = client.get(f"/api/documents/{doc.id}/file")
        assert view_resp.status_code == status.HTTP_200_OK
        assert view_resp.content == original_bytes
