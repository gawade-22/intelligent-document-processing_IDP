from pathlib import Path
import sys

# Ensure backend root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.extraction import InvoiceExtractionResult
from app.schemas.ocr import OCRBoundingBox, OCRPageData, OCRResult, OCRWordData
from app.schemas.pdf import PDFPageData, PDFParseResult
from app.services.extraction import (
    EXTRACTION_WEIGHTS,
    InvoiceExtractor,
    calculate_horizontal_proximity,
    calculate_keyword_proximity,
    compute_candidate_confidence,
    extract_invoice_fields,
    group_words_into_lines,
    is_above_below,
    is_nearby_line,
    is_same_line,
    is_top_of_page,
)



def test_extract_standard_invoice_all_fields():
    """Verify clean extraction of all 4 fields from a standard invoice text."""
    doc_text = """
    ABC Technologies Pvt Ltd
    123 Innovation Way, Tech Park, Bangalore 560100
    GSTIN: 29ABCDE1234F1Z5
    
    TAX INVOICE
    Invoice Number: INV-2026-00125
    Invoice Date: 12/08/2026
    Due Date: 26/08/2026
    
    Bill To:
    Acme Enterprises Inc
    456 Client Road, Mumbai 400001
    
    Description                  Qty     Rate       Amount
    Software Consulting            1   13,134.75   13,134.75
    Cloud Hosting Support          1    2,364.25    2,364.25
    
    Subtotal: $15,499.00
    Tax (18%): $2,789.82
    Grand Total: $15,499.00
    """
    result: InvoiceExtractionResult = extract_invoice_fields(doc_text)

    assert result.success is True
    assert result.vendor_name == "ABC Technologies Pvt Ltd"
    assert result.invoice_number == "INV-2026-00125"
    assert result.invoice_date == "12/08/2026"
    assert result.total_amount == "15499.00"

    # Verify confidence scores
    assert result.field_confidence["vendor_name"] >= 0.70
    assert result.field_confidence["invoice_number"] >= 0.80
    assert result.field_confidence["invoice_date"] >= 0.85
    assert result.field_confidence["total_amount"] >= 0.85

    # Verify field tracking lists
    assert set(result.fields_found) == {
        "vendor_name",
        "invoice_number",
        "invoice_date",
        "total_amount",
    }
    assert result.missing_fields == []
    assert result.errors == []

    # Verify extracted_fields detailed objects
    assert result.extracted_fields is not None
    assert result.extracted_fields["vendor_name"].value == "ABC Technologies Pvt Ltd"
    assert result.extracted_fields["invoice_number"].value == "INV-2026-00125"
    assert result.extracted_fields["invoice_date"].value == "12/08/2026"
    assert result.extracted_fields["total_amount"].value == "15499.00"


def test_extract_missing_fields_returns_null_and_zero_confidence():
    """Verify that when no fields can be found, null is returned with 0.0 confidence."""
    empty_doc = """
    Random notes from an internal discussion.
    Meeting held on a project roadmap.
    No billing or payment details are listed here.
    """
    result: InvoiceExtractionResult = extract_invoice_fields(empty_doc)

    assert result.success is True
    assert result.vendor_name is None
    assert result.invoice_number is None
    assert result.invoice_date is None
    assert result.total_amount is None

    # Confidence must be exactly 0.0
    assert result.field_confidence["vendor_name"] == 0.0
    assert result.field_confidence["invoice_number"] == 0.0
    assert result.field_confidence["invoice_date"] == 0.0
    assert result.field_confidence["total_amount"] == 0.0

    assert result.fields_found == []
    assert set(result.missing_fields) == {
        "vendor_name",
        "invoice_number",
        "invoice_date",
        "total_amount",
    }


def test_extract_invoice_number_variants():
    """Verify recognition of various invoice number formats and vertical layouts."""
    # 1. Bill No format with slash delimiter
    doc1 = """
    Acme Global Logistics Ltd
    Bill No: BL/2026/90412
    Date: 2026-09-01
    Total: 450.00
    """
    res1 = extract_invoice_fields(doc1)
    assert res1.invoice_number == "BL/2026/90412"

    # 2. Hash notation
    doc2 = """
    Quick Print Solutions
    Invoice #: #INV-88910
    Invoice Date: 15-Jan-2026
    Total: 120.00
    """
    res2 = extract_invoice_fields(doc2)
    assert res2.invoice_number in ["#INV-88910", "INV-88910"]

    # 3. Vertical label layout (label on line N, value on line N+1)
    doc3 = """
    Apex Engineering Corp
    Invoice Number:
    INV-99882
    Date of Issue: 2026-05-10
    Total: $2,500.00
    """
    res3 = extract_invoice_fields(doc3)
    assert res3.invoice_number == "INV-99882"


def test_extract_invoice_date_variants():
    """Verify recognition of various calendar date formats and disambiguation from due dates."""
    # 1. ISO format (YYYY-MM-DD)
    doc1 = """
    Delta Cloud Services LLC
    Invoice No: INV-001
    Date of Issue: 2026-11-25
    Due Date: 2026-12-10
    Total Amount: 800.00
    """
    res1 = extract_invoice_fields(doc1)
    assert res1.invoice_date == "2026-11-25"

    # 2. Textual month format (DD Month YYYY)
    doc2 = """
    Sunrise Bakery Ltd
    Inv No: SB-550
    Invoice Date: 14 August 2026
    Total: $75.50
    """
    res2 = extract_invoice_fields(doc2)
    assert "14 August 2026" in res2.invoice_date

    # 3. Textual month format (Month DD, YYYY)
    doc3 = """
    Zenith Legal Partners LLP
    Invoice No: ZL-101
    Bill Date: September 15, 2026
    Total: $1,200.00
    """
    res3 = extract_invoice_fields(doc3)
    assert "September 15, 2026" in res3.invoice_date


def test_extract_total_amount_variants():
    """Verify total amount parsing, currency symbols, and subtotal discrimination."""
    # 1. Rupee currency symbol with Indian comma grouping
    doc1 = """
    Bharat Electricals Pvt Ltd
    Invoice No: BE-8819
    Date: 10/08/2026
    
    Subtotal: ₹1,20,000.00
    CGST 9%: ₹10,800.00
    SGST 9%: ₹10,800.00
    Grand Total: ₹1,41,600.00
    """
    res1 = extract_invoice_fields(doc1)
    assert res1.total_amount == "141600.00"

    # 2. Total Payable anchor with Euro symbol
    doc2 = """
    EuroTech Systems GmbH
    Invoice No: ET-2026-09
    Date: 05.09.2026
    Subtotal: €3,500.00
    VAT: €700.00
    Total Payable: €4,200.00
    """
    res2 = extract_invoice_fields(doc2)
    assert res2.total_amount == "4200.00"

    # 3. Simple Total without symbol
    doc3 = """
    Metro Supplies Store
    Inv #: MS-101
    Dated: 01/09/2026
    Total Amount: 650.75
    """
    res3 = extract_invoice_fields(doc3)
    assert res3.total_amount == "650.75"


def test_extract_vendor_name_heuristics():
    """Verify vendor name detection via explicit anchors and top-header layout."""
    # 1. Explicit Seller / Vendor anchor
    doc1 = """
    Vendor: Prime Healthcare Services Inc
    Bill To: General Hospital
    Invoice No: PH-991
    Date: 12/09/2026
    Total: $500.00
    """
    res1 = extract_invoice_fields(doc1)
    assert res1.vendor_name == "Prime Healthcare Services Inc"

    # 2. Top-header corporate suffix without explicit label
    doc2 = """
    Summit Creative Agency LLP
    88 Creative Studio, Flat 2B
    
    TAX INVOICE
    Invoice No: SCA-441
    Invoice Date: 10/09/2026
    Total: $1,250.00
    """
    res2 = extract_invoice_fields(doc2)
    assert res2.vendor_name == "Summit Creative Agency LLP"


def test_extract_from_ocr_result_with_bounding_boxes():
    """Verify extraction utilizing structured OCRResult with OCR words, bounding boxes, and confidence."""
    # Construct OCR words for Page 1
    w_vendor = OCRWordData(
        text="AlphaTech",
        confidence=96.0,
        bounding_box=OCRBoundingBox(left=50, top=60, width=120, height=25, x2=170, y2=85),
    )
    w_vendor_suf = OCRWordData(
        text="Solutions",
        confidence=94.0,
        bounding_box=OCRBoundingBox(left=175, top=60, width=100, height=25, x2=275, y2=85),
    )
    w_inv_lbl = OCRWordData(
        text="Invoice",
        confidence=95.0,
        bounding_box=OCRBoundingBox(left=50, top=150, width=70, height=20, x2=120, y2=170),
    )
    w_inv_no = OCRWordData(
        text="No:",
        confidence=92.0,
        bounding_box=OCRBoundingBox(left=125, top=150, width=30, height=20, x2=155, y2=170),
    )
    w_inv_val = OCRWordData(
        text="INV-99001",
        confidence=98.0,
        bounding_box=OCRBoundingBox(left=165, top=150, width=90, height=20, x2=255, y2=170),
    )

    page1 = OCRPageData(
        page_number=1,
        raw_text="AlphaTech Solutions\nInvoice No: INV-99001\nInvoice Date: 2026-09-12\nGrand Total: $850.00",
        text="AlphaTech Solutions\nInvoice No: INV-99001\nInvoice Date: 2026-09-12\nGrand Total: $850.00",
        words=[w_vendor, w_vendor_suf, w_inv_lbl, w_inv_no, w_inv_val],
        character_count=80,
        word_count=5,
        average_confidence=95.0,
        has_text=True,
    )

    ocr_res = OCRResult(
        success=True,
        status="OCR_COMPLETED",
        file_type="IMAGE",
        page_count=1,
        pages=[page1],
        combined_text=page1.text,
        total_characters=80,
        total_words=5,
        average_confidence=95.0,
    )

    result = extract_invoice_fields(ocr_res)
    assert result.success is True
    assert result.vendor_name == "AlphaTech Solutions"
    assert result.invoice_number == "INV-99001"
    assert result.invoice_date == "2026-09-12"
    assert result.total_amount == "850.00"
    assert result.field_confidence["invoice_number"] >= 0.85

    # Check bounding box captured
    assert result.extracted_fields is not None
    assert result.extracted_fields["invoice_number"].bounding_box is not None
    assert result.extracted_fields["invoice_number"].bounding_box.left == 165


