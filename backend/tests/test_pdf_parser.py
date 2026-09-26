import os
from pathlib import Path
import sys
import tempfile

# Ensure backend root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pypdf

from app.schemas.pdf import PDFPageData, PDFParseResult
from app.services.pdf_parser import PdfParser, parse_pdf, pdf_parser


def test_pdf_parser_non_existent_file():
    """Verify non-existent files are rejected safely without crashing."""
    result = parse_pdf("non_existent_file.pdf")
    assert result.success is False
    assert result.error is not None
    assert "File does not exist" in result.error
    assert result.file_type == "PDF"


def test_pdf_parser_zero_byte_file():
    """Verify 0-byte PDF files return a clean failure result."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = parse_pdf(tmp_path)
        assert result.success is False
        assert "empty" in result.error.lower()
        assert result.total_pages == 0
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_pdf_parser_encrypted_pdf():
    """Verify password-protected PDFs are flagged with is_encrypted=True."""
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("super_secret_password")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
        with open(tmp_path, "wb") as f:
            writer.write(f)

    try:
        result = parse_pdf(tmp_path)
        assert result.success is False
        assert result.status == "PASSWORD_PROTECTED"
        assert result.error == "PDF is password protected and cannot be processed."
        assert result.is_encrypted is True
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_pdf_parser_blank_or_scanned_pdf():
    """Verify image-only / scanned PDFs are flagged with likely_scanned=True and status NO_USABLE_TEXT."""
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
        with open(tmp_path, "wb") as f:
            writer.write(f)

    try:
        result = parse_pdf(tmp_path)
        assert result.success is True
        assert result.status == "NO_USABLE_TEXT"
        assert result.page_count == 1
        assert result.total_characters == 0
        assert result.meaningful_characters == 0
        assert result.pages_with_text == 0
        assert result.pages_without_text == 1
        assert result.has_extractable_text is False
        assert result.likely_scanned is True
        assert result.pages[0].has_text is False
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_pdf_parser_digital_pdf_text_extraction():
    """Verify digital PDF extraction on sample uploaded PDF."""
    sample_pdf = Path(r"c:\Intelligent Document Processing(IDP)\backend\uploads\abb54f96-de5b-45aa-b24d-cf3503d247e2.pdf")
    if not sample_pdf.exists():
        print("Sample upload PDF not found, skipping digital test.")
        return

    result = parse_pdf(sample_pdf)
    assert result.success is True
    assert result.status == "TEXT_EXTRACTED"
    assert result.file_type == "PDF"
    assert result.page_count == 1
    assert result.total_characters > 500
    assert result.meaningful_characters > 500
    assert result.pages_with_text == 1
    assert result.pages_without_text == 0
    assert result.has_extractable_text is True
    assert result.likely_scanned is False
    assert len(result.pages) == 1
    assert result.pages[0].has_text is True
    assert result.pages[0].text != ""
    assert result.combined_text != ""
    assert "PRATHAMESH" in result.combined_text


def test_clean_extracted_text_artifacts():
    """Verify artifact cleaning removes only null bytes, normalizes line breaks, and preserves all text, numbers, and punctuation."""
    raw = (
        "Invoice No: INV-001/2026   \r\n"
        "\x00Vendor: ABC Pvt. Ltd. | Tax ID: 27AABCU9603R1ZM  \r\n"
        "\n\n\n\n"
        "Total Amount: $15,000.50 (Due: 2026-09-30)  \n"
    )
    cleaned = PdfParser._clean_extracted_text(raw)

    # Obvious artifacts removed
    assert "\x00" not in cleaned
    assert "\r" not in cleaned
    assert "\n\n\n" not in cleaned

    # Exact numbers, punctuation, invoice values, and case preserved
    assert "Invoice No: INV-001/2026" in cleaned
    assert "Vendor: ABC Pvt. Ltd. | Tax ID: 27AABCU9603R1ZM" in cleaned
    assert "Total Amount: $15,000.50 (Due: 2026-09-30)" in cleaned


def test_pdf_parser_corrupted_pdf():
    """Verify corrupted / truncated PDFs return status CORRUPTED with safe message."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
        with open(tmp_path, "wb") as f:
            f.write(b"%PDF-1.4\n%corrupt truncated body\n<< /Type /Catalog >>\nstartxref\n9999\n%%EOF")

    try:
        result = parse_pdf(tmp_path)
        assert result.success is False
        assert result.status == "CORRUPTED"
        assert result.error == "Unable to read the PDF file."
        assert result.total_pages == 0
        # Verify no absolute paths leaked in error
        assert tmp_path not in (result.error or "")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_pdf_parser_multipage_extraction():
    """Verify text is extracted from EVERY page, boundaries are preserved, and page_number starts at 1."""
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
        with open(tmp_path, "wb") as f:
            writer.write(f)

    try:
        result = parse_pdf(tmp_path)
        assert result.success is True
        assert result.total_pages == 2
        assert len(result.pages) == 2

        # Page numbers start from 1, not 0
        assert result.pages[0].page_number == 1
        assert result.pages[1].page_number == 2

        # Check structure fields
        assert hasattr(result.pages[0], "character_count")
        assert hasattr(result.pages[0], "text")
        assert result.pages[0].character_count == 0
        assert result.pages[1].character_count == 0
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_pdf_parser_empty_pages_preserved():
    """Verify PDFs with mixed empty and text pages retain all pages without failing."""
    sample_pdf = Path(r"c:\Intelligent Document Processing(IDP)\backend\uploads\abb54f96-de5b-45aa-b24d-cf3503d247e2.pdf")
    if not sample_pdf.exists():
        return

    reader = pypdf.PdfReader(str(sample_pdf))
    writer = pypdf.PdfWriter()
    # Page 1 -> text
    writer.add_page(reader.pages[0])
    # Page 2 -> empty (no text)
    writer.add_blank_page(width=200, height=200)
    # Page 3 -> text
    writer.add_page(reader.pages[0])

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
        with open(tmp_path, "wb") as f:
            writer.write(f)

    try:
        result = parse_pdf(tmp_path)
        assert result.success is True
        assert result.page_count == 3
        assert len(result.pages) == 3

        # Page 1 has text
        assert result.pages[0].page_number == 1
        assert result.pages[0].character_count > 0
        assert result.pages[0].text != ""

        # Page 2 is empty: { "page_number": 2, "text": "", "character_count": 0 }
        assert result.pages[1].page_number == 2
        assert result.pages[1].text == ""
        assert result.pages[1].character_count == 0

        # Page 3 has text
        assert result.pages[2].page_number == 3
        assert result.pages[2].character_count > 0
        assert result.pages[2].text != ""
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_pdf_parser_accidental_metadata_detected_as_scanned():
    """Verify PDFs with only 3 empty pages or accidental isolated characters are classified as likely_scanned=True."""
    # Scenario A: 3 completely empty pages (Page 1: "", Page 2: "", Page 3: "")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
        with open(tmp_path, "wb") as f:
            writer.write(f)

    try:
        result = parse_pdf(tmp_path)
        assert result.success is True
        assert result.page_count == 3
        assert result.total_character_count == 0
        assert result.alphanumeric_char_count == 0
        assert result.pages_with_text == 0
        assert result.likely_scanned is True
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_pdf_parser_table_line_breaks_and_ordering():
    """Verify invoice table text preserves individual rows, line breaks, and reading order without flattening."""
    table_raw = (
        "Item Description                Qty    Rate       Amount   \r\n"
        "Cloud Hosting Server 16GB        2     150.00     300.00  \r\n"
        "PostgreSQL Database Support      1     250.00     250.00  \r\n"
        "SSL Certificate Multi-Domain     1      80.00      80.00  \r\n"
        "--------------------------------------------------------  \r\n"
        "Subtotal                                          630.00  \r\n"
        "Tax (18%)                                         113.40  \r\n"
        "Total Due                                        $743.40  \n"
    )
    cleaned = PdfParser._clean_extracted_text(table_raw)
    lines = cleaned.split("\n")

    # Verify 8 distinct rows preserved
    assert len(lines) == 8
    # Verify row order
    assert "Item Description" in lines[0]
    assert "Cloud Hosting Server 16GB" in lines[1]
    assert "PostgreSQL Database Support" in lines[2]
    assert "SSL Certificate Multi-Domain" in lines[3]
    assert "Total Due" in lines[7] and "$743.40" in lines[7]


