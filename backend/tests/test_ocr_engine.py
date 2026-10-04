import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import MagicMock, patch

# Ensure backend root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.schemas.ocr import OCRBoundingBox, OCRPageData, OCRResult, OCRWordData
from app.services.ocr_engine import (
    OcrEngine,
    OcrEngineError,
    ocr_engine,
    perform_ocr,
    preprocess_image,
    process_document,
    process_image,
    process_pdf,
)


def create_sample_text_image(text: str = "INVOICE #INV-2026-001\nTOTAL: $500.00") -> Image.Image:
    """Helper to generate a clean synthetic PIL image with text."""
    img = Image.new("RGB", (400, 150), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 30), text, fill=(0, 0, 0))
    return img


def test_ocr_non_existent_file():
    """Verify non-existent files are safely rejected without throwing exceptions."""
    res = process_document("non_existent_file.png")
    assert res.success is False
    assert res.status == "FAILED"
    assert "not exist" in (res.error or "").lower()


def test_ocr_zero_byte_file():
    """Verify 0-byte files return a clean failure status."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        res = process_image(tmp_path)
        assert res.success is False
        assert res.status == "FAILED"
        assert "0 bytes" in (res.error or "").lower()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_ocr_unsupported_format():
    """Verify unsupported file types return UNSUPPORTED_FORMAT."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
        tmp.write(b"Hello world")
        tmp_path = tmp.name

    try:
        res = process_document(tmp_path)
        assert res.success is False
        assert res.status == "UNSUPPORTED_FORMAT"
        assert "unsupported file format" in (res.error or "").lower()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_ocr_empty_image_no_text_detected():
    """Verify that an image with no readable text returns success=True with status NO_TEXT_DETECTED."""
    # Blank white image with no text
    blank_img = Image.new("RGB", (300, 100), color=(255, 255, 255))
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
        blank_img.save(tmp_path)

    empty_tesseract_dict = {
        "block_num": [1],
        "par_num": [1],
        "line_num": [1],
        "left": [0],
        "top": [0],
        "width": [0],
        "height": [0],
        "conf": [-1.0],  # No words recognized
        "text": [""],
    }

    try:
        with patch.object(OcrEngine, "is_tesseract_available", return_value=True):
            with patch("pytesseract.image_to_data", return_value=empty_tesseract_dict):
                res = perform_ocr(tmp_path)

                assert res.success is True
                assert res.status == "NO_TEXT_DETECTED"
                assert res.file_type == "IMAGE"
                assert res.combined_text == ""
                assert res.total_words == 0
                assert res.total_word_count == 0
                assert res.pages[0].has_text is False
                assert res.pages[0].error is None
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_opencv_preprocessing_pipeline():
    """Verify OpenCV preprocessing handles PIL Images, numpy arrays, and outputs binarized image."""
    pil_img = create_sample_text_image("Test Preprocessing")
    binary_img = preprocess_image(pil_img)

    # Output must be a 2D numpy array (grayscale/binary)
    assert isinstance(binary_img, np.ndarray)
    assert len(binary_img.shape) == 2
    assert binary_img.shape[0] == pil_img.size[1]  # Height
    assert binary_img.shape[1] == pil_img.size[0]  # Width

    # Only values 0 and 255 should be present after Otsu thresholding
    unique_vals = set(np.unique(binary_img))
    assert unique_vals.issubset({0, 255})

    # Test with numpy array input directly
    bgr_img = np.zeros((100, 200, 3), dtype=np.uint8)
    bgr_img[:, :] = (200, 200, 200)
    binary_from_np = preprocess_image(bgr_img)
    assert isinstance(binary_from_np, np.ndarray)
    assert len(binary_from_np.shape) == 2


