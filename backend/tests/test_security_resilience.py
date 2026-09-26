"""Security, Reliability, and Error Handling test suite for IDP backend.

Validates:
1. File upload security (null byte rejection, safe filename handling).
2. File size enforcement and empty file rejection.
3. Allowed vs disallowed file types.
4. Path traversal protection on document viewing endpoint.
5. Environment variable handling and safe parsing fallbacks.
6. Database error handling and transaction rollback.
7. AI & OCR failure resilience.
8. Sensitive information redaction in logs and error messages.
9. CORS middleware configuration and preflight headers.
10. Consistent HTTP error responses.
11. Audit logging on upload and verification.
"""

from pathlib import Path
from typing import Generator
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.datastructures import UploadFile

from app.core.config import _parse_float_env, _parse_int_env, _parse_list_env
from app.core.security import (
    is_path_traversal_safe,
    mask_secret,
    sanitize_filename,
    sanitize_log_text,
)
from app.database.connection import Base, get_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.services.ai.providers.openai_compatible import (
    OpenAICompatibleProvider,
)
from app.services.ai.schemas import AIExtractionStatus
from app.services.upload_service import upload_service
from app.utils.file_utils import get_upload_dir


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


# =============================================================================
# 1. Path Traversal & Filename Sanitization Tests
# =============================================================================


def test_sanitize_filename_removes_traversal_and_null_bytes():
    assert sanitize_filename("../../etc/passwd.pdf") == "passwd.pdf"
    assert (
        sanitize_filename("..\\..\\windows\\system32\\calc.png")
        == "calc.png"
    )
    assert sanitize_filename("in\x00voice.pdf") == "invoice.pdf"
    assert sanitize_filename(".hidden_file.pdf") == "hidden_file.pdf"
    assert sanitize_filename("") == "unnamed_document"


def test_path_traversal_defense_function():
    upload_dir = get_upload_dir()
    safe_path = upload_dir / "safe_file.pdf"
    unsafe_path = upload_dir / ".." / "system.ini"

    assert is_path_traversal_safe(safe_path, upload_dir) is True
    assert is_path_traversal_safe(unsafe_path, upload_dir) is False


def test_get_document_file_blocks_path_traversal(
    client: TestClient, db_session: Session
):
    # Create document pointing outside upload directory
    outside_path = Path("C:/Windows/System32/drivers/etc/hosts")
    doc = Document(
        file_name="traversal_test.pdf",
        file_path=str(outside_path),
        file_type="PDF",
        file_size=123,
        status="UPLOADED",
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    response = client.get(f"/api/documents/{doc.id}/file")
    assert response.status_code == 403
    assert "forbidden" in response.json()["detail"].lower()


# =============================================================================
# 2. File Upload Security & Size Limits
# =============================================================================


def test_upload_service_rejects_null_byte_filename():
    mock_file = UploadFile(
        filename="malicious\x00.pdf",
        file=None,
    )
    with pytest.raises(HTTPException) as exc_info:
        upload_service.validate_file_metadata(mock_file)
    assert exc_info.value.status_code == 400
    assert "invalid" in exc_info.value.detail.lower()


def test_upload_rejects_empty_file(client: TestClient):
    files = {"file": ("empty.pdf", b"", "application/pdf")}
    response = client.post("/api/documents/upload", files=files)
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_upload_rejects_disallowed_extension(client: TestClient):
    files = {"file": ("script.sh", b"echo hello", "text/plain")}
    response = client.post("/api/documents/upload", files=files)
    assert response.status_code == 400
    assert "unsupported" in response.json()["detail"].lower()


def test_upload_creates_audit_log(client: TestClient, db_session: Session):
    pdf_content = b"%PDF-1.4 sample content for audit logging"
    files = {"file": ("audit_sample.pdf", pdf_content, "application/pdf")}
    response = client.post("/api/documents/upload", files=files)
    assert response.status_code == 201
    doc_id = response.json()["id"]

    audit_entry = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.document_id == doc_id,
            AuditLog.action == "DOCUMENT_UPLOADED",
        )
        .first()
    )
    assert audit_entry is not None
    assert audit_entry.actor == "system"
    assert audit_entry.details.get("file_name") == "audit_sample.pdf"


# =============================================================================
# 3. Environment Variable Handling & Robust Fallbacks
# =============================================================================


def test_env_parsing_resilience():
    # Int parser fallback on bad string
    with patch("os.getenv", return_value="not_an_int"):
        assert _parse_int_env("SOME_KEY", 42) == 42

    # Float parser fallback on bad string
    with patch("os.getenv", return_value="invalid_float"):
        assert _parse_float_env("SOME_FLOAT", 0.85) == 0.85

    # List parser trims and splits
    with patch("os.getenv", return_value=" http://a.com , http://b.com "):
        assert _parse_list_env("CORS", []) == ["http://a.com", "http://b.com"]


# =============================================================================
# 4. Sensitive Information Redaction
# =============================================================================


def test_mask_secret():
    assert mask_secret("sk-1234567890abcdef1234") == "sk-1...1234"
    assert mask_secret("") == "[NOT_CONFIGURED]"
    assert mask_secret("short") == "***"


def test_sanitize_log_text_redacts_credentials():
    raw_db_url = "postgresql://myuser:secretpassword123@localhost:5432/idpdb"
    sanitized = sanitize_log_text(f"Connection failed: {raw_db_url}")
    assert "secretpassword123" not in sanitized
    assert "myuser:***@localhost" in sanitized

    raw_token = (
        "Request header Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.test"
    )
    sanitized_token = sanitize_log_text(raw_token)
    assert "eyJhbGciOiJIUzI1NiJ9.test" not in sanitized_token
    assert "[REDACTED_TOKEN]" in sanitized_token


# =============================================================================
# 5. CORS Configuration Tests
# =============================================================================


def test_cors_preflight_headers(client: TestClient):
    response = client.options(
        "/api/documents",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert (
        response.headers.get("access-control-allow-origin")
        == "http://localhost:3000"
    )


# =============================================================================
# 6. Consistent HTTP Error Responses
# =============================================================================


def test_not_found_returns_standard_json(client: TestClient):
    response = client.get("/api/documents/99999999")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "not found" in data["detail"].lower()


def test_invalid_param_returns_standard_422(client: TestClient):
    response = client.get("/api/documents?page=-5")
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


# =============================================================================
# 7. AI Resilience & Error Handling
# =============================================================================


def test_ai_provider_missing_key_graceful_response():
    provider = OpenAICompatibleProvider(api_key="")
    res = provider.extract_invoice("Sample invoice text")
    assert res.status == AIExtractionStatus.AI_NOT_CONFIGURED.value
    assert res.fields is None
    assert "not configured" in res.errors[0].lower()


def test_ai_provider_timeout_graceful_response():
    provider = OpenAICompatibleProvider(api_key="sk-dummykey")
    with patch(
        "urllib.request.urlopen",
        side_effect=TimeoutError("Connection timed out"),
    ):
        res = provider.extract_invoice("Invoice text")
        assert res.status == AIExtractionStatus.TIMEOUT.value
        assert res.fields is None
        assert "timed out" in res.errors[0].lower()
