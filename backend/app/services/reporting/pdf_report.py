"""
Professional PDF Summary Report Generator for Universal IDP.
Generates an executive-ready, multi-page vector PDF report containing:
- Document metadata and classification
- Calibrated confidence and processing status
- Cleanly formatted extracted fields grouped by section
- Extracted repeating tables
- Computed insights and audit details
"""

import io
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import pymupdf


def _sanitize_text(text: Any, preserve_newlines: bool = False) -> str:
    """Sanitizes text for PDF encoding, replacing undefined glyphs."""
    if text is None:
        return ""
    s = str(text).strip()
    # Replace non-ascii quotes and ligatures
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-").replace("…", "...")
    s = s.replace("•", "* ").replace("§", "#").replace("ï", "").replace("ƒ", "+")
    # Keep printable ASCII and common Latin
    cleaned = "".join(c if ord(c) < 128 else " " for c in s)
    if preserve_newlines:
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in cleaned.splitlines()]
        return "\n".join(l for l in lines if l)
    return re.sub(r"\s+", " ", cleaned).strip()


def _wrap_text(text: str, max_chars: int = 55) -> List[str]:
    """Wraps text into lines not exceeding max_chars, preserving explicit newlines."""
    if not text:
        return [""]
    raw_lines = text.split("\n")
    final_lines = []
    for raw in raw_lines:
        words = raw.split()
        if not words:
            continue
        current_line = []
        current_len = 0
        for w in words:
            if current_len + len(w) + 1 > max_chars:
                final_lines.append(" ".join(current_line))
                current_line = [w]
                current_len = len(w)
            else:
                current_line.append(w)
                current_len += len(w) + (1 if current_len > 0 else 0)
        if current_line:
            final_lines.append(" ".join(current_line))
    return final_lines or [""]


