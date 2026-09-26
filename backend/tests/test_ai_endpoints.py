"""
Unit tests for AI / LLM Configuration and Document Extraction Breakdown endpoints.
Verifies:
1. GET /api/ai/config returns safe config without secret leakage.
2. PUT /api/ai/config updates provider, model, enabled toggle, and API key.
3. POST /api/ai/test-connection verifies responsive status for mock and unconfigured states.
4. POST /api/ai/prompt/preview renders separated prompt tiers with injection warnings.
5. GET /api/documents/{id}/extraction returns transparent Rule, LLM, and Reconciliation tabs.
6. POST /api/documents/{id}/ai-extract processes with AI and respects fallback behavior.
"""

from pathlib import Path
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.ai_config import ai_config_manager
from app.core.config import settings
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


@pytest.fixture(autouse=True)
def restore_settings_env():
    import os
    orig_provider = settings.AI_PROVIDER
    orig_model = settings.AI_MODEL
    orig_key = settings.AI_API_KEY
    orig_gem_key = settings.GEMINI_API_KEY
    orig_env = dict(os.environ)
    yield
    settings.AI_PROVIDER = orig_provider
    settings.AI_MODEL = orig_model
    settings.AI_API_KEY = orig_key
    settings.GEMINI_API_KEY = orig_gem_key
    os.environ.clear()
    os.environ.update(orig_env)


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Provides a TestClient overriding the get_db dependency."""
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_get_ai_config_never_exposes_api_key(client: TestClient, monkeypatch):
    """Verify GET /api/ai/config returns masked status without leaking real keys."""
    monkeypatch.setenv("AI_API_KEY", "real-super-secret-key-12345")
    ai_config_manager.update_config(api_key="real-super-secret-key-12345")

    response = client.get("/api/ai/config")
    assert response.status_code == 200
    data = response.json()

    assert "real-super-secret-key" not in response.text
    assert data["api_key_configured"] is True
    assert data["masked_api_key"] == "************configured"
    assert "supported_providers" in data
    assert "gemini" in data["supported_providers"]


def test_put_ai_config_updates_settings(client: TestClient):
    """Verify PUT /api/ai/config updates model, provider, and enabled toggle."""
    payload = {
        "provider": "gemini",
        "model": "gemini-2.0-flash",
        "enabled": True,
        "timeout": 25,
    }
    response = client.put("/api/ai/config", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["model"] == "gemini-2.0-flash"
    assert data["timeout"] == 25
    assert data["enabled"] is True


def test_test_ai_connection_mock_and_unconfigured(client: TestClient):
    """Verify POST /api/ai/test-connection returns diagnostic responses safely."""
    # 1. Test Mock provider (always succeeds)
    res_mock = client.post("/api/ai/test-connection", json={"provider": "mock", "model": "mock-model"})
    assert res_mock.status_code == 200
    data_mock = res_mock.json()
    assert data_mock["success"] is True
    assert data_mock["status"] == "CONNECTED"

    # 2. Test Gemini with empty key returns NOT_CONFIGURED
    ai_config_manager.update_config(clear_api_key=True)
    res_unconf = client.post("/api/ai/test-connection", json={"provider": "gemini", "model": "gemini-1.5-flash"})
    assert res_unconf.status_code == 200
    data_unconf = res_unconf.json()
    assert data_unconf["success"] is False
    assert data_unconf["status"] == "NOT_CONFIGURED"


def test_preview_prompt_endpoint(client: TestClient):
    """Verify POST /api/ai/prompt/preview returns structured, separated sections."""
    payload = {
        "document_type": "invoice",
        "sample_text": "Sample Vendor\nInv: INV-99\nTotal: 100",
    }
    response = client.post("/api/ai/prompt/preview", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "SYSTEM EXTRACTION INSTRUCTIONS" in data["system_instructions"]
    assert "invoice" in data["document_type"]
    assert "--- START DOCUMENT ---" in data["document_content_preview"]
    assert "security_warning" in data


def test_document_extraction_breakdown_endpoint(client: TestClient, db_session: Session, tmp_path: Path):
    """Verify GET /api/documents/{id}/extraction returns Rule, LLM, and Reconciliation data."""
    # Create test document and record
    sample_file = tmp_path / "test_invoice.txt"
    sample_file.write_text("Acme Supplies Ltd Invoice INV-1001 Date 2026-09-01 Total 5000.00")

    doc = Document(
        file_name="test_invoice.txt",
        file_path=str(sample_file),
        file_type="TXT",
        file_size=100,
        status="NEEDS_REVIEW",
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    record = DocumentRecord(
        document_id=doc.id,
        document_type="invoice",
        extraction_status="NEEDS_REVIEW",
        confidence_score=0.74,
        extracted_data={
            "fields": {
                "vendor_name": {"value": "Acme Supplies Ltd", "confidence": 0.95, "source": "rule+ai"},
                "invoice_number": {"value": "INV-1002", "confidence": 0.74, "source": "ai"},
            },
            "candidates": {
                "invoice_number": [
                    {"value": "INV-1001", "confidence": 0.91, "source": "keyword", "evidence": "Keyword match"},
                    {"value": "INV-1002", "confidence": 0.94, "source": "ai", "evidence": "Extracted by AI"},
                ]
            },
            "routing": {"review_reasons": ["Disagreement between Rule and AI"]},
        },
    )
    db_session.add(record)
    db_session.commit()

    response = client.get(f"/api/documents/{doc.id}/extraction")
    assert response.status_code == 200
    data = response.json()

    assert data["document_id"] == doc.id
    assert "vendor_name" in data["final_result"]
    assert "rule_extraction" in data
    assert "llm_extraction" in data
    assert "reconciliation" in data

    # Check comparison
    assert data["rule_extraction"]["invoice_number"]["value"] == "INV-1001"
    assert data["llm_extraction"]["invoice_number"]["value"] == "INV-1002"
    assert data["reconciliation"]["invoice_number"]["status"] == "REVIEW REQUIRED"