def test_extract_from_pdf_parse_result():
    """Verify seamless extraction directly from a PDFParseResult object."""
    pdf_page = PDFPageData(
        page_number=1,
        text="Global Logistics Services Ltd\nInvoice Number: GL-5002\nDate of Issue: 18/07/2026\nGrand Total: $3,200.00",
        character_count=95,
        word_count=12,
        has_text=True,
    )

    pdf_res = PDFParseResult(
        success=True,
        status="TEXT_EXTRACTED",
        file_type="PDF",
        page_count=1,
        pages=[pdf_page],
        combined_text=pdf_page.text,
        total_characters=95,
        total_word_count=12,
    )

    result = extract_invoice_fields(pdf_res)
    assert result.success is True
    assert result.vendor_name == "Global Logistics Services Ltd"
    assert result.invoice_number == "GL-5002"
    assert result.invoice_date == "18/07/2026"
    assert result.total_amount == "3200.00"
    assert result.fields_found == [
        "vendor_name",
        "invoice_number",
        "invoice_date",
        "total_amount",
    ]


def test_extract_empty_or_corrupted_input():
    """Verify engine handles empty or completely blank input gracefully."""
    # 1. Empty string
    res_empty = extract_invoice_fields("")
    assert res_empty.success is True
    assert res_empty.vendor_name is None
    assert res_empty.invoice_number is None
    assert res_empty.total_amount is None
    assert res_empty.field_confidence["vendor_name"] == 0.0

    # 2. Whitespace only
    res_ws = extract_invoice_fields("   \n\n\t   ")
    assert res_ws.success is True
    assert res_ws.missing_fields == [
        "vendor_name",
        "invoice_number",
        "invoice_date",
        "total_amount",
    ]


def test_invoice_extractor_class_with_independent_words():
    """
    Verify InvoiceExtractor class independence from OCR engine by directly
    supplying text and word dictionaries with text, confidence, bbox, line_num, etc.
    """
    custom_extractor = InvoiceExtractor()
    raw_text = "Acme Solutions Ltd\nInvoice No: INV-4451\nDate: 2026-08-10\nTotal: $990.00"

    ocr_words = [
        {
            "text": "Acme",
            "confidence": 98.0,
            "bbox": {"left": 40, "top": 50, "width": 80, "height": 22},
            "line_num": 1,
            "block_num": 1,
            "paragraph_num": 1,
            "word_num": 1,
        },
        {
            "text": "Solutions",
            "confidence": 97.0,
            "bbox": {"left": 125, "top": 50, "width": 100, "height": 22},
            "line_num": 1,
            "block_num": 1,
            "paragraph_num": 1,
            "word_num": 2,
        },
        {
            "text": "Ltd",
            "confidence": 99.0,
            "bbox": {"left": 230, "top": 50, "width": 50, "height": 22},
            "line_num": 1,
            "block_num": 1,
            "paragraph_num": 1,
            "word_num": 3,
        },
        {
            "text": "Invoice",
            "confidence": 96.0,
            "bbox": {"left": 40, "top": 120, "width": 60, "height": 20},
            "line_num": 2,
            "block_num": 1,
            "paragraph_num": 1,
            "word_num": 1,
        },
        {
            "text": "No:",
            "confidence": 95.0,
            "bbox": {"left": 105, "top": 120, "width": 30, "height": 20},
            "line_num": 2,
            "block_num": 1,
            "paragraph_num": 1,
            "word_num": 2,
        },
        {
            "text": "INV-4451",
            "confidence": 99.0,
            "bbox": {"left": 140, "top": 120, "width": 80, "height": 20},
            "line_num": 2,
            "block_num": 1,
            "paragraph_num": 1,
            "word_num": 3,
        },
    ]

    res = custom_extractor.extract(text=raw_text, words=ocr_words)

    assert res.success is True
    assert res.vendor_name == "Acme Solutions Ltd"
    assert res.invoice_number == "INV-4451"
    assert res.invoice_date == "2026-08-10"
    assert res.total_amount == "990.00"
    assert res.extracted_fields is not None
    assert res.extracted_fields["invoice_number"].bounding_box is not None
    assert res.extracted_fields["invoice_number"].bounding_box.left == 140
    assert res.extracted_fields["invoice_number"].confidence >= 0.85



def test_multi_candidate_evaluation_prioritizes_best_candidate_over_first_match():
    """
    Verify that when multiple candidates exist for the same field, the extractor
    evaluates candidates instead of blindly selecting the first match.

    Example:
    Reference Number: 4567
    Invoice Number: INV-001
    Invoice No: INV-001

    'INV-001' must be selected over '4567' even though '4567' appears first,
    because 'Invoice Number' has higher keyword specificity and alphanumeric format,
    plus reinforcement across multiple occurrences.
    """
    doc_text = """
    Apex Tech Solutions Ltd
    Reference Number: 4567
    Invoice Number: INV-001
    Invoice No: INV-001
    Date: 2026-09-12
    Total: $500.00
    """
    res = extract_invoice_fields(doc_text)

    assert res.success is True
    # The selected invoice_number must be INV-001, NOT 4567
    assert res.invoice_number == "INV-001"

    # Verify candidates dictionary is populated
    assert res.candidates is not None
    assert "invoice_number" in res.candidates
    cands = res.candidates["invoice_number"]

    # We should have at least 3 candidates (4567, INV-001 from 'Invoice Number', INV-001 from 'Invoice No')
    assert len(cands) >= 3

    # Check candidate values and field attributes
    values = [c.value for c in cands]
    assert "INV-001" in values
    assert "4567" in values

    # Check FieldCandidate attributes on all candidates
    for c in cands:
        assert c.field_name == "invoice_number"
        assert c.value != ""
        assert 0.0 <= c.confidence <= 1.0
        assert c.source in ["keyword", "regex", "positional", "combined"]
        assert c.matched_keyword is not None
        assert c.matched_text is not None
        assert c.line_num is not None
        assert c.evidence is not None and len(c.evidence) > 0

    # Best candidate must have higher confidence than the 4567 reference number candidate
    inv_cand = next(c for c in cands if c.value == "INV-001")
    ref_cand = next(c for c in cands if c.value == "4567")
    assert inv_cand.confidence > ref_cand.confidence
    assert "reinforced by" in inv_cand.evidence


def test_centralized_keyword_dictionaries_structure_and_coverage():
    """Verify that centralized keyword dictionaries cover all required variants."""
    from app.services.extraction import (
        FIELD_KEYWORD_DICTIONARIES,
        INVOICE_NUMBER_KEYWORDS,
        INVOICE_DATE_KEYWORDS,
        TOTAL_AMOUNT_KEYWORDS,
        VENDOR_KEYWORDS,
    )

    # 1. Centralized mapping check
    assert "invoice_number" in FIELD_KEYWORD_DICTIONARIES
    assert "invoice_date" in FIELD_KEYWORD_DICTIONARIES
    assert "total_amount" in FIELD_KEYWORD_DICTIONARIES
    assert "vendor_name" in FIELD_KEYWORD_DICTIONARIES
    assert "vendor" in VENDOR_KEYWORDS

    # 2. Invoice number required variations
    required_inv_num = [
        "invoice number",
        "invoice no",
        "invoice no.",
        "invoice #",
        "invoice id",
        "invoice ref",
        "invoice reference",
        "bill number",
        "bill no",
    ]
    for kw in required_inv_num:
        assert kw in INVOICE_NUMBER_KEYWORDS, f"Missing required invoice number keyword: {kw}"

    # 3. Invoice date required variations
    required_inv_date = [
        "invoice date",
        "date",
        "bill date",
        "dated",
        "invoice issued",
        "issue date",
    ]
    for kw in required_inv_date:
        assert kw in INVOICE_DATE_KEYWORDS, f"Missing required invoice date keyword: {kw}"

    # 4. Total amount required variations
    required_total = [
        "total",
        "grand total",
        "invoice total",
        "total amount",
        "net payable",
        "amount payable",
        "balance due",
        "total due",
        "amount due",
    ]
    for kw in required_total:
        assert kw in TOTAL_AMOUNT_KEYWORDS, f"Missing required total amount keyword: {kw}"


def test_field_candidate_attributes_and_schema():
    """Verify FieldCandidate schema and attributes."""
    from app.schemas.extraction import FieldCandidate
    from app.services.extraction import FieldCandidate as InternalFieldCandidate

    fc = FieldCandidate(
        field_name="invoice_number",
        value="INV-999",
        confidence=0.92,
        source="keyword",
        matched_keyword="invoice number",
        matched_text="Invoice Number: INV-999",
        bbox=None,
        line_num=5,
        evidence="Matched keyword 'invoice number' on line 5",
    )
    assert fc.field_name == "invoice_number"
    assert fc.value == "INV-999"
    assert fc.confidence == 0.92
    assert fc.source == "keyword"
    assert fc.matched_keyword == "invoice number"
    assert fc.matched_text == "Invoice Number: INV-999"
    assert fc.bbox is None
    assert fc.line_num == 5
    assert "Matched keyword" in fc.evidence

    internal_fc = InternalFieldCandidate(
        field_name="invoice_number",
        value="INV-999",
        confidence=0.92,
        matched_keyword="invoice number",
        matched_text="Invoice Number: INV-999",
        line_num=5,
        evidence="Matched keyword 'invoice number' on line 5",
    )
    schema_fc = internal_fc.to_schema_candidate()
    assert schema_fc.field_name == "invoice_number"
    assert schema_fc.value == "INV-999"
    assert schema_fc.confidence == 0.92