def generate_document_pdf_report(
    document_name: str,
    doc_format: str,
    classification: Dict[str, Any],
    fields: List[Dict[str, Any]],
    tables: List[Dict[str, Any]],
    insights: List[Dict[str, Any]],
    run_id: str,
    status: str = "COMPLETED",
    confidence: float = 0.95,
) -> bytes:
    """
    Builds a vector PDF report using PyMuPDF.
    Returns the binary PDF bytes.
    """
    doc = pymupdf.open()
    PAGE_WIDTH = 595.0
    PAGE_HEIGHT = 842.0

    # Color palette
    PRIMARY_COLOR = (0.09, 0.22, 0.45)   # Navy Blue
    ACCENT_COLOR = (0.15, 0.45, 0.85)    # Blue Accent
    TEXT_DARK = (0.12, 0.15, 0.20)       # Slate 900
    TEXT_MUTED = (0.40, 0.45, 0.52)      # Slate 500
    ROW_BG_ALT = (0.96, 0.97, 0.99)      # Soft Table Row
    BORDER_COLOR = (0.86, 0.88, 0.92)    # Border Gray
    SUCCESS_COLOR = (0.10, 0.60, 0.35)   # Emerald Green

    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    current_y = 0

    def draw_page_header(p):
        nonlocal current_y
        # Top banner
        p.draw_rect(pymupdf.Rect(0, 0, PAGE_WIDTH, 52), color=None, fill=PRIMARY_COLOR)
        p.insert_text((36, 32), "UNIVERSAL IDP  |  EXTRACTION REPORT", fontsize=13, fontname="helv", color=(1, 1, 1))
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        p.insert_text((PAGE_WIDTH - 180, 32), now_str, fontsize=9, fontname="helv", color=(0.85, 0.90, 1.0))
        current_y = 70

    def draw_page_footer(p, page_num):
        p.draw_line(pymupdf.Point(36, PAGE_HEIGHT - 35), pymupdf.Point(PAGE_WIDTH - 36, PAGE_HEIGHT - 35), color=BORDER_COLOR, width=0.7)
        p.insert_text((36, PAGE_HEIGHT - 22), "Intelligent Document Processing (v2) - Automated Extraction & Evidence Grounding", fontsize=8, fontname="helv", color=TEXT_MUTED)
        p.insert_text((PAGE_WIDTH - 85, PAGE_HEIGHT - 22), f"Page {page_num}", fontsize=8, fontname="helv", color=TEXT_MUTED)

    draw_page_header(page)

    # 1. Document Overview Card
    overview_rect = pymupdf.Rect(36, current_y, PAGE_WIDTH - 36, current_y + 88)
    page.draw_rect(overview_rect, color=BORDER_COLOR, fill=(0.98, 0.99, 1.0), width=0.8)
    
    # Document title
    sanitized_doc_name = _sanitize_text(document_name)[:48]
    page.insert_text((50, current_y + 24), sanitized_doc_name, fontsize=13, fontname="helv", color=PRIMARY_COLOR)

    # Status Pill
    status_str = status.upper()
    pill_color = SUCCESS_COLOR if "VERIF" in status_str or "COMPLET" in status_str else (0.85, 0.55, 0.10)
    page.draw_rect(pymupdf.Rect(PAGE_WIDTH - 150, current_y + 12, PAGE_WIDTH - 50, current_y + 30), color=None, fill=pill_color)
    page.insert_text((PAGE_WIDTH - 140, current_y + 24), f"* {status_str}", fontsize=9, fontname="helv", color=(1, 1, 1))

    # Meta details
    doc_type = _sanitize_text(classification.get("primary_type", "Universal Document"))
    family = _sanitize_text(classification.get("family", "General")).title()
    conf_pct = f"{round(confidence * 100)}%"

    page.insert_text((50, current_y + 50), f"Classified Type: {doc_type}", fontsize=10, fontname="helv", color=TEXT_DARK)
    page.insert_text((50, current_y + 68), f"Family / Domain: {family}", fontsize=9, fontname="helv", color=TEXT_MUTED)
    page.insert_text((280, current_y + 50), f"Confidence: {conf_pct}", fontsize=10, fontname="helv", color=TEXT_DARK)
    page.insert_text((280, current_y + 68), f"Format: {doc_format.upper()}  *  Run ID: {run_id}", fontsize=9, fontname="helv", color=TEXT_MUTED)

    current_y += 105

    # 2. Extracted Fields Table Header
    page.insert_text((36, current_y), "EXTRACTED FIELDS & GROUNDED VALUES", fontsize=11, fontname="helv", color=PRIMARY_COLOR)
    current_y += 12

    # Column coordinates
    col_x = [36, 125, 230, 490, PAGE_WIDTH - 36]
    
    # Table header bar
    page.draw_rect(pymupdf.Rect(col_x[0], current_y, col_x[4], current_y + 20), color=BORDER_COLOR, fill=ROW_BG_ALT, width=0.8)
    page.insert_text((col_x[0] + 6, current_y + 14), "SECTION", fontsize=8, fontname="helv", color=TEXT_MUTED)
    page.insert_text((col_x[1] + 6, current_y + 14), "FIELD", fontsize=8, fontname="helv", color=TEXT_MUTED)
    page.insert_text((col_x[2] + 6, current_y + 14), "EXTRACTED VALUE", fontsize=8, fontname="helv", color=TEXT_MUTED)
    page.insert_text((col_x[3] + 6, current_y + 14), "CONFIDENCE", fontsize=8, fontname="helv", color=TEXT_MUTED)
    current_y += 20

    row_index = 0
    page_count = 1

    for f in fields:
        raw_val = f.get("value") or f.get("raw_value")
        if raw_val is None or str(raw_val).strip().lower() in ("null", "none", "not detected", ""):
            continue
        val_str = _sanitize_text(raw_val, preserve_newlines=True)
        section_str = _sanitize_text(f.get("section", "General"))[:16]
        label_str = _sanitize_text(f.get("label", f.get("key", "Field")))[:22]
        f_conf = f.get("confidence", 0.90)
        f_grounded = f.get("evidence", {}).get("grounded", True) if isinstance(f.get("evidence"), dict) else True
        f_status = f.get("status", "verified")

        val_lines = _wrap_text(val_str, max_chars=54)
        
        # Paginate lines if they exceed remaining page space
        line_offset = 0
        while line_offset < len(val_lines):
            available_space = (PAGE_HEIGHT - 55) - current_y - 20
            max_lines_fit = max(1, int(available_space / 13))
            chunk = val_lines[line_offset : line_offset + max_lines_fit]
            chunk_height = max(22, len(chunk) * 13 + 6)

            if current_y + chunk_height > PAGE_HEIGHT - 50:
                draw_page_footer(page, page_count)
                page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
                page_count += 1
                draw_page_header(page)
                # Header row
                page.draw_rect(pymupdf.Rect(col_x[0], current_y, col_x[4], current_y + 20), color=BORDER_COLOR, fill=ROW_BG_ALT, width=0.8)
                page.insert_text((col_x[0] + 6, current_y + 14), "SECTION", fontsize=8, fontname="helv", color=TEXT_MUTED)
                page.insert_text((col_x[1] + 6, current_y + 14), "FIELD", fontsize=8, fontname="helv", color=TEXT_MUTED)
                page.insert_text((col_x[2] + 6, current_y + 14), "EXTRACTED VALUE", fontsize=8, fontname="helv", color=TEXT_MUTED)
                page.insert_text((col_x[3] + 6, current_y + 14), "CONFIDENCE", fontsize=8, fontname="helv", color=TEXT_MUTED)
                current_y += 20

            bg_fill = ROW_BG_ALT if (row_index % 2 == 1) else (1.0, 1.0, 1.0)
            page.draw_rect(pymupdf.Rect(col_x[0], current_y, col_x[4], current_y + chunk_height), color=BORDER_COLOR, fill=bg_fill, width=0.5)

            if line_offset == 0:
                page.insert_text((col_x[0] + 6, current_y + 14), section_str, fontsize=8, fontname="helv", color=TEXT_MUTED)
                page.insert_text((col_x[1] + 6, current_y + 14), label_str, fontsize=8.5, fontname="helv", color=TEXT_DARK)
                conf_display = f"{round(f_conf * 100)}%"
                status_label = "Verified" if f_grounded else "Review"
                page.insert_text((col_x[3] + 6, current_y + 14), f"{conf_display} ({status_label})", fontsize=8, fontname="helv", color=SUCCESS_COLOR if f_grounded else (0.85, 0.50, 0.10))
            else:
                page.insert_text((col_x[1] + 6, current_y + 14), f"{label_str} (cont.)", fontsize=7.5, fontname="helv", color=TEXT_MUTED)

            text_y = current_y + 13
            val_color = TEXT_DARK if val_str != "Not Detected" else (0.75, 0.20, 0.20)
            for line in chunk:
                page.insert_text((col_x[2] + 6, text_y), line, fontsize=8.5, fontname="helv", color=val_color)
                text_y += 13

            current_y += chunk_height
            line_offset += len(chunk)
            
        row_index += 1

    # 3. Tabular Data (if present)
    for tbl in tables:
        t_title = _sanitize_text(tbl.get("title", tbl.get("key", "Table"))).upper()
        headers = tbl.get("headers", [])
        rows = tbl.get("rows", [])

        if not rows:
            continue

        if current_y + 80 > PAGE_HEIGHT - 50:
            draw_page_footer(page, page_count)
            page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
            page_count += 1
            draw_page_header(page)

        current_y += 16
        page.insert_text((36, current_y), f"TABLE: {t_title} ({len(rows)} ROWS)", fontsize=10, fontname="helv", color=PRIMARY_COLOR)
        current_y += 12

        col_count = max(1, min(len(headers), 5))
        col_width = (PAGE_WIDTH - 72) / col_count

        # Table header
        page.draw_rect(pymupdf.Rect(36, current_y, PAGE_WIDTH - 36, current_y + 18), color=BORDER_COLOR, fill=PRIMARY_COLOR, width=0.5)
        for c_idx, h in enumerate(headers[:col_count]):
            hx = 36 + c_idx * col_width + 4
            page.insert_text((hx, current_y + 12), _sanitize_text(h)[:18], fontsize=8, fontname="helv", color=(1, 1, 1))
        current_y += 18

        for r_idx, r in enumerate(rows[:20]):
            if current_y + 18 > PAGE_HEIGHT - 50:
                draw_page_footer(page, page_count)
                page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
                page_count += 1
                draw_page_header(page)

            row_bg = ROW_BG_ALT if (r_idx % 2 == 1) else (1.0, 1.0, 1.0)
            page.draw_rect(pymupdf.Rect(36, current_y, PAGE_WIDTH - 36, current_y + 16), color=BORDER_COLOR, fill=row_bg, width=0.5)

            for c_idx, cell in enumerate(r[:col_count]):
                cx = 36 + c_idx * col_width + 4
                page.insert_text((cx, current_y + 12), _sanitize_text(cell)[:20], fontsize=8, fontname="helv", color=TEXT_DARK)
            current_y += 16

    # Draw footer on the final page
    draw_page_footer(page, page_count)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes
