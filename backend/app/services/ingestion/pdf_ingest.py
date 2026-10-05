"""
PDF Ingestion Service.
Handles both digital and scanned PDFs with per-page native/OCR routing,
block layout extraction, reading order, table detection, and bounding boxes.
"""

import logging
from pathlib import Path
from typing import List, Tuple
import pymupdf
import pytesseract
from PIL import Image
import io

from app.core.config import settings
from app.schemas.universal import ContentBlock, ExtractedTable, PageMeta

logger = logging.getLogger(__name__)


def ingest_pdf_file(
    file_path: Path,
) -> Tuple[List[PageMeta], List[ContentBlock], List[ExtractedTable]]:
    """
    Ingests a PDF document, routing per page between native digital parsing
    and OCR fallback for scanned pages.
    """
    pages_meta: List[PageMeta] = []
    all_blocks: List[ContentBlock] = []
    all_tables: List[ExtractedTable] = []

    doc = pymupdf.open(str(file_path))
    try:
        for page_idx in range(len(doc)):
            page_number = page_idx + 1
            page = doc[page_idx]
            rect = page.rect
            width = float(rect.width)
            height = float(rect.height)

            # 1. Inspect text blocks
            raw_blocks = page.get_text("blocks")
            # raw_blocks: list of (x0, y0, x1, y1, text, block_no, block_type)
            # block_type == 0 is text, 1 is image

            text_blocks = [b for b in raw_blocks if b[6] == 0 and b[4].strip()]
            total_chars = sum(len(b[4].strip()) for b in text_blocks)

            # Heuristic: if page has >= 30 characters of text, consider native digital
            if total_chars >= 30:
                page_source = "native"
                order = 0
                for b in text_blocks:
                    x0, y0, x1, y1, text, block_no, _ = b
                    cleaned_text = text.strip()
                    if not cleaned_text:
                        continue

                    # Determine block type (heading vs paragraph vs list)
                    block_type = "paragraph"
                    if len(cleaned_text) < 80 and (
                        cleaned_text.isupper() or cleaned_text.istitle()
                    ):
                        block_type = "heading"
                    elif cleaned_text.startswith(("- ", "• ", "* ", "1. ", "2. ")):
                        block_type = "list"

                    all_blocks.append(
                        ContentBlock(
                            id=f"blk_p{page_number}_{order}",
                            page=page_number,
                            type=block_type,
                            text=cleaned_text,
                            bbox=[round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
                            reading_order=order,
                            ocr_conf=1.0,
                        )
                    )
                    order += 1

                # 2. Extract tables natively
                try:
                    tables_found = page.find_tables()
                    for t_idx, tbl in enumerate(tables_found):
                        df = tbl.extract()
                        if df and len(df) > 0:
                            headers = [str(col).strip() if col is not None else "" for col in df[0]]
                            rows = []
                            for row in df[1:]:
                                rows.append([str(c).strip() if c is not None else "" for c in row])
                            t_bbox = [
                                round(tbl.bbox[0], 2),
                                round(tbl.bbox[1], 2),
                                round(tbl.bbox[2], 2),
                                round(tbl.bbox[3], 2),
                            ]
                            all_tables.append(
                                ExtractedTable(
                                    id=f"tbl_p{page_number}_{t_idx}",
                                    page=page_number,
                                    bbox=t_bbox,
                                    headers=headers,
                                    rows=rows,
                                    ocr_conf=1.0,
                                )
                            )
                except Exception as e:
                    logger.debug(f"Native table extraction skipped on page {page_number}: {e}")

            else:
                # Page is scanned or has no text layer -> fallback to OCR
                page_source = "ocr"
                pix = page.get_pixmap(dpi=200)
                img_data = pix.tobytes("png")
                pil_image = Image.open(io.BytesIO(img_data))

                ocr_blocks = _ocr_page_image(pil_image, page_number, width, height)
                all_blocks.extend(ocr_blocks)

            pages_meta.append(
                PageMeta(
                    n=page_number,
                    width=width,
                    height=height,
                    source=page_source,
                )
            )

    finally:
        doc.close()

    return pages_meta, all_blocks, all_tables


def _ocr_page_image(
    image: Image.Image,
    page_number: int,
    page_width: float,
    page_height: float,
) -> List[ContentBlock]:
    """Runs OCR (PaddleOCR by default or Tesseract fallback) on a page image and returns ContentBlocks."""
    engine_choice = getattr(settings, "OCR_ENGINE", "paddleocr").lower().strip()

    if engine_choice == "paddleocr":
        try:
            from app.services.ocr.paddle_engine import paddle_ocr_engine
            if paddle_ocr_engine.is_available():
                blocks = paddle_ocr_engine.extract_blocks_from_image(
                    image, page_number, page_width, page_height
                )
                if blocks:
                    return blocks
        except Exception as exc:
            logger.warning(
                f"PaddleOCR execution failed on page {page_number}: {exc}. "
                "Falling back to Tesseract OCR."
            )

    return _ocr_page_image_tesseract(image, page_number, page_width, page_height)


def _ocr_page_image_tesseract(
    image: Image.Image,
    page_number: int,
    page_width: float,
    page_height: float,
) -> List[ContentBlock]:
    """Runs Tesseract OCR on a page image and groups words into content blocks with bounding boxes."""
    blocks: List[ContentBlock] = []

    # Configure tesseract path if set
    if settings.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

    try:
        # Get OCR details down to word and block levels
        data = pytesseract.image_to_data(
            image,
            lang=settings.OCR_LANGUAGE,
            output_type=pytesseract.Output.DICT,
            config=f"--psm {settings.OCR_PSM}",
        )

        n_boxes = len(data["text"])
        img_w, img_h = image.size
        # Coordinate scale factors to scale from image pixel size to page point size
        scale_x = page_width / img_w if img_w else 1.0
        scale_y = page_height / img_h if img_h else 1.0

        # Group words by block_num and line_num
        grouped_lines = {}
        for i in range(n_boxes):
            word = data["text"][i].strip()
            conf = float(data["conf"][i])
            if not word or conf < 10:
                continue

            b_num = data["block_num"][i]
            l_num = data["line_num"][i]
            key = (b_num, l_num)

            x = data["left"][i] * scale_x
            y = data["top"][i] * scale_y
            w = data["width"][i] * scale_x
            h = data["height"][i] * scale_y

            if key not in grouped_lines:
                grouped_lines[key] = {
                    "words": [],
                    "confs": [],
                    "bbox": [x, y, x + w, y + h],
                }
            else:
                grouped_lines[key]["words"].append(word)
                grouped_lines[key]["confs"].append(conf)
                # Expand line bounding box
                cur_bbox = grouped_lines[key]["bbox"]
                grouped_lines[key]["bbox"] = [
                    min(cur_bbox[0], x),
                    min(cur_bbox[1], y),
                    max(cur_bbox[2], x + w),
                    max(cur_bbox[3], y + h),
                ]

        order = 0
        for (b_num, l_num), line_data in grouped_lines.items():
            line_text = " ".join(line_data["words"]).strip()
            if not line_text:
                continue
            avg_conf = (
                sum(line_data["confs"]) / len(line_data["confs"]) / 100.0
                if line_data["confs"]
                else 0.5
            )
            blocks.append(
                ContentBlock(
                    id=f"blk_ocr_p{page_number}_{order}",
                    page=page_number,
                    type="paragraph",
                    text=line_text,
                    bbox=[round(coord, 2) for coord in line_data["bbox"]],
                    reading_order=order,
                    ocr_conf=round(avg_conf, 3),
                )
            )
            order += 1

    except Exception as exc:
        logger.error(f"OCR failed for page {page_number}: {exc}")

    return blocks
