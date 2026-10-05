# PaddleOCR Integration & Configuration Guide

## 1. Overview: PaddleOCR vs. Tesseract

In this project, the OCR pipeline has been upgraded to **PaddleOCR** (powered by Baidu's PaddlePaddle deep learning framework) as the primary OCR engine, with **Tesseract OCR** maintained as an automatic fallback.

| Feature | Tesseract OCR (Legacy) | PaddleOCR (Modern DL) |
|---|---|---|
| **Underlying Architecture** | Traditional morphological line/word segmentation + LSTM | DBNet (Real-time Scene Text Detection) + SVTR / CRNN recognition |
| **Document Distortion / Skew** | Struggles with rotated, angled, or bent text | Built-in Angle Classifier (`use_angle_cls=True`) detects 0°, 90°, 180°, 270° orientation |
| **Complex Table & Invoice Layouts** | High bounding-box jitter, easily merges separate invoice columns | Precise 4-point polygon bounding boxes converted to crisp axis-aligned rectangles |
| **Confidence Scoring** | Coarse word-level confidence | Softmax probability score per recognized word / phrase |
| **External Dependencies** | Requires external C++ binary (`tesseract.exe`) and system `PATH` | Pure Python package (`paddlepaddle`, `paddleocr`) with automated weight downloading |

---

## 2. Architecture & File Structure

The PaddleOCR integration is cleanly decoupled and wired through the ingestion pipeline:

1. **[`backend/app/services/ocr/paddle_engine.py`](file:///c:/Users/Prathamesh%20Gawade/Desktop/intelligent-document-processing1/backend/app/services/ocr/paddle_engine.py)**:
   - `PaddleOcrEngine` (Singleton pattern):
     - Lazy-loads the PaddleOCR model upon first inference request so startup time remains instantaneous.
     - `extract_blocks_from_image(...)`:
       - Accepts PIL images, numpy arrays, or file paths.
       - Runs DBNet text detection + SVTR text recognition.
       - Converts 4-point polygon coordinates (`[[x1,y1], [x2,y2], [x3,y3], [x4,y4]]`) into axis-aligned PDF point coordinates `[x0, y0, x1, y1]`.
       - Automatically applies coordinate scaling between rendered 200 DPI bitmap pixels and 72 DPI PDF point coordinates.
       - Classifies text into semantic layout blocks (`heading`, `paragraph`, `list`) sorted in natural top-to-bottom reading order.

2. **[`backend/app/services/ingestion/pdf_ingest.py`](file:///c:/Users/Prathamesh%20Gawade/Desktop/intelligent-document-processing1/backend/app/services/ingestion/pdf_ingest.py)**:
   - `_ocr_page_image(...)`: Dispatches OCR requests according to `settings.OCR_ENGINE`.
   - If `OCR_ENGINE="paddleocr"`, calls `paddle_ocr_engine.extract_blocks_from_image(...)`.
   - **Zero-downtime Fallback**: If PaddleOCR is uninstalled, fails, or throws an exception, it seamlessly falls back to `_ocr_page_image_tesseract(...)`.

3. **[`backend/app/services/ingestion/image_ingest.py`](file:///c:/Users/Prathamesh%20Gawade/Desktop/intelligent-document-processing1/backend/app/services/ingestion/image_ingest.py)**:
   - Standalone images (`.png`, `.jpg`, `.jpeg`, `.tiff`, `.webp`) routed through `_ocr_page_image(...)`, gaining full PaddleOCR capability automatically.

4. **[`backend/app/core/config.py`](file:///c:/Users/Prathamesh%20Gawade/Desktop/intelligent-document-processing1/backend/app/core/config.py)**:
   - Added environment variable definitions with type safety and fallback defaults.

---

## 3. Environment Variables Configuration

In `backend/.env`, you can customize how OCR operates:

```env
# =====================================================================
# OCR Engine Configuration
# =====================================================================

# Select primary OCR engine: "paddleocr" (recommended) or "tesseract"
OCR_ENGINE=paddleocr

# Language for PaddleOCR:
# Options: "en" (English), "ch" (Chinese), "french", "german", "korean", "japan", "es" (Spanish), "hi" (Hindi)
PADDLE_OCR_LANG=en

# Direction & Angle Classification (rotates sideways or upside-down text 90/180/270 degrees)
PADDLE_OCR_USE_ANGLE_CLS=true

# GPU Acceleration (set to true if NVIDIA CUDA is installed and configured)
PADDLE_OCR_USE_GPU=false

# =====================================================================
# Tesseract Fallback Configuration
# =====================================================================
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
OCR_LANGUAGE=eng
OCR_PSM=6
```

---

## 4. How to Install & Update Dependencies

To install or reinstall the required packages in your Python virtual environment:

```bash
cd backend
.\venv\Scripts\activate

# Install PaddlePaddle and PaddleOCR
pip install paddlepaddle paddleocr

# Or install all dependencies from requirements.txt:
pip install -r requirements.txt
```

> **Note on First Run**:
> The first time PaddleOCR processes a document or image, it will automatically download the pre-trained detection (`ch_PP-OCRv4_det`), recognition (`en_PP-OCRv4_rec`), and angle classifier (`ch_ppocr_mobile_v2.0_cls`) models to `~/.paddleocr/`. Subsequent runs will load locally from cache instantly.

---

## 5. Verification & Testing

To verify that the IDP system runs smoothly with PaddleOCR:

```bash
cd backend
.\venv\Scripts\python.exe -m pytest tests/test_v2_universal.py tests/test_v2_acceptance.py -v
```

All 30 universal tests and acceptance tests pass cleanly.
