"""
Integration and Unit Tests for Universal IDP (v2).
Tests UniversalDocument contracts, Ingestion Engine, Database Models,
and v2 API routes.
"""

import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.database.connection import SessionLocal
from app.main import app
from app.models.document import Document
from app.models.document_schema import DocumentSchema
from app.models.extracted_field import ExtractedField
from app.models.extraction_run import ExtractionRun
from app.models.review_correction import ReviewCorrection
from app.models.schema_alias import SchemaAlias
from app.schemas.universal import (
    ContentBlock,
    DocumentMeta,
    PageMeta,
    UniversalDocument,
)
from app.services.ingestion.engine import ingestion_engine


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db_session():
    session = SessionLocal()
    yield session
    session.close()


def test_universal_document_contract():
    """Verify UniversalDocument schema validation and text reconstruction."""
    doc_meta = DocumentMeta(
        file_name="test.pdf",
        format="pdf",
        page_count=1,
        hash="test_hash_123",
        file_size=1024,
    )
    pages = [PageMeta(n=1, width=612.0, height=792.0, source="native")]
    blocks = [
        ContentBlock(
            id="blk_0",
            page=1,
            type="heading",
            text="Invoice #12345",
            bbox=[50.0, 50.0, 200.0, 75.0],
            reading_order=0,
        ),
        ContentBlock(
            id="blk_1",
            page=1,
            type="paragraph",
            text="Total: $500.00",
            bbox=[50.0, 80.0, 150.0, 95.0],
            reading_order=1,
        ),
    ]

    udoc = UniversalDocument(
        document=doc_meta,
        pages=pages,
        blocks=blocks,
    )

    assert udoc.document.file_name == "test.pdf"
    assert len(udoc.pages) == 1
    assert len(udoc.blocks) == 2
    assert "Invoice #12345" in udoc.full_text
    assert "Total: $500.00" in udoc.full_text
    assert udoc.page_text(1) == "Invoice #12345\nTotal: $500.00"