def test_tesseract_not_found_handling():
    """Verify that if Tesseract executable is missing, engine returns clean TESSERACT_NOT_FOUND."""
    pil_img = create_sample_text_image("Sample")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
        pil_img.save(tmp_path)

    try:
        with patch.object(OcrEngine, "is_tesseract_available", return_value=False):
            res = process_image(tmp_path)
            assert res.success is False
            assert res.status == "TESSERACT_NOT_FOUND"
            assert "Tesseract OCR engine is not installed" in (res.error or "")
            assert res.page_count == 0
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_poppler_not_found_handling_for_pdf():
    """Verify that if Poppler is missing, engine returns clean POPPLER_NOT_FOUND."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(b"%PDF-1.4 sample fake content")
        tmp_path = tmp.name

    try:
        with patch.object(OcrEngine, "is_tesseract_available", return_value=True):
            with patch("pdf2image.convert_from_path", side_effect=Exception("Unable to get page count. Is poppler installed?")):
                with patch.object(OcrEngine, "is_poppler_available", return_value=False):
                    res = process_pdf(tmp_path)
                    assert res.success is False
                    assert res.status == "POPPLER_NOT_FOUND"
                    assert "poppler" in (res.error or "").lower()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_word_level_extraction_and_bounding_boxes():
    """Verify word-level parsing, line grouping, bounding boxes, and confidence score calculation."""
    mock_tesseract_dict = {
        "level": [5, 5, 5, 5, 5],
        "page_num": [1, 1, 1, 1, 1],
        "block_num": [1, 1, 1, 2, 2],
        "par_num": [1, 1, 1, 1, 1],
        "line_num": [1, 1, 1, 1, 1],
        "word_num": [1, 2, 3, 1, 2],
        "left": [10, 50, 100, 10, 60],
        "top": [20, 20, 20, 60, 60],
        "width": [35, 45, 80, 40, 70],
        "height": [15, 15, 15, 18, 18],
        "conf": [95.5, 92.0, -1.0, 88.0, 96.2],  # Note the -1.0 which should be filtered
        "text": ["INVOICE", "NUMBER:", "   ", "TOTAL", "$1500.00"],
    }

    pil_img = create_sample_text_image("Test")

    with patch("pytesseract.image_to_data", return_value=mock_tesseract_dict) as mock_img_to_data:
        page_res = OcrEngine.extract_page_ocr(pil_img, page_number=1)

        # Verify config uses --psm 6 by default
        assert mock_img_to_data.call_args[1]["config"] == "--psm 6"

        assert page_res.page_number == 1
        assert page_res.has_text is True
        assert page_res.word_count == 4  # Blank/-1 conf filtered out
        assert len(page_res.words) == 4

        # Raw text captured for page
        assert page_res.raw_text != ""
        assert "INVOICE NUMBER:" in page_res.raw_text
        assert "TOTAL $1500.00" in page_res.raw_text

        # Word 1
        w1 = page_res.words[0]
        assert w1.text == "INVOICE"
        assert w1.confidence == 95.5
        assert w1.bounding_box.left == 10
        assert w1.bounding_box.top == 20
        assert w1.bounding_box.width == 35
        assert w1.bounding_box.height == 15
        assert w1.bounding_box.x2 == 45
        assert w1.bounding_box.y2 == 35
        assert w1.block_num == 1
        assert w1.paragraph_num == 1
        assert w1.line_num == 1
        assert w1.word_num == 1

        # Word 4: TOTAL $1500.00
        w4 = page_res.words[3]
        assert w4.text == "$1500.00"
        assert w4.confidence == 96.2
        assert w4.block_num == 2
        assert w4.word_num == 2

        # Average confidence: (95.5 + 92.0 + 88.0 + 96.2) / 4 = 92.925 -> 92.93
        assert round(page_res.average_confidence, 1) == 92.9

        # Text reconstructed line by line
        assert "INVOICE NUMBER:" in page_res.text
        assert "TOTAL $1500.00" in page_res.text


def test_process_image_success_workflow():
    """Verify full end-to-end workflow for an image file (.png)."""
    pil_img = create_sample_text_image("Invoice #001")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
        pil_img.save(tmp_path)

    mock_tesseract_dict = {
        "block_num": [1, 1],
        "par_num": [1, 1],
        "line_num": [1, 1],
        "left": [20, 80],
        "top": [30, 30],
        "width": [50, 40],
        "height": [15, 15],
        "conf": [96.0, 94.0],
        "text": ["Invoice", "#001"],
    }

    try:
        with patch.object(OcrEngine, "is_tesseract_available", return_value=True):
            with patch("pytesseract.image_to_data", return_value=mock_tesseract_dict):
                result = process_image(tmp_path)

                assert result.success is True
                assert result.status == "OCR_COMPLETED"
                assert result.file_type == "IMAGE"
                assert result.page_count == 1
                assert len(result.pages) == 1
                assert result.total_words == 2
                assert result.total_word_count == 2
                assert result.combined_text == "Invoice #001"
                assert result.average_confidence == 95.0
                assert result.metadata["filename"] == Path(tmp_path).name
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_process_scanned_pdf_multipage_workflow():
    """Verify multi-page scanned PDF rendering and fault isolation across pages."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(b"%PDF-1.4 mock pdf content")
        tmp_path = tmp.name

    page1_img = create_sample_text_image("Page 1 Vendor Information")
    page2_img = create_sample_text_image("Page 2 Total Amount")

    mock_dict_p1 = {
        "block_num": [1, 1],
        "par_num": [1, 1],
        "line_num": [1, 1],
        "left": [10, 50],
        "top": [10, 10],
        "width": [30, 40],
        "height": [12, 12],
        "conf": [90.0, 92.0],
        "text": ["Vendor:", "AcmeCorp"],
    }

    mock_dict_p2 = {
        "block_num": [1, 1],
        "par_num": [1, 1],
        "line_num": [1, 1],
        "left": [10, 50],
        "top": [10, 10],
        "width": [30, 40],
        "height": [12, 12],
        "conf": [88.0, 94.0],
        "text": ["Total:", "$950.00"],
    }

    def mock_extract_ocr(img, page_number=1, psm=None):
        if page_number == 1:
            return OcrEngine.extract_page_ocr(img, page_number=1, psm=psm)
        elif page_number == 2:
            return OcrEngine.extract_page_ocr(img, page_number=2, psm=psm)

    try:
        with patch.object(OcrEngine, "is_tesseract_available", return_value=True):
            with patch("pdf2image.convert_from_path", return_value=[page1_img, page2_img]):
                with patch("pytesseract.image_to_data", side_effect=[mock_dict_p1, mock_dict_p2]):
                    res = process_pdf(tmp_path)

                    assert res.success is True
                    assert res.status == "OCR_COMPLETED"
                    assert res.file_type == "PDF"
                    assert res.page_count == 2
                    assert len(res.pages) == 2

                    # Page 1
                    assert res.pages[0].page_number == 1
                    assert "Vendor: AcmeCorp" in res.pages[0].text
                    assert res.pages[0].average_confidence == 91.0

                    # Page 2
                    assert res.pages[1].page_number == 2
                    assert "Total: $950.00" in res.pages[1].text
                    assert res.pages[1].average_confidence == 91.0

                    # Combined document text contains both pages separated by double newlines
                    assert "Vendor: AcmeCorp" in res.combined_text
                    assert "Total: $950.00" in res.combined_text
                    assert res.total_words == 4
                    assert res.total_word_count == 4
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_process_scanned_pdf_page_level_error_isolation():
    """Verify that an extraction crash on one page does not fail the entire PDF."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(b"%PDF-1.4 mock pdf content")
        tmp_path = tmp.name

    p1_img = create_sample_text_image("Page 1")
    p2_img = create_sample_text_image("Page 2")

    mock_dict_p1 = {
        "block_num": [1],
        "par_num": [1],
        "line_num": [1],
        "left": [10],
        "top": [10],
        "width": [40],
        "height": [12],
        "conf": [95.0],
        "text": ["PageOne"],
    }

    try:
        with patch.object(OcrEngine, "is_tesseract_available", return_value=True):
            with patch("pdf2image.convert_from_path", return_value=[p1_img, p2_img]):
                # Page 1 returns valid dict, Page 2 throws an exception
                with patch("pytesseract.image_to_data", side_effect=[mock_dict_p1, RuntimeError("Corrupt image buffer")]):
                    res = process_pdf(tmp_path)

                    # Partial success
                    assert res.success is True
                    assert res.status == "OCR_PARTIAL"
                    assert res.file_type == "PDF"
                    assert res.page_count == 2

                    # Page 1 succeeded
                    assert res.pages[0].has_text is True
                    assert res.pages[0].text == "PageOne"
                    assert res.pages[0].error is None

                    # Page 2 recorded isolated error
                    assert res.pages[1].has_text is False
                    assert res.pages[1].error == "OCR failed for this page."

                    # Errors list has page 2 error
                    assert len(res.errors) == 1
                    assert "Page 2" in res.errors[0]
                    assert res.total_word_count == 1
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_perform_ocr_universal_entrypoint():
    """Verify perform_ocr works as the universal pipeline interface."""
    # 1. Unsupported file format
    res_unsupported = perform_ocr("document.docx")
    assert res_unsupported.success is False
    assert res_unsupported.status == "UNSUPPORTED_FORMAT"

    # 2. Image dispatch
    pil_img = create_sample_text_image("Universal Interface")
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = tmp.name
        pil_img.save(tmp_path)

    try:
        with patch.object(OcrEngine, "is_tesseract_available", return_value=False):
            res_img = perform_ocr(tmp_path)
            assert res_img.file_type == "IMAGE"
            assert res_img.status == "TESSERACT_NOT_FOUND"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_tesseract_cmd_explicit_valid_path():
    """Verify explicit valid path in TESSERACT_CMD is respected."""
    with tempfile.NamedTemporaryFile(suffix=".exe" if os.name == "nt" else "", delete=False) as tmp:
        fake_tesseract = tmp.name

    try:
        with patch("app.core.config.settings.TESSERACT_CMD", fake_tesseract):
            resolved = OcrEngine.resolve_tesseract_cmd()
            assert resolved == str(Path(fake_tesseract).resolve()) or resolved == fake_tesseract
    finally:
        if os.path.exists(fake_tesseract):
            os.remove(fake_tesseract)


def test_tesseract_cmd_empty_uses_system_path():
    """Verify empty TESSERACT_CMD falls back to system PATH."""
    with patch("app.core.config.settings.TESSERACT_CMD", None):
        with patch("shutil.which", return_value="C:\\system_path\\tesseract.exe"):
            resolved = OcrEngine.resolve_tesseract_cmd()
            assert resolved == "C:\\system_path\\tesseract.exe"


def test_tesseract_cmd_invalid_falls_back_to_system_path():
    """Verify non-existent TESSERACT_CMD logs warning and falls back to system PATH."""
    with patch("app.core.config.settings.TESSERACT_CMD", "C:\\non_existent_folder\\tesseract.exe"):
        with patch("shutil.which", return_value="C:\\system_path\\tesseract.exe"):
            resolved = OcrEngine.resolve_tesseract_cmd()
            assert resolved == "C:\\system_path\\tesseract.exe"


def test_real_tesseract_detection_and_ocr():
    """Verify that installed Tesseract is detected and successfully OCRs a test image."""
    is_avail = OcrEngine.is_tesseract_available()
    assert is_avail is True, "Tesseract should be detected on the system."

    # Create synthetic invoice text image scaled for OCR readability
    img = Image.new("RGB", (600, 200), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((30, 50), "INVOICE 12345", fill=(0, 0, 0))
    scaled_img = img.resize((1200, 400), Image.Resampling.NEAREST)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        img_path = tmp.name
        scaled_img.save(img_path)

    try:
        res = process_image(img_path)
        assert res.success is True
        assert res.status in ("OCR_COMPLETED", "OCR_PARTIAL")
        assert res.total_words > 0
        assert "INVOICE" in res.combined_text.upper()
    finally:
        if os.path.exists(img_path):
            os.remove(img_path)


if __name__ == "__main__":
    print("Running OCR Engine Unit Tests...")
    test_perform_ocr_universal_entrypoint()
    print("[PASS] test_perform_ocr_universal_entrypoint")
    test_ocr_non_existent_file()
    print("[PASS] test_ocr_non_existent_file")
    test_ocr_zero_byte_file()
    print("[PASS] test_ocr_zero_byte_file")
    test_ocr_unsupported_format()
    print("[PASS] test_ocr_unsupported_format")
    test_ocr_empty_image_no_text_detected()
    print("[PASS] test_ocr_empty_image_no_text_detected")
    test_opencv_preprocessing_pipeline()
    print("[PASS] test_opencv_preprocessing_pipeline")
    test_tesseract_not_found_handling()
    print("[PASS] test_tesseract_not_found_handling")
    test_poppler_not_found_handling_for_pdf()
    print("[PASS] test_poppler_not_found_handling_for_pdf")
    test_word_level_extraction_and_bounding_boxes()
    print("[PASS] test_word_level_extraction_and_bounding_boxes")
    test_process_image_success_workflow()
    print("[PASS] test_process_image_success_workflow")
    test_process_scanned_pdf_multipage_workflow()
    print("[PASS] test_process_scanned_pdf_multipage_workflow")
    test_process_scanned_pdf_page_level_error_isolation()
    print("[PASS] test_process_scanned_pdf_page_level_error_isolation")
    test_tesseract_cmd_explicit_valid_path()
    print("[PASS] test_tesseract_cmd_explicit_valid_path")
    test_tesseract_cmd_empty_uses_system_path()
    print("[PASS] test_tesseract_cmd_empty_uses_system_path")
    test_tesseract_cmd_invalid_falls_back_to_system_path()
    print("[PASS] test_tesseract_cmd_invalid_falls_back_to_system_path")
    test_real_tesseract_detection_and_ocr()
    print("[PASS] test_real_tesseract_detection_and_ocr")
    print("\nALL OCR ENGINE TESTS PASSED SUCCESSFULLY!")
