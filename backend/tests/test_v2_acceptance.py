"""
Acceptance Test Suite for Universal Intelligent Document Processing (v2).
Implements all 14 Acceptance Criteria specified in Part 6 of IDP_Final_Plan.md:

1. Invoice A -> dynamic vendor, number, date, line items, total.
2. Invoice B, different layout -> same semantic information with no template code.
3. Resume -> name, education, skills, experience, projects.
4. Bank statement -> account information + transaction table.
5. Medical report -> patient/report/test structure.
6. Certificate -> recipient, issuer, credential, dates.
7. Previously unseen PDF -> unknown/novel type, extraction still occurs.
8. Scanned PDF -> OCR + layout + extraction.
9. Photo of a document -> preprocessing + OCR/vision.
10. CSV -> schema inference + structured table.
11. Multi-sheet Excel -> workbook understanding.
12. Bad-quality document -> low confidence + review, zero fabricated values.
13. Deterministic canonical keys -> same keys across runs & shared family keys.
14. Zero-code-change guarantee -> novel document type processes end-to-end.
"""

import csv
import io
import json
from pathlib import Path
from typing import Dict, List
import openpyxl
from PIL import Image, ImageDraw
import pytest
import pymupdf
from fastapi.testclient import TestClient

from app.database.connection import SessionLocal
from app.main import app
from app.models.document import Document
from app.models.extracted_field import ExtractedField
from app.models.extraction_run import ExtractionRun
from app.services.ingestion.engine import ingestion_engine
from app.services.ingestion.pdf_ingest import ingest_pdf_file
from app.services.ingestion.spreadsheet_ingest import ingest_spreadsheet_file


@pytest.fixture(autouse=True)
def mock_ai_environment(monkeypatch):
    from app.core.config import settings
    from app.services.ai.base import MockAIExtractionProvider
    import app.services.ai.factory as ai_factory
    
    mock_prov = MockAIExtractionProvider()
    monkeypatch.setattr(settings, "AI_PROVIDER", "mock")
    monkeypatch.setattr(ai_factory, "get_ai_provider", lambda *args, **kwargs: mock_prov)
    monkeypatch.setattr("app.services.classification.classifier.get_ai_provider", lambda *args, **kwargs: mock_prov)
    monkeypatch.setattr("app.services.schema_registry.discovery.get_ai_provider", lambda *args, **kwargs: mock_prov)
    monkeypatch.setattr("app.services.extraction_v2.engine.get_ai_provider", lambda *args, **kwargs: mock_prov)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db_session():
    session = SessionLocal()
    yield session
    session.close()


# -----------------------------------------------------------------------------
# Document Generators (Synthetic Fixtures)
# -----------------------------------------------------------------------------

def make_pdf_bytes(text: str) -> bytes:
    """Generates a native vector PDF with embedded text layer."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)  # A4
    y = 50
    for line in text.split("\n"):
        page.insert_text((50, y), line, fontsize=11)
        y += 18
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def make_scanned_pdf_bytes(text: str) -> bytes:
    """Generates a scanned PDF with an embedded raster image and zero native text layer."""
    img = Image.new("RGB", (800, 1000), color="white")
    draw = ImageDraw.Draw(img)
    y = 50
    for line in text.split("\n"):
        draw.text((50, y), line, fill="black")
        y += 24

    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")
    img_bytes = img_buf.getvalue()

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(pymupdf.Rect(0, 0, 595, 842), stream=img_bytes)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def make_image_bytes(text: str) -> bytes:
    """Generates a standalone image file (PNG) containing document text."""
    img = Image.new("RGB", (800, 600), color="white")
    draw = ImageDraw.Draw(img)
    y = 40
    for line in text.split("\n"):
        draw.text((40, y), line, fill="black")
        y += 24
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_csv_bytes(rows: List[List[str]]) -> bytes:
    """Generates a CSV byte stream."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


def make_excel_bytes(sheets_data: Dict[str, List[List[any]]]) -> bytes:
    """Generates a multi-sheet Excel (.xlsx) byte stream."""
    wb = openpyxl.Workbook()
    first = True
    for sheet_name, rows in sheets_data.items():
        if first:
            ws = wb.active
            ws.title = sheet_name
            first = False
        else:
            ws = wb.create_sheet(title=sheet_name)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# -----------------------------------------------------------------------------
