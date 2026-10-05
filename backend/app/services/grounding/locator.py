"""
Grounding and Evidence Bounding Box Locator.
Verifies extracted quotes and values against physical text blocks in UniversalDocument.
Maps verified spans to precise bounding boxes [x0, y0, x1, y1] for frontend UI overlays.
Flags hallucinated extractions where grounded=False.
"""

from difflib import SequenceMatcher
import logging
import re
from typing import Any, List, Optional, Tuple

from app.schemas.universal import ContentBlock, FieldEvidence, UniversalDocument

logger = logging.getLogger(__name__)


class GroundingService:
    """Performs grounding verification and bounding box calculation for extracted fields."""

    def _normalize(self, text: str) -> str:
        """Lowercases, strips special unicode symbols/bullets, and normalizes whitespace."""
        if not text:
            return ""
        t = str(text)
        # Normalize replacement character, bullets, and non-printable control chars
        t = re.sub(r"[\ufffd\u2022\u25cf\*\x00-\x08\x0b\x0c\x0e-\x1f]", " ", t)
        t = re.sub(r"[\u2018\u2019]", "'", t)
        t = re.sub(r"[\u201c\u201d]", '"', t)
        t = re.sub(r"[\u2013\u2014\u2212]", "-", t)
        return re.sub(r"\s+", " ", t).lower().strip()

    def verify_and_locate(
        self,
        quote: Optional[str],
        raw_value: Any,
        page_hint: Optional[int],
        udoc: UniversalDocument,
    ) -> FieldEvidence:
        """
        Locates the evidence quote and/or raw value in the document's physical blocks.
        Computes the bounding box coordinates and marks grounded=True/False.
        """
        target_quote = (quote or "").strip()
        target_val = str(raw_value).strip() if raw_value is not None else ""

        # If neither quote nor value exists, cannot ground
        if not target_quote and not target_val:
            return FieldEvidence(
                page=page_hint or 1,
                quote="",
                bbox=[0.0, 0.0, 0.0, 0.0],
                grounded=False,
                match_score=0.0,
            )

        norm_quote = self._normalize(target_quote)
        norm_val = self._normalize(target_val)

        # Prioritize blocks from page_hint, then fall back to all blocks
        hint_page = page_hint if page_hint and page_hint > 0 else 1
        page_blocks = [b for b in udoc.blocks if b.page == hint_page]
        other_blocks = [b for b in udoc.blocks if b.page != hint_page]
        ordered_candidates = page_blocks + other_blocks

        best_score = 0.0
        best_block: Optional[ContentBlock] = None
        matched_blocks: List[ContentBlock] = []

        # 1. Exact Substring Search & Prefix Containment
        for block in ordered_candidates:
            norm_btext = self._normalize(block.text)
            if not norm_btext:
                continue

            # Check if quote is contained in block, or block is contained in quote
            if norm_quote and (norm_quote in norm_btext or (len(norm_btext) >= 15 and norm_btext in norm_quote)):
                matched_blocks.append(block)
                best_score = 1.0
                break

            # For longer quotes, check first 30 chars or first line
            if norm_quote and len(norm_quote) >= 20:
                first_chunk = norm_quote[:35].strip()
                if first_chunk and first_chunk in norm_btext:
                    matched_blocks.append(block)
                    best_score = 0.98
                    break

            # Check if raw value is contained in block
            if norm_val and len(norm_val) >= 2 and (norm_val in norm_btext or (len(norm_btext) >= 15 and norm_btext in norm_val)):
                matched_blocks.append(block)
                best_score = 0.95
                break

            # For longer values, check first 30 chars
            if norm_val and len(norm_val) >= 25:
                first_chunk_val = norm_val[:35].strip()
                if first_chunk_val and first_chunk_val in norm_btext:
                    matched_blocks.append(block)
                    best_score = 0.92
                    break

        # 2. Token Overlap & Fuzzy Search (if no exact match found)
        if not matched_blocks and (norm_quote or norm_val):
            search_target = norm_quote if norm_quote else norm_val
            target_words = [w for w in re.findall(r"[a-zA-Z0-9]+", search_target) if len(w) >= 3]

            for block in ordered_candidates:
                norm_btext = self._normalize(block.text)
                if not norm_btext:
                    continue

                # Token overlap scoring
                if target_words:
                    matched_words = sum(1 for w in target_words if w in norm_btext)
                    word_ratio = matched_words / len(target_words)
                    if word_ratio > best_score:
                        best_score = word_ratio
                        best_block = block

                # SequenceMatcher comparison
                if len(search_target) <= len(norm_btext) * 3:
                    ratio = SequenceMatcher(None, search_target, norm_btext).ratio()
                    if ratio > best_score:
                        best_score = ratio
                        best_block = block

            if best_score >= 0.65 and best_block:
                matched_blocks.append(best_block)

        # 3. Calculate Bounding Box Union
        if matched_blocks:
            min_x0 = min(b.bbox[0] for b in matched_blocks)
            min_y0 = min(b.bbox[1] for b in matched_blocks)
            max_x1 = max(b.bbox[2] for b in matched_blocks)
            max_y1 = max(b.bbox[3] for b in matched_blocks)
            matched_page = matched_blocks[0].page

            # Ensure valid box dimensions
            if max_x1 <= min_x0:
                max_x1 = min_x0 + 50.0
            if max_y1 <= min_y0:
                max_y1 = min_y0 + 20.0

            bbox = [round(min_x0, 2), round(min_y0, 2), round(max_x1, 2), round(max_y1, 2)]
            is_grounded = best_score >= 0.70

            return FieldEvidence(
                page=matched_page,
                quote=target_quote or target_val,
                bbox=bbox,
                grounded=is_grounded,
                match_score=round(best_score, 2),
            )

        # Not grounded in any block
        return FieldEvidence(
            page=hint_page,
            quote=target_quote or target_val,
            bbox=[0.0, 0.0, 0.0, 0.0],
            grounded=False,
            match_score=round(best_score, 2),
        )


# Singleton instance
grounding_service = GroundingService()