def test_pdf_parser_multipage_invoice_workflow():
    """Verify multi-page invoice extraction across pages (Page 1: Vendor+Invoice, Page 2: Items, Page 3: Tax+Total)."""
    def _make_pdf(pages_text):
        objects = []
        objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        kids = " ".join(f"{3 + i} 0 R" for i in range(len(pages_text)))
        objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages_text)} >>".encode())
        content_start_idx = 3 + len(pages_text)
        font_idx = content_start_idx + len(pages_text)
        for i in range(len(pages_text)):
            c_idx = content_start_idx + i
            objects.append(
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {c_idx} 0 R /Resources << /Font << /F1 {font_idx} 0 R >> >> >>".encode()
            )
        for text in pages_text:
            stream_content = f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET\n".encode()
            stream_obj = f"<< /Length {len(stream_content)} >>\nstream\n".encode() + stream_content + b"endstream"
            objects.append(stream_obj)
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

        out = [b"%PDF-1.4\n"]
        offsets = []
        for i, obj in enumerate(objects):
            offsets.append(sum(len(chunk) for chunk in out))
            out.append(f"{i + 1} 0 obj\n".encode() + obj + b"\nendobj\n")
        
        xref_offset = sum(len(chunk) for chunk in out)
        out.append(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
        for off in offsets:
            out.append(f"{off:010d} 00000 n \n".encode())
        out.append(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode())
        return b"".join(out)

    pdf_bytes = _make_pdf([
        "Vendor: Acme Logistics Pvt Ltd - Invoice Number: INV-2026-001",
        "Item 1: Dedicated Cloud Server 32GB - Rate: 500.00 Qty: 2",
        "Subtotal: 1000.00 - Tax: 180.00 - Total Due: 1180.00"
    ])

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
        with open(tmp_path, "wb") as f:
            f.write(pdf_bytes)

    try:
        result = parse_pdf(tmp_path)
        assert result.success is True
        assert result.status == "TEXT_EXTRACTED"
        assert result.page_count == 3
        assert len(result.pages) == 3

        # Page 1: Vendor + Invoice Number
        assert result.pages[0].page_number == 1
        assert "Vendor: Acme Logistics" in result.pages[0].text
        assert "Invoice Number: INV-2026-001" in result.pages[0].text

        # Page 2: Items
        assert result.pages[1].page_number == 2
        assert "Item 1: Dedicated Cloud Server" in result.pages[1].text
        assert "Qty: 2" in result.pages[1].text

        # Page 3: Tax + Total
        assert result.pages[2].page_number == 3
        assert "Subtotal: 1000.00" in result.pages[2].text
        assert "Tax: 180.00" in result.pages[2].text
        assert "Total Due: 1180.00" in result.pages[2].text

        # Combined text preserves all 3 pages with double newlines
        assert "Vendor: Acme Logistics" in result.combined_text
        assert "Item 1: Dedicated Cloud Server" in result.combined_text
        assert "Total Due: 1180.00" in result.combined_text
        assert result.likely_scanned is False
        assert result.has_extractable_text is True
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_pdf_parser_mixed_pages_images_and_text():
    """Verify mixed documents (Page 1: text, Page 2: scanned image/blank, Page 3: text) do NOT fail or falsely classify as scanned."""
    sample_pdf = Path(r"c:\Intelligent Document Processing(IDP)\backend\uploads\abb54f96-de5b-45aa-b24d-cf3503d247e2.pdf")
    if not sample_pdf.exists():
        return

    reader = pypdf.PdfReader(str(sample_pdf))
    writer = pypdf.PdfWriter()
    # Page 1: Digital text
    writer.add_page(reader.pages[0])
    # Page 2: Scanned image placeholder / blank (no digital text)
    writer.add_blank_page(width=200, height=200)
    # Page 3: Digital text
    writer.add_page(reader.pages[0])

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
        with open(tmp_path, "wb") as f:
            writer.write(f)

    try:
        result = parse_pdf(tmp_path)
        assert result.success is True
        assert result.page_count == 3
        assert result.pages_with_text == 2
        assert result.pages_without_text == 1
        assert result.pages[0].has_text is True
        assert result.pages[1].has_text is False
        assert result.pages[2].has_text is True
        # Do not classify the whole document as scanned just because Page 2 has no text!
        assert result.has_extractable_text is True
        assert result.likely_scanned is False
        assert result.status == "TEXT_EXTRACTED"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_pdf_parser_page_level_error_isolation():
    """Verify that a failure on a single page does not abort remaining pages and records page-level error."""
    sample_pdf = Path(r"c:\Intelligent Document Processing(IDP)\backend\uploads\abb54f96-de5b-45aa-b24d-cf3503d247e2.pdf")
    if not sample_pdf.exists():
        return

    from unittest.mock import patch
    original_extract = pypdf._page.PageObject.extract_text

    def mock_extract(self, *args, **kwargs):
        # Simulate a crash only on the 2nd page in reader
        if getattr(self, "_mock_fail", False):
            raise RuntimeError("Corrupt font descriptor in page stream")
        return original_extract(self, *args, **kwargs)

    reader = pypdf.PdfReader(str(sample_pdf))
    writer = pypdf.PdfWriter()
    writer.add_page(reader.pages[0])
    writer.add_page(reader.pages[0])
    writer.add_page(reader.pages[0])

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
        with open(tmp_path, "wb") as f:
            writer.write(f)

    # Patch extract_text to fail only for page 2
    original_pypdf_reader = pypdf.PdfReader

    class MockPdfReader(pypdf.PdfReader):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if len(self.pages) >= 2:
                self.pages[1]._mock_fail = True

    with patch("pypdf.PdfReader", MockPdfReader):
        with patch.object(pypdf._page.PageObject, "extract_text", mock_extract):
            try:
                result = parse_pdf(tmp_path)
                assert result.success is True
                assert result.page_count == 3
                # Page 1 succeeded
                assert result.pages[0].has_text is True
                assert result.pages[0].error is None
                # Page 2 recorded isolated error without failing document
                assert result.pages[1].has_text is False
                assert result.pages[1].error == "Text extraction failed for this page."
                # Page 3 continued safely
                assert result.pages[2].has_text is True
                assert result.pages[2].error is None
                # Check top-level errors list
                assert len(result.errors) == 1
                assert "Page 2: Text extraction failed." in result.errors[0]
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)