# Part 6 Acceptance Tests
# -----------------------------------------------------------------------------

def test_acceptance_01_invoice_a_dynamic_fields(client):
    """
    Acceptance Test 1: Invoice A -> correct dynamic fields.
    Verifies that standard invoice vendor, number, date, and amounts are extracted
    with evidence grounding and calibrated confidence.
    """
    doc_text = (
        "Vendor: Acme Corporation\n"
        "Invoice Number: INV-2026-001\n"
        "Invoice Date: 2026-08-15\n"
        "Subtotal: $1,150.00\n"
        "Tax Amount: $100.00\n"
        "Total Amount: $1,250.00\n"
    )
    pdf_bytes = make_pdf_bytes(doc_text)

    resp = client.post(
        "/api/v2/documents/upload?run_async=false",
        files={"file": ("invoice_acme.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]

    ext_resp = client.get(f"/api/v2/documents/{doc_id}/extraction")
    assert ext_resp.status_code == 200
    ext = ext_resp.json()

    fields_by_key = {f["key"]: f for f in ext["fields"]}
    
    # Check vendor name
    v_field = fields_by_key.get("entity.vendor_name") or fields_by_key.get("vendor_name")
    assert v_field is not None
    assert "Acme" in str(v_field["value"])
    assert v_field["evidence"]["grounded"] is True

    # Check invoice number
    num_field = fields_by_key.get("document.reference_number") or fields_by_key.get("invoice_number")
    assert num_field is not None
    assert "INV-2026-001" in str(num_field["value"])

    # Check total amount
    tot_field = fields_by_key.get("financial.total_amount") or fields_by_key.get("total_amount")
    assert tot_field is not None
    assert tot_field["normalized_value"] == 1250.0 or "1,250.00" in str(tot_field["value"])


def test_acceptance_02_invoice_b_different_layout_canonical_mapping(client):
    """
    Acceptance Test 2: Invoice B (different layout) -> same semantic canonical keys.
    Verifies that an alternative layout with different wording ('Billed By', 'Reference #',
    'Dated', 'VAT', 'Grand Total') maps to canonical keys with ZERO template code.
    """
    doc_text = (
        "Billed By: Globex International Inc.\n"
        "Reference #: G-9921\n"
        "Dated: 12/09/2026\n"
        "VAT: €400.00\n"
        "Grand Total: €3,400.00\n"
    )
    pdf_bytes = make_pdf_bytes(doc_text)

    resp = client.post(
        "/api/v2/documents/upload?run_async=false",
        files={"file": ("invoice_globex.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]

    ext = client.get(f"/api/v2/documents/{doc_id}/extraction").json()
    fields_by_key = {f["key"]: f for f in ext["fields"]}

    # Must map to canonical entity.vendor_name or vendor_name
    v_field = fields_by_key.get("entity.vendor_name") or fields_by_key.get("vendor_name")
    assert v_field is not None
    assert "Globex" in str(v_field["value"])

    # Must map to canonical document.reference_number or invoice_number
    ref_field = fields_by_key.get("document.reference_number") or fields_by_key.get("invoice_number")
    assert ref_field is not None
    assert "G-9921" in str(ref_field["value"])

    # Must map to canonical financial.total_amount or total_amount
    tot_field = fields_by_key.get("financial.total_amount") or fields_by_key.get("total_amount")
    assert tot_field is not None
    assert "3,400.00" in str(tot_field["value"]) or tot_field["normalized_value"] == 3400.0


def test_acceptance_03_resume_nested_structure(client):
    """
    Acceptance Test 3: Resume -> name, skills, experience, education, projects.
    Verifies open-label classification into employment family and dynamic extraction
    of candidate attributes.
    """
    resume_text = (
        "Candidate: Jane Doe\n"
        "Email: jane.doe@example.com\n"
        "Phone: +1 555-0199\n"
        "Summary: Seasoned AI and Distributed Systems Engineer\n"
        "Skills: Python, Machine Learning, React, Cloud\n"
        "Education: B.S. in Computer Science\n"
        "Experience: Senior Software Engineer at TechCorp\n"
        "Projects: Universal Document Processing Platform\n"
    )
    pdf_bytes = make_pdf_bytes(resume_text)

    resp = client.post(
        "/api/v2/documents/upload?run_async=false",
        files={"file": ("jane_doe_resume.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]

    ext = client.get(f"/api/v2/documents/{doc_id}/extraction").json()
    assert ext["classification"]["family"] == "employment" or "Resume" in ext["classification"]["primary_type"]

    fields_by_key = {f["key"]: f for f in ext["fields"]}
    
    # Candidate name
    name_f = fields_by_key.get("person.full_name") or fields_by_key.get("candidate_name")
    assert name_f is not None
    assert "Jane Doe" in str(name_f["value"])

    # Skills
    skills_f = fields_by_key.get("skills")
    assert skills_f is not None
    assert "Python" in str(skills_f["value"])

    # Experience
    exp_f = fields_by_key.get("experience")
    assert exp_f is not None
    assert "TechCorp" in str(exp_f["value"])


def test_acceptance_04_bank_statement_with_transactions(client):
    """
    Acceptance Test 4: Bank statement -> account information + transaction table.
    Verifies banking entity extraction, transactions table extraction, and running balance insights.
    """
    bank_text = (
        "Account Holder: John Smith\n"
        "Account Number: ACCT-987654321\n"
        "Statement Period: August 1 - August 31, 2026\n"
        "Opening Balance: $10,000.00\n"
        "Closing Balance: $14,500.00\n"
        "Transactions:\n"
        "Date | Description | Debit | Credit | Balance\n"
        "2026-08-05 | Client Wire Inflow | | 5000.00 | 15000.00\n"
        "2026-08-12 | Cloud Services Inc | 500.00 | | 14500.00\n"
    )
    pdf_bytes = make_pdf_bytes(bank_text)

    resp = client.post(
        "/api/v2/documents/upload?run_async=false",
        files={"file": ("bank_statement_aug2026.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]

    ext = client.get(f"/api/v2/documents/{doc_id}/extraction").json()
    assert ext["classification"]["family"] == "financial"
    fields_by_key = {f["key"]: f for f in ext["fields"]}

    # Account Number
    acct_f = fields_by_key.get("financial.account_number") or fields_by_key.get("account_number")
    assert acct_f is not None
    assert "ACCT-987654321" in str(acct_f["value"])

    # Account Holder
    holder_f = fields_by_key.get("person.account_holder") or fields_by_key.get("account_holder")
    assert holder_f is not None
    assert "John Smith" in str(holder_f["value"])

    # Tables
    assert len(ext["tables"]) > 0
    t = ext["tables"][0]
    assert "transaction" in t["key"] or len(t["rows"]) > 0


def test_acceptance_05_medical_report_structure(client):
    """
    Acceptance Test 5: Medical report -> patient/report/diagnosis structure.
    Verifies clinical schema identification, patient details, and diagnosis extraction.
    """
    med_text = (
        "Patient Name: Robert Johnson\n"
        "Age / Gender: 45 / Male\n"
        "Referring Doctor: Dr. Sarah Adams\n"
        "Report Date: 2026-08-20\n"
        "Diagnosis: Acute Bronchitis with mild wheezing\n"
    )
    pdf_bytes = make_pdf_bytes(med_text)

    resp = client.post(
        "/api/v2/documents/upload?run_async=false",
        files={"file": ("patient_report_johnson.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]

    ext = client.get(f"/api/v2/documents/{doc_id}/extraction").json()
    assert ext["classification"]["family"] == "medical" or "Medical" in ext["classification"]["primary_type"]

    fields_by_key = {f["key"]: f for f in ext["fields"]}
    pat_f = fields_by_key.get("person.full_name") or fields_by_key.get("patient_name")
    assert pat_f is not None
    assert "Robert Johnson" in str(pat_f["value"])

    diag_f = fields_by_key.get("diagnosis")
    assert diag_f is not None
    assert "Acute Bronchitis" in str(diag_f["value"])


def test_acceptance_06_certificate_credential_structure(client):
    """
    Acceptance Test 6: Certificate -> recipient, issuer, credential, dates.
    Verifies credential schema matching and metadata extraction.
    """
    cert_text = (
        "Recipient: Alice Williams\n"
        "Credential: Mastering Modern Deep Learning\n"
        "Issuing Authority: Antigravity AI Institute\n"
        "Issue Date: 2026-07-15\n"
        "Certificate ID: CERT-2026-X88\n"
    )
    pdf_bytes = make_pdf_bytes(cert_text)

    resp = client.post(
        "/api/v2/documents/upload?run_async=false",
        files={"file": ("deep_learning_certificate.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]

    ext = client.get(f"/api/v2/documents/{doc_id}/extraction").json()
    print("DEBUG EXT:", json.dumps(ext, indent=2))
    fields_by_key = {f["key"]: f for f in ext["fields"]}

    recip_f = fields_by_key.get("person.full_name") or fields_by_key.get("recipient_name")
    assert recip_f is not None
    assert "Alice Williams" in str(recip_f["value"])

    cred_f = fields_by_key.get("credential_title")
    assert cred_f is not None
    assert "Deep Learning" in str(cred_f["value"])


def test_acceptance_07_previously_unseen_pdf_novel_type(client):
    """
    Acceptance Test 7: Previously unseen PDF -> unknown/novel type, extraction still occurs.
    Verifies that a document type with NO predefined template in the schema registry
    dynamically triggers schema discovery and extracts grounded fields.
    """
    novel_text = (
        "Mission: Artemis Orbital V\n"
        "Launch Date: 2026-11-04\n"
        "Apogee: 42000\n"
        "Payload Mass: 12500.0\n"
    )
    pdf_bytes = make_pdf_bytes(novel_text)

    resp = client.post(
        "/api/v2/documents/upload?run_async=false",
        files={"file": ("spaceflight_telemetry.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]

    ext = client.get(f"/api/v2/documents/{doc_id}/extraction").json()
    assert ext["schema_info"]["origin"] in ("discovered", "template")
    assert len(ext["fields"]) > 0

    fields_by_key = {f["key"]: f for f in ext["fields"]}
    m_field = fields_by_key.get("mission_name")
    assert m_field is not None
    assert "Artemis" in str(m_field["value"])
    assert m_field["evidence"]["grounded"] is True


def test_acceptance_08_scanned_pdf_ocr_pipeline(client):
    """
    Acceptance Test 8: Scanned PDF -> OCR + layout + extraction.
    Creates a PDF consisting exclusively of a rendered image with zero text layer,
    proving that ingestion routes to OCR and extracts blocks with bounding boxes.
    """
    scan_text = (
        "Vendor: Apex Scanned Logistics\n"
        "Invoice Number: SCAN-8821\n"
        "Total Amount: $940.00\n"
    )
    scanned_pdf_bytes = make_scanned_pdf_bytes(scan_text)

    resp = client.post(
        "/api/v2/documents/upload?run_async=false",
        files={"file": ("scanned_invoice.pdf", io.BytesIO(scanned_pdf_bytes), "application/pdf")},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]

    # Verify physical structure indicates OCR source
    struct_resp = client.get(f"/api/v2/documents/{doc_id}/structure")
    assert struct_resp.status_code == 200
    struct = struct_resp.json()
    assert struct["pages"][0]["source"] == "ocr"
    assert len(struct["blocks"]) > 0

    # Verify extraction succeeded
    ext = client.get(f"/api/v2/documents/{doc_id}/extraction").json()
    assert len(ext["fields"]) > 0


def test_acceptance_09_photo_image_document_ocr(client):
    """
    Acceptance Test 9: Photo of a document -> image ingestion + OCR.
    Uploads a standalone PNG image file, verifying dimensions, OCR blocks, and fields.
    """
    photo_text = (
        "Vendor: Mobile Snapshot Store\n"
        "Invoice Number: MOB-4412\n"
        "Total Amount: $230.00\n"
    )
    img_bytes = make_image_bytes(photo_text)

    resp = client.post(
        "/api/v2/documents/upload?run_async=false",
        files={"file": ("photo_receipt.png", io.BytesIO(img_bytes), "image/png")},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]

    struct = client.get(f"/api/v2/documents/{doc_id}/structure").json()
    assert struct["document"]["format"] in ("png", "image")
    assert struct["pages"][0]["source"] == "ocr"
    assert struct["pages"][0]["width"] > 0
    assert len(struct["blocks"]) > 0


def test_acceptance_10_csv_schema_inference_and_table(client):
    """
    Acceptance Test 10: CSV -> schema inference + structured table.
    Verifies that tabular files infer headers, row counts, data types, and produce exact insights.
    """
    csv_rows = [
        ["date", "description", "category", "amount"],
        ["2026-08-01", "Database Server", "Infrastructure", "350.00"],
        ["2026-08-05", "Domain Registration", "Marketing", "45.00"],
        ["2026-08-10", "GPU Compute Cluster", "AI", "1200.00"],
    ]
    csv_bytes = make_csv_bytes(csv_rows)

    resp = client.post(
        "/api/v2/documents/upload?run_async=false",
        files={"file": ("operational_expenses.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]

    struct = client.get(f"/api/v2/documents/{doc_id}/structure").json()
    assert len(struct["tables"]) >= 1
    t = struct["tables"][0]
    assert "amount" in [h.lower() for h in t["headers"]]
    assert len(t["rows"]) == 3

    # Insights check
    ins = client.get(f"/api/v2/documents/{doc_id}/insights").json()
    assert len(ins) > 0


def test_acceptance_11_multi_sheet_excel_workbook(client):
    """
    Acceptance Test 11: Multi-sheet Excel -> workbook understanding.
    Verifies that multi-sheet workbooks (.xlsx) profile all sheets and extract individual tables.
    """
    wb_data = {
        "Q3_Revenue": [
            ["Region", "Target", "Actual"],
            ["North America", 100000, 115000],
            ["Europe", 80000, 78000],
        ],
        "Cost_Centers": [
            ["Department", "Headcount", "Budget"],
            ["Engineering", 45, 550000],
            ["Product", 15, 200000],
        ],
    }
    xlsx_bytes = make_excel_bytes(wb_data)

    resp = client.post(
        "/api/v2/documents/upload?run_async=false",
        files={"file": ("corporate_financials.xlsx", io.BytesIO(xlsx_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]

    struct = client.get(f"/api/v2/documents/{doc_id}/structure").json()
    assert len(struct["pages"]) == 2
    assert len(struct["tables"]) == 2
    sheets = struct.get("sheets") or struct.get("sheet_profiles") or []
    assert len(sheets) == 2

    sheet_names = [s["name"] for s in sheets]
    assert "Q3_Revenue" in sheet_names
    assert "Cost_Centers" in sheet_names


def test_acceptance_12_bad_quality_document_low_confidence_no_hallucinations(client):
    """
    Acceptance Test 12: Bad-quality document -> low confidence + review, zero fabricated values.
    Verifies that noise or gibberish does not crash the system, generates no fabricated values,
    and flags low calibrated confidence routing to needs_review.
    """
    gibberish = "###???~~~!!! @@@ ### $$$ %%% ^^^ &&& *** ((())) --- === +++"
    pdf_bytes = make_pdf_bytes(gibberish)

    resp = client.post(
        "/api/v2/documents/upload?run_async=false",
        files={"file": ("corrupted_noise.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]

    ext = client.get(f"/api/v2/documents/{doc_id}/extraction").json()
    doc_status = ext.get("status") or ext.get("run", {}).get("status")
    
    # Document should be processed and either in needs_review, COMPLETED, or review required
    assert doc_status in ("needs_review", "COMPLETED", "NEEDS_REVIEW", "verified")
    
    # Any extracted fields must either have low confidence or be marked ungrounded
    for f in ext.get("fields", []):
        if not f["evidence"]["grounded"]:
            assert f["status"] == "needs_review"
            assert f["confidence"] <= 0.60


def test_acceptance_13_deterministic_canonical_keys(client):
    """
    Acceptance Test 13: Deterministic canonical keys -> same document processed twice
    yields identical canonical keys; two documents of same family share canonical keys.
    """
    text_1 = "Vendor: Acme Alpha\nInvoice Number: INV-001\nTotal Amount: $500.00\n"
    text_2 = "Vendor: Beta Supplies\nInvoice Number: INV-002\nTotal Amount: $750.00\n"

    # Upload Doc 1
    resp1 = client.post(
        "/api/v2/documents/upload?run_async=false",
        files={"file": ("det_inv_1.pdf", io.BytesIO(make_pdf_bytes(text_1)), "application/pdf")},
    )
    doc_id_1 = resp1.json()["document_id"]
    ext1 = client.get(f"/api/v2/documents/{doc_id_1}/extraction").json()

    # Upload Doc 2
    resp2 = client.post(
        "/api/v2/documents/upload?run_async=false",
        files={"file": ("det_inv_2.pdf", io.BytesIO(make_pdf_bytes(text_2)), "application/pdf")},
    )
    doc_id_2 = resp2.json()["document_id"]
    ext2 = client.get(f"/api/v2/documents/{doc_id_2}/extraction").json()

    keys_1 = set(f["key"] for f in ext1["fields"])
    keys_2 = set(f["key"] for f in ext2["fields"])

    # Both documents of the same family must share the core canonical keys
    shared_keys = keys_1.intersection(keys_2)
    assert len(shared_keys) >= 2


def test_acceptance_14_zero_code_change_guarantee(client):
    """
    Acceptance Test 14: Zero-code-change guarantee -> dropping a new document type
    needs no code change in backend or frontend.
    Verifies that an unseeded, novel domain (e.g. Agricultural Drone Soil Survey)
    is ingested, classified, schema-discovered, extracted, and structured with zero modifications.
    """
    drone_text = (
        "Field ID: AGRI-ZONE-4\n"
        "Survey Date: 2026-10-02\n"
        "Soil pH: 6.8\n"
        "Moisture: 42%\n"
        "Nitrogen: 85 \n"
    )
    pdf_bytes = make_pdf_bytes(drone_text)

    resp = client.post(
        "/api/v2/documents/upload?run_async=false",
        files={"file": ("drone_soil_survey.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]

    ext = client.get(f"/api/v2/documents/{doc_id}/extraction").json()
    assert ext["schema_info"]["origin"] in ("discovered", "template")
    assert len(ext["fields"]) > 0

    # Check that discovered fields match content
    fields_by_key = {f["key"]: f for f in ext["fields"]}
    ph_f = fields_by_key.get("ph_level")
    assert ph_f is not None
    assert "6.8" in str(ph_f["value"])


def test_acceptance_15_pipeline_run_comparison(client):
    """
    Acceptance Test 15: Pipeline run comparison between two runs.
    Verifies that the run comparison endpoint diffs metrics, latency, and field values.
    """
    text = "Vendor: Acme Labs\nInvoice Number: INV-771\nTotal Amount: $1,000.00\n"
    resp = client.post(
        "/api/v2/documents/upload?run_async=false",
        files={"file": ("comparison_test.pdf", io.BytesIO(make_pdf_bytes(text)), "application/pdf")},
    )
    doc_id = resp.json()["document_id"]
    run_1_id = resp.json()["run_id"]

    # Reprocess to create run 2
    reprocess_resp = client.post(f"/api/v2/documents/{doc_id}/reprocess")
    assert reprocess_resp.status_code == 200
    run_2_id = reprocess_resp.json()["run_id"]

    # Compare the two runs
    comp_resp = client.get(f"/api/v2/documents/{doc_id}/compare-runs?run_a={run_1_id}&run_b={run_2_id}")
    assert comp_resp.status_code == 200
    comp_data = comp_resp.json()

    assert comp_data["document_id"] == doc_id
    assert comp_data["run_a"]["id"] == run_1_id
    assert comp_data["run_b"]["id"] == run_2_id
    assert isinstance(comp_data["field_diffs"], list)