def test_vendor_name_strategies_a_b_c_d():
    """
    Verify Vendor Name extraction across Strategies A, B, C, and D:
    - Strategy A: Explicit vendor labels (Vendor Name, Seller Name, Supplier, From, Billed From, Company)
    - Strategy B: Top-of-document heuristic avoiding titles (Quotation, Tax Invoice, Bill, Date, etc.)
    - Strategy C: Company/business indicators as supporting evidence (not mandatory)
    - Strategy D: OCR positional layout and horizontal alignment
    """
    # 1. Strategy A: Explicit label "Vendor Name: ABC Technologies Pvt Ltd"
    doc_a = """
    Vendor Name: ABC Technologies Pvt Ltd
    Invoice Number: INV-001
    Date: 2026-09-12
    Total: $500.00
    """
    res_a = extract_invoice_fields(doc_a)
    assert res_a.vendor_name == "ABC Technologies Pvt Ltd"
    assert res_a.field_confidence["vendor_name"] >= 0.85

    # 1b. Strategy A: Explicit label "Billed From: Horizon Corp"
    doc_a2 = """
    Billed From: Horizon Corp
    Invoice No: HC-991
    Total: $120.00
    """
    res_a2 = extract_invoice_fields(doc_a2)
    assert res_a2.vendor_name == "Horizon Corp"

    # 1c. Strategy A: Vertical label format
    doc_a3 = """
    Vendor Name:
    Prime Logistics Inc
    Invoice No: PL-404
    Total: 250.00
    """
    res_a3 = extract_invoice_fields(doc_a3)
    assert res_a3.vendor_name == "Prime Logistics Inc"

    # 2. Strategy B: Top-of-document heuristic with document titles to avoid (Quotation, Tax Invoice, Bill)
    doc_b = """
    TAX INVOICE
    QUOTATION
    Apex Traders
    123 Commercial Street, Near Metro Station, Bangalore 560001
    GSTIN: 29ABCDE1234F1Z5
    Phone: +91-9876543210
    
    Invoice Number: APX-101
    Total: $1,500.00
    """
    res_b = extract_invoice_fields(doc_b)
    # Must pick 'Apex Traders', NOT 'TAX INVOICE', 'QUOTATION', or address/GSTIN
    assert res_b.vendor_name == "Apex Traders"
    assert res_b.field_confidence["vendor_name"] >= 0.70

    # 3. Strategy C: Company indicator not mandatory (company name without suffix still extracted)
    doc_c = """
    Zenith Horizon
    45 Industrial Area, Phase 2, Pune 411001
    GSTIN: 27AABCT1234Q1ZM
    
    Bill No: ZH-550
    Total: $800.00
    """
    res_c = extract_invoice_fields(doc_c)
    assert res_c.vendor_name == "Zenith Horizon"

    # 3b. Strategy C: Company indicator (Traders, Stores, Industries) provides boost
    doc_c2 = """
    Metro Hardware Stores
    Main Market, Sector 18, Noida 201301
    Phone: 9812345678
    
    Invoice No: MHS-12
    Total: $350.00
    """
    res_c2 = extract_invoice_fields(doc_c2)
    assert res_c2.vendor_name == "Metro Hardware Stores"
    assert any("Strategy C" in c.evidence for c in res_c2.candidates["vendor_name"])


def test_invoice_number_diverse_formats():
    """
    Verify recognition of diverse robust invoice number formats:
    INV-001, INV/2026/001, INV2026001, 2026-INV-001, ABC-12345, 12345, B-10025.
    Do not assume every invoice number contains 'INV'.
    """
    cases = [
        ("Invoice Number: INV-001", "INV-001"),
        ("Invoice No: INV/2026/001", "INV/2026/001"),
        ("Invoice Number: INV2026001", "INV2026001"),
        ("Invoice No: 2026-INV-001", "2026-INV-001"),
        ("Bill No: ABC-12345", "ABC-12345"),
        ("Invoice #: 12345", "12345"),
        ("Bill No: B-10025", "B-10025"),
        ("Invoice Number: INV-2026-00125", "INV-2026-00125"),
        ("Invoice No: INV-00125", "INV-00125"),
    ]
    for line, expected in cases:
        doc = f"""
        Acme Technologies Pvt Ltd
        {line}
        Invoice Date: 12/08/2026
        Grand Total: $1,000.00
        """
        res = extract_invoice_fields(doc)
        assert res.invoice_number == expected, f"Failed for input line '{line}', got '{res.invoice_number}' instead of '{expected}'"


def test_invoice_number_penalizes_disqualified_patterns():
    """
    Verify that candidate scorer heavily penalizes values that strongly resemble:
    - GST numbers (e.g. 29ABCDE1234F1Z5)
    - Phone numbers (e.g. +91-9876543210, 9876543210)
    - PIN codes (e.g. 560100)
    - Bank account numbers (e.g. 123456789012)
    - Tax percentages (e.g. 18%)
    - HSN/SAC product codes (e.g. 998311)
    and successfully selects the genuine invoice number.
    """
    doc = """
    Nexus Enterprise Solutions Ltd
    100 Tech Boulevard, Electronic City, Bangalore 560100
    GSTIN: 29ABCDE1234F1Z5
    Phone: +91-9876543210
    Bank A/C: 12345678901234
    
    TAX INVOICE
    Invoice Number: NX-2026-8801
    Date: 10/09/2026
    
    Item Description          HSN Code    Tax Rate    Amount
    Software Development        998311         18%   $5,000.00
    
    Grand Total: $5,900.00
    """
    res = extract_invoice_fields(doc)

    assert res.success is True
    assert res.invoice_number == "NX-2026-8801"

    # Verify that candidates collection contains diagnostic evidence of penalties
    cands = res.candidates["invoice_number"]
    candidate_values = {c.value: c for c in cands}

    # If any non-invoice number was evaluated as a candidate, verify it was penalized
    for val, cand in candidate_values.items():
        if "29ABCDE" in val or "9876543210" in val or "560100" in val or "1234567890" in val:
            assert "penalized" in cand.evidence.lower()
            assert cand.confidence < 0.35


def test_candidate_scoring_weights_and_breakdown():
    """
    Verify transparent candidate scoring:
    - Centralized configurable weights in EXTRACTION_WEIGHTS.
    - Multi-signal composition: keyword (0.30), pattern (0.25), ocr (0.20), position (0.15), context (0.10).
    - Clamping strictly between 0.0 and 1.0.
    - Evidence breakdown string contains individual signal contributions.
    """
    # 1. Weights structure and configuration
    assert "keyword" in EXTRACTION_WEIGHTS
    assert "pattern" in EXTRACTION_WEIGHTS
    assert "ocr" in EXTRACTION_WEIGHTS
    assert "position" in EXTRACTION_WEIGHTS
    assert "context" in EXTRACTION_WEIGHTS

    assert EXTRACTION_WEIGHTS["keyword"] == 0.30
    assert EXTRACTION_WEIGHTS["pattern"] == 0.25
    assert EXTRACTION_WEIGHTS["ocr"] == 0.20
    assert EXTRACTION_WEIGHTS["position"] == 0.15
    assert EXTRACTION_WEIGHTS["context"] == 0.10

    # Class-level alias on InvoiceExtractor
    assert InvoiceExtractor.EXTRACTION_WEIGHTS == EXTRACTION_WEIGHTS

    # 2. Perfect signals yield 1.0
    conf, breakdown = compute_candidate_confidence(
        keyword_score=1.0,
        pattern_score=1.0,
        ocr_score=1.0,
        position_score=1.0,
        context_score=1.0,
        penalty_score=0.0,
    )
    assert conf == 1.00
    assert "keyword=1.00*0.30" in breakdown
    assert "pattern=1.00*0.25" in breakdown
    assert "ocr=1.00*0.20" in breakdown
    assert "position=1.00*0.15" in breakdown
    assert "context=1.00*0.10" in breakdown
    assert "final=1.00" in breakdown

    # 3. Intermediate signals combination
    # 0.30*0.80 + 0.25*0.90 + 0.20*0.95 + 0.15*1.0 + 0.10*0.70 = 0.24 + 0.225 + 0.19 + 0.15 + 0.07 = 0.875 -> 0.88
    conf2, breakdown2 = compute_candidate_confidence(
        keyword_score=0.80,
        pattern_score=0.90,
        ocr_score=0.95,
        position_score=1.0,
        context_score=0.70,
        penalty_score=0.0,
    )
    assert conf2 == 0.88
    assert "final=0.88" in breakdown2

    # 4. Penalty subtraction
    # 0.875 - 0.30 = 0.575 -> 0.58
    conf3, breakdown3 = compute_candidate_confidence(
        keyword_score=0.80,
        pattern_score=0.90,
        ocr_score=0.95,
        position_score=1.0,
        context_score=0.70,
        penalty_score=0.30,
    )
    assert conf3 in [0.57, 0.58]
    assert "penalty=0.30" in breakdown3

    # 5. Clamping bounds: lower clamp to 0.0 and upper clamp to 1.0
    conf_low, _ = compute_candidate_confidence(
        keyword_score=0.20,
        pattern_score=0.20,
        ocr_score=0.20,
        position_score=0.20,
        context_score=0.20,
        penalty_score=1.50,
    )
    assert conf_low == 0.0

    conf_high, _ = compute_candidate_confidence(
        keyword_score=1.50,
        pattern_score=1.50,
        ocr_score=1.50,
        position_score=1.50,
        context_score=1.50,
        penalty_score=0.0,
    )
    assert conf_high == 1.0

    # 6. Custom weights support
    custom_w = {"keyword": 0.60, "pattern": 0.40, "ocr": 0.0, "position": 0.0, "context": 0.0}
    conf_custom, _ = compute_candidate_confidence(
        keyword_score=1.0,
        pattern_score=0.50,
        ocr_score=0.0,
        position_score=0.0,
        context_score=0.0,
        weights=custom_w,
    )
    assert conf_custom == 0.80  # 0.60*1.0 + 0.40*0.50 = 0.80