if __name__ == "__main__":
    print("Running PDF Parser Unit Tests...")
    test_pdf_parser_non_existent_file()
    print("[PASS] test_pdf_parser_non_existent_file")
    test_pdf_parser_zero_byte_file()
    print("[PASS] test_pdf_parser_zero_byte_file")
    test_pdf_parser_encrypted_pdf()
    print("[PASS] test_pdf_parser_encrypted_pdf")
    test_pdf_parser_corrupted_pdf()
    print("[PASS] test_pdf_parser_corrupted_pdf")
    test_pdf_parser_blank_or_scanned_pdf()
    print("[PASS] test_pdf_parser_blank_or_scanned_pdf")
    test_pdf_parser_digital_pdf_text_extraction()
    print("[PASS] test_pdf_parser_digital_pdf_text_extraction")
    test_pdf_parser_multipage_extraction()
    print("[PASS] test_pdf_parser_multipage_extraction")
    test_pdf_parser_empty_pages_preserved()
    print("[PASS] test_pdf_parser_empty_pages_preserved")
    test_pdf_parser_accidental_metadata_detected_as_scanned()
    print("[PASS] test_pdf_parser_accidental_metadata_detected_as_scanned")
    test_clean_extracted_text_artifacts()
    print("[PASS] test_clean_extracted_text_artifacts")
    test_pdf_parser_table_line_breaks_and_ordering()
    print("[PASS] test_pdf_parser_table_line_breaks_and_ordering")
    test_pdf_parser_multipage_invoice_workflow()
    print("[PASS] test_pdf_parser_multipage_invoice_workflow")
    test_pdf_parser_mixed_pages_images_and_text()
    print("[PASS] test_pdf_parser_mixed_pages_images_and_text")
    test_pdf_parser_page_level_error_isolation()
    print("[PASS] test_pdf_parser_page_level_error_isolation")
    print("\nALL PDF PARSER TESTS PASSED SUCCESSFULLY!")