def test_v2_database_models(db_session):
    """Verify that all v2 database models instantiate and persist correctly."""
    # 1. DocumentSchema
    schema = DocumentSchema(
        id="test_schema_v1",
        name="Test Universal Schema",
        family="test",
        version=1,
        origin="discovered",
        schema_definition={"sections": ["Overview"], "fields": []},
    )
    schema = db_session.merge(schema)
    db_session.commit()

    # 2. SchemaAlias
    alias = SchemaAlias(
        canonical_key="entity.name",
        alias="company",
        data_type="string",
    )
    db_session.add(alias)

    # 3. Document
    doc = Document(
        file_name="test_v2_file.pdf",
        file_path="uploads/test_v2_file.pdf",
        file_type="pdf",
        file_size=2048,
        file_hash="dummy_hash_v2",
        status="UPLOADED",
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    # 4. ExtractionRun
    run = ExtractionRun(
        id="test_run_v2_01",
        document_id=doc.id,
        schema_id=schema.id,
        pipeline_version="v2",
        status="PROCESSING",
        stage="INGESTION",
    )
    db_session.merge(run)
    db_session.commit()

    # 5. ExtractedField
    field = ExtractedField(
        run_id=run.id,
        document_id=doc.id,
        canonical_key="entity.name",
        field_key="company",
        label="Company Name",
        section="Overview",
        data_type="string",
        raw_value="Acme Corp",
        normalized_value="Acme Corp",
        confidence=0.98,
        status="verified",
    )
    db_session.add(field)
    db_session.commit()
    db_session.refresh(field)

    # 6. ReviewCorrection
    correction = ReviewCorrection(
        field_id=field.id,
        run_id=run.id,
        canonical_key="entity.name",
        original_value="Acme Corp",
        corrected_value="Acme Corp Ltd",
        reviewer_id="tester",
    )
    db_session.add(correction)
    db_session.commit()

    # Assertions
    fetched_run = db_session.query(ExtractionRun).filter_by(id="test_run_v2_01").first()
    assert fetched_run is not None
    assert fetched_run.document_id == doc.id
    assert len(fetched_run.fields) >= 1
    assert len(fetched_run.review_corrections) >= 1

    # Cleanup test rows
    db_session.delete(doc)
    db_session.delete(schema)
    db_session.delete(alias)
    db_session.commit()


def test_v2_api_upload_and_inspect(client, tmp_path):
    """Verify v2 upload endpoint and structure inspection."""
    # Create dummy text/pdf file
    sample_content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    file_tuple = ("test_sample.pdf", io.BytesIO(sample_content), "application/pdf")

    response = client.post(
        "/api/v2/documents/upload?run_async=false",
        files={"file": file_tuple},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert "document_id" in data
    assert "run_id" in data
    assert data["stage"] in ("INGESTION", "CLASSIFYING", "SCHEMA_DISCOVERY", "EXTRACTING", "GROUNDING", "VALIDATING", "UPLOADED", "COMPLETED")


    doc_id = data["document_id"]

    # Check status endpoint
    status_resp = client.get(f"/api/v2/documents/{doc_id}/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["document_id"] == doc_id
    assert "stage" in status_data

    # Check list endpoint
    list_resp = client.get("/api/v2/documents")
    assert list_resp.status_code == 200
    doc_list = list_resp.json()
    assert any(d["id"] == doc_id for d in doc_list)


def test_open_label_classifier():
    """Verify open-label classifier on sample UniversalDocument."""
    from app.services.classification.classifier import UniversalDocumentClassifier
    from app.services.ai.base import MockAIExtractionProvider

    mock_provider = MockAIExtractionProvider()
    classifier = UniversalDocumentClassifier(ai_provider=mock_provider)

    udoc = UniversalDocument(
        document=DocumentMeta(file_name="jane_resume.pdf", format="pdf"),
        pages=[PageMeta(n=1, width=612.0, height=792.0)],
        blocks=[
            ContentBlock(id="b0", page=1, type="heading", text="Jane Doe - Software Engineer"),
            ContentBlock(id="b1", page=1, type="paragraph", text="Work Experience: Senior Developer at Tech Corp. Skills: Python, FastAPI."),
        ],
    )

    res = classifier.classify(udoc, ai_provider=mock_provider)
    assert "Resume" in res.primary_type or res.family == "employment"
    assert res.confidence >= 0.8
    assert res.family in ("employment", "general")


def test_schema_registry_lookup_and_discovery(db_session):
    """Verify schema resolution: reuse template for known types, discover for novel types."""
    from app.services.schema_registry.service import schema_registry
    from app.services.ai.base import MockAIExtractionProvider
    from app.schemas.universal import ClassificationResult

    schema_registry.seed_registry(db_session)

    # 1. Known type -> Should reuse existing template schema
    class_resume = ClassificationResult(
        primary_type="Resume / CV",
        family="employment",
        confidence=0.98,
    )
    udoc_resume = UniversalDocument(
        document=DocumentMeta(file_name="candidate.pdf", format="pdf"),
        pages=[PageMeta(n=1, width=612.0, height=792.0)],
        blocks=[ContentBlock(id="b0", page=1, text="Candidate resume details")],
    )
    resolved_schema = schema_registry.resolve_schema(udoc_resume, class_resume, db_session)
    assert resolved_schema.origin == "template"
    assert "Resume" in resolved_schema.name

    # 2. Novel / Unseen type -> Should trigger dynamic discovery
    mock_ai = MockAIExtractionProvider()
    class_novel = ClassificationResult(
        primary_type="Spaceflight Flight Logbook",
        family="general",
        confidence=0.92,
    )
    udoc_novel = UniversalDocument(
        document=DocumentMeta(file_name="flight_log.pdf", format="pdf"),
        pages=[PageMeta(n=1, width=612.0, height=792.0)],
        blocks=[ContentBlock(id="b0", page=1, text="Flight Mission: Mars Orbital Insertion")],
    )
    disc_schema = schema_registry.resolve_schema(udoc_novel, class_novel, db_session, ai_provider=mock_ai)
    assert disc_schema.origin == "discovered"
    assert disc_schema.name == "Spaceflight Flight Logbook"
    assert len(disc_schema.schema_definition.get("fields", [])) > 0

    # Cleanup the newly discovered test schema
    db_session.delete(disc_schema)
    db_session.commit()


def test_schema_registry_api_endpoints(client, db_session):
    """Verify GET /api/v2/documents/schemas/list and GET /api/v2/documents/schemas/{id}."""
    from app.services.schema_registry.service import schema_registry
    schema_registry.seed_registry(db_session)

    # List schemas
    resp = client.get("/api/v2/documents/schemas/list")
    assert resp.status_code == 200
    schemas = resp.json()
    assert len(schemas) >= 13
    assert any(s["id"] == "sch_commercial_invoice_v1" for s in schemas)

    # Get single schema detail
    detail_resp = client.get("/api/v2/documents/schemas/sch_commercial_invoice_v1")
    assert detail_resp.status_code == 200
    schema_detail = detail_resp.json()
    assert schema_detail["id"] == "sch_commercial_invoice_v1"
    assert "sections" in schema_detail["definition"]
    assert "fields" in schema_detail["definition"]


def test_grounding_service():
    """Verify quote grounding against physical blocks."""
    from app.services.grounding.locator import grounding_service

    udoc = UniversalDocument(
        document=DocumentMeta(file_name="invoice.pdf", format="pdf"),
        pages=[PageMeta(n=1, width=612.0, height=792.0)],
        blocks=[
            ContentBlock(id="b0", page=1, text="Vendor: Acme Global Solutions Ltd", bbox=[50.0, 50.0, 300.0, 70.0]),
            ContentBlock(id="b1", page=1, text="Invoice Number: INV-987654", bbox=[50.0, 80.0, 250.0, 100.0]),
            ContentBlock(id="b2", page=1, text="Total Due: $4,500.00", bbox=[400.0, 500.0, 550.0, 520.0]),
        ],
    )

    # 1. Grounded exact match
    ev1 = grounding_service.verify_and_locate(
        quote="Acme Global Solutions",
        raw_value="Acme Global Solutions Ltd",
        page_hint=1,
        udoc=udoc,
    )
    assert ev1.grounded is True
    assert ev1.bbox == [50.0, 50.0, 300.0, 70.0]

    # 2. Grounded raw value match
    ev2 = grounding_service.verify_and_locate(
        quote="",
        raw_value="INV-987654",
        page_hint=1,
        udoc=udoc,
    )
    assert ev2.grounded is True
    assert ev2.bbox == [50.0, 80.0, 250.0, 100.0]

    # 3. Ungrounded / Hallucinated quote
    ev3 = grounding_service.verify_and_locate(
        quote="Nonexistent hallucinated supplier",
        raw_value="Fake Corp",
        page_hint=1,
        udoc=udoc,
    )
    assert ev3.grounded is False
    assert ev3.bbox == [0.0, 0.0, 0.0, 0.0]


def test_multi_pass_reconciler():
    """Verify reconciliation of multi-pass candidates."""
    from app.services.reconciliation_v2.reconciler import multi_pass_reconciler
    from app.schemas.universal import FieldEvidence

    ev_grounded = FieldEvidence(page=1, quote="test@example.com", grounded=True, bbox=[10.0, 10.0, 50.0, 20.0])
    doc_text = "Contact us at test@example.com or support@example.com"

    # Agreement pass
    val, passes, conf, status, msgs = multi_pass_reconciler.reconcile_field(
        key="email",
        llm_value="test@example.com",
        data_type="email",
        evidence=ev_grounded,
        document_text=doc_text,
    )
    assert val == "test@example.com"
    assert status == "verified"
    assert conf >= 0.90
    assert len(passes) >= 2  # text-llm + pattern-detector

    # Conflict pass
    ev_conflict = FieldEvidence(page=1, quote="Total: $1,200", grounded=True)
    val2, passes2, conf2, status2, msgs2 = multi_pass_reconciler.reconcile_field(
        key="total",
        llm_value="1200.00",
        data_type="money",
        evidence=ev_conflict,
        document_text="Subtotal is $800.00 and Total is $1,200.00",
        secondary_llm_value="800.00",  # conflicting candidate
    )
    assert status2 == "needs_review"
    assert conf2 < 0.90
    assert len(msgs2) > 0


def test_v2_end_to_end_extraction(client, db_session):
    """Verify end-to-end extraction endpoint with UniversalExtractionResult contract."""
    from app.services.schema_registry.service import schema_registry
    schema_registry.seed_registry(db_session)

    invoice_content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    file_tuple = ("invoice_test.pdf", io.BytesIO(invoice_content), "application/pdf")

    resp = client.post("/api/v2/documents/upload?run_async=false", files={"file": file_tuple})
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]

    # Check extraction endpoint
    ext_resp = client.get(f"/api/v2/documents/{doc_id}/extraction")
    assert ext_resp.status_code == 200
    ext_data = ext_resp.json()
    assert ext_data["document_id"] == doc_id
    assert "classification" in ext_data
    assert "schema_info" in ext_data
    assert "fields" in ext_data

    # Check evidence endpoint
    ev_resp = client.get(f"/api/v2/documents/{doc_id}/evidence")
    assert ev_resp.status_code == 200


def test_generic_data_normalizer():
    """Verify data normalization across all supported types."""
    from app.services.normalization_v2.normalizer import generic_normalizer

    # Date normalization
    assert generic_normalizer.normalize_date("2026-10-04") == "2026-10-04"
    assert generic_normalizer.normalize_date("14/08/2024") == "2024-08-14"
    assert generic_normalizer.normalize_date("August 14, 2024") == "2024-08-14"
    assert generic_normalizer.normalize_date("14-Aug-2024") == "2024-08-14"

    # Money normalization
    assert generic_normalizer.normalize_money("$1,250.50") == 1250.50
    assert generic_normalizer.normalize_money("₹ 1,25,000.50") == 125000.50
    assert generic_normalizer.normalize_money("1.250,50 €") == 1250.50
    assert generic_normalizer.normalize_money(500) == 500.0

    # Percent & Number
    assert generic_normalizer.normalize_percent("18%") == 18.0
    assert generic_normalizer.normalize_percent("0.18") == 18.0
    assert generic_normalizer.normalize_number("1,500.25") == 1500.25

    # Email & Phone & Bool & ID
    assert generic_normalizer.normalize_email(" John.Doe@Example.COM ") == "john.doe@example.com"
    assert generic_normalizer.normalize_phone("+1 (555) 234-5678") == "+15552345678"
    assert generic_normalizer.normalize_bool("yes") is True
    assert generic_normalizer.normalize_bool("No") is False
    assert generic_normalizer.normalize_id(" #0012345. ") == "0012345"


def test_dsl_validation_engine():
    """Verify safe execution of cross-field DSL validation rules."""
    from app.services.validation_v2.engine import dsl_validation_engine
    from app.schemas.universal import DynamicFieldResult, DynamicTableResult

    fields = [
        DynamicFieldResult(id="f1", key="financial.total_amount", label="Total Amount", value="1500.00"),
        DynamicFieldResult(id="f2", key="financial.tax_amount", label="Tax Amount", value="100.00"),
        DynamicFieldResult(id="f3", key="start_date", label="Start Date", value="2026-01-01"),
        DynamicFieldResult(id="f4", key="end_date", label="End Date", value="2026-12-31"),
        DynamicFieldResult(id="f5", key="score", label="Score", value="85"),
    ]
    tables = [
        DynamicTableResult(
            id="t1",
            key="items",
            title="Items",
            headers=["description", "amount"],
            rows=[["Item A", "1000.00"], ["Item B", "400.00"]],
        )
    ]

    rules = [
        # sum_equals: items.amount (1400) + tax_amount (100) == total_amount (1500) -> PASS
        {"rule": "sum_equals", "target": "financial.total_amount", "terms": ["items.amount", "financial.tax_amount"]},
        # date_order: start_date <= end_date -> PASS
        {"rule": "date_order", "earlier": "start_date", "later": "end_date"},
        # in_range: score between 0 and 100 -> PASS
        {"rule": "in_range", "value": "score", "min": 0, "max": 100},
    ]

    outcomes = dsl_validation_engine.evaluate_rules(rules, fields, tables)
    assert len(outcomes) == 3
    assert all(o["status"] == "pass" for o in outcomes)


def test_dynamic_insights_engine():
    """Verify exact mathematical aggregation in Insights Engine."""
    from app.services.insights_v2.engine import insights_engine_v2
    from app.schemas.universal import DynamicFieldResult, DynamicTableResult

    fields = [DynamicFieldResult(id="f1", key="total", label="Total", value="300.0")]
    tables = [
        DynamicTableResult(
            id="t1",
            key="transactions",
            title="Transactions",
            headers=["date", "amount"],
            rows=[["2026-10-01", "100.00"], ["2026-10-02", "200.00"]],
        )
    ]

    definitions = [
        {"id": "sum_tx", "title": "Total Transactions", "kind": "metric", "agg": "sum", "table": "transactions", "column": "amount"},
        {"id": "avg_tx", "title": "Average Transaction", "kind": "metric", "agg": "avg", "table": "transactions", "column": "amount"},
        {"id": "count_tx", "title": "Transaction Count", "kind": "metric", "agg": "count", "table": "transactions"},
    ]

    insights = insights_engine_v2.generate_insights(definitions, fields, tables, [])
    insight_dict = {i.id: i.value for i in insights}

    assert insight_dict["sum_tx"] == 300.00
    assert insight_dict["avg_tx"] == 150.00
    assert insight_dict["count_tx"] == 2
    assert "ins_field_coverage" in insight_dict


def test_v2_insights_api_endpoint(client):
    """Verify GET /api/v2/documents/{id}/insights endpoint."""
    resp = client.post(
        "/api/v2/documents/upload?run_async=false",
        files={"file": ("test_doc.pdf", io.BytesIO(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"), "application/pdf")},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]

    ins_resp = client.get(f"/api/v2/documents/{doc_id}/insights")
    assert ins_resp.status_code == 200
    insights = ins_resp.json()
    assert isinstance(insights, list)
    assert len(insights) > 0
    assert any(i["id"] == "ins_field_coverage" for i in insights)


def test_v2_field_correction_and_verification(client, db_session):
    """Verify HITL field correction, normalization, audit logging, and document verification."""
    from app.models.audit_log import AuditLog
    from app.models.review_correction import ReviewCorrection

    # 1. Upload doc
    resp = client.post(
        "/api/v2/documents/upload?run_async=false",
        files={"file": ("correction_test.pdf", io.BytesIO(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"), "application/pdf")},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]

    # 2. Get an extracted field
    field = db_session.query(ExtractedField).filter(ExtractedField.document_id == doc_id).first()
    assert field is not None
    field_id = field.id

    # 3. Patch the field
    patch_resp = client.patch(
        f"/api/v2/documents/{doc_id}/fields/{field_id}",
        json={"value": "$9,999.50", "reviewer_id": "test_reviewer"},
    )
    assert patch_resp.status_code == 200
    patch_data = patch_resp.json()
    assert patch_data["success"] is True
    assert patch_data["status"] == "edited"
    assert patch_data["confidence"] == 1.0

    # Verify ReviewCorrection row
    rc = db_session.query(ReviewCorrection).filter(ReviewCorrection.field_id == field_id).first()
    assert rc is not None
    assert rc.reviewer_id == "test_reviewer"

    # Verify AuditLog row
    audit = db_session.query(AuditLog).filter(
        AuditLog.document_id == doc_id,
        AuditLog.action == "FIELD_CORRECTION_V2",
    ).first()
    assert audit is not None
    assert audit.actor == "test_reviewer"

    # Verify that latest run extraction JSON has updated field
    ext_resp = client.get(f"/api/v2/documents/{doc_id}/extraction")
    assert ext_resp.status_code == 200
    ext_fields = ext_resp.json().get("fields", [])
    matched_f = next((f for f in ext_fields if f["id"] == field_id or f["key"] == field.canonical_key), None)
    assert matched_f is not None
    assert matched_f["status"] == "edited"
    assert matched_f["confidence"] == 1.0

    # 4. Verify document
    ver_resp = client.post(f"/api/v2/documents/{doc_id}/verify")
    assert ver_resp.status_code == 200
    assert ver_resp.json()["status"] == "VERIFIED"


def test_v2_schema_crud_and_reprocess(client, db_session):
    """Verify creating a custom schema, updating it, and triggering document reprocessing."""
    # 1. Create custom schema
    new_schema_payload = {
        "name": "Custom Logistics Waybill",
        "family": "logistics",
        "description": "Waybills and consignment notes",
        "schema_definition": {
            "sections": ["Header", "Tracking"],
            "fields": [
                {"name": "tracking_number", "label": "Tracking Number", "data_type": "id", "required": True},
                {"name": "weight_kg", "label": "Weight (kg)", "data_type": "number"},
            ],
            "validation_rules": [],
            "insight_definitions": [],
        },
    }
    create_resp = client.post("/api/v2/documents/schemas", json=new_schema_payload)
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    assert created_data["success"] is True
    schema_id = created_data["schema_id"]
    assert created_data["version"] == 1

    # 2. Update the custom schema
    updated_payload = {
        "name": "Custom Logistics Waybill Pro",
        "schema_definition": {
            "sections": ["Header", "Tracking", "Cost"],
            "fields": [
                {"name": "tracking_number", "label": "Tracking Number", "data_type": "id", "required": True},
                {"name": "freight_charge", "label": "Freight Charge", "data_type": "money"},
            ],
            "validation_rules": [],
            "insight_definitions": [],
        },
    }
    update_resp = client.put(f"/api/v2/documents/schemas/{schema_id}", json=updated_payload)
    assert update_resp.status_code == 200
    updated_data = update_resp.json()
    assert updated_data["version"] == 2
    assert "Cost" in updated_data["definition"]["sections"]

    # 3. Test reprocess endpoint
    # Create a document
    doc_resp = client.post(
        "/api/v2/documents/upload?run_async=false",
        files={"file": ("waybill.pdf", io.BytesIO(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"), "application/pdf")},
    )
    doc_id = doc_resp.json()["document_id"]

    reprocess_resp = client.post(f"/api/v2/documents/{doc_id}/reprocess")
    assert reprocess_resp.status_code == 200
    assert reprocess_resp.json()["status"] == "QUEUED"
    assert "run_id" in reprocess_resp.json()

    # Clean up schema
    del_schema = db_session.query(DocumentSchema).filter(DocumentSchema.id == schema_id).first()
    if del_schema:
        db_session.delete(del_schema)
        db_session.commit()





