"""
Image Ingestion Service.
Handles standalone image files (PNG, JPG, TIFF, WEBP, etc.)
Extracts dimensions and OCR blocks with word coordinates and confidence.
"""

import logging
from pathlib import Path
from typing import List, Tuple
from PIL import Image

from app.schemas.universal import ContentBlock, ExtractedTable, PageMeta
from app.services.ingestion.pdf_ingest import _ocr_page_image

logger = logging.getLogger(__name__)


def ingest_image_file(
    file_path: Path,
) -> Tuple[List[PageMeta], List[ContentBlock], List[ExtractedTable]]:
    """Ingests a standalone image file via OCR."""
    with Image.open(str(file_path)) as pil_img:
        width, height = pil_img.size
        # Normalize image mode for tesseract
        if pil_img.mode not in ("RGB", "L"):
            pil_img = pil_img.convert("RGB")

        blocks = _ocr_page_image(pil_img, page_number=1, page_width=float(width), page_height=float(height))

    pages = [
        PageMeta(
            n=1,
            width=float(width),
            height=float(height),
            source="ocr",
        )
    ]
    return pages, blocks, []
