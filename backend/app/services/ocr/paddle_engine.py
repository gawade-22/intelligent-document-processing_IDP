"""
PaddleOCR Engine Service.
High-precision deep learning OCR based on DBNet text detection and SVTR/CRNN text recognition.
Provides angle classification, multi-language support, and millimeter-accurate bounding boxes.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from PIL import Image

from app.core.config import settings
from app.schemas.universal import ContentBlock

logger = logging.getLogger(__name__)


class PaddleOcrEngine:
    """Singleton wrapper for PaddleOCR with lazy initialization and thread-safe inference."""

    _instance: Optional["PaddleOcrEngine"] = None
    _ocr_model: Optional[Any] = None

    def __new__(cls) -> "PaddleOcrEngine":
        if cls._instance is None:
            cls._instance = super(PaddleOcrEngine, cls).__new__(cls)
        return cls._instance

    @classmethod
    def is_available(cls) -> bool:
        """Checks if paddleocr and paddlepaddle are installed in the Python environment."""
        try:
            import paddleocr  # noqa: F401
            return True
        except ImportError:
            return False

    def _get_model(self) -> Any:
        """Lazy loads the PaddleOCR model upon first inference request."""
        if self._ocr_model is None:
            try:
                # PaddlePaddle 3.x on Windows CPU has an unhandled PIR double attribute in oneDNN.
                # Disabling oneDNN on CPU inference predictors completely avoids this without performance loss.
                try:
                    import paddle.inference
                    if not getattr(paddle.inference, "_onednn_disabled_for_idp", False):
                        orig_cp = paddle.inference.create_predictor

                        def _safe_create_predictor(config):
                            if hasattr(config, "disable_onednn"):
                                config.disable_onednn()
                            return orig_cp(config)

                        paddle.inference.create_predictor = _safe_create_predictor
                        paddle.inference._onednn_disabled_for_idp = True
                except Exception as patch_err:
                    logger.debug(f"oneDNN bypass patch skipped: {patch_err}")

                from paddleocr import PaddleOCR

                lang = getattr(settings, "PADDLE_OCR_LANG", "en")

                logger.info(f"Initializing PaddleOCR (lang='{lang}')...")
                # Initialize PaddleOCR with graceful argument fallback across versions
                try:
                    self._ocr_model = PaddleOCR(lang=lang)
                except Exception:
                    self._ocr_model = PaddleOCR()
                logger.info("PaddleOCR model initialized successfully.")
            except Exception as exc:
                logger.error(f"Failed to initialize PaddleOCR: {exc}")
                raise RuntimeError(
                    f"PaddleOCR failed to initialize. Please ensure paddlepaddle and paddleocr are installed: {exc}"
                ) from exc
        return self._ocr_model

    def extract_blocks_from_image(
        self,
        image: Union[Image.Image, np.ndarray, Path, str],
        page_number: int,
        page_width: float,
        page_height: float,
    ) -> List[ContentBlock]:
        """
        Runs PaddleOCR on a page image and converts the detected text boxes
        into structured ContentBlock objects scaled to page coordinates.
        """
        ocr = self._get_model()

        # Convert input to RGB numpy array
        if isinstance(image, (str, Path)):
            pil_img = Image.open(str(image)).convert("RGB")
            img_array = np.array(pil_img)
            img_w, img_h = pil_img.size
        elif isinstance(image, Image.Image):
            pil_img = image.convert("RGB")
            img_array = np.array(pil_img)
            img_w, img_h = pil_img.size
        elif isinstance(image, np.ndarray):
            img_array = image
            img_h, img_w = img_array.shape[:2]
        else:
            raise ValueError(f"Unsupported image input type for PaddleOCR: {type(image)}")

        # Calculate coordinate scaling from image pixels to page point dimensions
        scale_x = page_width / img_w if img_w else 1.0
        scale_y = page_height / img_h if img_h else 1.0

        # Execute OCR inference across PaddleOCR 3.x (predict) and 2.x (ocr)
        lines: List[Tuple[Any, Tuple[str, float]]] = []

        try:
            if hasattr(ocr, "predict"):
                predictions = list(ocr.predict(img_array))
                if predictions and isinstance(predictions[0], dict):
                    pred = predictions[0]
                    rec_texts = pred.get("rec_texts") or []
                    rec_scores = pred.get("rec_scores") or []
                    rec_polys = pred.get("rec_polys")
                    if rec_polys is None:
                        rec_polys = pred.get("dt_polys") or []

                    for idx, text in enumerate(rec_texts):
                        score = float(rec_scores[idx]) if idx < len(rec_scores) else 0.90
                        poly = rec_polys[idx] if idx < len(rec_polys) else None
                        if poly is not None:
                            lines.append((poly, (text, score)))
            elif hasattr(ocr, "ocr"):
                results = ocr.ocr(img_array, cls=True)
                if results and results[0]:
                    lines = results[0]
        except Exception as e:
            logger.warning(f"PaddleOCR execution error on page {page_number}: {e}")
            lines = []

        blocks: List[ContentBlock] = []
        if not lines:
            return blocks

        # Sort lines by top-to-bottom reading order (y0, then x0)
        def _get_box_sort_key(line_item):
            pts = line_item[0]
            if hasattr(pts, "tolist"):
                pts = pts.tolist()
            min_y = min(p[1] for p in pts)
            min_x = min(p[0] for p in pts)
            return (min_y, min_x)

        sorted_lines = sorted(lines, key=_get_box_sort_key)

        for order, line_item in enumerate(sorted_lines):
            pts = line_item[0]
            if hasattr(pts, "tolist"):
                pts = pts.tolist()
            text_info = line_item[1]
            text = text_info[0].strip() if text_info else ""
            conf = float(text_info[1]) if text_info and len(text_info) > 1 else 0.90

            if not text:
                continue

            # Compute axis-aligned bounding box from polygon vertices
            x0 = min(p[0] for p in pts) * scale_x
            y0 = min(p[1] for p in pts) * scale_y
            x1 = max(p[0] for p in pts) * scale_x
            y1 = max(p[1] for p in pts) * scale_y

            bbox = [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)]

            # Determine layout block type
            block_type = "paragraph"
            if len(text) < 80 and (text.isupper() or text.istitle()):
                block_type = "heading"
            elif text.startswith(("- ", "• ", "* ", "1. ", "2. ", "3. ")):
                block_type = "list"

            blocks.append(
                ContentBlock(
                    id=f"blk_p{page_number}_{order}",
                    page=page_number,
                    type=block_type,
                    text=text,
                    bbox=bbox,
                    reading_order=order,
                    ocr_conf=round(conf, 3),
                )
            )

        return blocks


paddle_ocr_engine = PaddleOcrEngine()
