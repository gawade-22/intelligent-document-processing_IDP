"""Test suite for Dashboard Backend APIs.

Implements all 16 required dashboard tests:
Test 1  — List Documents (GET /api/documents successful response & metadata)
Test 2  — Pagination (page, page_size, total, total_pages)
Test 3  — Vendor Search (vendor_name case-insensitive database filtering)
Test 4  — Invoice Search (invoice_number case-insensitive filtering)
Test 5  — Status Filter (status=NEEDS_REVIEW, status=VERIFIED)
Test 6  — Document Type Filter (document_type=PDF, document_type=receipt)
Test 7  — Combined Filters (multiple filters work together)
Test 8  — Invalid Page (page=0 returns 422 validation error)
Test 9  — Invalid Page Size (page_size=0, 101, -5 return 422 validation error)
Test 10 — Invalid Status (invalid status rejected with 422 error)
Test 11 — Empty Results (valid query with no matches returns 200 with total=0)
Test 12 — Document Details (GET /api/documents/{id} continues to work)
Test 13 — Document Not Found (GET /api/documents/999999 returns 404)
Test 14 — Statistics (total_processed, total_verified, stats)
Test 15 — Statistics With No Documents (returns sensible zero/null values)
Test 16 — HITL Regression (verifies existing HITL review workflow passes)
"""

import math
from typing import Generator

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


# =============================================================================
# Helper function to seed test documents
# =============================================================================


