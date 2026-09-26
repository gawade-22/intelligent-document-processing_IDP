from abc import ABC, abstractmethod
import logging
import math
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from app.schemas.extraction import ExtractedField, FieldCandidate as FieldCandidateSchema, InvoiceExtractionResult
from app.schemas.ocr import OCRBoundingBox, OCRPageData, OCRResult, OCRWordData
from app.schemas.pdf import PDFParseResult
from app.services.ai.base import (
    AIExtractionProvider,
    MockAIExtractionProvider,
    NoOpAIExtractionProvider,
)
from app.services.reconciliation import ReconciliationEngine, reconcile_rule_and_ai

logger = logging.getLogger(__name__)

# Minimum composite confidence threshold required to accept a candidate field
MIN_CONFIDENCE_THRESHOLD = 0.35

# -----------------------------------------------------------------------------
# Transparent Candidate Scoring Weights (Configurable)
# -----------------------------------------------------------------------------
# Weights combining meaningful signals: keyword, pattern, ocr, position, context.
# Clamped between 0.0 and 1.0.
# Note: This is an extraction confidence score, NOT a statistically calibrated probability.
EXTRACTION_WEIGHTS: Dict[str, float] = {
    "keyword": 0.30,
    "pattern": 0.25,
    "ocr": 0.20,
    "position": 0.15,
    "context": 0.10,
}

# -----------------------------------------------------------------------------
# Centralized Field Keyword Dictionaries
# -----------------------------------------------------------------------------

INVOICE_NUMBER_KEYWORDS: List[str] = [
    "invoice number",
    "invoice no",
    "invoice no.",
    "invoice #",
    "invoice id",
    "invoice ref",
    "invoice reference",
    "tax invoice number",
    "tax invoice no",
    "tax invoice no.",
    "tax invoice #",
    "bill number",
    "bill no",
    "bill no.",
    "bill #",
    "inv number",
    "inv num",
    "inv no",
    "inv no.",
    "inv #",
    "inv ref",
    "inv id",
    "reference number",
    "reference no",
    "reference no.",
    "reference #",
    "reference",
    "ref number",
    "ref no",
    "ref no.",
    "ref #",
    "ref",
]

INVOICE_DATE_KEYWORDS: List[str] = [
    "invoice date",
    "invoice dt",
    "date of issue",
    "date of invoice",
    "issue date",
    "invoice issued",
    "bill date",
    "billing date",
    "dated",
    "date",
]

TOTAL_AMOUNT_KEYWORDS: List[str] = [
    "grand total",
    "total amount",
    "invoice total",
    "net payable",
    "amount payable",
    "balance due",
    "total due",
    "amount due",
    "total payable",
    "net total",
    "final amount",
    "gross total",
    "total",
]

VENDOR_KEYWORDS: List[str] = [
    "vendor name",
    "vendor",
    "seller name",
    "seller",
    "supplier name",
    "supplier",
    "billed from",
    "billed by",
    "sold by",
    "from",
    "issued by",
    "company name",
    "company",
    "merchant",
    "provider",
]

# Centralized registry mapping field names to their specific keyword dictionaries
FIELD_KEYWORD_DICTIONARIES: Dict[str, List[str]] = {
    "vendor_name": VENDOR_KEYWORDS,
    "invoice_number": INVOICE_NUMBER_KEYWORDS,
    "invoice_date": INVOICE_DATE_KEYWORDS,
    "total_amount": TOTAL_AMOUNT_KEYWORDS,
}


def build_prefix_regex(keywords: List[str]) -> re.Pattern:
    """
    Builds an optimized regex pattern from a list of keywords, sorting by length
    descending to prevent shorter subphrases from masking longer phrases.
    """
    sorted_kws = sorted(keywords, key=lambda k: len(k.strip()), reverse=True)
    patterns: List[str] = []
    for kw in sorted_kws:
        escaped = re.escape(kw.strip()).replace(r"\ ", r"\s+")
        if re.search(r"\w$", kw.strip()):
            patterns.append(escaped + r"\b")
        else:
            patterns.append(escaped)
    pattern_str = r"(?i)\b(?:" + "|".join(patterns) + r")\s*[:.\-#]?\s*"
    return re.compile(pattern_str)


def find_matched_keyword(text: str, keywords: List[str]) -> Optional[str]:
    """Finds the longest matching keyword in the provided text snippet."""
    text_lower = text.lower()
    for kw in sorted(keywords, key=lambda k: len(k.strip()), reverse=True):
        if kw.lower() in text_lower:
            return kw
    return None


# -----------------------------------------------------------------------------
# Keyword Proximity & Multi-Signal Confidence Scoring
# -----------------------------------------------------------------------------

def calculate_keyword_proximity(
    line_distance: int = 0,
    char_distance: Optional[int] = None,
    intervening_lines: int = 0,
    keyword_bbox: Optional[OCRBoundingBox] = None,
    candidate_bbox: Optional[OCRBoundingBox] = None,
) -> float:
    """
    Calculates proximity score in [0.0, 1.0] between a keyword anchor and candidate value.

    Examples:
    - 'Invoice Number: INV-001' (small distance, same line) -> 1.0
    - 'Invoice Number' ... 'Subtotal' ... 'INV-001' (intervening lines) -> 0.20-0.30
    - Incorporates spatial pixel distance when OCR bounding boxes exist.
    """
    # 1. Base proximity based on line distance and intervening lines
    if intervening_lines > 0:
        base_prox = max(0.10, 0.70 - (0.20 * intervening_lines))
    elif line_distance == 0:
        if char_distance is not None:
            if char_distance <= 4:
                base_prox = 1.0
            elif char_distance <= 20:
                base_prox = max(0.75, 1.0 - (char_distance - 4) * 0.015)
            else:
                base_prox = max(0.40, 0.75 - (char_distance - 20) * 0.01)
        else:
            base_prox = 1.0
    elif line_distance == 1:
        base_prox = 0.80
    else:
        base_prox = max(0.10, 0.80 - (0.25 * (line_distance - 1)))

    # 2. Spatial bounding box proximity adjustment if both bboxes exist
    if keyword_bbox and candidate_bbox:
        dx = (
            max(0, candidate_bbox.left - (keyword_bbox.left + keyword_bbox.width))
            if candidate_bbox.left >= keyword_bbox.left
            else abs(candidate_bbox.left - keyword_bbox.left)
        )
        dy = (
            max(0, candidate_bbox.top - (keyword_bbox.top + keyword_bbox.height))
            if candidate_bbox.top >= keyword_bbox.top
            else abs(candidate_bbox.top - keyword_bbox.top)
        )
        pixel_dist = math.sqrt(dx * dx + dy * dy)

        if pixel_dist < 40:
            spatial_score = 1.0
        elif pixel_dist < 120:
            spatial_score = max(0.60, 1.0 - (pixel_dist - 40) * 0.005)
        else:
            spatial_score = max(0.10, 0.60 - (pixel_dist - 120) * 0.002)

        return round(0.50 * base_prox + 0.50 * spatial_score, 2)

    return round(base_prox, 2)


def compute_candidate_confidence(
    keyword_score: float,
    pattern_score: float,
    ocr_score: float = 1.0,
    position_score: float = 1.0,
    context_score: float = 1.0,
    penalty_score: float = 0.0,
    weights: Optional[Dict[str, float]] = None,
) -> Tuple[float, str]:
    """
    Transparently combines meaningful extraction signals into a confidence score:
    - keyword_score: Keyword strength / specificity (weight ~0.30)
    - pattern_score: Regex & structural formatting quality (weight ~0.25)
    - ocr_score: OCR engine confidence score (weight ~0.20)
    - position_score: Document layout & positional relevance (weight ~0.15)
    - context_score: Proximity to keyword & supporting indicators (weight ~0.10)
    - penalty_score: Negative evidence penalties (subtractive)

    Weights are centralized in EXTRACTION_WEIGHTS and easily configurable.
    The final confidence is strictly clamped between 0.0 and 1.0.

    Note: This is a field extraction confidence score, NOT a statistically calibrated probability.
    """
    w = weights or EXTRACTION_WEIGHTS
    kw_w = w.get("keyword", 0.30)
    pat_w = w.get("pattern", 0.25)
    ocr_w = w.get("ocr", 0.20)
    pos_w = w.get("position", 0.15)
    ctx_w = w.get("context", 0.10)

    # Normalize weights to sum to 1.0
    total_w = kw_w + pat_w + ocr_w + pos_w + ctx_w
    if total_w > 0 and abs(total_w - 1.0) > 0.001:
        kw_w /= total_w
        pat_w /= total_w
        ocr_w /= total_w
        pos_w /= total_w
        ctx_w /= total_w

    raw_weighted = (
        (kw_w * keyword_score)
        + (pat_w * pattern_score)
        + (ocr_w * ocr_score)
        + (pos_w * position_score)
        + (ctx_w * context_score)
    )
    final_score = max(0.0, min(1.0, raw_weighted - penalty_score))
    final_clamped = round(final_score, 2)

    breakdown = (
        f"signals: keyword={keyword_score:.2f}*{kw_w:.2f}, pattern={pattern_score:.2f}*{pat_w:.2f}, "
        f"ocr={ocr_score:.2f}*{ocr_w:.2f}, position={position_score:.2f}*{pos_w:.2f}, "
        f"context={context_score:.2f}*{ctx_w:.2f}"
    )
    if penalty_score > 0:
        breakdown += f" - penalty={penalty_score:.2f}"
    breakdown += f" -> final={final_clamped:.2f}"

    return final_clamped, breakdown


# -----------------------------------------------------------------------------
# Spatial & Bounding Box Heuristics
# (Evaluates left, top, width, height, x2, y2, line_num, block_num)
# -----------------------------------------------------------------------------

def is_same_line(
    box1: OCRBoundingBox,
    box2: OCRBoundingBox,
    line_num1: Optional[int] = None,
    line_num2: Optional[int] = None,
    block_num1: Optional[int] = None,
    block_num2: Optional[int] = None,
    tolerance_ratio: float = 0.5,
) -> bool:
    """
    Determines if two bounding boxes are on the same horizontal text line using
    left, top, width, height, x2, y2, and line_num/block_num metadata.
    """
    # 1. Structural line_num and block_num if available and valid
    if (
        line_num1 is not None
        and line_num2 is not None
        and line_num1 > 0
        and line_num2 > 0
        and block_num1 is not None
        and block_num2 is not None
        and block_num1 > 0
        and block_num2 > 0
    ):
        if block_num1 == block_num2 and line_num1 == line_num2:
            return True

    # 2. Geometric vertical overlap check
    top1, y2_1 = box1.top, getattr(box1, "y2", box1.top + box1.height)
    top2, y2_2 = box2.top, getattr(box2, "y2", box2.top + box2.height)
    h1 = max(1, box1.height, y2_1 - top1)
    h2 = max(1, box2.height, y2_2 - top2)
    min_h = min(h1, h2)

    vertical_overlap = max(0, min(y2_1, y2_2) - max(top1, top2))
    if vertical_overlap >= (min_h * tolerance_ratio):
        return True

    # 3. Vertical center distance check
    center1_y = top1 + (h1 / 2.0)
    center2_y = top2 + (h2 / 2.0)
    if abs(center1_y - center2_y) <= (min_h * 0.6):
        return True

    return False


def is_nearby_line(
    box1: OCRBoundingBox,
    box2: OCRBoundingBox,
    line_num1: Optional[int] = None,
    line_num2: Optional[int] = None,
    max_line_delta: int = 2,
    max_pixel_gap: int = 80,
) -> bool:
    """
    Determines if box2 is on an immediately adjacent or nearby line relative to box1.
    """
    if line_num1 is not None and line_num2 is not None and line_num1 > 0 and line_num2 > 0:
        if 0 < abs(line_num2 - line_num1) <= max_line_delta:
            return True

    top1, y2_1 = box1.top, getattr(box1, "y2", box1.top + box1.height)
    top2, y2_2 = box2.top, getattr(box2, "y2", box2.top + box2.height)

    vertical_gap = max(0, top2 - y2_1) if top2 >= y2_1 else max(0, top1 - y2_2)
    return vertical_gap <= max_pixel_gap


def is_above_below(
    box_above: OCRBoundingBox,
    box_below: OCRBoundingBox,
    max_vertical_gap: int = 150,
    max_horizontal_drift: int = 140,
) -> bool:
    """
    Determines if box_below is vertically positioned beneath box_above (e.g. vertical label layout).
    """
    y2_above = getattr(box_above, "y2", box_above.top + box_above.height)
    top_below = box_below.top

    # Below must be vertically lower down on page (greater y)
    if top_below < (box_above.top + (box_above.height * 0.4)):
        return False

    vertical_gap = top_below - y2_above
    if not (-10 <= vertical_gap <= max_vertical_gap):
        return False

    # Horizontal alignment check (box_below overlaps horizontally or within drift tolerance)
    x2_above = getattr(box_above, "x2", box_above.left + box_above.width)
    x2_below = getattr(box_below, "x2", box_below.left + box_below.width)

    horizontal_overlap = max(0, min(x2_above, x2_below) - max(box_above.left, box_below.left))
    if horizontal_overlap > 0:
        return True

    drift = min(abs(box_below.left - box_above.left), abs(box_below.left - x2_above))
    return drift <= max_horizontal_drift


def calculate_horizontal_proximity(
    box_left: OCRBoundingBox,
    box_right: OCRBoundingBox,
) -> float:
    """
    Calculates normalized horizontal proximity score in [0.0, 1.0] for elements on the same line.
    Handles small gaps ('Invoice No: INV-001') and large table gaps ('Grand Total        ₹11,300').
    """
    x2_left = getattr(box_left, "x2", box_left.left + box_left.width)
    gap = box_right.left - x2_left

    if gap < 0:
        return 0.80 if abs(gap) < 20 else 0.50

    if gap <= 40:
        return 1.0
    elif gap <= 120:
        return max(0.80, 1.0 - ((gap - 40) * 0.0025))
    elif gap <= 400:
        # Table gap scenario e.g. Grand Total left aligned, ₹11,300 right aligned
        return max(0.60, 0.80 - ((gap - 120) * 0.0007))
    else:
        return max(0.30, 0.60 - ((gap - 400) * 0.0005))


def is_top_of_page(
    box: OCRBoundingBox,
    threshold_pixels: int = 350,
) -> bool:
    """
    Determines if bounding box is located in the top section of the page (typical for Vendor/Company info).
    """
    return box.top < threshold_pixels