def test_keyword_proximity_mechanism():
    """
    Verify the reusable keyword proximity mechanism:
    - Same-line immediate proximity (Invoice Number: INV-001) scores 1.0.
    - Same-line character distance decay.
    - Vertical line distance and intervening lines penalty (Invoice Number ... Subtotal ... INV-001).
    - Spatial bounding box Euclidean distance evaluation.
    - End-to-end extraction confidence contrast between adjacent vs. separated invoice number.
    """
    # 1. Same-line proximity with short character distance
    p_close = calculate_keyword_proximity(line_distance=0, char_distance=2)
    assert p_close == 1.0

    # 2. Same-line with moderate distance
    p_med = calculate_keyword_proximity(line_distance=0, char_distance=15)
    assert 0.75 <= p_med < 1.0

    # 3. Next line without intervening lines
    p_next = calculate_keyword_proximity(line_distance=1, intervening_lines=0)
    assert p_next == 0.80

    # 4. Intervening lines penalty (Invoice Number ... Subtotal ... INV-001)
    p_intervene_1 = calculate_keyword_proximity(line_distance=2, intervening_lines=1)
    p_intervene_2 = calculate_keyword_proximity(line_distance=3, intervening_lines=2)
    assert p_close > p_next > p_intervene_1 > p_intervene_2
    assert p_intervene_1 == 0.50
    assert p_intervene_2 == 0.30

    # 5. Spatial bounding box proximity
    kw_box = OCRBoundingBox(left=50, top=100, width=80, height=20, x2=130, y2=120)
    # Right next to keyword horizontally (10px gap)
    cand_box_near = OCRBoundingBox(left=140, top=100, width=60, height=20, x2=200, y2=120)
    # Far from keyword (300px away)
    cand_box_far = OCRBoundingBox(left=450, top=100, width=60, height=20, x2=510, y2=120)

    p_spatial_near = calculate_keyword_proximity(
        line_distance=0,
        keyword_bbox=kw_box,
        candidate_bbox=cand_box_near,
    )
    p_spatial_far = calculate_keyword_proximity(
        line_distance=0,
        keyword_bbox=kw_box,
        candidate_bbox=cand_box_far,
    )
    assert p_spatial_near > p_spatial_far
    assert p_spatial_near == 1.0
    assert p_spatial_far < 0.65

    # 6. End-to-end extraction contrast:
    # Document 1: Invoice Number: INV-001 (immediate proximity)
    doc_direct = """
    Nexus Enterprise Technologies Ltd
    Invoice Number: INV-001
    Invoice Date: 12/08/2026
    Total: $1,200.00
    """
    res_direct = extract_invoice_fields(doc_direct)
    assert res_direct.invoice_number == "INV-001"
    conf_direct = res_direct.field_confidence["invoice_number"]

    # Document 2: Intervening line: Invoice Number \n Subtotal: $1,000.00 \n INV-001
    doc_separated = """
    Nexus Enterprise Technologies Ltd
    Invoice Number
    Subtotal: $1,000.00
    INV-001
    Invoice Date: 12/08/2026
    Total: $1,200.00
    """
    res_separated = extract_invoice_fields(doc_separated)
    assert res_separated.invoice_number == "INV-001"
    conf_separated = res_separated.field_confidence["invoice_number"]

    # Direct proximity must yield higher confidence than separated with intervening subtotal line
    assert conf_direct > conf_separated
    assert conf_direct >= 0.90
    assert conf_separated < conf_direct


def test_bounding_box_heuristics_relationships_and_grouping():
    """
    Verify spatial bounding-box heuristics:
    - is_same_line detects horizontally aligned words across wide gaps (e.g. Grand Total ... ₹11,300).
    - is_nearby_line detects adjacent line proximity.
    - is_above_below detects vertical label relationships.
    - calculate_horizontal_proximity scores horizontal spacing.
    - is_top_of_page identifies header/vendor region.
    - group_words_into_lines clusters OCR words into structured lines.
    - End-to-end extraction with bounding boxes for spaced invoice number and grand total.
    """
    # 1. Same-line relationship across wide horizontal gap
    # e.g. Grand Total (left=50, top=600) and ₹11,300 (left=500, top=602)
    box_total_lbl = OCRBoundingBox(left=50, top=600, width=100, height=20, x2=150, y2=620)
    box_total_val = OCRBoundingBox(left=500, top=602, width=80, height=20, x2=580, y2=622)
    box_other_line = OCRBoundingBox(left=500, top=750, width=80, height=20, x2=580, y2=770)

    assert is_same_line(box_total_lbl, box_total_val) is True
    assert is_same_line(box_total_lbl, box_other_line) is False

    # Also check with line_num / block_num
    assert is_same_line(box_total_lbl, box_total_val, line_num1=5, line_num2=5, block_num1=2, block_num2=2) is True
    assert is_same_line(box_total_lbl, box_other_line, line_num1=5, line_num2=8, block_num1=2, block_num2=2) is False

    # 2. Nearby-line relationship
    assert is_nearby_line(box_total_lbl, box_total_val, line_num1=5, line_num2=6) is True
    assert is_nearby_line(box_total_lbl, box_other_line, line_num1=5, line_num2=15) is False

    # 3. Above/Below relationship (vertical label layout)
    box_lbl_above = OCRBoundingBox(left=50, top=100, width=120, height=20, x2=170, y2=120)
    box_val_below = OCRBoundingBox(left=50, top=128, width=100, height=20, x2=150, y2=148)
    box_val_far_side = OCRBoundingBox(left=400, top=130, width=100, height=20, x2=500, y2=150)

    assert is_above_below(box_lbl_above, box_val_below) is True
    assert is_above_below(box_lbl_above, box_val_far_side) is False
    assert is_above_below(box_val_below, box_lbl_above) is False  # Cannot be below if it's above

    # 4. Horizontal proximity across table gap
    box_inv_lbl = OCRBoundingBox(left=50, top=200, width=80, height=20, x2=130, y2=220)
    box_inv_close = OCRBoundingBox(left=145, top=200, width=90, height=20, x2=235, y2=220)
    box_inv_spaced = OCRBoundingBox(left=350, top=200, width=90, height=20, x2=440, y2=220)

    prox_close = calculate_horizontal_proximity(box_inv_lbl, box_inv_close)
    prox_spaced = calculate_horizontal_proximity(box_inv_lbl, box_inv_spaced)
    assert prox_close == 1.0
    assert 0.60 <= prox_spaced < 1.0

    # 5. Top of page position
    box_header = OCRBoundingBox(left=50, top=80, width=200, height=30, x2=250, y2=110)
    box_footer = OCRBoundingBox(left=50, top=750, width=200, height=30, x2=250, y2=780)
    assert is_top_of_page(box_header) is True
    assert is_top_of_page(box_footer) is False

    # 6. Group words into lines
    raw_words = [
        OCRWordData(text="World", confidence=95.0, bounding_box=OCRBoundingBox(left=100, top=50, width=50, height=20, x2=150, y2=70), line_num=1, block_num=1),
        OCRWordData(text="Hello", confidence=96.0, bounding_box=OCRBoundingBox(left=40, top=50, width=50, height=20, x2=90, y2=70), line_num=1, block_num=1),
        OCRWordData(text="Line2", confidence=92.0, bounding_box=OCRBoundingBox(left=40, top=80, width=50, height=20, x2=90, y2=100), line_num=2, block_num=1),
    ]
    grouped = group_words_into_lines(raw_words)
    assert len(grouped) == 2
    assert [w.text for w in grouped[0]] == ["Hello", "World"]
    assert [w.text for w in grouped[1]] == ["Line2"]

    # 7. End-to-end spatial extraction with spaced invoice number and grand total
    ocr_words = [
        OCRWordData(text="Vertex", confidence=98.0, bounding_box=OCRBoundingBox(left=50, top=60, width=70, height=25, x2=120, y2=85), line_num=1),
        OCRWordData(text="Dynamics", confidence=98.0, bounding_box=OCRBoundingBox(left=125, top=60, width=90, height=25, x2=215, y2=85), line_num=1),
        OCRWordData(text="Pvt", confidence=97.0, bounding_box=OCRBoundingBox(left=220, top=60, width=35, height=25, x2=255, y2=85), line_num=1),
        OCRWordData(text="Ltd", confidence=97.0, bounding_box=OCRBoundingBox(left=260, top=60, width=35, height=25, x2=295, y2=85), line_num=1),
        # Invoice No:       INV-2026-001 (spaced)
        OCRWordData(text="Invoice", confidence=96.0, bounding_box=OCRBoundingBox(left=50, top=150, width=60, height=20, x2=110, y2=170), line_num=2),
        OCRWordData(text="No:", confidence=95.0, bounding_box=OCRBoundingBox(left=115, top=150, width=30, height=20, x2=145, y2=170), line_num=2),
        OCRWordData(text="INV-2026-001", confidence=95.0, bounding_box=OCRBoundingBox(left=300, top=151, width=120, height=20, x2=420, y2=171), line_num=2),
        # Date
        OCRWordData(text="Date:", confidence=95.0, bounding_box=OCRBoundingBox(left=50, top=180, width=40, height=20, x2=90, y2=200), line_num=3),
        OCRWordData(text="15/09/2026", confidence=95.0, bounding_box=OCRBoundingBox(left=100, top=180, width=80, height=20, x2=180, y2=200), line_num=3),
        # Grand Total                         ₹11,300 (wide gap)
        OCRWordData(text="Grand", confidence=96.0, bounding_box=OCRBoundingBox(left=50, top=600, width=50, height=20, x2=100, y2=620), line_num=10),
        OCRWordData(text="Total:", confidence=96.0, bounding_box=OCRBoundingBox(left=105, top=600, width=50, height=20, x2=155, y2=620), line_num=10),
        OCRWordData(text="₹11,300", confidence=94.0, bounding_box=OCRBoundingBox(left=480, top=600, width=70, height=20, x2=550, y2=620), line_num=10),
    ]
    res = extract_invoice_fields(words=ocr_words)
    assert res.success is True
    assert res.vendor_name == "Vertex Dynamics Pvt Ltd"
    assert res.invoice_number == "INV-2026-001"
    assert res.invoice_date == "15/09/2026"
    assert res.total_amount == "11300.00"