def _seed_document(
    db: Session,
    file_name: str,
    file_type: str = "PDF",
    status_val: str = "VERIFIED",
    vendor_name: str = None,
    invoice_number: str = None,
    total_amount: str = None,
    invoice_date: str = None,
    confidence_score: float = None,
    document_type: str = "invoice",
) -> Document:
    """Helper to seed a Document and optional DocumentRecord."""
    doc = Document(
        file_name=file_name,
        file_path=f"storage/uploads/{file_name}",
        file_type=file_type,
        file_size=1024,
        status=status_val,
        error_message=None,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    if (
        document_type is not None
        or vendor_name
        or invoice_number
        or total_amount
        or invoice_date
        or confidence_score is not None
    ):
        fields = {}
        if vendor_name:
            fields["vendor_name"] = {
                "value": vendor_name,
                "normalized_value": vendor_name,
                "confidence": confidence_score,
                "source": "ocr",
            }
        if invoice_number:
            fields["invoice_number"] = {
                "value": invoice_number,
                "normalized_value": invoice_number,
                "confidence": confidence_score,
                "source": "rule",
            }
        if total_amount:
            fields["total_amount"] = {
                "value": total_amount,
                "normalized_value": total_amount,
                "confidence": confidence_score,
                "source": "rule",
            }
        if invoice_date:
            fields["invoice_date"] = {
                "value": invoice_date,
                "normalized_value": invoice_date,
                "confidence": confidence_score,
                "source": "rule",
            }

        rec = DocumentRecord(
            document_id=doc.id,
            document_type=document_type,
            extraction_status=status_val,
            raw_text=(
                f"{vendor_name or ''} {invoice_number or ''} "
                f"{total_amount or ''}"
            ).strip(),
            extracted_data={"fields": fields},
            confidence_score=confidence_score,
        )
        db.add(rec)
        db.commit()

    return doc


# =============================================================================
# Test 1 — List Documents
# =============================================================================


def test_01_list_documents(client: TestClient, db_session: Session):
    """Test 1: Verify successful document listing and required metadata."""
    _seed_document(
        db=db_session,
        file_name="invoice_001.pdf",
        status_val="VERIFIED",
        vendor_name="ABC Technologies",
        invoice_number="INV-1001",
        confidence_score=0.96,
    )

    resp = client.get("/api/documents")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total"] == 1
    assert data["total_pages"] == 1
    assert len(data["items"]) == 1

    item = data["items"][0]
    assert item["document_id"] > 0
    assert item["file_name"] == "invoice_001.pdf"
    assert item["file_type"] == "PDF"
    assert item["status"] == "VERIFIED"
    assert item["vendor_name"] == "ABC Technologies"
    assert item["invoice_number"] == "INV-1001"
    assert item["confidence"] == 0.96
    assert item["uploaded_at"] is not None
    assert item["updated_at"] is not None


# =============================================================================
# Test 2 — Pagination
# =============================================================================


def test_02_pagination(client: TestClient, db_session: Session):
    """Test 2: Verify page, page_size, total, and total_pages calculations."""
    for i in range(7):
        _seed_document(
            db=db_session,
            file_name=f"doc_{i}.pdf",
            vendor_name=f"Vendor {i}",
        )

    # Page 1 of size 3
    resp1 = client.get("/api/documents?page=1&page_size=3")
    assert resp1.status_code == status.HTTP_200_OK
    data1 = resp1.json()
    assert data1["page"] == 1
    assert data1["page_size"] == 3
    assert data1["total"] == 7
    assert data1["total_pages"] == 3
    assert len(data1["items"]) == 3

    # Page 2 of size 3
    resp2 = client.get("/api/documents?page=2&page_size=3")
    assert resp2.status_code == status.HTTP_200_OK
    data2 = resp2.json()
    assert data2["page"] == 2
    assert len(data2["items"]) == 3

    # Page 3 of size 3
    resp3 = client.get("/api/documents?page=3&page_size=3")
    assert resp3.status_code == status.HTTP_200_OK
    data3 = resp3.json()
    assert data3["page"] == 3
    assert len(data3["items"]) == 1


# =============================================================================
# Test 3 — Vendor Search
# =============================================================================


def test_03_vendor_search(client: TestClient, db_session: Session):
    """Test 3: Verify vendor_name filters correctly with case-insensitivity."""
    _seed_document(
        db=db_session,
        file_name="inv_alpha.pdf",
        vendor_name="Acme Corporation",
    )
    _seed_document(
        db=db_session,
        file_name="inv_beta.pdf",
        vendor_name="Globex Tech",
    )
    _seed_document(
        db=db_session,
        file_name="inv_gamma.pdf",
        vendor_name="ABC Technologies",
    )

    # Case-insensitive matches: abc, ABC, Abc
    for term in ["abc", "ABC", "Abc"]:
        resp = client.get(f"/api/documents?vendor_name={term}")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["vendor_name"] == "ABC Technologies"

    # Search for "acme"
    resp_acme = client.get("/api/documents?vendor_name=acme")
    assert resp_acme.status_code == status.HTTP_200_OK
    assert resp_acme.json()["total"] == 1
    assert resp_acme.json()["items"][0]["vendor_name"] == "Acme Corporation"


# =============================================================================
# Test 4 — Invoice Number Search
# =============================================================================


def test_04_invoice_number_search(client: TestClient, db_session: Session):
    """Test 4: Verify invoice_number filters with case-insensitivity."""
    _seed_document(
        db=db_session,
        file_name="doc1.pdf",
        invoice_number="INV-1001",
    )
    _seed_document(
        db=db_session,
        file_name="doc2.pdf",
        invoice_number="INV-2002",
    )

    for term in ["INV-2002", "inv-2002", "Inv-2002"]:
        resp = client.get(f"/api/documents?invoice_number={term}")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["invoice_number"] == "INV-2002"


# =============================================================================
# Test 5 — Status Filter
# =============================================================================


def test_05_status_filter(client: TestClient, db_session: Session):
    """Test 5: Verify status=NEEDS_REVIEW and status=VERIFIED work."""
    _seed_document(
        db=db_session,
        file_name="verified_1.pdf",
        status_val="VERIFIED",
    )
    _seed_document(
        db=db_session,
        file_name="verified_2.pdf",
        status_val="VERIFIED",
    )
    _seed_document(
        db=db_session,
        file_name="review_1.pdf",
        status_val="NEEDS_REVIEW",
    )
    _seed_document(
        db=db_session,
        file_name="failed_1.pdf",
        status_val="FAILED",
    )

    # Filter NEEDS_REVIEW
    resp_rev = client.get("/api/documents?status=NEEDS_REVIEW")
    assert resp_rev.status_code == status.HTTP_200_OK
    data_rev = resp_rev.json()
    assert data_rev["total"] == 1
    assert data_rev["items"][0]["status"] == "NEEDS_REVIEW"

    # Filter VERIFIED
    resp_ver = client.get("/api/documents?status=VERIFIED")
    assert resp_ver.status_code == status.HTTP_200_OK
    data_ver = resp_ver.json()
    assert data_ver["total"] == 2
    for item in data_ver["items"]:
        assert item["status"] == "VERIFIED"


# =============================================================================
# Test 6 — Document Type Filter
# =============================================================================


def test_06_document_type_filter(client: TestClient, db_session: Session):
    """Test 6: Verify document_type=PDF and classified types filter."""
    _seed_document(
        db=db_session,
        file_name="sample.pdf",
        file_type="PDF",
        document_type="invoice",
    )
    _seed_document(
        db=db_session,
        file_name="photo.png",
        file_type="IMAGE",
        document_type="receipt",
    )
    _seed_document(
        db=db_session,
        file_name="data.csv",
        file_type="CSV",
        document_type="sheet",
    )

    # Filter by file format PDF
    resp_pdf = client.get("/api/documents?document_type=PDF")
    assert resp_pdf.status_code == status.HTTP_200_OK
    data_pdf = resp_pdf.json()
    assert data_pdf["total"] == 1
    assert data_pdf["items"][0]["file_type"] == "PDF"

    # Filter by semantic type receipt
    resp_rcpt = client.get("/api/documents?document_type=receipt")
    assert resp_rcpt.status_code == status.HTTP_200_OK
    data_rcpt = resp_rcpt.json()
    assert data_rcpt["total"] == 1
    assert data_rcpt["items"][0]["document_type"] == "receipt"


# =============================================================================
# Test 7 — Combined Filters
# =============================================================================


def test_07_combined_filters(client: TestClient, db_session: Session):
    """Test 7: Verify multiple filters work together simultaneously."""
    _seed_document(
        db=db_session,
        file_name="match.pdf",
        file_type="PDF",
        status_val="NEEDS_REVIEW",
        vendor_name="Acme Corp",
        invoice_number="INV-888",
    )
    _seed_document(
        db=db_session,
        file_name="other.pdf",
        file_type="PDF",
        status_val="VERIFIED",
        vendor_name="Acme Corp",
        invoice_number="INV-889",
    )
    _seed_document(
        db=db_session,
        file_name="diff_vendor.pdf",
        file_type="PDF",
        status_val="NEEDS_REVIEW",
        vendor_name="Global Inc",
        invoice_number="INV-990",
    )

    url = (
        "/api/documents?page=1&page_size=10&vendor_name=Acme"
        "&status=NEEDS_REVIEW&document_type=PDF"
    )
    resp = client.get(url)
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["file_name"] == "match.pdf"
    assert data["items"][0]["vendor_name"] == "Acme Corp"
    assert data["items"][0]["status"] == "NEEDS_REVIEW"


# =============================================================================
# Test 8 — Invalid Page
# =============================================================================


def test_08_invalid_page(client: TestClient):
    """Test 8: Verify page=0 returns validation error (HTTP 422)."""
    resp_zero = client.get("/api/documents?page=0")
    assert resp_zero.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    resp_neg = client.get("/api/documents?page=-1")
    assert resp_neg.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# =============================================================================
# Test 9 — Invalid Page Size
# =============================================================================


def test_09_invalid_page_size(client: TestClient):
    """Test 9: Verify page_size=0, 101, -5 return validation errors (422)."""
    resp_zero = client.get("/api/documents?page_size=0")
    assert resp_zero.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    resp_too_large = client.get("/api/documents?page_size=101")
    assert resp_too_large.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    resp_neg = client.get("/api/documents?page_size=-5")
    assert resp_neg.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# =============================================================================
# Test 10 — Invalid Status
# =============================================================================


def test_10_invalid_status(client: TestClient):
    """Test 10: Verify invalid status is rejected with HTTP 422."""
    resp = client.get("/api/documents?status=INVALID_STATUS")
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    data = resp.json()
    assert "detail" in data
    assert "Invalid status" in data["detail"]


# =============================================================================
# Test 11 — Empty Results
# =============================================================================


def test_11_empty_results(client: TestClient, db_session: Session):
    """Test 11: Valid query matching no docs returns 200 with total=0."""
    _seed_document(
        db=db_session,
        file_name="doc.pdf",
        vendor_name="Existing Vendor",
    )

    resp = client.get("/api/documents?vendor_name=NoSuchVendor")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    assert data["items"] == []
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total"] == 0
    assert data["total_pages"] == 0


# =============================================================================
# Test 12 — Document Details
# =============================================================================


def test_12_document_details(client: TestClient, db_session: Session):
    """Test 12: Verify GET /api/documents/{id} continues to work."""
    doc = _seed_document(
        db=db_session,
        file_name="inv_detail.pdf",
        file_type="PDF",
        status_val="NEEDS_REVIEW",
        vendor_name="Acme Global",
        invoice_number="INV-9999",
        total_amount="1500.00",
        invoice_date="2026-09-15",
        confidence_score=0.88,
    )

    resp = client.get(f"/api/documents/{doc.id}")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    assert data["document_id"] == doc.id
    assert data["file_name"] == "inv_detail.pdf"
    assert data["status"] == "NEEDS_REVIEW"
    assert "document" in data
    assert data["document"]["viewer_url"] == f"/api/documents/{doc.id}/file"
    assert "fields" in data
    assert "vendor_name" in data["fields"]
    assert data["fields"]["vendor_name"]["value"] == "Acme Global"


# =============================================================================
# Test 13 — Document Not Found
# =============================================================================


def test_13_document_not_found(client: TestClient):
    """Test 13: Verify GET /api/documents/999999 returns 404 cleanly."""
    resp = client.get("/api/documents/999999")
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in resp.json()["detail"].lower()


# =============================================================================
# Test 14 — Statistics
# =============================================================================


def test_14_statistics(client: TestClient, db_session: Session):
    """Test 14: Verify total_processed, total_verified, and review count."""
    # 2 VERIFIED
    _seed_document(
        db=db_session,
        file_name="v1.pdf",
        file_type="PDF",
        status_val="VERIFIED",
        confidence_score=0.95,
    )
    _seed_document(
        db=db_session,
        file_name="v2.pdf",
        file_type="PDF",
        status_val="VERIFIED",
        confidence_score=0.85,
    )
    # 1 NEEDS_REVIEW
    _seed_document(
        db=db_session,
        file_name="r1.png",
        file_type="IMAGE",
        status_val="NEEDS_REVIEW",
        confidence_score=0.60,
    )
    # 1 FAILED
    _seed_document(
        db=db_session,
        file_name="f1.csv",
        file_type="CSV",
        status_val="FAILED",
    )

    resp = client.get("/api/documents/stats")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    # Total processed: 2 VERIFIED + 1 NEEDS_REVIEW = 3
    assert data["total_processed"] == 3
    assert data["total_verified"] == 2
    assert data["total_needing_review"] == 1
    assert data["total_failed"] == 1
    assert data["total_documents"] == 4

    # Average confidence: (0.95 + 0.85 + 0.60) / 3 = 0.8000
    assert math.isclose(data["average_confidence"], 0.80, abs_tol=0.0001)


# =============================================================================
# Test 15 — Statistics With No Documents
# =============================================================================


def test_15_statistics_with_no_documents(client: TestClient):
    """Test 15: Verify stats with no documents returns zeros and null."""
    resp = client.get("/api/documents/stats")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    assert data["total_processed"] == 0
    assert data["total_verified"] == 0
    assert data["total_needing_review"] == 0
    assert data["average_confidence"] is None
    assert data["total_documents"] == 0


# =============================================================================
# Test 16 — HITL Regression
# =============================================================================


def test_16_hitl_regression(client: TestClient, db_session: Session):
    """Test 16: Verify existing HITL review workflow endpoints still pass."""
    doc = _seed_document(
        db=db_session,
        file_name="hitl_test.pdf",
        status_val="NEEDS_REVIEW",
        vendor_name="Test Vendor",
        confidence_score=0.65,
    )

    # 1. Review list returns only NEEDS_REVIEW
    resp_rev = client.get("/api/documents/review")
    assert resp_rev.status_code == status.HTTP_200_OK
    rev_data = resp_rev.json()
    assert rev_data["count"] >= 1
    assert any(it["document_id"] == doc.id for it in rev_data["items"])

    # 2. Document detail returns HITL viewer_url and review fields
    resp_detail = client.get(f"/api/documents/{doc.id}")
    assert resp_detail.status_code == status.HTTP_200_OK
    detail_data = resp_detail.json()
    expected_url = f"/api/documents/{doc.id}/file"
    assert detail_data["document"]["viewer_url"] == expected_url
    assert "vendor_name" in detail_data["fields"]