def group_words_into_lines(
    words: List[OCRWordData],
    vertical_tolerance: int = 8,
) -> List[List[OCRWordData]]:
    """
    Groups OCR word items into lines based on block_num, line_num, and spatial y-coordinates.
    Returns lines ordered top-to-bottom, each line sorted left-to-right.
    """
    if not words:
        return []

    # First attempt: grouping by (block_num, line_num) if meaningful
    grouped_by_meta: Dict[Tuple[int, int], List[OCRWordData]] = {}
    has_meta = any((w.line_num or 0) > 0 for w in words)
    if has_meta:
        for w in words:
            b_num = w.block_num or 1
            l_num = w.line_num or 1
            grouped_by_meta.setdefault((b_num, l_num), []).append(w)

        lines: List[List[OCRWordData]] = []
        for key in sorted(grouped_by_meta.keys(), key=lambda k: (min(w.bounding_box.top for w in grouped_by_meta[k]))):
            line_words = sorted(grouped_by_meta[key], key=lambda w: w.bounding_box.left)
            lines.append(line_words)
        return lines

    # Fallback: spatial clustering based on vertical overlap
    sorted_words = sorted(words, key=lambda w: (w.bounding_box.top, w.bounding_box.left))
    spatial_lines: List[List[OCRWordData]] = []

    for w in sorted_words:
        placed = False
        for line in spatial_lines:
            sample = line[0]
            if is_same_line(sample.bounding_box, w.bounding_box, tolerance_ratio=0.4):
                line.append(w)
                placed = True
                break
        if not placed:
            spatial_lines.append([w])

    for line in spatial_lines:
        line.sort(key=lambda w: w.bounding_box.left)
    spatial_lines.sort(key=lambda line: line[0].bounding_box.top)

    return spatial_lines


# -----------------------------------------------------------------------------
# Entity & Format Patterns
# -----------------------------------------------------------------------------

# Vendor entity indicators and business suffixes (Strategy C supporting patterns)
VENDOR_SUFFIXES = [
    r"\bpvt\.?\s*ltd\.?\b",
    r"\bprivate\s+limited\b",
    r"\bltd\.?\b",
    r"\blimited\b",
    r"\bllp\b",
    r"\binc\.?\b",
    r"\bincorporated\b",
    r"\bcorporation\b",
    r"\bcorp\.?\b",
    r"\bindustries\b",
    r"\benterprises\b",
    r"\btechnologies\b",
    r"\bsolutions\b",
    r"\bservices\b",
    r"\btraders\b",
    r"\bstores\b",
    r"\bstore\b",
    r"\bcompany\b",
    r"\bco\.?\b",
    r"\bgmbh\b",
    r"\btech\b",
    r"\bsystems\b",
    r"\bconsulting\b",
    r"\bconsultancy\b",
    r"\bagency\b",
    r"\bpharmacy\b",
    r"\bmedia\b",
    r"\blabs\b",
    r"\bgroup\b",
]
RE_VENDOR_SUFFIXES = re.compile("|".join(VENDOR_SUFFIXES), re.IGNORECASE)

# -----------------------------------------------------------------------------
# Centralized Field-Specific Exclusion Dictionaries & Disqualifiers
# (Avoid false positives: GSTIN, PAN, Phone, Bank Acct, IFSC, Date, PIN code, etc.)
# -----------------------------------------------------------------------------

# Vendor exclusions: avoid selecting Tax Invoice, Invoice, Bill, Quotation, Purchase Order, Invoice Number as company names
VENDOR_DISQUALIFIERS: List[str] = [
    r"^\s*tax\s+invoice\s*$",
    r"\btax\s+invoice\b",
    r"^\s*commercial\s+invoice\s*$",
    r"\bcommercial\s+invoice\b",
    r"^\s*proforma\s+invoice\s*$",
    r"\bproforma\s+invoice\b",
    r"^\s*invoice\s*$",
    r"^\s*bill\s*$",
    r"^\s*quotation\s*$",
    r"\bquotation\b",
    r"\bquote\b",
    r"\bestimate\b",
    r"^\s*purchase\s+order\s*$",
    r"\bpurchase\s+order\b",
    r"\bpo\s+number\b",
    r"\binvoice\s*number\b",
    r"\binvoice\s*no\.?\b",
    r"\binvoice\s*#\b",
    r"\binvoice\s*date\b",
    r"\bbill\s*number\b",
    r"\bbill\s*no\.?\b",
    r"\bbill\s*date\b",
    r"\bbill\s+to\b",
    r"\bship\s+to\b",
    r"\binvoice\s+to\b",
    r"\bcustomer\b",
    r"\bclient\b",
    r"\bconsignee\b",
    r"^\s*receipt\s*$",
    r"\boriginal\s+for\s+recipient\b",
    r"\bgstin\b",
    r"\bgst\s*no\b",
    r"\bpan\s*no\b",
    r"\bphone\b",
    r"\btel\b",
    r"\bmobile\b",
    r"\bemail\b",
    r"\bwebsite\b",
    r"\bwww\.\b",
    r"\bhttp\b",
    r"\baddress\b",
    r"\bp\.?o\.?\s*box\b",
    r"\broad\b",
    r"\bstreet\b",
    r"\bfloor\b",
    r"\bgrand\s*total\b",
    r"\bsubtotal\b",
    r"\btotal\b",
    r"\bamount\b",
    r"\bbalance\b",
]
RE_VENDOR_DISQUALIFIERS = re.compile("|".join(VENDOR_DISQUALIFIERS), re.IGNORECASE)

# Vendor explicit prefix anchors dynamically compiled from VENDOR_KEYWORDS
VENDOR_PREFIX_ANCHORS = [
    r"^(?:" + "|".join(re.escape(k.strip()).replace(r"\ ", r"\s+") for k in sorted(VENDOR_KEYWORDS, key=len, reverse=True)) + r")\s*[:\-]\s*(.+)$",
]

# Invoice Number prefix regex dynamically compiled from INVOICE_NUMBER_KEYWORDS
INVOICE_NUMBER_PREFIX_REGEX = build_prefix_regex(INVOICE_NUMBER_KEYWORDS)