def test_ocr_confidence_as_supporting_evidence_not_blindly_copied():
    """
    Verify requirement 15:
    - OCR confidence is used only as supporting evidence (weight 0.20 in EXTRACTION_WEIGHTS).
    - OCR confidence = 0.98 does NOT automatically make field confidence = 0.98.
    - Field confidence is determined by multi-signal contextual evidence.
    """
    # 1. Direct check of compute_candidate_confidence
    # Even with OCR confidence = 0.98, if keyword or pattern evidence is moderate/low,
    # the field confidence does NOT equal 0.98.
    score_with_high_ocr, _ = compute_candidate_confidence(
        keyword_score=0.40,
        pattern_score=0.50,
        ocr_score=0.98,
        position_score=0.50,
        context_score=0.40,
        penalty_score=0.0,
    )
    # Expected: 0.30*0.40 + 0.25*0.50 + 0.20*0.98 + 0.15*0.50 + 0.10*0.40 = 0.12 + 0.125 + 0.196 + 0.075 + 0.04 = 0.556 -> 0.56
    assert score_with_high_ocr != 0.98
    assert abs(score_with_high_ocr - 0.56) <= 0.01

    # 2. End-to-end check: OCR word token with 98.0 confidence in an invoice
    words = [
        OCRWordData(
            text="INV-9999",
            confidence=98.0,  # 98% raw OCR confidence
            bounding_box=OCRBoundingBox(left=200, top=300, width=80, height=20, x2=280, y2=320),
            line_num=5,
        ),
        OCRWordData(
            text="Date:",
            confidence=98.0,
            bounding_box=OCRBoundingBox(left=50, top=100, width=40, height=20, x2=90, y2=120),
            line_num=1,
        ),
        OCRWordData(
            text="01/01/2026",
            confidence=98.0,
            bounding_box=OCRBoundingBox(left=100, top=100, width=80, height=20, x2=180, y2=120),
            line_num=1,
        ),
    ]
    # No explicit 'Invoice Number:' keyword was provided near INV-9999, so it matches via regex
    res = extract_invoice_fields(words=words)
    assert res.invoice_number == "INV-9999"
    # Because there was no explicit keyword anchor, field_confidence is lower than the raw OCR confidence of 0.98
    assert res.field_confidence["invoice_number"] != 0.98
    assert res.field_confidence["invoice_number"] < 0.90


def test_digital_pdf_compatibility_without_ocr_words():
    """
    Verify requirement 16:
    - Extractor works seamlessly when words=None or OCR metadata is unavailable.
    - extract(text=pdf_text, words=None) attempts extraction using keywords, regex, line relationships.
    - Gracefully falls back to pure text extraction.
    """
    pdf_text = """
    Zenith Cloud Infrastructure LLP
    78 Innovation Boulevard, Tech City, Bangalore 560001
    GSTIN: 29AAAAA0000A1Z5
    
    INVOICE
    Invoice Number: ZCI-2026-4401
    Invoice Date: 18/09/2026
    
    Bill To:
    Global Enterprises Inc
    
    Line Item                 Qty    Price      Total
    Cloud Compute Units        10   $150.00  $1,500.00
    
    Subtotal: $1,500.00
    Grand Total: $1,500.00
    """
    # Explicitly pass words=None (pure digital PDF output)
    result = InvoiceExtractor.extract(text=pdf_text, words=None)

    assert result.success is True
    assert result.vendor_name == "Zenith Cloud Infrastructure LLP"
    assert result.invoice_number == "ZCI-2026-4401"
    assert result.invoice_date == "18/09/2026"
    assert result.total_amount == "1500.00"

    assert result.field_confidence["vendor_name"] >= 0.70
    assert result.field_confidence["invoice_number"] >= 0.80
    assert result.field_confidence["invoice_date"] >= 0.80
    assert result.field_confidence["total_amount"] >= 0.85


def test_ocr_compatibility_and_clean_decoupling():
    """
    Verify requirement 17:
    - extract(text=ocr_combined_text, words=ocr_words) accepts structured OCR output.
    - InvoiceExtractor does not call OCR engine / Tesseract / OpenCV.
    - Clean architectural separation: OCR Engine -> OCRResult -> InvoiceExtractor -> InvoiceExtractionResult.
    """
    import app.services.extraction as ext_module

    # Verify no OCR execution libraries or functions are imported into extraction.py
    assert "pytesseract" not in ext_module.__dict__
    assert "cv2" not in ext_module.__dict__
    assert "pdf2image" not in ext_module.__dict__
    assert "perform_ocr" not in ext_module.__dict__
    assert "convert_from_path" not in ext_module.__dict__

    # Verify that passing OCRResult or combined_text + ocr_words works seamlessly
    page_words = [
        OCRWordData(text="Apex", confidence=95.0, bounding_box=OCRBoundingBox(left=50, top=50, width=50, height=20, x2=100, y2=70), line_num=1),
        OCRWordData(text="Corp", confidence=95.0, bounding_box=OCRBoundingBox(left=105, top=50, width=50, height=20, x2=155, y2=70), line_num=1),
        OCRWordData(text="Invoice", confidence=97.0, bounding_box=OCRBoundingBox(left=50, top=100, width=60, height=20, x2=110, y2=120), line_num=2),
        OCRWordData(text="#:", confidence=97.0, bounding_box=OCRBoundingBox(left=115, top=100, width=20, height=20, x2=135, y2=120), line_num=2),
        OCRWordData(text="APX-101", confidence=96.0, bounding_box=OCRBoundingBox(left=140, top=100, width=70, height=20, x2=210, y2=120), line_num=2),
        OCRWordData(text="Date:", confidence=96.0, bounding_box=OCRBoundingBox(left=50, top=130, width=40, height=20, x2=90, y2=150), line_num=3),
        OCRWordData(text="2026-09-12", confidence=96.0, bounding_box=OCRBoundingBox(left=95, top=130, width=80, height=20, x2=175, y2=150), line_num=3),
        OCRWordData(text="Total:", confidence=98.0, bounding_box=OCRBoundingBox(left=50, top=200, width=45, height=20, x2=95, y2=220), line_num=5),
        OCRWordData(text="350.00", confidence=98.0, bounding_box=OCRBoundingBox(left=100, top=200, width=60, height=20, x2=160, y2=220), line_num=5),
    ]
    combined_text = "Apex Corp\nInvoice #: APX-101\nDate: 2026-09-12\nTotal: 350.00"

    res = extract_invoice_fields(text=combined_text, words=page_words)
    assert res.success is True
    assert res.vendor_name == "Apex Corp"
    assert res.invoice_number == "APX-101"
    assert res.invoice_date == "2026-09-12"
    assert res.total_amount == "350.00"
    # Bounding boxes must be populated on extracted fields
    assert res.extracted_fields is not None
    assert res.extracted_fields["invoice_number"].bounding_box is not None
    assert res.extracted_fields["invoice_number"].bounding_box.left == 140


def test_ai_extraction_provider_interface_and_noop_placeholder():
    """
    Verify requirement 18:
    - AIExtractionProvider is an abstract base class (cannot be instantiated directly).
    - Subclasses must implement extract(self, text: str) -> dict.
    - NoOpAIExtractionProvider is a safe placeholder returning {} with zero API calls.
    - Extractor defaults to NoOpAIExtractionProvider and makes no external API calls.
    """
    from app.services.extraction import AIExtractionProvider, NoOpAIExtractionProvider

    # 1. ABC cannot be instantiated directly
    try:
        AIExtractionProvider()
        assert False, "AIExtractionProvider must be abstract and raise TypeError on direct instantiation"
    except TypeError:
        pass

    # 2. Concrete implementation requires extract method
    class IncompleteProvider(AIExtractionProvider):
        pass

    try:
        IncompleteProvider()
        assert False, "IncompleteProvider without extract() must raise TypeError"
    except TypeError:
        pass

    # 3. NoOpAIExtractionProvider instantiation and behavior
    noop = NoOpAIExtractionProvider()
    assert isinstance(noop, AIExtractionProvider)
    output = noop.extract("Sample invoice text ABC Technologies INV-001 $100")
    assert output == {}

    # 4. Extractor class-level references
    assert InvoiceExtractor.AIExtractionProvider is AIExtractionProvider
    assert InvoiceExtractor.NoOpAIExtractionProvider is NoOpAIExtractionProvider
    assert isinstance(InvoiceExtractor.default_ai_provider, NoOpAIExtractionProvider)


def test_candidate_reconciliation_architecture_and_extension_points():
    """
    Verify requirement 19:
    - Candidate reconciliation architecture combines rule candidates with AI candidates.
    - Example: Rule candidate INV-001 (conf=0.94) + AI candidate INV-001 (conf=0.91)
      Agreement serves as useful corroborating evidence, reinforcing confidence.
    - Preserves candidates transparently in result.candidates.
    - Clean extension points without requiring active external AI services.
    """
    from app.services.extraction import AIExtractionProvider, FieldCandidate, reconcile_candidates

    # 1. Test direct reconciliation function
    rule_cand = FieldCandidate(
        field_name="invoice_number",
        value="INV-001",
        confidence=0.94,
        source="keyword",
        matched_keyword="invoice number",
        score=0.94,
        evidence="keyword match",
    )
    rule_candidates = {
        "vendor_name": [],
        "invoice_number": [rule_cand],
        "invoice_date": [],
        "total_amount": [],
    }

    # AI candidate also provides INV-001 with 0.91 confidence
    ai_output = {
        "invoice_number": "INV-001",
        "confidence": {"invoice_number": 0.91},
    }

    selected, all_cands = reconcile_candidates(rule_candidates=rule_candidates, ai_results=ai_output)

    # Both Rule and AI candidates must be present in the candidate audit trail
    inv_cands = all_cands["invoice_number"]
    assert len(inv_cands) == 2
    sources = [c.source for c in inv_cands]
    assert "keyword" in sources
    assert "ai" in sources

    # Agreement must have reinforced the rule candidate's confidence
    rule_cand_reconciled = next(c for c in inv_cands if c.source == "keyword")
    assert rule_cand_reconciled.confidence >= 0.94
    assert "Reinforced by AI agreement" in rule_cand_reconciled.evidence

    # Selected candidate must be INV-001
    assert selected["invoice_number"] is not None
    assert selected["invoice_number"].value == "INV-001"

    # 2. End-to-end extraction with a mock AI provider
    class MockAIExtractionProvider(AIExtractionProvider):
        def extract(self, text: str) -> dict:
            return {
                "vendor_name": "ABC Technologies Pvt Ltd",
                "invoice_number": "INV-2026-001",
                "confidence": {
                    "vendor_name": 0.95,
                    "invoice_number": 0.92,
                },
            }

    doc = """
    ABC Technologies Pvt Ltd
    Invoice No: INV-2026-001
    Date: 2026-09-12
    Total: $450.00
    """
    res = InvoiceExtractor.extract(text=doc, ai_provider=MockAIExtractionProvider())

    assert res.success is True
    assert res.vendor_name == "ABC Technologies Pvt Ltd"
    assert res.invoice_number == "INV-2026-001"
    # Check that AI candidate was recorded in candidates list
    assert any(c.source == "ai" for c in res.candidates["invoice_number"])
    assert any("Reinforced by AI agreement" in c.evidence for c in res.candidates["invoice_number"] if c.source != "ai")


def test_missing_fields_graceful_handling_does_not_fail_document():
    """
    Verify requirement 20:
    - Invoices may not contain all four fields.
    - Extractor must NOT fail the entire document because one field is missing.
    - Example from requirements:
      vendor_name = "ABC Technologies", invoice_number = "INV-001",
      invoice_date = null (confidence = 0.0), total_amount = "11300.00".
    - fields_found must contain ["vendor_name", "invoice_number", "total_amount"].
    - missing_fields must contain ["invoice_date"].
    """
    # Document with vendor, invoice number, and grand total, but NO invoice date
    doc = """
    ABC Technologies
    100 Industrial Parkway, Innovation Sector
    GSTIN: 27AAAAA0000A1Z5

    Invoice Number: INV-001

    Description              Amount
    Software Licensing     11,300.00

    Grand Total: 11,300.00
    """
    result = extract_invoice_fields(doc)

    assert result.success is True
    assert result.vendor_name == "ABC Technologies"
    assert result.invoice_number == "INV-001"
    assert result.invoice_date is None
    assert result.total_amount == "11300.00"

    # Confidence check
    assert result.field_confidence["vendor_name"] >= 0.70
    assert result.field_confidence["invoice_number"] >= 0.80
    assert result.field_confidence["total_amount"] >= 0.80
    assert result.field_confidence["invoice_date"] == 0.0

    # Fields found and missing check
    assert "vendor_name" in result.fields_found
    assert "invoice_number" in result.fields_found
    assert "total_amount" in result.fields_found
    assert "invoice_date" not in result.fields_found

    assert result.missing_fields == ["invoice_date"]


def test_avoid_false_positives_field_specific_exclusions():
    """
    Verify requirement 21:
    Field-specific exclusion logic to avoid false positives:
    - Invoice number avoids: GSTIN, PAN, phone number, bank account, IFSC, date, PIN code.
    - Invoice date avoids: due date, delivery date, order date, shipping date (when invoice date exists).
    - Total amount avoids: subtotal, tax amount, discount, unit price, quantity.
    - Vendor name avoids: Tax Invoice, Invoice, Bill, Quotation, Purchase Order, Invoice Number.
    """
    from app.services.extraction import (
        check_invoice_number_exclusions,
        check_invoice_date_exclusions,
        check_total_amount_exclusions,
        check_vendor_name_exclusions,
    )

    # 1. Direct Invoice Number exclusion checks
    assert check_invoice_number_exclusions("29AAAAA0000A1Z5")[0] is True  # GSTIN
    assert check_invoice_number_exclusions("ABCDE1234F")[0] is True       # PAN
    assert check_invoice_number_exclusions("9876543210")[0] is True       # Phone number
    assert check_invoice_number_exclusions("12345678901234")[0] is True   # Bank account
    assert check_invoice_number_exclusions("HDFC0001234")[0] is True      # IFSC
    assert check_invoice_number_exclusions("2026-09-12")[0] is True       # Date
    assert check_invoice_number_exclusions("560001", "PIN: 560001 Bangalore")[0] is True  # PIN code

    # A valid invoice number is NOT disqualified
    assert check_invoice_number_exclusions("INV-2026-099")[0] is False

    # 2. Direct Invoice Date exclusion checks
    assert check_invoice_date_exclusions("Due Date: 2026-10-15")[0] is True
    assert check_invoice_date_exclusions("Delivery Date: 2026-09-25")[0] is True
    assert check_invoice_date_exclusions("Order Date: 2026-09-01")[0] is True
    assert check_invoice_date_exclusions("Shipping Date: 2026-09-18")[0] is True
    assert check_invoice_date_exclusions("Invoice Date: 2026-09-12")[0] is False

    # 3. Direct Total Amount exclusion checks
    assert check_total_amount_exclusions("Subtotal: $1,000.00")[0] is True
    assert check_total_amount_exclusions("Tax Amount: $180.00")[0] is True
    assert check_total_amount_exclusions("Discount: $50.00")[0] is True
    assert check_total_amount_exclusions("Unit Price: $100.00")[0] is True
    assert check_total_amount_exclusions("Quantity: 10")[0] is True
    assert check_total_amount_exclusions("Grand Total: $1,130.00")[0] is False

    # 4. Direct Vendor Name exclusion checks
    assert check_vendor_name_exclusions("Tax Invoice")[0] is True
    assert check_vendor_name_exclusions("Invoice")[0] is True
    assert check_vendor_name_exclusions("Bill")[0] is True
    assert check_vendor_name_exclusions("Quotation")[0] is True
    assert check_vendor_name_exclusions("Purchase Order")[0] is True
    assert check_vendor_name_exclusions("Invoice Number: INV-001")[0] is True
    assert check_vendor_name_exclusions("Vertex Cloud Technologies Pvt Ltd")[0] is False

    # 5. End-to-end Document Test with all false-positive distractors present
    doc = """
    TAX INVOICE
    PURCHASE ORDER
    QUOTATION
    
    Vertex Cloud Technologies Pvt Ltd
    Plot 45, Tech Zone, Whitefield, Bangalore 560066
    GSTIN: 29ABCDE1234F1Z5
    PAN: ABCDE1234F
    Phone: +91 9876543210
    Bank A/C: 987654321012345
    IFSC: HDFC0001234
    
    Order Date: 01/09/2026
    Shipping Date: 05/09/2026
    Delivery Date: 10/09/2026
    Invoice Date: 12/09/2026
    Due Date: 30/09/2026
    
    Invoice No: INV-2026-8801
    
    Item Description     Qty   Unit Price    Tax Amount    Discount    Total
    Cloud Compute Server  10      $100.00        $18.00      $10.00  $1,000.00
    
    Subtotal: $1,000.00
    Tax Amount (GST 18%): $180.00
    Discount: $50.00
    Grand Total: $1,130.00
    """
    res = extract_invoice_fields(doc)

    assert res.success is True
    # Vendor must be Vertex Cloud Technologies, NOT 'TAX INVOICE' or 'PURCHASE ORDER'
    assert res.vendor_name == "Vertex Cloud Technologies Pvt Ltd"
    # Invoice number must be INV-2026-8801, NOT GSTIN, PAN, Phone, Bank A/C, or IFSC
    assert res.invoice_number == "INV-2026-8801"
    # Invoice date must be 12/09/2026, NOT Due Date, Delivery Date, Order Date, or Shipping Date
    assert res.invoice_date == "12/09/2026"
    # Total amount must be 1130.00, NOT Subtotal, Tax Amount, Discount, Unit Price, or Quantity
    assert res.total_amount == "1130.00"


def test_conservative_text_preprocessing():
    """
    Verify requirement 22:
    - Conservative text preparation preserves numbers, punctuation, currency symbols, dates, line boundaries.
    - Trims excessive horizontal whitespace and collapses repeated spaces.
    - Does NOT perform date normalization, currency normalization, amount conversion, business validation, spelling correction.
    """
    from app.services.extraction import prepare_text

    raw_invoice = (
        "   Acme   Logistics   Pvt   Ltd   \n"
        "\n"
        "   Invoice   No:      INV/2026/001   \n"
        "   Date:   12/08/2026   \n"
        "   Total   Amount:      ₹15,499.50   \n"
    )

    clean_text, lines = prepare_text(raw_invoice)

    # 1. Preserves line boundaries as distinct non-empty lines
    assert len(lines) == 4

    # 2. Excessive horizontal whitespace trimmed and collapsed
    assert lines[0] == "Acme Logistics Pvt Ltd"
    assert lines[1] == "Invoice No: INV/2026/001"
    assert lines[2] == "Date: 12/08/2026"
    assert lines[3] == "Total Amount: ₹15,499.50"

    # 3. Currency symbol (₹), punctuation (:, /, .), numbers (15,499.50), and date format (12/08/2026) are strictly preserved
    assert "₹" in lines[3]
    assert "15,499.50" in lines[3]
    assert "12/08/2026" in lines[2]
    assert "INV/2026/001" in lines[1]

    # 4. No aggressive conversions occurred
    assert "2026-08-12" not in clean_text  # Did NOT normalize date format
    assert "INR" not in clean_text          # Did NOT convert currency symbol
    assert "15499.5" not in lines[3]       # Did NOT convert amount to float representation


