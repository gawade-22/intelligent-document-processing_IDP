import logging
import os
from pathlib import Path
import re
import shutil
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
from PIL import Image
import pytesseract
from pytesseract import Output

from app.core.config import settings
from app.schemas.ocr import OCRBoundingBox, OCRPageData, OCRResult, OCRWordData

logger = logging.getLogger(__name__)

# Supported file extensions
SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
SUPPORTED_PDF_EXTENSIONS = {".pdf"}
ALL_SUPPORTED_EXTENSIONS = SUPPORTED_IMAGE_EXTENSIONS | SUPPORTED_PDF_EXTENSIONS

# Configurable Tesseract Page Segmentation Mode (PSM)
# PSM 6 = Assume a single uniform block of text (optimal for structured forms and invoices)
# PSM 3 = Fully automatic page segmentation (general multi-column layout)
DEFAULT_OCR_PSM_MODE: int = getattr(settings, "OCR_PSM_MODE", 6)


class OcrEngineError(Exception):
    """Custom exception raised for unrecoverable OCR pipeline failures."""
    pass


class OcrEngine:
    """
    Production-grade OCR Engine supporting image files (.png, .jpg, .jpeg)
    and scanned multi-page PDFs.

    Processing Pipeline:
    1. Safe File & Dependency Validation:
       - Verifies path, permissions, and file integrity.
       - Validates Tesseract OCR executable and Poppler (for PDFs).
    2. Document Loading & Page Rendering:
       - Single image: loaded directly into PIL/OpenCV.
       - Multi-page scanned PDF: converted to PIL images via pdf2image.
    3. OpenCV Preprocessing:
       - Grayscale conversion.
       - Denoising with Gaussian blur.
       - Binarization via Otsu's thresholding.
    4. Tesseract OCR Execution:
       - Captures word-level text, bounding boxes (left, top, width, height), and confidence scores.
    5. Aggregation & Metrics:
       - Reconstructs text preserving layout lines.
       - Calculates page-level and document-level confidence metrics.
    6. Fault Isolation:
       - Failures on individual pages in a PDF do not crash the document processing.
    """

    def __init__(self) -> None:
        self._configure_tesseract()

    def _configure_tesseract(self) -> None:
        """
        Configures Tesseract executable path if specified in environment/settings.
        Defaults to system PATH if TESSERACT_CMD is not set.
        """
        tesseract_cmd = settings.TESSERACT_CMD or os.getenv("TESSERACT_CMD")
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = str(tesseract_cmd).strip()
            logger.info(f"Tesseract executable configured from environment: {tesseract_cmd}")

    @classmethod
    def is_tesseract_available(cls) -> bool:
        """
        Checks whether the Tesseract OCR engine is available and executable.
        """
        configured_cmd = pytesseract.pytesseract.tesseract_cmd
        if configured_cmd and configured_cmd != "tesseract":
            return Path(configured_cmd).exists()
        return shutil.which("tesseract") is not None

    @classmethod
    def is_poppler_available(cls) -> bool:
        """
        Checks whether Poppler (pdftoppm) is available for pdf2image on the system.
        """
        poppler_path = settings.POPPLER_PATH or os.getenv("POPPLER_PATH")
        if poppler_path:
            pdftoppm = Path(poppler_path) / ("pdftoppm.exe" if os.name == "nt" else "pdftoppm")
            if pdftoppm.exists():
                return True
        return shutil.which("pdftoppm") is not None

    # -------------------------------------------------------------------------
    # Image Preprocessing (OpenCV)
    # -------------------------------------------------------------------------

    @classmethod
    def preprocess_image(
        cls,
        image_input: Union[np.ndarray, Image.Image, Path, str],
    ) -> np.ndarray:
        """
        Conservative OpenCV image preprocessing pipeline tailored for invoice OCR:
        
        Pipeline Steps:
        1. Grayscale Conversion:
           - Invoices do not use color semantically for character identification.
           - Reduces 3 color channels to 1 intensity channel, removing chromatic artifacts.
        2. Noise Reduction:
           - Applies a gentle 3x3 Gaussian blur.
           - Suppresses scanner grain and background noise without blurring fine character
             edges or destroying small punctuation marks (e.g. decimals in currency amounts).
        3. Contrast Enhancement & Binarization (Otsu's Thresholding):
           - Automatically computes the optimal global threshold that minimizes intraclass variance.
           - Produces a clean, high-contrast black-on-white image that matches Tesseract's
             internal Leptonica expectations.
        4. Conservative Morphological Restraint:
           - Deliberately omits aggressive erosion or dilation, which can bridge closely spaced
             table columns or erase critical invoice symbols (such as '.', ',', '1' vs 'l').

        Args:
            image_input: NumPy array (BGR/RGB), PIL Image, or file path.

        Returns:
            np.ndarray: Cleaned binary image ready for Tesseract OCR.
        """
        # Load / convert to numpy array
        if isinstance(image_input, (str, Path)):
            img = cv2.imread(str(image_input))
            if img is None:
                raise OcrEngineError(f"OpenCV could not read image from path: {image_input}")
        elif isinstance(image_input, Image.Image):
            img = cv2.cvtColor(np.array(image_input), cv2.COLOR_RGB2BGR)
        elif isinstance(image_input, np.ndarray):
            img = image_input.copy()
        else:
            raise OcrEngineError(f"Unsupported image input type: {type(image_input)}")

        # 1. Grayscale conversion
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img

        # 2. Noise reduction with a gentle 3x3 Gaussian kernel
        denoised = cv2.GaussianBlur(gray, (3, 3), 0)

        # 3. Otsu's thresholding for sharp foreground/background separation
        _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        return binary

    # -------------------------------------------------------------------------
    # Core OCR Extraction (Per Page / Image)
    # -------------------------------------------------------------------------

    @classmethod
    def extract_page_ocr(
        cls,
        image: Union[np.ndarray, Image.Image],
        page_number: int = 1,
        psm: Optional[int] = None,
    ) -> OCRPageData:
        """
        Preprocesses an image and runs Tesseract OCR to extract word-level
        text, bounding boxes, and confidence scores.

        Args:
            image: Image object or numpy array for the page.
            page_number: 1-indexed page number.
            psm: Page segmentation mode (defaults to DEFAULT_OCR_PSM_MODE / 6).

        Returns:
            OCRPageData: Per-page structured OCR result.
        """
        effective_psm = psm if psm is not None else DEFAULT_OCR_PSM_MODE
        tess_config = f"--psm {effective_psm}"
        try:
            # Preprocess image with OpenCV (Original -> Grayscale -> Denoise -> Otsu Threshold)
            preprocessed_img = cls.preprocess_image(image)

            # Run Tesseract with structured dictionary output for word-level data
            ocr_data = pytesseract.image_to_data(
                preprocessed_img,
                output_type=Output.DICT,
                config=tess_config,
            )

            # Capture direct raw string output via image_to_string
            try:
                raw_ocr_string = pytesseract.image_to_string(
                    preprocessed_img,
                    config=tess_config,
                ).strip()
            except Exception:
                raw_ocr_string = ""
        except Exception as exc:
            logger.warning(f"OCR execution failed on page {page_number}: {exc}", exc_info=True)
            return OCRPageData(
                page_number=page_number,
                raw_text="",
                text="",
                words=[],
                character_count=0,
                word_count=0,
                average_confidence=0.0,
                has_text=False,
                error="OCR failed for this page.",
            )

        words_list: List[OCRWordData] = []
        confidences: List[float] = []

        # Data structure returned by pytesseract.image_to_data:
        # dict with keys: 'level', 'page_num', 'block_num', 'par_num', 'line_num',
        #                 'word_num', 'left', 'top', 'width', 'height', 'conf', 'text'
        total_items = len(ocr_data.get("text", []))

        # Reconstruct lines using (block_num, par_num, line_num)
        lines_dict: Dict[Tuple[int, int, int], List[str]] = {}

        for i in range(total_items):
            raw_text = str(ocr_data["text"][i]).strip()
            conf_val = float(ocr_data["conf"][i])

            # -----------------------------------------------------------------
            # Tesseract Confidence & Bounding Box Preservation Rules:
            # 1. Direct Confidence: Use Tesseract's `conf` value directly as the
            #    raw confidence score (0.0 to 100.0). Never invent artificial scores
            #    such as (detected_words / total_words).
            # 2. Safe Hierarchy Filtering: Tesseract returns `conf = -1` for non-word
            #    structural nodes (page, block, paragraph, or empty line levels).
            #    We safely filter out any entry where `conf < 0` or text is blank,
            #    ensuring only valid recognized words enter `words_list`.
            # 3. Exact Pixel Coordinates: `left`, `top`, `width`, `height` are preserved
            #    strictly in pixel units relative to the processed page image.
            # -----------------------------------------------------------------
            if not raw_text or conf_val < 0:
                continue

            left = int(ocr_data["left"][i])
            top = int(ocr_data["top"][i])
            width = int(ocr_data["width"][i])
            height = int(ocr_data["height"][i])
            block_num = int(ocr_data["block_num"][i])
            par_num = int(ocr_data.get("par_num", [1])[i]) if "par_num" in ocr_data else 1
            line_num = int(ocr_data.get("line_num", [1])[i]) if "line_num" in ocr_data else 1
            word_num = int(ocr_data.get("word_num", [1])[i]) if "word_num" in ocr_data else 1

            bbox = OCRBoundingBox(
                left=left,
                top=top,
                width=width,
                height=height,
                x2=left + width,
                y2=top + height,
            )

            word_obj = OCRWordData(
                text=raw_text,
                confidence=round(conf_val, 2),
                bounding_box=bbox,
                bbox=bbox,
                block_num=block_num,
                paragraph_num=par_num,
                line_num=line_num,
                word_num=word_num,
            )
            words_list.append(word_obj)
            confidences.append(conf_val)

            line_key = (block_num, par_num, line_num)
            if line_key not in lines_dict:
                lines_dict[line_key] = []
            lines_dict[line_key].append(raw_text)

        # Reconstruct page text preserving lines
        reconstructed_lines = [" ".join(words) for words in lines_dict.values()]
        page_text = "\n".join(reconstructed_lines).strip()
        final_raw_text = raw_ocr_string if raw_ocr_string else page_text

        avg_confidence = round(float(np.mean(confidences)), 2) if confidences else 0.0
        char_count = len(final_raw_text)
        word_count = len(words_list)
        has_text = bool(word_count > 0 and char_count > 0)

        return OCRPageData(
            page_number=page_number,
            raw_text=final_raw_text,
            text=final_raw_text,
            words=words_list,
            character_count=char_count,
            word_count=word_count,
            average_confidence=avg_confidence,
            has_text=has_text,
            error=None,
        )

    # -------------------------------------------------------------------------
    # Image File OCR Processing (.png, .jpg, .jpeg)
    # -------------------------------------------------------------------------

    @classmethod
    def process_image(
        cls,
        file_path: Union[Path, str],
        psm: Optional[int] = None,
    ) -> OCRResult:
        """
        Executes OCR on an image file (.png, .jpg, .jpeg).

        Args:
            file_path: Path to the image file.
            psm: Page segmentation mode (defaults to settings.OCR_PSM_MODE or 6).

        Returns:
            OCRResult: Structured document OCR result with bounding boxes and metrics.
        """
        try:
            path = cls._validate_file_path(file_path, expected_extensions=SUPPORTED_IMAGE_EXTENSIONS)
        except OcrEngineError as val_err:
            logger.warning(f"OCR path validation error: {val_err}")
            return OCRResult(
                success=False,
                status="FAILED",
                error=str(val_err),
                file_type="IMAGE",
                page_count=0,
                pages=[],
            )

        if not cls.is_tesseract_available():
            return cls._tesseract_not_found_result(file_type="IMAGE")

        try:
            with Image.open(path) as raw_img:
                pil_image = raw_img.copy()

            # Normalize orientation if EXIF tag exists
            try:
                from PIL import ImageOps
                pil_image = ImageOps.exif_transpose(pil_image)
            except Exception:
                pass

            page_data = cls.extract_page_ocr(pil_image, page_number=1, psm=psm)
            status = "OCR_COMPLETED" if page_data.has_text else "NO_TEXT_DETECTED"

            return OCRResult(
                success=True,
                status=status,
                error=None,
                errors=[page_data.error] if page_data.error else [],
                file_type="IMAGE",
                page_count=1,
                pages=[page_data],
                combined_text=page_data.text,
                total_characters=page_data.character_count,
                total_words=page_data.word_count,
                total_word_count=page_data.word_count,
                average_confidence=page_data.average_confidence,
                metadata={
                    "filename": path.name,
                    "image_size": list(pil_image.size),  # [width, height]
                    "format": pil_image.format,
                },
            )
        except Exception as exc:
            logger.error(f"Failed to process image '{path.name}': {exc}", exc_info=True)
            return OCRResult(
                success=False,
                status="OCR_FAILED",
                error="Unable to read or process the image file.",
                file_type="IMAGE",
                page_count=0,
                pages=[],
            )

    # -------------------------------------------------------------------------
    # Scanned PDF OCR Processing
    # -------------------------------------------------------------------------

    @classmethod
    def process_pdf(
        cls,
        file_path: Union[Path, str],
        dpi: Optional[int] = None,
        psm: Optional[int] = None,
    ) -> OCRResult:
        """
        Executes OCR on a scanned multi-page PDF document:
        1. Converts each PDF page into an image via pdf2image (poppler).
        2. Applies OpenCV preprocessing to each page.
        3. Runs Tesseract OCR on each page.
        4. Captures word-level bounding boxes, text, and confidence scores.
        5. Combines results across all pages.

        Args:
            file_path: Path to the PDF file.
            dpi: Resolution for PDF rendering (defaults to settings.OCR_PDF_DPI or 300).
            psm: Page segmentation mode (defaults to settings.OCR_PSM_MODE or 6).

        Returns:
            OCRResult: Structured document OCR result.
        """
        effective_dpi = dpi or getattr(settings, "OCR_PDF_DPI", 300)
        try:
            path = cls._validate_file_path(file_path, expected_extensions=SUPPORTED_PDF_EXTENSIONS)
        except OcrEngineError as val_err:
            logger.warning(f"PDF path validation error: {val_err}")
            return OCRResult(
                success=False,
                status="OCR_FAILED",
                error=str(val_err),
                file_type="PDF",
                page_count=0,
                pages=[],
            )

        if not cls.is_tesseract_available():
            return cls._tesseract_not_found_result(file_type="PDF")

        # Check Poppler availability for pdf2image
        poppler_path = settings.POPPLER_PATH or os.getenv("POPPLER_PATH")
        from pdf2image import convert_from_path

        try:
            # Convert PDF pages into list of PIL Images
            kwargs: Dict[str, Any] = {"dpi": effective_dpi}
            if poppler_path:
                kwargs["poppler_path"] = str(poppler_path)

            pages_images = convert_from_path(str(path), **kwargs)
        except Exception as poppler_err:
            logger.error(f"pdf2image conversion failed for '{path.name}': {poppler_err}", exc_info=True)
            err_msg = str(poppler_err).lower()
            if "poppler" in err_msg or not cls.is_poppler_available():
                return OCRResult(
                    success=False,
                    status="POPPLER_NOT_FOUND",
                    error="Poppler is not installed or not configured in system PATH / POPPLER_PATH. Required for PDF OCR.",
                    file_type="PDF",
                    page_count=0,
                    pages=[],
                )
            return OCRResult(
                success=False,
                status="OCR_FAILED",
                error="Unable to render PDF pages into images for OCR.",
                file_type="PDF",
                page_count=0,
                pages=[],
            )

        if not pages_images:
            return OCRResult(
                success=False,
                status="EMPTY_DOCUMENT",
                error="PDF contains 0 renderable pages.",
                file_type="PDF",
                page_count=0,
                pages=[],
            )

        # Process each page with fault isolation
        pages_data: List[OCRPageData] = []
        page_errors: List[str] = []
        all_confidences: List[float] = []

        for idx, page_img in enumerate(pages_images):
            page_num = idx + 1
            try:
                page_res = cls.extract_page_ocr(page_img, page_number=page_num, psm=psm)
                pages_data.append(page_res)
                if page_res.error:
                    page_errors.append(f"Page {page_num}: {page_res.error}")
                if page_res.words:
                    all_confidences.extend(w.confidence for w in page_res.words)
            except Exception as page_err:
                logger.warning(f"Error extracting page {page_num} of '{path.name}': {page_err}", exc_info=True)
                page_errors.append(f"Page {page_num}: OCR failed for this page.")
                pages_data.append(
                    OCRPageData(
                        page_number=page_num,
                        raw_text="",
                        text="",
                        words=[],
                        character_count=0,
                        word_count=0,
                        average_confidence=0.0,
                        has_text=False,
                        error="OCR failed for this page.",
                    )
                )

        combined_text = "\n\n".join(p.text for p in pages_data if p.text).strip()
        total_chars = sum(p.character_count for p in pages_data)
        total_words = sum(p.word_count for p in pages_data)
        overall_confidence = round(float(np.mean(all_confidences)), 2) if all_confidences else 0.0

        # Evaluate status: OCR_COMPLETED, NO_TEXT_DETECTED, OCR_PARTIAL, or OCR_FAILED
        if page_errors:
            if len(page_errors) == len(pages_data):
                status = "OCR_FAILED"
                success = False
            else:
                status = "OCR_PARTIAL"
                success = True
        else:
            status = "OCR_COMPLETED" if total_words > 0 else "NO_TEXT_DETECTED"
            success = True

        return OCRResult(
            success=success,
            status=status,
            error=None if success else "OCR extraction failed for all pages in the PDF.",
            errors=page_errors,
            file_type="PDF",
            page_count=len(pages_data),
            pages=pages_data,
            combined_text=combined_text,
            total_characters=total_chars,
            total_words=total_words,
            total_word_count=total_words,
            average_confidence=overall_confidence,
            metadata={
                "filename": path.name,
                "dpi": effective_dpi,
            },
        )

    # -------------------------------------------------------------------------
    # Unified Document Processor Dispatcher
    # -------------------------------------------------------------------------

    @classmethod
    def process_document(
        cls,
        file_path: Union[Path, str],
        dpi: Optional[int] = None,
        psm: Optional[int] = None,
    ) -> OCRResult:
        """
        Universal entry point: automatically determines file format (.png, .jpg, .jpeg, .pdf)
        and invokes the appropriate OCR processing method.
        """
        try:
            path = Path(file_path).resolve()
        except Exception as exc:
            return OCRResult(
                success=False,
                status="FAILED",
                error="Invalid file path syntax.",
                file_type="UNKNOWN",
                page_count=0,
                pages=[],
            )

        ext = path.suffix.lower()
        if ext in SUPPORTED_IMAGE_EXTENSIONS:
            return cls.process_image(path, psm=psm)
        elif ext in SUPPORTED_PDF_EXTENSIONS:
            return cls.process_pdf(path, dpi=dpi, psm=psm)
        else:
            return OCRResult(
                success=False,
                status="UNSUPPORTED_FORMAT",
                error=f"Unsupported file format '{ext}' for OCR. Expected one of: {sorted(ALL_SUPPORTED_EXTENSIONS)}",
                file_type="UNKNOWN",
                page_count=0,
                pages=[],
            )

    @classmethod
    def perform_ocr(
        cls,
        file_path: Union[Path, str],
        dpi: Optional[int] = None,
        psm: Optional[int] = None,
    ) -> OCRResult:
        """
        Public pipeline entry point for OCR processing.
        Determines file format (IMAGE vs. PDF) and executes OCR.
        """
        return cls.process_document(file_path, dpi=dpi, psm=psm)

    # Internal helper aliases
    _ocr_image = process_image
    _process_pdf = process_pdf
    _preprocess_image = preprocess_image
    _extract_word_data = extract_page_ocr

    # -------------------------------------------------------------------------
    # Helper Validation & Error Builders
    # -------------------------------------------------------------------------

    @staticmethod
    def _validate_file_path(
        file_path: Union[Path, str],
        expected_extensions: Optional[set] = None,
    ) -> Path:
        """Validates path safety, existence, read permissions, and extension."""
        if isinstance(file_path, str) and ("\x00" in file_path or not file_path.strip()):
            raise OcrEngineError("Invalid file path provided.")

        try:
            path = Path(file_path).resolve()
        except Exception as exc:
            raise OcrEngineError(f"Invalid file path syntax: {exc}") from exc

        if not path.exists():
            raise OcrEngineError("File does not exist.")

        if not path.is_file():
            raise OcrEngineError("Path is not a regular file.")

        if not os.access(path, os.R_OK):
            raise OcrEngineError("File is not readable.")

        if expected_extensions and path.suffix.lower() not in expected_extensions:
            raise OcrEngineError(
                f"Invalid file extension '{path.suffix}'. Expected one of: {sorted(expected_extensions)}"
            )

        if path.stat().st_size == 0:
            raise OcrEngineError("The file is empty (0 bytes).")

        return path

    @staticmethod
    def _tesseract_not_found_result(file_type: str) -> OCRResult:
        """Returns a helpful, non-crashing result when Tesseract binary is not installed."""
        return OCRResult(
            success=False,
            status="TESSERACT_NOT_FOUND",
            error=(
                "Tesseract OCR engine is not installed or not found in system PATH. "
                "Please install Tesseract and either add it to PATH or configure TESSERACT_CMD in .env."
            ),
            file_type=file_type,
            page_count=0,
            pages=[],
        )


# Singleton instance
ocr_engine = OcrEngine()

# Convenience functional exports
perform_ocr = ocr_engine.perform_ocr
process_document = ocr_engine.process_document
process_image = ocr_engine.process_image
process_pdf = ocr_engine.process_pdf
preprocess_image = ocr_engine.preprocess_image