# Invoice Number exclusions (avoid GSTIN, PAN, phone number, bank account, IFSC, date, PIN code)
RE_GSTIN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}\b", re.IGNORECASE)
RE_PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.IGNORECASE)
RE_PHONE_NUMBER = re.compile(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|\b[6-9]\d{9}\b")
RE_PIN_CODE = re.compile(r"\b\d{6}\b|\b\d{5}(?:-\d{4})?\b")
RE_BANK_ACCOUNT = re.compile(r"\b\d{11,18}\b")
RE_IFSC = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b", re.IGNORECASE)
RE_TAX_PERCENT = re.compile(r"^\d+(?:\.\d+)?%$")
RE_HSN_SAC = re.compile(r"\b(?:hsn|sac)\b", re.IGNORECASE)

# Generic candidate token for invoice numbers (alphanumeric with delimiters)
RE_INVOICE_NUM_CANDIDATE = re.compile(
    r"^[A-Za-z0-9]+(?:[-/_#][A-Za-z0-9]+)+$|^[A-Za-z]{1,5}[0-9]{3,10}$|^[0-9]{3,12}$"
)

# Date regex patterns (covers DD/MM/YYYY, YYYY-MM-DD, Month DD YYYY, DD-MMM-YYYY, etc.)
DATE_PATTERNS = [
    # 2026-09-12 or 2026/09/12
    r"\b\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\b",
    # 12/08/2026 or 12-08-2026 or 12.08.2026
    r"\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b",
    # 12 Aug 2026, 12 August 2026, 12-Aug-2026
    r"\b\d{1,2}[-\s](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*[-\s]\d{2,4}\b",
    # Aug 12, 2026 or August 12 2026
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{2,4}\b",
]
RE_COMBINED_DATE = re.compile(r"(?i)(" + "|".join(DATE_PATTERNS) + r")")

# Invoice Date prefix regex dynamically compiled from INVOICE_DATE_KEYWORDS
INVOICE_DATE_PREFIX_REGEX = build_prefix_regex(INVOICE_DATE_KEYWORDS)

# Invoice Date exclusions (due date, delivery date, order date, shipping date)
INVOICE_DATE_EXCLUSIONS: List[str] = [
    r"\bdue\s*(?:date)?\b",
    r"\bpayment\s*(?:due\s*)?date\b",
    r"\bdelivery\s*date\b",
    r"\bdelivered\s*(?:on|date)?\b",
    r"\border\s*date\b",
    r"\bpo\s*date\b",
    r"\bpurchase\s*order\s*date\b",
    r"\bshipping\s*date\b",
    r"\bship\s*date\b",
    r"\bdispatch\s*date\b",
    r"\bdispatched\s*(?:on)?\b",
    r"\bexpiry\s*date\b",
    r"\bvalid\s*(?:until|through)\b",
]
RE_INVOICE_DATE_EXCLUSIONS = re.compile("|".join(INVOICE_DATE_EXCLUSIONS), re.IGNORECASE)

# Total Amount prefix regexes dynamically compiled from TOTAL_AMOUNT_KEYWORDS
TOTAL_AMOUNT_STRONG_PREFIX = build_prefix_regex([k for k in TOTAL_AMOUNT_KEYWORDS if k != "total"])
TOTAL_AMOUNT_MODERATE_PREFIX = build_prefix_regex(["total"])

# Total Amount exclusions (avoid subtotal, tax amount, discount, unit price, quantity)
TOTAL_AMOUNT_EXCLUSIONS: List[str] = [
    r"\bsub\s*total\b",
    r"\bsub-total\b",
    r"\btax\s*amount\b",
    r"\btaxable\s*(?:amount|value)?\b",
    r"\bcgst\b",
    r"\bsgst\b",
    r"\bigst\b",
    r"\bvat\b",
    r"\btax\b",
    r"\bdiscount\b",
    r"\brebate\b",
    r"\bunit\s*price\b",
    r"\bunit\s*cost\b",
    r"\brate\b",
    r"\bprice\b",
    r"\bquantity\b",
    r"\bqty\b",
    r"\bhours\b",
    r"\bunits\b",
    r"\bnos\b",
    r"\bcount\b",
    r"\battendees\b",
    r"\bitems\b",
    r"\bpieces\b",
    r"\bpcs\b",
    r"\busers\b",
    r"\bpeople\b",
    r"\bmembers\b",
    r"\btickets\b",
]
RE_TOTAL_AMOUNT_EXCLUSIONS = re.compile("|".join(TOTAL_AMOUNT_EXCLUSIONS), re.IGNORECASE)
TOTAL_AMOUNT_DISQUALIFIERS = RE_TOTAL_AMOUNT_EXCLUSIONS

# Currency and number pattern (supports Western 1,000,000.00 and Indian 1,00,000.00 formats)
RE_CURRENCY_AMOUNT = re.compile(
    r"(?i)(?:[\$₹€£]|(?:rs\.?|inr|usd|eur|gbp)\s*)?\s*(\d+(?:,\d+)*(?:\.\d{1,2})?)"
)


# -----------------------------------------------------------------------------
# Clean Field-Specific Exclusion Helper Functions
# -----------------------------------------------------------------------------

def check_invoice_number_exclusions(val: str, line: str = "") -> Tuple[bool, Optional[str]]:
    """
    Exclusion logic for Invoice Number:
    Avoids GSTIN, PAN, phone number, bank account, IFSC, date, PIN code, etc.
    """
    cleaned_val = val.strip()
    if RE_GSTIN.search(cleaned_val) or (re.search(r"(?i)\bgstin\b", line) and not any(k in line.lower() for k in ["inv", "bill"])):
        return True, "GSTIN"
    if RE_PAN.search(cleaned_val) or (re.search(r"(?i)\bpan\s*(?:no|number)?\b", line) and not any(k in line.lower() for k in ["inv", "bill"])):
        return True, "PAN"
    if RE_PHONE_NUMBER.search(cleaned_val) or re.search(r"(?i)\b(?:phone|tel|mobile|mob|fax)\b", line):
        return True, "phone number"
    if RE_BANK_ACCOUNT.search(cleaned_val) or re.search(r"(?i)\b(?:a/c|account|bank|iban|swift)\b", line):
        return True, "bank account"
    if RE_IFSC.search(cleaned_val) or re.search(r"(?i)\bifsc\b", line):
        return True, "IFSC code"
    if RE_COMBINED_DATE.search(cleaned_val) or re.match(r"^(\d{1,4})[-/. ](\d{1,2})[-/. ](\d{1,4})$", cleaned_val):
        return True, "date"
    if (re.match(r"^\d{6}$", cleaned_val) or re.match(r"^\d{5}(?:-\d{4})?$", cleaned_val)) and re.search(
        r"(?i)\b(?:pin|zip|postal|road|street|nagar|marg|bangalore|mumbai|delhi|pune)\b", line
    ):
        return True, "PIN code"
    if RE_TAX_PERCENT.match(cleaned_val):
        return True, "tax percentage"
    if re.search(r"(?i)\b(?:hsn|sac)\b", line):
        return True, "HSN/SAC code"
    return False, None


def check_invoice_date_exclusions(line: str) -> Tuple[bool, Optional[str]]:
    """
    Exclusion logic for Invoice Date:
    Identifies if line context represents due date, delivery date, order date, shipping date, etc.
    """
    if re.search(r"(?i)\bdue\s*(?:date)?\b|\bpayment\s*(?:due\s*)?date\b", line):
        return True, "due date"
    if re.search(r"(?i)\bdelivery\s*date\b|\bdelivered\s*(?:on|date)?\b", line):
        return True, "delivery date"
    if re.search(r"(?i)\border\s*date\b|\bpo\s*date\b|\bpurchase\s*order\s*date\b", line):
        return True, "order date"
    if re.search(r"(?i)\bshipping\s*date\b|\bship\s*date\b|\bdispatch\s*date\b", line):
        return True, "shipping date"
    if re.search(r"(?i)\bexpiry\s*date\b|\bvalid\s*(?:until|through)\b", line):
        return True, "expiry date"
    return False, None


def check_total_amount_exclusions(line: str) -> Tuple[bool, Optional[str]]:
    """
    Exclusion logic for Total Amount:
    Avoids subtotal, tax amount, discount, unit price, quantity unless
    document structure indicates that it is actually the total.
    """
    # If line has explicit strong total indicator (e.g. 'Grand Total', 'Net Payable', 'Total Amount'), don't exclude
    if TOTAL_AMOUNT_STRONG_PREFIX.search(line):
        return False, None

    if re.search(r"(?i)\b(?:sub\s*total|sub-total)\b", line):
        return True, "subtotal"
    if re.search(r"(?i)\b(?:tax\s*amount|taxable|cgst|sgst|igst|vat|tax)\b", line):
        return True, "tax amount"
    if re.search(r"(?i)\b(?:discount|rebate)\b", line):
        return True, "discount"
    if re.search(r"(?i)\b(?:unit\s*price|unit\s*cost|rate|price)\b", line):
        return True, "unit price"
    if re.search(r"(?i)\b(?:quantity|qty|hours|units|nos|count|attendees|items|pieces|pcs|users|people|members|tickets)\b", line):
        return True, "quantity"
    return False, None


def check_vendor_name_exclusions(line: str) -> Tuple[bool, Optional[str]]:
    """
    Exclusion logic for Vendor Name:
    Avoids Tax Invoice, Invoice, Bill, Quotation, Purchase Order, Invoice Number as company names.
    """
    cleaned = line.strip().lower()
    for title in [
        "tax invoice",
        "invoice",
        "bill",
        "quotation",
        "quote",
        "purchase order",
        "po",
        "invoice number",
        "invoice no",
        "bill number",
        "bill no",
    ]:
        if cleaned == title or cleaned.startswith(f"{title}:") or cleaned.startswith(f"{title} -"):
            return True, title
    if RE_VENDOR_DISQUALIFIERS.search(cleaned):
        return True, "disqualified document keyword"
    return False, None


# -----------------------------------------------------------------------------
# Conservative Text Preprocessing
# -----------------------------------------------------------------------------

def prepare_text(raw_text: Optional[str]) -> Tuple[str, List[str]]:
    """
    Conservative text preprocessing for extraction.

    Preserves:
    - numbers (e.g. 11,300, 15499.00)
    - punctuation (e.g. ., :, -, /, #)
    - currency symbols (e.g. ₹, $, €, £, Rs.)
    - dates (e.g. 12/08/2026, 2026-09-12)
    - line boundaries (preserves carriage returns / newlines as line units)

    Allowed:
    - trimming leading and trailing whitespace per line
    - normalizing repeated horizontal spaces (e.g. '   ' -> ' ') where safe
    - creating line-based representations

    Explicitly Forbidden (deferred to later normalization & validation stages):
    - date normalization (e.g. converting DD/MM/YYYY to ISO format)
    - currency normalization (e.g. stripping currency symbols into ISO currency codes)
    - amount conversion (e.g. parsing numbers to floats/decimals)
    - business validation (e.g. GSTIN checksums or subtotal + tax = total math)
    - spelling correction (e.g. modifying raw OCR tokens)
    """
    if not raw_text:
        return "", []

    lines: List[str] = []
    for raw_line in raw_text.splitlines():
        trimmed = raw_line.strip()
        if trimmed:
            # Safely normalize repeated horizontal spaces without altering symbols or numbers
            normalized_line = re.sub(r"[ \t]+", " ", trimmed)
            lines.append(normalized_line)

    reconstructed_text = "\n".join(lines)
    return reconstructed_text, lines


class FieldCandidate:
    """
    Internal candidate representation holding extraction evidence, spatial bounding box,
    matched keyword, line number, multi-signal transparent score breakdown, and final confidence.
    """

    def __init__(
        self,
        field_name: str,
        value: str,
        confidence: float = 0.0,
        source: str = "keyword",
        matched_keyword: Optional[str] = None,
        matched_text: Optional[str] = None,
        bbox: Optional[OCRBoundingBox] = None,
        line_num: Optional[int] = None,
        evidence: Optional[str] = None,
        score: Optional[float] = None,
        ocr_confidence: Optional[float] = None,
        bounding_box: Optional[OCRBoundingBox] = None,
        page_number: Optional[int] = None,
        notes: Optional[str] = None,
        keyword_score: float = 0.0,
        pattern_score: float = 0.0,
        ocr_score: float = 1.0,
        position_score: float = 1.0,
        context_score: float = 1.0,
        penalty_score: float = 0.0,
    ) -> None:
        self.field_name = field_name
        self.value = value.strip()
        self.keyword_score = float(keyword_score)
        self.pattern_score = float(pattern_score)
        self.ocr_score = float(ocr_score)
        self.position_score = float(position_score)
        self.context_score = float(context_score)
        self.penalty_score = float(penalty_score)

        effective_score = confidence if score is None else score
        self.score = float(effective_score)
        self.confidence = self.get_clamped_confidence()
        self.source = source
        self.matched_keyword = matched_keyword
        self.matched_text = matched_text or value
        effective_bbox = bbox or bounding_box
        self.bbox = effective_bbox
        self.bounding_box = effective_bbox
        self.line_num = line_num
        self.evidence = evidence or notes or ""
        self.notes = self.evidence
        self.ocr_confidence = ocr_confidence
        self.page_number = page_number

    def get_clamped_confidence(self) -> float:
        """Returns normalized confidence score rounded to 2 decimal places in [0.0, 1.0]."""
        return round(max(0.0, min(1.0, self.score)), 2)

    def to_schema_candidate(self) -> FieldCandidateSchema:
        """Converts to Pydantic FieldCandidate schema."""
        return FieldCandidateSchema(
            field_name=self.field_name,
            value=self.value,
            confidence=self.get_clamped_confidence(),
            source=self.source,
            matched_keyword=self.matched_keyword,
            matched_text=self.matched_text,
            bbox=self.bbox,
            line_num=self.line_num,
            evidence=self.evidence,
        )

    def to_extracted_field(self) -> ExtractedField:
        """Converts to Pydantic ExtractedField schema."""
        return ExtractedField(
            value=self.value,
            confidence=self.get_clamped_confidence(),
            source=self.source,
            bounding_box=self.bbox,
            page_number=self.page_number,
        )


# Backward-compatibility alias
Candidate = FieldCandidate


# -----------------------------------------------------------------------------
# AI/LLM Extraction Provider Interface & Placeholder
# (Clean architectural separation: does NOT call any external AI API)
# -----------------------------------------------------------------------------

def reconcile_candidates(
    rule_candidates: Dict[str, List[FieldCandidate]],
    ai_results: Optional[Any] = None,
) -> Tuple[Dict[str, Optional[FieldCandidate]], Dict[str, List[FieldCandidate]]]:
    """
    Reconciliation architecture combining rule/heuristic candidates with AI provider outputs.
    Delegates to independent ReconciliationEngine in app.services.reconciliation.
    """
    selected, all_cands, _ = ReconciliationEngine.reconcile(
        rule_candidates=rule_candidates,
        ai_result=ai_results,
    )
    return selected, all_cands


class InvoiceExtractor:
    """
    Reusable Invoice Field Extractor service.

    Architectural Principles:
    - Fully independent from OCR engine implementations (does NOT call Tesseract, pdf2image, or OpenCV).
    - Accepts diverse input modalities:
        1. Pure digital PDF extracted text
        2. OCR raw extracted text
        3. OCR structured word and bounding-box data (as OCRWordData objects or dictionaries)
        4. Structured OCRResult or PDFParseResult models
    - Multi-signal extraction combining keyword matching, regular expressions,
      positional layout heuristics, and OCR confidence scoring.
    - AI/LLM Provider interface and reconciliation extension point (does NOT call any external API).
    """

    # Centralized configurable scoring weights
    EXTRACTION_WEIGHTS: Dict[str, float] = EXTRACTION_WEIGHTS

    # Reusable keyword proximity and transparent scoring methods
    calculate_keyword_proximity = staticmethod(calculate_keyword_proximity)
    calculate_proximity_score = staticmethod(calculate_keyword_proximity)
    compute_candidate_confidence = staticmethod(compute_candidate_confidence)

    # Spatial and bounding-box relationship heuristics
    is_same_line = staticmethod(is_same_line)
    is_nearby_line = staticmethod(is_nearby_line)
    is_above_below = staticmethod(is_above_below)
    calculate_horizontal_proximity = staticmethod(calculate_horizontal_proximity)
    is_top_of_page = staticmethod(is_top_of_page)
    group_words_into_lines = staticmethod(group_words_into_lines)

    # AI Extraction Provider & Reconciliation extension points
    AIExtractionProvider = AIExtractionProvider
    NoOpAIExtractionProvider = NoOpAIExtractionProvider
    default_ai_provider: AIExtractionProvider = NoOpAIExtractionProvider()
    reconcile_candidates = staticmethod(reconcile_candidates)

    # Conservative text preparation & centralized field exclusions
    prepare_text = staticmethod(prepare_text)
    check_invoice_number_exclusions = staticmethod(check_invoice_number_exclusions)
    check_invoice_date_exclusions = staticmethod(check_invoice_date_exclusions)
    check_total_amount_exclusions = staticmethod(check_total_amount_exclusions)
    check_vendor_name_exclusions = staticmethod(check_vendor_name_exclusions)
    is_disqualified_invoice_number = staticmethod(check_invoice_number_exclusions)
    is_disqualified_invoice_date = staticmethod(check_invoice_date_exclusions)
    is_disqualified_total_amount = staticmethod(check_total_amount_exclusions)
    is_disqualified_vendor_name = staticmethod(check_vendor_name_exclusions)

    @classmethod
    def extract(
        cls,
        document_input: Optional[Union[OCRResult, PDFParseResult, str, Dict[str, Any]]] = None,
        text: Optional[str] = None,
        words: Optional[Union[List[Any], Dict[int, List[Any]]]] = None,
        ocr_pages: Optional[List[OCRPageData]] = None,
        full_text: Optional[str] = None,
        ai_provider: Optional[AIExtractionProvider] = None,
        **kwargs: Any,
    ) -> InvoiceExtractionResult:
        """
        Primary universal extraction method.

        Supports calling patterns such as:
            extractor.extract(text=raw_text, words=ocr_words)
            extractor.extract(text=digital_pdf_text)
            extractor.extract(ocr_result)
            extractor.extract(pdf_parse_result)
            extractor.extract(document_text_string)

        Args:
            document_input: Optional structured OCRResult, PDFParseResult, raw text, or dict.
            text: Optional explicit document text.
            words: Optional OCR word items with bounding boxes and confidences.
            ocr_pages: Optional list of OCRPageData.
            full_text: Alias for text.

        Returns:
            InvoiceExtractionResult: Structured extracted fields, confidence scores,
                                    and extraction metrics.
        """
        effective_text = text if text is not None else full_text
        errors: List[str] = []
        try:
            doc_text, pages_word_map = cls._normalize_document_input(
                document_input=document_input,
                text=effective_text,
                words=words,
                ocr_pages=ocr_pages,
            )
        except Exception as exc:
            logger.error(f"Failed to normalize document input for extraction: {exc}", exc_info=True)
            return InvoiceExtractionResult(
                success=False,
                vendor_name=None,
                invoice_number=None,
                invoice_date=None,
                total_amount=None,
                field_confidence={
                    "vendor_name": 0.0,
                    "invoice_number": 0.0,
                    "invoice_date": 0.0,
                    "total_amount": 0.0,
                },
                fields_found=[],
                missing_fields=["vendor_name", "invoice_number", "invoice_date", "total_amount"],
                errors=[f"Input normalization error: {str(exc)}"],
            )

        if not doc_text or not doc_text.strip():
            return InvoiceExtractionResult(
                success=True,
                vendor_name=None,
                invoice_number=None,
                invoice_date=None,
                total_amount=None,
                field_confidence={
                    "vendor_name": 0.0,
                    "invoice_number": 0.0,
                    "invoice_date": 0.0,
                    "total_amount": 0.0,
                },
                fields_found=[],
                missing_fields=["vendor_name", "invoice_number", "invoice_date", "total_amount"],
                errors=["Document contains no text to extract fields from."],
            )

        # ---------------------------------------------------------------------
        # Extraction Pipeline
        # 1. Prepare text and OCR word data (conservative text preprocessing)
        #    Preserves numbers, punctuation, currency symbols, dates, line boundaries
        # ---------------------------------------------------------------------
        clean_text, lines = cls.prepare_text(doc_text)

        # ---------------------------------------------------------------------
        # 2. Detect field labels/keywords
        # 3. Generate candidates
        # 4. Apply regex/pattern detection
        # 5. Apply nearby-text heuristics
        # 6. Apply positional heuristics
        # 7. Use OCR confidence (supporting evidence, never blindly copied)
        # 8. Apply negative evidence (GSTIN, PAN, Phone, Bank, IFSC, Date, PIN code, etc.)
        # 9. Score candidates transparently
        # ---------------------------------------------------------------------
        # ---------------------------------------------------------------------
        # Field Extraction with error isolation per field
        # The extraction service must NEVER crash because one field fails
        # ---------------------------------------------------------------------
        vendor_cands: List[FieldCandidate] = []
        try:
            _, vendor_cands = cls._extract_vendor_name(lines, pages_word_map)
        except Exception as exc:
            logger.warning(f"Error during vendor_name extraction: {exc}", exc_info=True)
            errors.append(f"vendor_name extraction error: {str(exc)}")

        inv_num_cands: List[FieldCandidate] = []
        try:
            _, inv_num_cands = cls._extract_invoice_number(lines, pages_word_map)
        except Exception as exc:
            logger.warning(f"Error during invoice_number extraction: {exc}", exc_info=True)
            errors.append(f"invoice_number extraction error: {str(exc)}")

        inv_date_cands: List[FieldCandidate] = []
        try:
            _, inv_date_cands = cls._extract_invoice_date(lines, pages_word_map)
        except Exception as exc:
            logger.warning(f"Error during invoice_date extraction: {exc}", exc_info=True)
            errors.append(f"invoice_date extraction error: {str(exc)}")

        total_cands: List[FieldCandidate] = []
        try:
            _, total_cands = cls._extract_total_amount(lines, pages_word_map)
        except Exception as exc:
            logger.warning(f"Error during total_amount extraction: {exc}", exc_info=True)
            errors.append(f"total_amount extraction error: {str(exc)}")

        rule_candidates_map: Dict[str, List[FieldCandidate]] = {
            "vendor_name": vendor_cands,
            "invoice_number": inv_num_cands,
            "invoice_date": inv_date_cands,
            "total_amount": total_cands,
        }

        # ---------------------------------------------------------------------
        # 10. AI Extraction Provider extension point & Candidate Reconciliation
        # (Default is NoOpAIExtractionProvider: does NOT call any external API)
        # ---------------------------------------------------------------------
        vendor_candidate_val: Optional[str] = None
        if vendor_cands:
            valid_v = [c for c in vendor_cands if c.get_clamped_confidence() >= MIN_CONFIDENCE_THRESHOLD]
            if valid_v:
                vendor_candidate_val = max(valid_v, key=lambda c: c.get_clamped_confidence()).value

        ai_context: Dict[str, Any] = kwargs.get("context", {}) or {}
        if vendor_candidate_val and "vendor_name" not in ai_context:
            ai_context["vendor_name"] = vendor_candidate_val
        ai_context.setdefault("document_type", "invoice")
        ai_context.setdefault("rule_candidates", {
            f: [c.value for c in cands[:3]] for f, cands in rule_candidates_map.items()
        })

        provider = ai_provider or cls.default_ai_provider
        ai_response: Any = None
        if provider and not isinstance(provider, NoOpAIExtractionProvider):
            try:
                if hasattr(provider, "extract_invoice"):
                    ai_response = provider.extract_invoice(clean_text, context=ai_context)
                else:
                    ai_response = provider.extract(clean_text)
            except Exception as exc:
                logger.warning(f"AI provider extraction failed or threw exception: {exc}")
                errors.append(f"AI extraction provider warning: {str(exc)}")

        # ---------------------------------------------------------------------
        # 11. Select best candidate per field via ReconciliationEngine
        # ---------------------------------------------------------------------
        selected_candidates, reconciled_candidates_map, field_sources = ReconciliationEngine.reconcile(
            rule_candidates=rule_candidates_map,
            ai_result=ai_response,
        )

        # Assemble evaluated candidate schemas for transparency & debugging
        all_candidates_map: Dict[str, List[FieldCandidateSchema]] = {
            f: [c.to_schema_candidate() for c in cands]
            for f, cands in reconciled_candidates_map.items()
        }

        # Assemble extracted fields dictionary and confidence scores
        extracted_dict: Dict[str, ExtractedField] = {}
        confidence_dict: Dict[str, float] = {
            "vendor_name": 0.0,
            "invoice_number": 0.0,
            "invoice_date": 0.0,
            "total_amount": 0.0,
        }
        fields_found: List[str] = []
        missing_fields: List[str] = []
        final_values: Dict[str, Optional[str]] = {}

        for field_name in ["vendor_name", "invoice_number", "invoice_date", "total_amount"]:
            cands_for_field = reconciled_candidates_map.get(field_name, [])
            cand = selected_candidates.get(field_name)
            if cand and cand.get_clamped_confidence() >= MIN_CONFIDENCE_THRESHOLD:
                conf = cand.get_clamped_confidence()
                final_values[field_name] = cand.value
                confidence_dict[field_name] = conf
                fields_found.append(field_name)
                final_source = field_sources.get(field_name, cand.source)
                extracted_dict[field_name] = ExtractedField(
                    value=cand.value,
                    confidence=conf,
                    source=final_source,
                    bounding_box=cand.bounding_box,
                    page_number=cand.page_number,
                )
                logger.debug(
                    f"Field: {field_name}\n"
                    f"Candidates found: {len(cands_for_field)}\n"
                    f"Selected: {cand.value}\n"
                    f"Confidence: {conf:.2f}\n"
                    f"Source: {final_source}"
                )
            else:
                final_values[field_name] = None
                confidence_dict[field_name] = 0.0
                missing_fields.append(field_name)
                extracted_dict[field_name] = ExtractedField(
                    value=None,
                    confidence=0.0,
                    source=field_sources.get(field_name, "none"),
                    bounding_box=None,
                    page_number=None,
                )
                logger.debug(
                    f"Field: {field_name}\n"
                    f"Candidates found: {len(cands_for_field)}\n"
                    f"Selected: None\n"
                    f"Confidence: 0.00\n"
                    f"Source: None"
                )

        return InvoiceExtractionResult(
            success=True,
            vendor_name=final_values["vendor_name"],
            invoice_number=final_values["invoice_number"],
            invoice_date=final_values["invoice_date"],
            total_amount=final_values["total_amount"],
            field_confidence=confidence_dict,
            fields_found=fields_found,
            missing_fields=missing_fields,
            errors=errors,
            extracted_fields=extracted_dict,
            candidates=all_candidates_map,
            metadata={
                "line_count": len(lines),
                "has_ocr_words": bool(pages_word_map),
            },
        )

    # -------------------------------------------------------------------------
    # Recommended Modular Internal Helper Methods
    # -------------------------------------------------------------------------

    @classmethod
    def _find_keyword_matches(cls, line: str, keywords: List[str]) -> List[Tuple[str, int, int]]:
        """
        Locates all keyword occurrences in a line of text.
        Returns a list of (keyword, start_idx, end_idx) tuples sorted by match length descending.
        """
        matches: List[Tuple[str, int, int]] = []
        lower_line = line.lower()
        for kw in sorted(keywords, key=len, reverse=True):
            kw_clean = kw.strip().lower()
            pattern = r"\b" + re.escape(kw_clean) + r"\b"
            for m in re.finditer(pattern, lower_line):
                matches.append((kw, m.start(), m.end()))
        return matches

    @classmethod
    def _generate_candidates(
        cls,
        field_name: str,
        lines: List[str],
        pages_word_map: Optional[Dict[int, List[OCRWordData]]] = None,
    ) -> List[FieldCandidate]:
        """
        Modular candidate generation interface for a specific invoice field.
        """
        word_map = pages_word_map or {}
        if field_name == "vendor_name":
            return cls._extract_vendor_name(lines, word_map)[1]
        elif field_name == "invoice_number":
            return cls._extract_invoice_number(lines, word_map)[1]
        elif field_name == "invoice_date":
            return cls._extract_invoice_date(lines, word_map)[1]
        elif field_name == "total_amount":
            return cls._extract_total_amount(lines, word_map)[1]
        return []

    @classmethod
    def _score_candidate(cls, candidate: FieldCandidate) -> float:
        """
        Recomputes and returns candidate confidence using the multi-signal scoring model.
        """
        score, _ = compute_candidate_confidence(
            keyword_score=candidate.keyword_score,
            pattern_score=candidate.pattern_score,
            ocr_score=candidate.ocr_score,
            position_score=candidate.position_score,
            context_score=candidate.context_score,
            penalty_score=candidate.penalty_score,
        )
        return score

    @classmethod
    def _get_nearby_text(
        cls,
        lines: List[str],
        line_idx: int,
        window: int = 2,
        direction: str = "both",
    ) -> List[str]:
        """
        Retrieves text lines situated nearby line_idx within a window radius.
        direction can be 'above', 'below', or 'both'.
        """
        if not lines or line_idx < 0 or line_idx >= len(lines):
            return []

        if direction == "above":
            start = max(0, line_idx - window)
            return lines[start:line_idx]
        elif direction == "below":
            end = min(len(lines), line_idx + window + 1)
            return lines[line_idx + 1:end]
        else:  # both
            start = max(0, line_idx - window)
            end = min(len(lines), line_idx + window + 1)
            return [lines[i] for i in range(start, end) if i != line_idx]

    @classmethod
    def _calculate_text_distance(
        cls,
        line_distance: int,
        char_distance: Optional[int] = None,
        intervening_lines: int = 0,
    ) -> float:
        """
        Computes text-based proximity score between keyword and candidate value.
        """
        return calculate_keyword_proximity(
            line_distance=line_distance,
            char_distance=char_distance,
            intervening_lines=intervening_lines,
        )

    @classmethod
    def _calculate_spatial_distance(
        cls,
        box1: OCRBoundingBox,
        box2: OCRBoundingBox,
    ) -> float:
        """
        Computes Euclidean pixel distance between two OCR bounding boxes.
        """
        x2_1 = getattr(box1, "x2", box1.left + box1.width)
        y2_1 = getattr(box1, "y2", box1.top + box1.height)
        x2_2 = getattr(box2, "x2", box2.left + box2.width)
        y2_2 = getattr(box2, "y2", box2.top + box2.height)

        dx = max(0, box2.left - x2_1) if box2.left >= x2_1 else (max(0, box1.left - x2_2) if box1.left >= x2_2 else 0)
        dy = max(0, box2.top - y2_1) if box2.top >= y2_1 else (max(0, box1.top - y2_2) if box1.top >= y2_2 else 0)
        return float(math.sqrt(dx * dx + dy * dy))

    @classmethod
    def _get_ocr_confidence(
        cls,
        candidate_val: str,
        pages_word_map: Dict[int, List[OCRWordData]],
    ) -> Optional[float]:
        """
        Retrieves average normalized OCR confidence (0.0 to 1.0) for words matching candidate_val.
        """
        if not pages_word_map or not candidate_val:
            return None

        clean_val = candidate_val.strip().lower()
        matched_confs: List[float] = []

        for _, words in pages_word_map.items():
            for w in words:
                w_text = w.text.strip().lower()
                if w_text and (w_text == clean_val or clean_val in w_text or w_text in clean_val):
                    matched_confs.append(w.confidence / 100.0)

        if matched_confs:
            return sum(matched_confs) / len(matched_confs)
        return None

    @classmethod
    def _is_valid_invoice_number_candidate(cls, val: str, line: str = "") -> bool:
        """
        Validates whether val represents a plausible invoice number and is not disqualified
        (avoids GSTIN, PAN, phone, bank account, IFSC, date, PIN code).
        """
        if not cls._is_valid_invoice_number(val):
            return False
        disqualified, _ = check_invoice_number_exclusions(val, line)
        return not disqualified

    @classmethod
    def _is_valid_date_candidate(cls, val: str, line: str = "") -> bool:
        """
        Validates whether val is a plausible invoice date candidate and is not disqualified
        by due/delivery/order/shipping date context.
        """
        if not cls._is_valid_date_format(val):
            return False
        disqualified, _ = check_invoice_date_exclusions(line)
        return not disqualified

    @classmethod
    def _is_valid_total_candidate(cls, val: str, line: str = "") -> bool:
        """
        Validates whether val is a plausible total amount candidate and is not disqualified
        by subtotal/tax/discount/unit price/quantity context.
        """
        amt = cls._extract_amount_from_string(val)
        if not amt:
            return False
        disqualified, _ = check_total_amount_exclusions(line)
        return not disqualified

    @classmethod
    def _is_likely_vendor_candidate(cls, val: str, line: str = "") -> bool:
        """
        Validates whether val is a plausible vendor name candidate and is not disqualified
        by document titles (Tax Invoice, Invoice, Bill, Quotation, Purchase Order, Invoice Number).
        """
        cleaned = cls._clean_candidate_string(val)
        if not cleaned or len(cleaned) < 3 or len(cleaned) > 100:
            return False
        disqualified, _ = check_vendor_name_exclusions(cleaned)
        return not disqualified

    # -------------------------------------------------------------------------
    # 1. Vendor Name Extraction
    # -------------------------------------------------------------------------

    @classmethod
    def _extract_vendor_name(
        cls,
        lines: List[str],
        pages_word_map: Dict[int, List[OCRWordData]],
    ) -> Tuple[Optional[FieldCandidate], List[FieldCandidate]]:
        """
        Extracts Vendor Name by evaluating candidates using multiple complementary strategies:
        - Strategy A: Explicit vendor labels (vendor, vendor name, seller, seller name, supplier,
                      supplier name, from, billed from, company) inspecting nearby text.
        - Strategy B: Top-of-document heuristic (inspects first 10 lines near the top, avoiding
                      titles like Invoice, Tax Invoice, Bill, Quotation, Date, Invoice Number).
        - Strategy C: Company/business indicators (Pvt Ltd, Ltd, LLP, Inc, Corp, Technologies,
                      Solutions, Services, Traders, Stores, etc.) as supporting evidence (not mandatory).
        - Strategy D: OCR positional information (top-of-page layout, block/line grouping,
                      horizontal alignment, proximity to keywords, and OCR confidence).
        """
        candidates: List[FieldCandidate] = []

        # Strategy A — Explicit vendor labels (anchored to line start with delimiter)
        vendor_label_pattern = re.compile(
            r"^(?:\*\s*|-\s*)?(?:"
            + "|".join(re.escape(k.strip()).replace(r"\ ", r"\s+") for k in sorted(VENDOR_KEYWORDS, key=len, reverse=True))
            + r")\s*[:.\-]\s*(.*)$",
            re.IGNORECASE,
        )
        for idx, line in enumerate(lines[:15]):
            line_num = idx + 1
            m = vendor_label_pattern.match(line.strip())
            if m:
                matched_kw = find_matched_keyword(line, VENDOR_KEYWORDS) or "vendor"
                remainder = m.group(1).strip()
                cleaned = cls._clean_candidate_string(remainder)

                # Same-line right neighbor
                if cleaned and not RE_VENDOR_DISQUALIFIERS.search(cleaned):
                    has_suffix = bool(RE_VENDOR_SUFFIXES.search(cleaned))
                    kw_score = 1.0 if any(p in matched_kw.lower() for p in ["vendor", "seller", "supplier", "company"]) else 0.85
                    pat_score = 1.0 if has_suffix else 0.80
                    ocr_s = 1.0
                    pos_s = 1.0 if line_num <= 5 else 0.85
                    char_dist = len(remainder) - len(cleaned)
                    ctx_s = calculate_keyword_proximity(line_distance=0, char_distance=char_dist)
                    score, breakdown = compute_candidate_confidence(
                        keyword_score=kw_score,
                        pattern_score=pat_score,
                        ocr_score=ocr_s,
                        position_score=pos_s,
                        context_score=ctx_s,
                        penalty_score=0.0,
                    )
                    evidence_notes = [
                        breakdown,
                        f"Strategy A: Matched explicit label '{matched_kw}' on line {line_num} (same-line, prox={ctx_s:.2f})",
                    ]
                    if has_suffix:
                        evidence_notes.append("Strategy C: contains company/business indicator")
                    candidates.append(
                        FieldCandidate(
                            field_name="vendor_name",
                            value=cleaned,
                            confidence=score,
                            source="keyword",
                            matched_keyword=matched_kw,
                            matched_text=line,
                            line_num=line_num,
                            evidence="; ".join(evidence_notes),
                            keyword_score=kw_score,
                            pattern_score=pat_score,
                            ocr_score=ocr_s,
                            position_score=pos_s,
                            context_score=ctx_s,
                            penalty_score=0.0,
                        )
                    )
                # Next-line inspection (vertical label)
                elif idx + 1 < len(lines):
                    next_line = lines[idx + 1].strip()
                    cleaned_next = cls._clean_candidate_string(next_line)
                    if cleaned_next and not RE_VENDOR_DISQUALIFIERS.search(cleaned_next):
                        has_suffix = bool(RE_VENDOR_SUFFIXES.search(cleaned_next))
                        kw_score = 1.0 if any(p in matched_kw.lower() for p in ["vendor", "seller", "supplier", "company"]) else 0.85
                        pat_score = 1.0 if has_suffix else 0.80
                        ocr_s = 1.0
                        pos_s = 1.0 if line_num <= 5 else 0.85
                        ctx_s = calculate_keyword_proximity(line_distance=1)
                        score, breakdown = compute_candidate_confidence(
                            keyword_score=kw_score,
                            pattern_score=pat_score,
                            ocr_score=ocr_s,
                            position_score=pos_s,
                            context_score=ctx_s,
                            penalty_score=0.0,
                        )
                        evidence_notes = [
                            breakdown,
                            f"Strategy A: Matched explicit label '{matched_kw}' on line {line_num} (next-line inspection, prox={ctx_s:.2f})",
                        ]
                        if has_suffix:
                            evidence_notes.append("Strategy C: contains company/business indicator")
                        candidates.append(
                            FieldCandidate(
                                field_name="vendor_name",
                                value=cleaned_next,
                                confidence=score,
                                source="positional",
                                matched_keyword=matched_kw,
                                matched_text=next_line,
                                line_num=line_num + 1,
                                evidence="; ".join(evidence_notes),
                                keyword_score=kw_score,
                                pattern_score=pat_score,
                                ocr_score=ocr_s,
                                position_score=pos_s,
                                context_score=ctx_s,
                                penalty_score=0.0,
                            )
                        )

        # Strategy B — Top-of-document heuristic
        header_lines = lines[:10]
        for idx, line in enumerate(header_lines):
            line_num = idx + 1
            raw_line = line.strip()
            if raw_line.endswith((".", "!", "?")):
                continue

            # If line matches explicit vendor label, skip it here (Strategy A handles it cleanly)
            if vendor_label_pattern.match(raw_line):
                continue

            cleaned = cls._clean_candidate_string(raw_line)
            if not cleaned or len(cleaned) < 3 or len(cleaned) > 100:
                continue

            # Strategy B: Avoid selecting Invoice, Tax Invoice, Bill, Quotation, Invoice Number, Date, etc.
            if RE_VENDOR_DISQUALIFIERS.search(cleaned):
                continue
            if RE_COMBINED_DATE.search(cleaned) or INVOICE_NUMBER_PREFIX_REGEX.search(cleaned):
                continue

            words_in_line = cleaned.split()
            if len(words_in_line) > 8:
                continue

            # Strategy C — Company/business indicators (supporting evidence, not mandatory)
            has_suffix = bool(RE_VENDOR_SUFFIXES.search(cleaned))

            # Positional score based on top position
            pos_s = max(0.60, 1.0 - (idx * 0.05))
            pat_score = 1.0 if has_suffix else (0.85 if (cleaned.isupper() or cleaned.istitle()) else 0.65)
            ocr_s = 1.0
            kw_score = 0.25  # Heuristic without explicit label

            # Check if adjacent following lines look like Company Address, GSTIN, Phone, Email
            following_lines = " ".join(header_lines[idx + 1:idx + 4]).lower()
            has_address = bool(re.search(r"\b(?:gstin|gst\s*no|pan|phone|tel|email|road|street|nagar|park|floor|box|suite|bangalore|mumbai|delhi)\b", following_lines))
            
            # Accuracy-focused rule: Do NOT assume first line = vendor unless supporting contextual evidence exists.
            # Require either a company/business indicator (has_suffix) OR confirmed adjacent address/contact/GSTIN lines (has_address).
            if not has_suffix and not has_address:
                continue

            ctx_s = 0.95 if has_address else 0.60

            penalty = 0.30 if re.search(r"\d{4,}", cleaned) else 0.0

            score, breakdown = compute_candidate_confidence(
                keyword_score=kw_score,
                pattern_score=pat_score,
                ocr_score=ocr_s,
                position_score=pos_s,
                context_score=ctx_s,
                penalty_score=penalty,
            )
            evidence_notes = [
                breakdown,
                f"Strategy B: Top-of-document line {line_num} (pos={pos_s:.2f})",
            ]
            if has_suffix:
                evidence_notes.append("Strategy C: contains company/business indicator")
            if has_address:
                evidence_notes.append("Strategy B: confirmed by adjacent address/contact/GSTIN lines")

            candidates.append(
                FieldCandidate(
                    field_name="vendor_name",
                    value=cleaned,
                    confidence=score,
                    source="combined" if has_suffix else "positional",
                    matched_keyword=None,
                    matched_text=raw_line,
                    line_num=line_num,
                    evidence="; ".join(evidence_notes),
                    keyword_score=kw_score,
                    pattern_score=pat_score,
                    ocr_score=ocr_s,
                    position_score=pos_s,
                    context_score=ctx_s,
                    penalty_score=penalty,
                )
            )

        # Strategy D — OCR positional information (bounding boxes, top of page 1, horizontal alignment)
        if pages_word_map and 1 in pages_word_map:
            page_words = pages_word_map[1]
            grouped_lines = group_words_into_lines(page_words)

            for words_sorted in grouped_lines:
                if not words_sorted:
                    continue
                min_top = min(w.bounding_box.top for w in words_sorted)
                if not is_top_of_page(words_sorted[0].bounding_box, threshold_pixels=350):
                    continue
                ln = words_sorted[0].line_num or 1
                line_text = " ".join(w.text for w in words_sorted).strip()
                cleaned_line = cls._clean_candidate_string(line_text)
                if not cleaned_line or len(cleaned_line) < 3 or len(cleaned_line) > 100:
                    continue
                if RE_VENDOR_DISQUALIFIERS.search(cleaned_line):
                    continue
                if RE_COMBINED_DATE.search(cleaned_line) or INVOICE_NUMBER_PREFIX_REGEX.search(cleaned_line):
                    continue

                avg_conf = sum(w.confidence for w in words_sorted) / len(words_sorted) / 100.0
                min_top = min(w.bounding_box.top for w in words_sorted)
                has_suffix = bool(RE_VENDOR_SUFFIXES.search(cleaned_line))
                
                # Check adjacent OCR text for company address/contact/GSTIN context
                page_text_sample = " ".join(w.text for w in page_words[:30]).lower()
                has_address = bool(re.search(r"\b(?:gstin|gst\s*no|pan|phone|tel|email|road|street|nagar|park|floor|box|suite|bangalore|mumbai|delhi)\b", page_text_sample))
                
                # Accuracy-focused rule: Require supporting contextual evidence
                if not has_suffix and not has_address:
                    continue

                composite_bbox = OCRBoundingBox(
                    left=min(w.bounding_box.left for w in words_sorted),
                    top=min_top,
                    width=max(w.bounding_box.x2 for w in words_sorted) - min(w.bounding_box.left for w in words_sorted),
                    height=max(w.bounding_box.height for w in words_sorted),
                    x2=max(w.bounding_box.x2 for w in words_sorted),
                    y2=max(w.bounding_box.y2 for w in words_sorted),
                )
                kw_score = 0.35
                pat_score = 1.0 if has_suffix else 0.80
                ocr_s = avg_conf
                pos_s = 1.0 if min_top < 200 else 0.85
                ctx_s = 0.85  # horizontal line alignment
                score, breakdown = compute_candidate_confidence(
                    keyword_score=kw_score,
                    pattern_score=pat_score,
                    ocr_score=ocr_s,
                    position_score=pos_s,
                    context_score=ctx_s,
                    penalty_score=0.0,
                )
                evidence_notes = [
                    breakdown,
                    f"Strategy D: OCR Page 1 top={min_top}px (conf={avg_conf:.2f})",
                    "horizontal line alignment",
                ]
                if has_suffix:
                    evidence_notes.append("Strategy C: contains company/business indicator")

                candidates.append(
                    FieldCandidate(
                        field_name="vendor_name",
                        value=cleaned_line,
                        confidence=score,
                        source="combined",
                        matched_keyword=None,
                        matched_text=line_text,
                        bbox=composite_bbox,
                        line_num=ln,
                        evidence="; ".join(evidence_notes),
                        ocr_confidence=avg_conf,
                        bounding_box=composite_bbox,
                        page_number=1,
                        keyword_score=kw_score,
                        pattern_score=pat_score,
                        ocr_score=ocr_s,
                        position_score=pos_s,
                        context_score=ctx_s,
                        penalty_score=0.0,
                    )
                )

        # Strategy D: Enrich existing candidates with OCR bounding boxes
        if pages_word_map:
            cls._enrich_candidates_with_ocr_boxes(candidates, pages_word_map)

        if not candidates:
            return None, []

        # Deduplicate and boost candidates with multiple corroborating detections
        val_occurrences: Dict[str, int] = {}
        for c in candidates:
            val_occurrences[c.value.lower()] = val_occurrences.get(c.value.lower(), 0) + 1
        for c in candidates:
            if val_occurrences[c.value.lower()] > 1:
                c.score = min(1.0, c.score + 0.05)
                c.evidence += f"; reinforced across {val_occurrences[c.value.lower()]} strategies/occurrences"

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[0], candidates

    # -------------------------------------------------------------------------
    # 2. Invoice Number Extraction
    # -------------------------------------------------------------------------

    @classmethod
    def _extract_invoice_number(
        cls,
        lines: List[str],
        pages_word_map: Dict[int, List[OCRWordData]],
    ) -> Tuple[Optional[FieldCandidate], List[FieldCandidate]]:
        """
        Extracts Invoice Number by evaluating candidates using multiple complementary strategies:
        - Strategy 1: Keyword matching ("Invoice Number:", "Invoice No:", "Invoice #:", "Bill No:")
                      with nearby text extraction (same-line right or vertical next-line).
        - Strategy 2: Robust invoice-number pattern matching:
                      INV-001, INV/2026/001, INV2026001, 2026-INV-001, ABC-12345, 12345, B-10025.
        - Strategy 3: Spatial layout & OCR positional relationship (horizontal right-neighbor
                      and vertical neighbor beneath keyword, with OCR confidence).
        - Strategy 4: Disqualification & penalties: penalizes candidates that resemble
                      GSTIN, phone numbers, PIN codes, dates, bank account numbers, tax %,
                      or HSN/SAC product codes.
        """
        candidates: List[FieldCandidate] = []

        # Strategy 1: Keyword matching & nearby text
        for idx, line in enumerate(lines):
            line_num = idx + 1
            match = INVOICE_NUMBER_PREFIX_REGEX.search(line)
            if not match:
                continue

            matched_kw = find_matched_keyword(line[:match.end()], INVOICE_NUMBER_KEYWORDS)

            # 1a. Value on same line to right of keyword
            remainder = line[match.end():].strip()
            val = cls._clean_invoice_number_token(remainder)

            if val and cls._is_valid_invoice_number(val):
                char_dist = len(remainder) - len(remainder.lstrip(" :.-#"))
                score, notes, s_dict = cls._score_and_penalize_invoice_number(
                    val,
                    line,
                    matched_kw=matched_kw,
                    source="keyword",
                    line_distance=0,
                    char_distance=char_dist,
                    line_num=line_num,
                )
                notes.append(f"same-line extraction line {line_num}")
                candidates.append(
                    FieldCandidate(
                        field_name="invoice_number",
                        value=val,
                        confidence=score,
                        source="keyword",
                        matched_keyword=matched_kw,
                        matched_text=line,
                        line_num=line_num,
                        evidence="; ".join(notes),
                        keyword_score=s_dict["keyword"],
                        pattern_score=s_dict["pattern"],
                        ocr_score=s_dict["ocr"],
                        position_score=s_dict["position"],
                        context_score=s_dict["context"],
                        penalty_score=s_dict["penalty"],
                    )
                )

            # 1b. Value on subsequent lines (vertical label format or intervening lines)
            if not (val and cls._is_valid_invoice_number(val)):
                for offset in range(1, min(5, len(lines) - idx)):
                    target_line = lines[idx + offset].strip()
                    val_sub = cls._clean_invoice_number_token(target_line)
                    if val_sub and cls._is_valid_invoice_number(val_sub):
                        intervening = offset - 1
                        score, notes, s_dict = cls._score_and_penalize_invoice_number(
                            val_sub,
                            target_line,
                            matched_kw=matched_kw,
                            source="positional",
                            line_distance=offset,
                            intervening_lines=intervening,
                            line_num=line_num + offset,
                        )
                        if intervening > 0:
                            notes.append(f"intervening lines={intervening} between keyword and candidate line {line_num + offset}")
                        else:
                            notes.append(f"next-line fallback line {line_num + 1}")
                        candidates.append(
                            FieldCandidate(
                                field_name="invoice_number",
                                value=val_sub,
                                confidence=score,
                                source="positional",
                                matched_keyword=matched_kw,
                                matched_text=target_line,
                                line_num=line_num + offset,
                                evidence="; ".join(notes),
                                keyword_score=s_dict["keyword"],
                                pattern_score=s_dict["pattern"],
                                ocr_score=s_dict["ocr"],
                                position_score=s_dict["position"],
                                context_score=s_dict["context"],
                                penalty_score=s_dict["penalty"],
                            )
                        )
                        break

        # Strategy 3: Spatial word detection via OCR Bounding Boxes
        if pages_word_map:
            spatial_cands = cls._extract_invoice_number_spatial(pages_word_map)
            candidates.extend(spatial_cands)
            cls._enrich_candidates_with_ocr_boxes(candidates, pages_word_map)

        # Strategy 2: Robust pattern scanning across the header section
        # Formats: INV-001, INV/2026/001, INV2026001, 2026-INV-001, ABC-12345, 12345, B-10025
        standalone_patterns = [
            r"\b(?:INV|BILL|TAX|REC)(?:[-_/][A-Z0-9]{1,15}){1,3}\b",
            r"\b\d{4}[-_/](?:INV|BILL)[-_/][A-Z0-9]{2,10}\b",
            r"\b(?:INV|BILL)\d{4,10}\b",
            r"\b[A-Z]{1,5}[-_/]\d{3,10}\b",
            r"\b[A-Z0-9]{2,5}(?:[-_/][A-Z0-9]{1,10}){1,3}\b",
        ]
        re_standalone = re.compile("|".join(standalone_patterns), re.IGNORECASE)

        for idx, line in enumerate(lines[:25]):
            line_num = idx + 1
            for m_tok in re_standalone.finditer(line):
                tok_val = cls._clean_invoice_number_token(m_tok.group(0))
                if tok_val and cls._is_valid_invoice_number(tok_val):
                    if not any(c.value == tok_val for c in candidates):
                        score, notes, s_dict = cls._score_and_penalize_invoice_number(
                            tok_val,
                            line,
                            matched_kw=None,
                            source="regex",
                            line_distance=0,
                            line_num=line_num,
                        )
                        notes.append(f"robust standalone pattern match line {line_num}")
                        candidates.append(
                            FieldCandidate(
                                field_name="invoice_number",
                                value=tok_val,
                                confidence=score,
                                source="regex",
                                matched_keyword=None,
                                matched_text=line,
                                line_num=line_num,
                                evidence="; ".join(notes),
                                keyword_score=s_dict["keyword"],
                                pattern_score=s_dict["pattern"],
                                ocr_score=s_dict["ocr"],
                                position_score=s_dict["position"],
                                context_score=s_dict["context"],
                                penalty_score=s_dict["penalty"],
                            )
                        )

        if not candidates:
            return None, []

        # Boost candidates that appear multiple times or across multiple keywords
        val_occurrences: Dict[str, int] = {}
        for c in candidates:
            val_occurrences[c.value] = val_occurrences.get(c.value, 0) + 1
        for c in candidates:
            if val_occurrences[c.value] > 1:
                c.score = min(1.0, c.score + 0.05)
                c.evidence += f"; reinforced by {val_occurrences[c.value]} matching occurrences"

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[0], candidates

    @classmethod
    def _extract_invoice_number_spatial(
        cls,
        pages_word_map: Dict[int, List[OCRWordData]],
    ) -> List[FieldCandidate]:
        """Detects invoice number using spatial OCR bounding box layout (horizontal & vertical relationship)."""
        spatial_candidates: List[FieldCandidate] = []
        for page_num, words in pages_word_map.items():
            for i, w in enumerate(words):
                if INVOICE_NUMBER_PREFIX_REGEX.search(w.text):
                    matched_kw = find_matched_keyword(w.text, INVOICE_NUMBER_KEYWORDS) or "invoice no"

                    # 1. Horizontal right-neighbor on same line
                    for j in range(i + 1, min(i + 8, len(words))):
                        next_w = words[j]
                        if next_w.bounding_box.left > w.bounding_box.left and is_same_line(
                            w.bounding_box,
                            next_w.bounding_box,
                            line_num1=w.line_num,
                            line_num2=next_w.line_num,
                            block_num1=w.block_num,
                            block_num2=next_w.block_num,
                        ):
                            token = cls._clean_invoice_number_token(next_w.text)
                            if token and cls._is_valid_invoice_number(token):
                                conf = next_w.confidence / 100.0
                                horiz_prox = calculate_horizontal_proximity(w.bounding_box, next_w.bounding_box)
                                score, notes, s_dict = cls._score_and_penalize_invoice_number(
                                    token,
                                    next_w.text,
                                    matched_kw=matched_kw,
                                    source="spatial",
                                    line_distance=0,
                                    keyword_bbox=w.bounding_box,
                                    candidate_bbox=next_w.bounding_box,
                                    ocr_confidence=conf,
                                    line_num=next_w.line_num,
                                )
                                notes.append(f"Spatial OCR horizontal neighbor on page {page_num} (prox={horiz_prox:.2f})")
                                spatial_candidates.append(
                                    FieldCandidate(
                                        field_name="invoice_number",
                                        value=token,
                                        confidence=score,
                                        source="combined",
                                        matched_keyword=matched_kw,
                                        matched_text=f"{w.text} {next_w.text}",
                                        bbox=next_w.bounding_box,
                                        line_num=next_w.line_num,
                                        ocr_confidence=conf,
                                        bounding_box=next_w.bounding_box,
                                        page_number=page_num,
                                        evidence="; ".join(notes),
                                        keyword_score=s_dict["keyword"],
                                        pattern_score=s_dict["pattern"],
                                        ocr_score=s_dict["ocr"],
                                        position_score=s_dict["position"],
                                        context_score=s_dict["context"],
                                        penalty_score=s_dict["penalty"],
                                    )
                                )
                                break

                    # 2. Vertical neighbor directly beneath keyword (above/below relationship)
                    for j in range(i + 1, min(i + 12, len(words))):
                        below_w = words[j]
                        if is_above_below(w.bounding_box, below_w.bounding_box):
                            token = cls._clean_invoice_number_token(below_w.text)
                            if token and cls._is_valid_invoice_number(token):
                                conf = below_w.confidence / 100.0
                                score, notes, s_dict = cls._score_and_penalize_invoice_number(
                                    token,
                                    below_w.text,
                                    matched_kw=matched_kw,
                                    source="spatial",
                                    line_distance=1,
                                    keyword_bbox=w.bounding_box,
                                    candidate_bbox=below_w.bounding_box,
                                    ocr_confidence=conf,
                                    line_num=below_w.line_num,
                                )
                                notes.append(f"Spatial OCR vertical neighbor on page {page_num} (above/below layout)")
                                spatial_candidates.append(
                                    FieldCandidate(
                                        field_name="invoice_number",
                                        value=token,
                                        confidence=score,
                                        source="combined",
                                        matched_keyword=matched_kw,
                                        matched_text=f"{w.text} / {below_w.text}",
                                        bbox=below_w.bounding_box,
                                        line_num=below_w.line_num,
                                        ocr_confidence=conf,
                                        bounding_box=below_w.bounding_box,
                                        page_number=page_num,
                                        evidence="; ".join(notes),
                                        keyword_score=s_dict["keyword"],
                                        pattern_score=s_dict["pattern"],
                                        ocr_score=s_dict["ocr"],
                                        position_score=s_dict["position"],
                                        context_score=s_dict["context"],
                                        penalty_score=s_dict["penalty"],
                                    )
                                )
                                break
        return spatial_candidates

    @classmethod
    def _enrich_candidates_with_ocr_boxes(
        cls,
        candidates: List[FieldCandidate],
        pages_word_map: Dict[int, List[OCRWordData]],
    ) -> None:
        """
        Enriches textual candidates with OCR spatial bounding boxes, page numbers,
        and OCR confidence scores if matching word tokens are found in pages_word_map.
        """
        if not pages_word_map or not candidates:
            return

        for cand in candidates:
            cand_val = cand.value.strip().lower()
            if not cand.bbox:
                for p_num, words in pages_word_map.items():
                    for w in words:
                        w_text = w.text.strip().lower()
                        if w_text and (w_text == cand_val or cand_val in w_text or w_text in cand_val):
                            cand.bbox = w.bounding_box
                            cand.bounding_box = w.bounding_box
                            cand.page_number = p_num
                            if cand.ocr_confidence is None:
                                cand.ocr_confidence = w.confidence / 100.0
                                cand.ocr_score = cand.ocr_confidence
                                new_conf, new_breakdown = compute_candidate_confidence(
                                    keyword_score=cand.keyword_score,
                                    pattern_score=cand.pattern_score,
                                    ocr_score=cand.ocr_score,
                                    position_score=cand.position_score,
                                    context_score=cand.context_score,
                                    penalty_score=cand.penalty_score,
                                )
                                cand.score = new_conf
                                cand.confidence = new_conf
                                cand.evidence += f"; enriched with OCR conf {w.confidence:.1f}% ({new_breakdown})"
                            cand.evidence += f"; spatial bounding box linked from page {p_num}"
                            break
                    if cand.bbox:
                        break

    # -------------------------------------------------------------------------
    # 3. Invoice Date Extraction
    # -------------------------------------------------------------------------

    @classmethod
    def _extract_invoice_date(
        cls,
        lines: List[str],
        pages_word_map: Dict[int, List[OCRWordData]],
    ) -> Tuple[Optional[FieldCandidate], List[FieldCandidate]]:
        """
        Extracts Invoice Date by evaluating all detected candidates using:
        - Explicit keyword anchors ("Invoice Date:", "Date of Issue:", "Bill Date:")
        - Proximity matching (same-line right or next-line below)
        - Calendar sanity checks (valid days, months, reasonable years)
        - OCR word confidence if available
        """
        candidates: List[FieldCandidate] = []

        # Strategy 1: Explicit Date Keyword Anchors
        for idx, line in enumerate(lines):
            line_num = idx + 1
            is_disq_date, disq_date_type = check_invoice_date_exclusions(line)

            match = INVOICE_DATE_PREFIX_REGEX.search(line)
            if not match:
                continue

            matched_kw = find_matched_keyword(line[:match.end()], INVOICE_DATE_KEYWORDS) or "date"

            # Check same line
            remainder = line[match.end():].strip()
            date_match = RE_COMBINED_DATE.search(remainder)
            if date_match:
                raw_date = date_match.group(1).strip(" ,;:")
                if cls._is_valid_date_format(raw_date):
                    is_primary = any(p in matched_kw.lower() for p in ["invoice", "issue", "bill"])
                    kw_s = 1.0 if is_primary else 0.80
                    pat_s = 1.0
                    ocr_s = 1.0
                    pos_s = 1.0 if line_num <= 15 else 0.80
                    char_dist = len(remainder) - len(remainder.lstrip(" :.-#"))
                    ctx_s = calculate_keyword_proximity(line_distance=0, char_distance=char_dist)
                    penalty_s = 0.65 if is_disq_date else 0.0
                    score, breakdown = compute_candidate_confidence(
                        keyword_score=kw_s,
                        pattern_score=pat_s,
                        ocr_score=ocr_s,
                        position_score=pos_s,
                        context_score=ctx_s,
                        penalty_score=penalty_s,
                    )
                    evidence_msg = f"{breakdown}; Matched keyword '{matched_kw}' on line {line_num} (same-line, prox={ctx_s:.2f})"
                    if is_disq_date:
                        evidence_msg += f" (penalized: context indicates {disq_date_type})"
                    candidates.append(
                        FieldCandidate(
                            field_name="invoice_date",
                            value=raw_date,
                            confidence=score,
                            source="keyword",
                            matched_keyword=matched_kw,
                            matched_text=line,
                            line_num=line_num,
                            evidence=evidence_msg,
                            keyword_score=kw_s,
                            pattern_score=pat_s,
                            ocr_score=ocr_s,
                            position_score=pos_s,
                            context_score=ctx_s,
                            penalty_score=penalty_s,
                        )
                    )

            # Check subsequent lines (vertical label or lookahead)
            elif not date_match:
                for offset in range(1, min(4, len(lines) - idx)):
                    next_line = lines[idx + offset].strip()
                    is_disq_next, disq_next_type = check_invoice_date_exclusions(next_line)
                    date_match_next = RE_COMBINED_DATE.search(next_line)
                    if date_match_next:
                        raw_date = date_match_next.group(1).strip(" ,;:")
                        if cls._is_valid_date_format(raw_date):
                            is_primary = any(p in matched_kw.lower() for p in ["invoice", "issue", "bill"])
                            kw_s = 1.0 if is_primary else 0.80
                            pat_s = 1.0
                            ocr_s = 1.0
                            pos_s = 1.0 if (line_num + offset) <= 15 else 0.80
                            intervening = offset - 1
                            ctx_s = calculate_keyword_proximity(line_distance=offset, intervening_lines=intervening)
                            penalty_s = 0.65 if (is_disq_date or is_disq_next) else 0.0
                            score, breakdown = compute_candidate_confidence(
                                keyword_score=kw_s,
                                pattern_score=pat_s,
                                ocr_score=ocr_s,
                                position_score=pos_s,
                                context_score=ctx_s,
                                penalty_score=penalty_s,
                            )
                            evidence_msg = f"{breakdown}; Matched keyword '{matched_kw}' on line {line_num} (offset={offset}, prox={ctx_s:.2f})"
                            if is_disq_date or is_disq_next:
                                evidence_msg += f" (penalized: context indicates {disq_date_type or disq_next_type})"
                            candidates.append(
                                FieldCandidate(
                                    field_name="invoice_date",
                                    value=raw_date,
                                    confidence=score,
                                    source="positional",
                                    matched_keyword=matched_kw,
                                    matched_text=next_line,
                                    line_num=line_num + offset,
                                    evidence=evidence_msg,
                                    keyword_score=kw_s,
                                    pattern_score=pat_s,
                                    ocr_score=ocr_s,
                                    position_score=pos_s,
                                    context_score=ctx_s,
                                    penalty_score=penalty_s,
                                )
                            )
                            break

        # Strategy 2: Document-wide Regex Extraction (Upper Half / Header Region)
        header_lines = lines[:20]
        for idx, line in enumerate(header_lines):
            # Skip lines matching date exclusions (due date, delivery date, order date, shipping date)
            if check_invoice_date_exclusions(line)[0]:
                continue

            # Accuracy-focused rule: Do NOT assume first date = invoice date without supporting contextual evidence.
            # Require date or invoice keyword context on the line or adjacent lines.
            surrounding_context = (line + " " + " ".join(lines[max(0, idx - 1):min(len(lines), idx + 2)])).lower()
            has_date_context = bool(re.search(r"\b(?:date|dated|dt|issued|issuing|billing|invoice|inv)\b", surrounding_context))
            if not has_date_context:
                continue

            for match in RE_COMBINED_DATE.finditer(line):
                raw_date = match.group(1).strip(" ,;:")
                if cls._is_valid_date_format(raw_date):
                    kw_s = 0.15
                    pat_s = 0.95
                    ocr_s = 1.0
                    pos_s = 0.90 if (idx + 1) <= 10 else 0.70
                    ctx_s = 0.25
                    score, breakdown = compute_candidate_confidence(
                        keyword_score=kw_s,
                        pattern_score=pat_s,
                        ocr_score=ocr_s,
                        position_score=pos_s,
                        context_score=ctx_s,
                        penalty_score=0.0,
                    )
                    candidates.append(
                        FieldCandidate(
                            field_name="invoice_date",
                            value=raw_date,
                            confidence=score,
                            source="regex",
                            matched_keyword=None,
                            matched_text=line,
                            line_num=idx + 1,
                            evidence=f"{breakdown}; Header regex date scan on line {idx + 1}",
                            keyword_score=kw_s,
                            pattern_score=pat_s,
                            ocr_score=ocr_s,
                            position_score=pos_s,
                            context_score=ctx_s,
                            penalty_score=0.0,
                        )
                    )

        # Enrich with OCR bounding boxes
        if pages_word_map:
            cls._enrich_candidates_with_ocr_boxes(candidates, pages_word_map)

        if not candidates:
            return None, []

        # Avoid false positives: when an actual invoice date candidate exists,
        # avoid due date, delivery date, order date, shipping date
        actual_inv_date_cands = [
            c for c in candidates
            if not check_invoice_date_exclusions(c.matched_text or "")[0]
        ]
        if actual_inv_date_cands:
            actual_inv_date_cands.sort(key=lambda c: c.score, reverse=True)
            return actual_inv_date_cands[0], candidates

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[0], candidates

    # -------------------------------------------------------------------------
    # 4. Total Amount Extraction
    # -------------------------------------------------------------------------

    @classmethod
    def _extract_total_amount(
        cls,
        lines: List[str],
        pages_word_map: Dict[int, List[OCRWordData]],
    ) -> Tuple[Optional[FieldCandidate], List[FieldCandidate]]:
        """
        Extracts Total Amount by evaluating all detected candidates using:
        - Strong keyword prefixes ("Grand Total:", "Total Amount:", "Total Payable:", "Net Payable:")
        - Moderate keyword prefixes ("Total:")
        - Disqualification of subtotal, tax breakdown, and item rates
        - Currency symbol & decimal formatting heuristics
        - Spatial position (invoice summary tables near bottom of page)
        """
        candidates: List[FieldCandidate] = []

        for idx, line in enumerate(lines):
            line_num = idx + 1
            has_disqualifier, disq_reason = check_total_amount_exclusions(line)

            # 1. Strong total keywords
            strong_match = TOTAL_AMOUNT_STRONG_PREFIX.search(line)
            if strong_match and not has_disqualifier:
                matched_kw = find_matched_keyword(line[:strong_match.end()], TOTAL_AMOUNT_KEYWORDS) or "total amount"
                remainder = line[strong_match.end():].strip()
                amt = cls._extract_amount_from_string(remainder)
                if amt:
                    kw_s = 1.0
                    pat_s = 1.0 if "." in amt else 0.85
                    ocr_s = 1.0
                    pos_s = 1.0 if idx > (len(lines) // 3) else 0.80
                    char_dist = len(remainder) - len(remainder.lstrip(" :.-#$₹€£"))
                    ctx_s = calculate_keyword_proximity(line_distance=0, char_distance=char_dist)
                    score, breakdown = compute_candidate_confidence(
                        keyword_score=kw_s,
                        pattern_score=pat_s,
                        ocr_score=ocr_s,
                        position_score=pos_s,
                        context_score=ctx_s,
                        penalty_score=0.0,
                    )
                    candidates.append(
                        FieldCandidate(
                            field_name="total_amount",
                            value=amt,
                            confidence=score,
                            source="keyword",
                            matched_keyword=matched_kw,
                            matched_text=line,
                            line_num=line_num,
                            evidence=f"{breakdown}; Matched strong total keyword '{matched_kw}' on line {line_num} (same-line, prox={ctx_s:.2f})",
                            keyword_score=kw_s,
                            pattern_score=pat_s,
                            ocr_score=ocr_s,
                            position_score=pos_s,
                            context_score=ctx_s,
                            penalty_score=0.0,
                        )
                    )
                # Next line check
                elif idx + 1 < len(lines):
                    amt_next = cls._extract_amount_from_string(lines[idx + 1])
                    if amt_next:
                        kw_s = 1.0
                        pat_s = 1.0 if "." in amt_next else 0.85
                        ocr_s = 1.0
                        pos_s = 1.0 if idx > (len(lines) // 3) else 0.80
                        ctx_s = calculate_keyword_proximity(line_distance=1)
                        score, breakdown = compute_candidate_confidence(
                            keyword_score=kw_s,
                            pattern_score=pat_s,
                            ocr_score=ocr_s,
                            position_score=pos_s,
                            context_score=ctx_s,
                            penalty_score=0.0,
                        )
                        candidates.append(
                            FieldCandidate(
                                field_name="total_amount",
                                value=amt_next,
                                confidence=score,
                                source="positional",
                                matched_keyword=matched_kw,
                                matched_text=lines[idx + 1],
                                line_num=line_num + 1,
                                evidence=f"{breakdown}; Matched strong keyword '{matched_kw}' on line {line_num} (next-line amount, prox={ctx_s:.2f})",
                                keyword_score=kw_s,
                                pattern_score=pat_s,
                                ocr_score=ocr_s,
                                position_score=pos_s,
                                context_score=ctx_s,
                                penalty_score=0.0,
                            )
                        )

            # 2. Moderate total keywords
            elif not has_disqualifier:
                mod_match = TOTAL_AMOUNT_MODERATE_PREFIX.search(line)
                if mod_match:
                    matched_kw = "total"
                    remainder = line[mod_match.end():].strip()
                    amt = cls._extract_amount_from_string(remainder)
                    if amt:
                        kw_s = 0.70
                        pat_s = 1.0 if "." in amt else 0.85
                        ocr_s = 1.0
                        pos_s = 1.0 if idx > (len(lines) // 2) else 0.75
                        char_dist = len(remainder) - len(remainder.lstrip(" :.-#$₹€£"))
                        ctx_s = calculate_keyword_proximity(line_distance=0, char_distance=char_dist)
                        score, breakdown = compute_candidate_confidence(
                            keyword_score=kw_s,
                            pattern_score=pat_s,
                            ocr_score=ocr_s,
                            position_score=pos_s,
                            context_score=ctx_s,
                            penalty_score=0.0,
                        )
                        candidates.append(
                            FieldCandidate(
                                field_name="total_amount",
                                value=amt,
                                confidence=score,
                                source="keyword",
                                matched_keyword=matched_kw,
                                matched_text=line,
                                line_num=line_num,
                                evidence=f"{breakdown}; Matched moderate keyword 'total' on line {line_num} (same-line, prox={ctx_s:.2f})",
                                keyword_score=kw_s,
                                pattern_score=pat_s,
                                ocr_score=ocr_s,
                                position_score=pos_s,
                                context_score=ctx_s,
                                penalty_score=0.0,
                            )
                        )

        # Strategy 3: Spatial layout OCR scan (bottom right corner)
        if pages_word_map:
            spatial_cands = cls._extract_total_amount_spatial(pages_word_map)
            candidates.extend(spatial_cands)
            cls._enrich_candidates_with_ocr_boxes(candidates, pages_word_map)

        if not candidates:
            return None, []

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[0], candidates

    @classmethod
    def _extract_total_amount_spatial(
        cls,
        pages_word_map: Dict[int, List[OCRWordData]],
    ) -> List[FieldCandidate]:
        """Detects total amount using spatial OCR bounding box coordinates."""
        spatial_candidates: List[FieldCandidate] = []
        for page_num, words in pages_word_map.items():
            for i, w in enumerate(words):
                if re.search(r"(?i)\b(?:grand\s*total|total)\b", w.text):
                    matched_kw = find_matched_keyword(w.text, TOTAL_AMOUNT_KEYWORDS) or "total"
                    # Look for amounts to the right on the same line (handles wide gaps e.g. 'Grand Total     ₹11,300')
                    for j in range(i + 1, min(i + 15, len(words))):
                        next_w = words[j]
                        if next_w.bounding_box.left > w.bounding_box.left and is_same_line(
                            w.bounding_box,
                            next_w.bounding_box,
                            line_num1=w.line_num,
                            line_num2=next_w.line_num,
                            block_num1=w.block_num,
                            block_num2=next_w.block_num,
                        ):
                            amt = cls._extract_amount_from_string(next_w.text)
                            if amt:
                                conf = next_w.confidence / 100.0
                                is_strong = any(p in matched_kw.lower() for p in ["grand", "payable", "due", "net"])
                                kw_s = 1.0 if is_strong else 0.75
                                pat_s = 1.0 if "." in amt else 0.85
                                ocr_s = conf
                                pos_s = 0.95
                                horiz_prox = calculate_horizontal_proximity(w.bounding_box, next_w.bounding_box)
                                ctx_s = calculate_keyword_proximity(
                                    line_distance=0,
                                    keyword_bbox=w.bounding_box,
                                    candidate_bbox=next_w.bounding_box,
                                )
                                score, breakdown = compute_candidate_confidence(
                                    keyword_score=kw_s,
                                    pattern_score=pat_s,
                                    ocr_score=ocr_s,
                                    position_score=pos_s,
                                    context_score=ctx_s,
                                    penalty_score=0.0,
                                )
                                spatial_candidates.append(
                                    FieldCandidate(
                                        field_name="total_amount",
                                        value=amt,
                                        confidence=score,
                                        source="combined",
                                        matched_keyword=matched_kw,
                                        matched_text=f"{w.text} {next_w.text}",
                                        bbox=next_w.bounding_box,
                                        line_num=next_w.line_num,
                                        ocr_confidence=conf,
                                        bounding_box=next_w.bounding_box,
                                        page_number=page_num,
                                        evidence=f"{breakdown}; Spatial OCR right-neighbor of '{matched_kw}' on page {page_num} (prox={horiz_prox:.2f})",
                                        keyword_score=kw_s,
                                        pattern_score=pat_s,
                                        ocr_score=ocr_s,
                                        position_score=pos_s,
                                        context_score=ctx_s,
                                        penalty_score=0.0,
                                    )
                                )
                                break
        return spatial_candidates

    # Alias for backwards compatibility
    extract_fields = extract

    # -------------------------------------------------------------------------
    # Helper Validation & Sanitization Methods
    # -------------------------------------------------------------------------

    @classmethod
    def _dict_to_word_obj(cls, item: Any) -> Optional[OCRWordData]:
        """
        Safely converts an arbitrary dictionary or object into OCRWordData.
        Gracefully handles:
        - malformed OCR word data
        - missing bounding boxes
        - missing confidence
        - invalid confidence values (strings, negative, NaN, etc.)
        """
        if isinstance(item, OCRWordData):
            return item
        if not isinstance(item, dict):
            return None
        try:
            # 1. Handle text
            raw_text = item.get("text")
            if raw_text is None:
                return None
            clean_text = str(raw_text).strip()
            if not clean_text:
                return None

            # 2. Handle missing or malformed bounding boxes
            bbox_raw = item.get("bbox") or item.get("bounding_box")
            if isinstance(bbox_raw, dict):
                try:
                    l = max(0, int(float(bbox_raw.get("left", 0) or 0)))
                    t = max(0, int(float(bbox_raw.get("top", 0) or 0)))
                    w = max(0, int(float(bbox_raw.get("width", 0) or 0)))
                    h = max(0, int(float(bbox_raw.get("height", 0) or 0)))
                    x2_val = int(float(bbox_raw.get("x2", l + w) or (l + w)))
                    y2_val = int(float(bbox_raw.get("y2", t + h) or (t + h)))
                    bbox_obj = OCRBoundingBox(
                        left=l,
                        top=t,
                        width=w,
                        height=h,
                        x2=x2_val,
                        y2=y2_val,
                    )
                except (ValueError, TypeError):
                    bbox_obj = OCRBoundingBox(left=0, top=0, width=0, height=0, x2=0, y2=0)
            elif isinstance(bbox_raw, OCRBoundingBox):
                bbox_obj = bbox_raw
            else:
                # Missing bounding box gracefully defaulted
                bbox_obj = OCRBoundingBox(left=0, top=0, width=0, height=0, x2=0, y2=0)

            # 3. Handle missing, negative, or invalid confidence values
            conf_raw = item.get("confidence")
            conf_val = 100.0
            if conf_raw is not None:
                try:
                    parsed_conf = float(conf_raw)
                    if math.isnan(parsed_conf) or math.isinf(parsed_conf):
                        conf_val = 100.0
                    elif parsed_conf < 0.0:
                        conf_val = 0.0
                    elif parsed_conf > 100.0:
                        conf_val = 100.0
                    else:
                        conf_val = parsed_conf
                except (ValueError, TypeError):
                    conf_val = 100.0

            # 4. Handle hierarchy indices safely
            def _safe_int(val: Any, default: int = 1) -> int:
                try:
                    return max(1, int(float(val)))
                except (ValueError, TypeError):
                    return default

            return OCRWordData(
                text=clean_text,
                confidence=conf_val,
                bounding_box=bbox_obj,
                bbox=bbox_obj,
                block_num=_safe_int(item.get("block_num")),
                paragraph_num=_safe_int(item.get("paragraph_num")),
                line_num=_safe_int(item.get("line_num")),
                word_num=_safe_int(item.get("word_num")),
            )
        except Exception:
            return None

    @classmethod
    def _normalize_document_input(
        cls,
        document_input: Optional[Union[OCRResult, PDFParseResult, str, Dict[str, Any]]] = None,
        text: Optional[str] = None,
        words: Optional[Union[List[Any], Dict[int, List[Any]]]] = None,
        ocr_pages: Optional[List[OCRPageData]] = None,
    ) -> Tuple[str, Dict[int, List[OCRWordData]]]:
        """
        Normalizes various document representations into a unified (doc_text, pages_word_map) tuple.
        Independent of OCR engine - processes pure text, dictionary words, or schema objects.
        """
        pages_word_map: Dict[int, List[OCRWordData]] = {}
        doc_text = ""

        if text is not None:
            doc_text = text
        elif isinstance(document_input, str):
            doc_text = document_input

        if ocr_pages:
            for p in ocr_pages:
                pages_word_map[p.page_number] = p.words

        if words:
            if isinstance(words, list):
                page_words = []
                for w in words:
                    w_obj = cls._dict_to_word_obj(w)
                    if w_obj:
                        page_words.append(w_obj)
                pages_word_map[1] = page_words
            elif isinstance(words, dict):
                for p_num, p_words in words.items():
                    page_words = []
                    if isinstance(p_words, list):
                        for w in p_words:
                            w_obj = cls._dict_to_word_obj(w)
                            if w_obj:
                                page_words.append(w_obj)
                    pages_word_map[int(p_num)] = page_words

        if isinstance(document_input, OCRResult):
            if not doc_text:
                doc_text = document_input.combined_text
            for p in document_input.pages:
                if p.page_number not in pages_word_map:
                    pages_word_map[p.page_number] = p.words

        elif isinstance(document_input, PDFParseResult):
            if not doc_text:
                doc_text = document_input.combined_text

        elif isinstance(document_input, dict):
            if not doc_text:
                doc_text = document_input.get("combined_text") or document_input.get("text", "")
            if "words" in document_input and not pages_word_map:
                w_list = document_input["words"]
                if isinstance(w_list, list):
                    page_words = [cls._dict_to_word_obj(w) for w in w_list]
                    pages_word_map[1] = [w for w in page_words if w]
            if "pages" in document_input and isinstance(document_input["pages"], list):
                for p_idx, p in enumerate(document_input["pages"]):
                    p_num = p.get("page_number", p_idx + 1)
                    raw_words = p.get("words", [])
                    word_objs = [cls._dict_to_word_obj(w) for w in raw_words]
                    if word_objs and p_num not in pages_word_map:
                        pages_word_map[p_num] = [w for w in word_objs if w]

        # If text is not provided but words list was provided, reconstruct text preserving lines
        if not doc_text.strip() and pages_word_map:
            reconstructed_lines: List[str] = []
            for p_num in sorted(pages_word_map.keys()):
                p_words = pages_word_map[p_num]
                lines_dict: Dict[int, List[str]] = {}
                for w in p_words:
                    ln = w.line_num or 1
                    lines_dict.setdefault(ln, []).append(w.text)
                for ln in sorted(lines_dict.keys()):
                    reconstructed_lines.append(" ".join(lines_dict[ln]))
            doc_text = "\n".join(reconstructed_lines)

        return doc_text.strip(), pages_word_map

    @staticmethod
    def _clean_candidate_string(text: str) -> str:
        """Sanitizes raw string by removing excess punctuation and whitespace."""
        cleaned = re.sub(r"[\t\r\n]+", " ", text).strip()
        cleaned = re.sub(r"^[^\w]+|[^\w\.\,\(\)\-\&]+$", "", cleaned)
        return cleaned.strip()

    @staticmethod
    def _clean_invoice_number_token(token: str) -> Optional[str]:
        """Extracts and cleans an invoice number token from raw string remainder."""
        if not token:
            return None
        cleaned = token.strip(" :.-#[](){}")
        if not cleaned:
            return None
        # Normalize spaces around delimiters (e.g. "INV / 2026 / 001" -> "INV/2026/001")
        cleaned = re.sub(r"([A-Za-z0-9])\s*([/\-_#])\s*([A-Za-z0-9])", r"\1\2\3", cleaned)
        parts = cleaned.split()
        if not parts:
            return None
        candidate = parts[0].strip(" ,;:")
        return candidate if candidate else None

    @classmethod
    def _is_valid_invoice_number(cls, val: str) -> bool:
        """Validates that candidate is not a date, phone number, or pure currency."""
        if not val or len(val) < 2 or len(val) > 35:
            return False
        # Cannot be date
        if RE_COMBINED_DATE.match(val):
            return False
        # Cannot be an explicit currency amount or decimal currency amount (e.g. $500, ₹1500, 1500.50)
        if re.match(r"^(?:[\$₹€£]|(?:rs\.?|inr|usd|eur|gbp)\s*)\d+", val, re.IGNORECASE):
            return False
        if re.match(r"^\d+\.\d{2}$", val):
            return False
        # Cannot be a tax percentage
        if RE_TAX_PERCENT.match(val):
            return False
        # Must have at least 1 digit or reasonable identifier structure
        if not re.search(r"\d", val) and not re.search(r"[-_/]", val):
            return False
        return True

    @classmethod
    def _resembles_gstin(cls, val: str, line: str = "") -> bool:
        """Detects whether token or line resembles an Indian GSTIN (15 chars)."""
        if RE_GSTIN.search(val):
            return True
        if re.search(r"(?i)\b(?:gstin|gst\s*no|gst\s*#)\b", line) and not any(k in line.lower() for k in ["inv", "bill"]):
            return True
        return False

    @classmethod
    def _resembles_pan(cls, val: str, line: str = "") -> bool:
        """Detects whether token or line resembles an Indian PAN card number (10 chars: 5 letters, 4 digits, 1 letter)."""
        cleaned = re.sub(r"[\s-]", "", val)
        if RE_PAN.match(cleaned):
            return True
        if re.search(r"(?i)\bpan\s*(?:no|#|number)?\b", line) and not any(k in line.lower() for k in ["inv", "bill"]):
            return True
        return False

    @classmethod
    def _resembles_phone_number(cls, val: str, line: str = "") -> bool:
        """Detects whether token or line resembles a telephone or mobile number."""
        cleaned_digits = re.sub(r"\D", "", val)
        if len(cleaned_digits) == 10 and cleaned_digits[0] in "6789":
            return True
        if len(cleaned_digits) >= 10 and re.search(r"(?i)\b(?:phone|tel|mobile|mob|contact|fax|call)\b", line):
            return True
        if RE_PHONE_NUMBER.search(val):
            return True
        return False

    @classmethod
    def _resembles_pin_code(cls, val: str, line: str = "") -> bool:
        """Detects whether token resembles a postal PIN/ZIP code."""
        cleaned = val.strip()
        if re.match(r"^\d{6}$", cleaned) or re.match(r"^\d{5}(?:-\d{4})?$", cleaned):
            if re.search(r"(?i)\b(?:pin|zip|postal|road|street|nagar|park|marg|lane|floor|building|bangalore|mumbai|delhi|kolkata|chennai|hyderabad|pune)\b", line):
                return True
        return False

    @classmethod
    def _resembles_bank_account(cls, val: str, line: str = "") -> bool:
        """Detects whether token resembles a bank account number."""
        cleaned_digits = re.sub(r"\D", "", val)
        if 11 <= len(cleaned_digits) <= 18:
            if re.search(r"(?i)\b(?:a/c|account|bank|ifsc|iban|swift|branch)\b", line):
                return True
        return False

    @classmethod
    def _resembles_ifsc(cls, val: str, line: str = "") -> bool:
        """Detects whether token or line resembles an Indian IFSC code (11 chars: 4 letters, '0', 6 alphanumeric)."""
        cleaned = re.sub(r"[\s-]", "", val)
        if RE_IFSC.match(cleaned):
            return True
        if re.search(r"(?i)\bifsc\s*(?:code)?\b", line):
            return True
        return False

    @classmethod
    def _resembles_date(cls, val: str, line: str = "") -> bool:
        """Detects whether candidate value is formatted as a calendar date."""
        if cls._is_valid_date_format(val):
            return True
        if re.search(r"^\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}$", val.strip()):
            return True
        return False

    @classmethod
    def _resembles_tax_percentage(cls, val: str, line: str = "") -> bool:
        """Detects whether token resembles a tax percentage."""
        if RE_TAX_PERCENT.match(val):
            return True
        if re.search(r"(?i)\b(?:cgst|sgst|igst|vat|tax)\s*(?:rate|%|@)", line):
            return True
        return False

    @classmethod
    def _resembles_product_code_or_hsn(cls, val: str, line: str = "") -> bool:
        """Detects whether token or line resembles a product code, HSN, or SAC."""
        if re.search(r"(?i)\b(?:hsn|sac|sku|item\s*code|part\s*no|code)\b", line):
            return True
        return False

    @classmethod
    def _score_and_penalize_invoice_number(
        cls,
        val: str,
        line: str,
        matched_kw: Optional[str] = None,
        source: str = "keyword",
        line_distance: int = 0,
        char_distance: Optional[int] = None,
        intervening_lines: int = 0,
        keyword_bbox: Optional[OCRBoundingBox] = None,
        candidate_bbox: Optional[OCRBoundingBox] = None,
        ocr_confidence: Optional[float] = None,
        line_num: int = 1,
    ) -> Tuple[float, List[str], Dict[str, float]]:
        """
        Calculates composite confidence for invoice number candidates using transparent scoring
        signals: keyword_score, pattern_score, ocr_score, position_score, context_score (proximity),
        and penalty_score.
        """
        evidence_notes: List[str] = []

        # 1. Keyword Score (weight 0.30)
        has_inv_prefix = bool(re.search(r"^(?:INV|BILL|TAX|REC)[-_/0-9]", val, re.IGNORECASE))
        if matched_kw:
            is_primary = any(p in matched_kw.lower() for p in ["invoice", "inv", "bill", "tax"])
            keyword_score = 1.0 if is_primary else 0.70
            evidence_notes.append(f"keyword '{matched_kw}' (strength={keyword_score:.2f})")
        elif source == "spatial":
            keyword_score = 0.85
            evidence_notes.append("spatial OCR keyword relationship")
        elif has_inv_prefix:
            keyword_score = 0.60
            evidence_notes.append("standalone token with explicit invoice prefix")
        else:
            keyword_score = 0.15
            evidence_notes.append("standalone regex pattern (no explicit keyword or invoice prefix)")

        # 2. Pattern Score (weight 0.25)
        has_alpha = bool(re.search(r"[A-Za-z]", val))
        has_digits = bool(re.search(r"\d", val))
        has_delims = any(sep in val for sep in ["-", "/", "_", "#"])

        if has_alpha and has_digits and has_delims:
            pattern_score = 1.0
            evidence_notes.append("alphanumeric with delimiters")
        elif has_alpha and has_digits:
            pattern_score = 0.90
            evidence_notes.append("alphanumeric sequence")
        elif has_delims and has_digits:
            pattern_score = 0.90
            evidence_notes.append("delimited numeric sequence")
        elif has_digits and 3 <= len(val) <= 10:
            pattern_score = 0.80
            evidence_notes.append("valid numeric identifier")
        else:
            pattern_score = 0.60

        # 3. OCR Score (weight 0.20)
        ocr_score = float(ocr_confidence) if ocr_confidence is not None else 1.0

        # 4. Position Score (weight 0.15)
        if line_num <= 10:
            position_score = 1.0
        elif line_num <= 20:
            position_score = 0.80
        else:
            position_score = 0.50

        # 5. Context Score (proximity to keyword, weight 0.10)
        prox = calculate_keyword_proximity(
            line_distance=line_distance,
            char_distance=char_distance,
            intervening_lines=intervening_lines,
            keyword_bbox=keyword_bbox,
            candidate_bbox=candidate_bbox,
        )
        context_score = prox
        evidence_notes.append(f"proximity={prox:.2f}")

        # 6. Penalty Score (negative evidence / field-specific exclusions)
        # Avoid false positives: GSTIN, PAN, phone number, bank account, IFSC, date, PIN code
        penalty_score = 0.0
        if cls._resembles_gstin(val, line):
            penalty_score += 0.80
            evidence_notes.append("penalized: resembles GSTIN")
        if cls._resembles_pan(val, line):
            penalty_score += 0.80
            evidence_notes.append("penalized: resembles PAN")
        if cls._resembles_phone_number(val, line):
            penalty_score += 0.80
            evidence_notes.append("penalized: resembles phone number")
        if cls._resembles_bank_account(val, line):
            penalty_score += 0.75
            evidence_notes.append("penalized: resembles bank account number")
        if cls._resembles_ifsc(val, line):
            penalty_score += 0.80
            evidence_notes.append("penalized: resembles IFSC code")
        if cls._resembles_date(val, line):
            penalty_score += 0.85
            evidence_notes.append("penalized: resembles date")
        if cls._resembles_pin_code(val, line):
            penalty_score += 0.75
            evidence_notes.append("penalized: resembles postal PIN code")
        if cls._resembles_tax_percentage(val, line):
            penalty_score += 0.85
            evidence_notes.append("penalized: resembles tax percentage")
        if cls._resembles_product_code_or_hsn(val, line):
            penalty_score += 0.60
            evidence_notes.append("penalized: resembles HSN/SAC code")
        # Accuracy-focused rule: Do NOT assume first number = invoice number.
        # Penalize pure numeric tokens that lack an explicit invoice keyword anchor.
        if val.isdigit() and not matched_kw:
            penalty_score += 0.80
            evidence_notes.append("penalized: pure numeric token without invoice keyword anchor")

        final_conf, breakdown = compute_candidate_confidence(
            keyword_score=keyword_score,
            pattern_score=pattern_score,
            ocr_score=ocr_score,
            position_score=position_score,
            context_score=context_score,
            penalty_score=penalty_score,
        )
        evidence_notes.insert(0, breakdown)

        scores_dict = {
            "keyword": keyword_score,
            "pattern": pattern_score,
            "ocr": ocr_score,
            "position": position_score,
            "context": context_score,
            "penalty": penalty_score,
        }
        return final_conf, evidence_notes, scores_dict

    @staticmethod
    def _is_valid_date_format(date_str: str) -> bool:
        """Validates calendar date ranges (day 1-31, month 1-12, year 1990-2040). Safely handles malformed dates."""
        if not date_str or not isinstance(date_str, str):
            return False
        try:
            # Numeric date check: DD/MM/YYYY or YYYY-MM-DD
            m_num = re.match(r"^(\d{1,4})[-/. ](\d{1,2})[-/. ](\d{1,4})$", date_str)
            if m_num:
                p1, p2, p3 = int(m_num.group(1)), int(m_num.group(2)), int(m_num.group(3))
                # If p1 is 4-digit year (YYYY-MM-DD)
                if p1 > 1000:
                    year, month, day = p1, p2, p3
                # If p3 is 4-digit year (DD-MM-YYYY)
                elif p3 > 1000:
                    day, month, year = p1, p2, p3
                else:
                    # 2-digit year fallback
                    day, month, year = p1, p2, 2000 + p3 if p3 < 100 else p3

                if not (1 <= month <= 12):
                    return False
                if not (1 <= day <= 31):
                    return False
                if not (1990 <= year <= 2040):
                    return False
                return True

            # Textual month check: 12 Aug 2026, 14 August 2026, or Aug 12, 2026
            if re.search(r"(?i)\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\b", date_str):
                m_year = re.search(r"\b(19\d\d|20\d\d)\b", date_str)
                if m_year:
                    year = int(m_year.group(1))
                    return 1990 <= year <= 2040
                return True
        except (ValueError, TypeError, AttributeError):
            return False

        return False

    @staticmethod
    def _extract_amount_from_string(text: str) -> Optional[str]:
        """Extracts and standardizes numeric amount from candidate line string."""
        if not text:
            return None
        m = RE_CURRENCY_AMOUNT.search(text)
        if m:
            raw_amt = m.group(1).replace(",", "")
            # Verify numeric float validity
            try:
                val = float(raw_amt)
                if val > 0:
                    # Return formatted string with 2 decimal places if present, else original
                    return f"{val:.2f}" if "." in raw_amt else f"{val:.2f}"
            except ValueError:
                pass
        return None


# Backwards compatibility class alias
InvoiceFieldExtractor = InvoiceExtractor

# Singleton instances
invoice_extractor = InvoiceExtractor()
extractor = invoice_extractor
invoice_field_extractor = invoice_extractor

# Convenience functional exports
extract = invoice_extractor.extract
extract_invoice_fields = invoice_extractor.extract

__all__ = [
    "InvoiceExtractor",
    "InvoiceFieldExtractor",
    "FieldCandidate",
    "Candidate",
    "AIExtractionProvider",
    "NoOpAIExtractionProvider",
    "MockAIExtractionProvider",
    "ReconciliationEngine",
    "reconcile_candidates",
    "extract",
    "extract_invoice_fields",
    "invoice_extractor",
    "prepare_text",
    "check_invoice_number_exclusions",
    "check_invoice_date_exclusions",
    "check_total_amount_exclusions",
    "check_vendor_name_exclusions",
    "calculate_keyword_proximity",
    "compute_candidate_confidence",
    "is_same_line",
    "is_nearby_line",
    "is_above_below",
    "calculate_horizontal_proximity",
    "is_top_of_page",
    "group_words_into_lines",
]