def test_extraction_pipeline_conceptual_flow():
    """
    Verify requirement 23:
    Pipeline modularity follows the conceptual flow:
    Input -> Prepare text/OCR -> Detect keywords -> Generate candidates ->
    Apply regex/patterns -> Apply nearby heuristics -> Apply positional heuristics ->
    Use OCR confidence -> Apply negative evidence -> Score candidates ->
    Select best candidate -> Return structured extraction result.
    """
    text = """
    Nexus Global Technologies Ltd
    100 Tech Park, Electronic City
    Invoice Number: NX-2026-042
    Date: 2026-09-12
    Grand Total: $7,500.00
    """
    result = InvoiceExtractor.extract(text=text)

    # 1. Returns structured result
    assert result.success is True
    assert result.vendor_name == "Nexus Global Technologies Ltd"
    assert result.invoice_number == "NX-2026-042"
    assert result.invoice_date == "2026-09-12"
    assert result.total_amount == "7500.00"

    # 2. Pipeline metrics and metadata
    assert result.metadata is not None
    assert result.metadata["line_count"] > 0
    assert result.fields_found == ["vendor_name", "invoice_number", "invoice_date", "total_amount"]
    assert result.missing_fields == []

    # 3. All evaluated candidates and multi-signal scoring evidence preserved
    assert result.candidates is not None
    assert "invoice_number" in result.candidates
    top_cand = result.candidates["invoice_number"][0]
    assert top_cand.value == "NX-2026-042"
    assert top_cand.confidence >= 0.85
    assert "signals:" in top_cand.evidence


def test_recommended_internal_modular_methods():
    """
    Verify requirement 10: Recommended internal methods:
    - extract()
    - _extract_vendor_name()
    - _extract_invoice_number()
    - _extract_invoice_date()
    - _extract_total_amount()
    - _find_keyword_matches()
    - _generate_candidates()
    - _score_candidate()
    - _get_nearby_text()
    - _calculate_text_distance()
    - _calculate_spatial_distance()
    - _get_ocr_confidence()
    - _is_valid_invoice_number_candidate()
    - _is_valid_date_candidate()
    - _is_valid_total_candidate()
    - _is_likely_vendor_candidate()
    """
    # 1. extract()
    sample_text = """
    Apex Global Solutions Ltd
    Invoice No: APX-901
    Date: 2026-09-15
    Total Amount: $4,500.00
    """
    res = InvoiceExtractor.extract(text=sample_text)
    assert res.success is True
    assert res.vendor_name == "Apex Global Solutions Ltd"
    assert res.invoice_number == "APX-901"
    assert res.invoice_date == "2026-09-15"
    assert res.total_amount == "4500.00"

    lines = [
        "Apex Global Solutions Ltd",
        "123 Tech Park, Bangalore",
        "Invoice No: APX-901",
        "Date: 2026-09-15",
        "Total Amount: $4,500.00",
    ]

    # 2. _extract_vendor_name()
    v_cand, v_all = InvoiceExtractor._extract_vendor_name(lines, {})
    assert v_cand is not None
    assert v_cand.value == "Apex Global Solutions Ltd"
    assert len(v_all) >= 1

    # 3. _extract_invoice_number()
    num_cand, num_all = InvoiceExtractor._extract_invoice_number(lines, {})
    assert num_cand is not None
    assert num_cand.value == "APX-901"
    assert len(num_all) >= 1

    # 4. _extract_invoice_date()
    d_cand, d_all = InvoiceExtractor._extract_invoice_date(lines, {})
    assert d_cand is not None
    assert d_cand.value == "2026-09-15"
    assert len(d_all) >= 1

    # 5. _extract_total_amount()
    tot_cand, tot_all = InvoiceExtractor._extract_total_amount(lines, {})
    assert tot_cand is not None
    assert tot_cand.value == "4500.00"
    assert len(tot_all) >= 1

    # 6. _find_keyword_matches()
    kw_matches = InvoiceExtractor._find_keyword_matches(
        "Invoice Number: INV-001",
        ["invoice number", "invoice", "number"],
    )
    assert len(kw_matches) >= 1
    # Longest match first
    assert kw_matches[0][0] == "invoice number"
    assert kw_matches[0][1] == 0

    # 7. _generate_candidates()
    gen_cands = InvoiceExtractor._generate_candidates("invoice_number", lines, {})
    assert len(gen_cands) >= 1
    assert any(c.value == "APX-901" for c in gen_cands)
    unknown_cands = InvoiceExtractor._generate_candidates("unsupported_field", lines, {})
    assert unknown_cands == []

    # 8. _score_candidate()
    test_cand = gen_cands[0]
    score = InvoiceExtractor._score_candidate(test_cand)
    assert 0.0 <= score <= 1.0

    # 9. _get_nearby_text()
    five_lines = ["Line 0", "Line 1", "Target Line 2", "Line 3", "Line 4"]
    above = InvoiceExtractor._get_nearby_text(five_lines, line_idx=2, window=1, direction="above")
    assert above == ["Line 1"]
    below = InvoiceExtractor._get_nearby_text(five_lines, line_idx=2, window=1, direction="below")
    assert below == ["Line 3"]
    both = InvoiceExtractor._get_nearby_text(five_lines, line_idx=2, window=1, direction="both")
    assert both == ["Line 1", "Line 3"]

    # 10. _calculate_text_distance()
    prox_same = InvoiceExtractor._calculate_text_distance(line_distance=0, char_distance=2)
    prox_distant = InvoiceExtractor._calculate_text_distance(line_distance=4, intervening_lines=3)
    assert prox_same > prox_distant
    assert prox_same >= 0.90

    # 11. _calculate_spatial_distance()
    b1 = OCRBoundingBox(left=10, top=10, width=50, height=20, x2=60, y2=30)
    b2 = OCRBoundingBox(left=70, top=10, width=50, height=20, x2=120, y2=30)
    dist = InvoiceExtractor._calculate_spatial_distance(b1, b2)
    assert dist == 10.0  # 70 - 60 = 10 horizontally, 0 vertically

    # 12. _get_ocr_confidence()
    w1 = OCRWordData(text="APX-901", confidence=96.0, bounding_box=b1)
    conf = InvoiceExtractor._get_ocr_confidence("APX-901", {1: [w1]})
    assert conf is not None
    assert abs(conf - 0.96) < 1e-4
    assert InvoiceExtractor._get_ocr_confidence("NONEXISTENT", {1: [w1]}) is None

    # 13. _is_valid_invoice_number_candidate()
    assert InvoiceExtractor._is_valid_invoice_number_candidate("APX-901", "Invoice No: APX-901") is True
    # Disqualified: GSTIN
    assert InvoiceExtractor._is_valid_invoice_number_candidate("29ABCDE1234F1Z5", "GSTIN: 29ABCDE1234F1Z5") is False
    # Disqualified: PAN
    assert InvoiceExtractor._is_valid_invoice_number_candidate("ABCDE1234F", "PAN: ABCDE1234F") is False

    # 14. _is_valid_date_candidate()
    assert InvoiceExtractor._is_valid_date_candidate("15/09/2026", "Invoice Date: 15/09/2026") is True
    # Disqualified by due/delivery date exclusion
    assert InvoiceExtractor._is_valid_date_candidate("30/09/2026", "Due Date: 30/09/2026") is False

    # 15. _is_valid_total_candidate()
    assert InvoiceExtractor._is_valid_total_candidate("4500.00", "Grand Total: 4,500.00") is True
    # Disqualified by subtotal/tax exclusion
    assert InvoiceExtractor._is_valid_total_candidate("100.00", "Subtotal: $100.00") is False

    # 16. _is_likely_vendor_candidate()
    assert InvoiceExtractor._is_likely_vendor_candidate("Apex Global Solutions Ltd") is True
    # Disqualified by generic document title
    assert InvoiceExtractor._is_likely_vendor_candidate("Tax Invoice") is False
    assert InvoiceExtractor._is_likely_vendor_candidate("Invoice") is False
    assert InvoiceExtractor._is_likely_vendor_candidate("Purchase Order") is False


def test_accuracy_focused_design_no_guessing_or_fabrication():
    """
    Verify accuracy-focused design principles:
    1. Primary goal is accurate extraction, not simply producing a result.
    2. Prefer high-quality candidate over random candidate.
    3. If evidence is weak: value = None, confidence = 0.0 rather than guessing.
    4. Do not fabricate missing information.
    5. Do not assume:
       - first line = vendor (without supporting company indicator or address evidence)
       - first number = invoice number (without invoice keyword anchor or explicit prefix)
       - largest number = total amount (without total keyword anchor)
       - first date = invoice date (without supporting date contextual evidence)
    """
    # Test 1: Non-invoice document with numbers, dates, titles, and amounts
    # but NO invoice-specific contextual evidence.
    memo_text = """
    Quarterly Product Retrospective Meeting
    Created by Engineering Team
    Room 402, Building 3
    
    Session recorded on 14/05/2026 for review.
    Total attendees present: 45
    We reviewed 1,500 user tickets and 98 pull requests.
    Bug backlog count: 120
    Server budget remaining: $25,000.00
    """
    res = InvoiceExtractor.extract(text=memo_text)
    assert res.success is True
    
    # 1. Does not assume first line ("Quarterly Product Retrospective Meeting") = vendor
    assert res.vendor_name is None
    assert res.field_confidence["vendor_name"] == 0.0
    
    # 2. Does not assume first number ("402" or "3" or "45") = invoice number
    assert res.invoice_number is None
    assert res.field_confidence["invoice_number"] == 0.0
    
    # 3. Does not assume first date ("14/05/2026") = invoice date without invoice/date keyword
    assert res.invoice_date is None
    assert res.field_confidence["invoice_date"] == 0.0
    
    # 4. Does not assume largest number ("25,000.00" or "1,500") = total amount without total keyword
    assert res.total_amount is None
    assert res.field_confidence["total_amount"] == 0.0
    
    # 5. Missing fields are tracked, not fabricated
    assert set(res.missing_fields) == {"vendor_name", "invoice_number", "invoice_date", "total_amount"}
    assert res.fields_found == []

    # Test 2: Valid invoice with high-quality candidates alongside distracting random numbers/dates
    invoice_text = """
    Nexus Global Technologies Ltd
    100 Tech Park, Electronic City, Bangalore 560100
    GSTIN: 29ABCDE1234F1Z5
    Phone: 9876543210
    
    TAX INVOICE
    Invoice Number: NX-2026-901
    Invoice Date: 12/09/2026
    
    Line Items:
    Software License (Qty: 50, Unit: $100.00)     Amount: $5,000.00
    Hardware Server (Qty: 2, Unit: $15,000.00)    Amount: $30,000.00
    
    Subtotal: $35,000.00
    Tax (18%): $6,300.00
    Grand Total: $41,300.00
    """
    res_inv = InvoiceExtractor.extract(text=invoice_text)
    assert res_inv.success is True
    # Prefers high-quality vendor with suffix & address
    assert res_inv.vendor_name == "Nexus Global Technologies Ltd"
    # Prefers high-quality invoice number over phone, GSTIN, Qty 50, Unit 100
    assert res_inv.invoice_number == "NX-2026-901"
    # Prefers invoice date over any other dates
    assert res_inv.invoice_date == "12/09/2026"
    # Prefers Grand Total over larger or intermediate subtotal/item amounts
    assert res_inv.total_amount == "41300.00"
    assert res_inv.fields_found == ["vendor_name", "invoice_number", "invoice_date", "total_amount"]
    assert res_inv.missing_fields == []


def test_logging_and_robust_error_handling():
    """
    Verify:
    1. Standard logging module is used with useful debug messages.
    2. Format matches:
       Field: ...
       Candidates found: ...
       Selected: ...
       Confidence: ...
       Source: ...
    3. Robust error handling without crashes for:
       - empty text
       - malformed OCR word data (non-dicts, missing keys, invalid coords)
       - missing bounding boxes
       - missing confidence
       - invalid confidence values (NaN, negative, string, > 100)
       - unexpected input types (int, float, list of ints, boolean)
       - malformed dates
       - unusual invoice layouts
    4. In-memory results: no database changes, documents/records/audits untouched.
    """
    import io
    import logging

    # 1. Test Debug Logging capture
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setLevel(logging.DEBUG)
    ext_logger = logging.getLogger("app.services.extraction")
    orig_level = ext_logger.level
    ext_logger.setLevel(logging.DEBUG)
    ext_logger.addHandler(handler)

    try:
        sample_doc = """
        ABC Technologies Pvt Ltd
        Invoice Number: INV-2026-001
        Invoice Date: 12/08/2026
        Grand Total: $1,500.00
        """
        res = InvoiceExtractor.extract(text=sample_doc)
        assert res.success is True
        logs = log_capture.getvalue()
        
        # Verify logging format
        assert "Field: invoice_number" in logs
        assert "Candidates found:" in logs
        assert "Selected: INV-2026-001" in logs
        assert "Confidence:" in logs
        assert "Source:" in logs
    finally:
        ext_logger.removeHandler(handler)
        ext_logger.setLevel(orig_level)

    # 2. Test Empty and Whitespace Text
    res_empty = InvoiceExtractor.extract(text="")
    assert res_empty.success is True
    assert res_empty.missing_fields == ["vendor_name", "invoice_number", "invoice_date", "total_amount"]
    assert len(res_empty.errors) > 0

    # 3. Test Unexpected Input Types (int, float, list, bool)
    for bad_input in [12345, 99.99, [1, 2, 3], True, None]:
        res_bad = InvoiceExtractor.extract(document_input=bad_input)
        assert res_bad is not None
        # Does not crash, handles gracefully
        assert isinstance(res_bad.success, bool)

    # 4. Test Malformed OCR Word Data & Missing/Invalid Bounding Boxes & Confidences
    malformed_words = [
        "not_a_dict",
        {"no_text": True},
        {"text": ""},  # empty string
        {"text": "INV-001", "confidence": "not_a_float", "bbox": None},
        {"text": "Total", "confidence": -50.0, "bbox": "invalid_bbox"},
        {"text": "100.00", "confidence": float("nan"), "bounding_box": {"left": "bad", "top": -5}},
        {"text": "2026-09-12", "confidence": 999.0, "bbox": {"left": 10, "top": 20, "width": 50, "height": 20}},
    ]
    res_malformed_ocr = InvoiceExtractor.extract(text="Sample Invoice INV-001", words=malformed_words)
    assert res_malformed_ocr.success is True
    assert res_malformed_ocr.invoice_number == "INV-001"

    # 5. Test Malformed Dates
    assert InvoiceExtractor._is_valid_date_format(None) is False
    assert InvoiceExtractor._is_valid_date_format("99/99/9999") is False
    assert InvoiceExtractor._is_valid_date_format("not-a-date") is False
    assert InvoiceExtractor._is_valid_date_format("32/01/2026") is False
    assert InvoiceExtractor._is_valid_date_format("15/13/2026") is False

    # 6. Test Unusual Invoice Layouts (deeply indented, irregular line breaks)
    unusual_layout = """
                                Acme Corp
                                
    TAX INVOICE
    
    Ref:                                         Date:
    INV/2026/99                                  15-Sep-2026
    
    
    
    ---------------------------------------------------------
    Item                          Qty                   Price
    ---------------------------------------------------------
    Widget                         1                  $500.00
    ---------------------------------------------------------
    
                                  Total Due:          $500.00
    """
    res_unusual = InvoiceExtractor.extract(text=unusual_layout)
    assert res_unusual.success is True
    assert res_unusual.invoice_number == "INV/2026/99"
    assert res_unusual.invoice_date == "15-Sep-2026"
    assert res_unusual.total_amount == "500.00"

    # 7. No Database Changes
    # Ensure extraction remains pure in-memory calculation with zero DB imports or mutations
    assert hasattr(res_unusual, "model_dump")
    assert not hasattr(res_unusual, "_sa_instance_state")


if __name__ == "__main__":
    print("Running Invoice Field Extraction Unit Tests...")
    test_invoice_extractor_class_with_independent_words()
    print("[PASS] test_invoice_extractor_class_with_independent_words")
    test_extract_standard_invoice_all_fields()
    print("[PASS] test_extract_standard_invoice_all_fields")
    test_extract_missing_fields_returns_null_and_zero_confidence()
    print("[PASS] test_extract_missing_fields_returns_null_and_zero_confidence")
    test_extract_invoice_number_variants()
    print("[PASS] test_extract_invoice_number_variants")
    test_extract_invoice_date_variants()
    print("[PASS] test_extract_invoice_date_variants")
    test_extract_total_amount_variants()
    print("[PASS] test_extract_total_amount_variants")
    test_extract_vendor_name_heuristics()
    print("[PASS] test_extract_vendor_name_heuristics")
    test_extract_from_ocr_result_with_bounding_boxes()
    print("[PASS] test_extract_from_ocr_result_with_bounding_boxes")
    test_extract_from_pdf_parse_result()
    print("[PASS] test_extract_from_pdf_parse_result")
    test_extract_empty_or_corrupted_input()
    print("[PASS] test_extract_empty_or_corrupted_input")
    test_multi_candidate_evaluation_prioritizes_best_candidate_over_first_match()
    print("[PASS] test_multi_candidate_evaluation_prioritizes_best_candidate_over_first_match")
    test_centralized_keyword_dictionaries_structure_and_coverage()
    print("[PASS] test_centralized_keyword_dictionaries_structure_and_coverage")
    test_field_candidate_attributes_and_schema()
    print("[PASS] test_field_candidate_attributes_and_schema")
    test_vendor_name_strategies_a_b_c_d()
    print("[PASS] test_vendor_name_strategies_a_b_c_d")
    test_invoice_number_diverse_formats()
    print("[PASS] test_invoice_number_diverse_formats")
    test_invoice_number_penalizes_disqualified_patterns()
    print("[PASS] test_invoice_number_penalizes_disqualified_patterns")
    test_candidate_scoring_weights_and_breakdown()
    print("[PASS] test_candidate_scoring_weights_and_breakdown")
    test_keyword_proximity_mechanism()
    print("[PASS] test_keyword_proximity_mechanism")
    test_bounding_box_heuristics_relationships_and_grouping()
    print("[PASS] test_bounding_box_heuristics_relationships_and_grouping")
    test_ocr_confidence_as_supporting_evidence_not_blindly_copied()
    print("[PASS] test_ocr_confidence_as_supporting_evidence_not_blindly_copied")
    test_digital_pdf_compatibility_without_ocr_words()
    print("[PASS] test_digital_pdf_compatibility_without_ocr_words")
    test_ocr_compatibility_and_clean_decoupling()
    print("[PASS] test_ocr_compatibility_and_clean_decoupling")
    test_ai_extraction_provider_interface_and_noop_placeholder()
    print("[PASS] test_ai_extraction_provider_interface_and_noop_placeholder")
    test_candidate_reconciliation_architecture_and_extension_points()
    print("[PASS] test_candidate_reconciliation_architecture_and_extension_points")
    test_missing_fields_graceful_handling_does_not_fail_document()
    print("[PASS] test_missing_fields_graceful_handling_does_not_fail_document")
    test_avoid_false_positives_field_specific_exclusions()
    print("[PASS] test_avoid_false_positives_field_specific_exclusions")
    test_conservative_text_preprocessing()
    print("[PASS] test_conservative_text_preprocessing")
    test_extraction_pipeline_conceptual_flow()
    print("[PASS] test_extraction_pipeline_conceptual_flow")
    test_recommended_internal_modular_methods()
    print("[PASS] test_recommended_internal_modular_methods")
    test_accuracy_focused_design_no_guessing_or_fabrication()
    print("[PASS] test_accuracy_focused_design_no_guessing_or_fabrication")
    test_logging_and_robust_error_handling()
    print("[PASS] test_logging_and_robust_error_handling")
    print("\nALL INVOICE EXTRACTION TESTS PASSED SUCCESSFULLY!")




