"""
Reconciliation layer combining Rule-based and AI/LLM extraction candidates.
Applies transparent arbitration rules, field-specific priority heuristics,
mutual agreement boosts, and detailed source tracking (rule, ai, rule+ai, none).
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from app.schemas.extraction import ExtractedField, FieldCandidate
from app.services.ai.schemas import AIExtractedFields, AIExtractionResponse

logger = logging.getLogger(__name__)

TARGET_FIELDS = ["vendor_name", "invoice_number", "invoice_date", "total_amount"]


class ReconciledCandidate:
    """
    Representation for candidates during reconciliation.
    Compatible with both schema models and internal pipeline representations.
    """

    def __init__(
        self,
        field_name: str,
        value: str,
        confidence: float = 0.0,
        source: str = "ai",
        matched_keyword: Optional[str] = "ai_provider",
        matched_text: Optional[str] = None,
        bbox: Any = None,
        line_num: Optional[int] = None,
        evidence: Optional[str] = None,
        score: Optional[float] = None,
        bounding_box: Any = None,
        page_number: Optional[int] = None,
    ) -> None:
        self.field_name = field_name
        self.value = value.strip()
        self.score = float(confidence if score is None else score)
        self.confidence = self.get_clamped_confidence()
        self.source = source
        self.matched_keyword = matched_keyword
        self.matched_text = matched_text or value
        self.bbox = bbox or bounding_box
        self.bounding_box = self.bbox
        self.line_num = line_num
        self.evidence = evidence or ""
        self.page_number = page_number

    def get_clamped_confidence(self) -> float:
        return round(max(0.0, min(1.0, self.score)), 2)

    def to_schema_candidate(self) -> FieldCandidate:
        return FieldCandidate(
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
        return ExtractedField(
            value=self.value,
            confidence=self.get_clamped_confidence(),
            source=self.source,
            bounding_box=self.bbox,
            page_number=self.page_number,
        )


def normalize_token(val: Optional[str]) -> str:
    """Normalizes a string for comparative matching (lowercase, alphanumeric only)."""
    if not val or not isinstance(val, str):
        return ""
    return re.sub(r"[^\w\.-]", "", val.strip().lower())


class ReconciliationEngine:
    """
    Independent reconciliation service that arbitrates between rule-based candidates
    and AI-extracted fields without tightly coupling to any specific provider.
    """

    @classmethod
    def _is_disqualified_by_context(cls, field_name: str, value: str, evidence: str) -> bool:
        """Checks if a candidate is disqualified by field-specific negative evidence."""
        lower_ev = evidence.lower()

        if field_name == "total_amount":
            subtotal_keywords = ["subtotal", "sub-total", "tax", "cgst", "sgst", "discount", "unit price", "qty"]
            if any(k in lower_ev for k in subtotal_keywords) and not any(k in lower_ev for k in ["grand total", "net payable", "total amount", "total due"]):
                return True

        elif field_name == "invoice_date":
            due_date_keywords = ["due date", "delivery date", "shipping date", "order date", "po date", "expiry"]
            if any(k in lower_ev for k in due_date_keywords) and not any(k in lower_ev for k in ["invoice date", "bill date", "date of issue", "dated"]):
                return True

        elif field_name == "vendor_name":
            buyer_keywords = ["bill to", "buyer", "customer", "ship to", "consignee", "client"]
            if any(k in lower_ev for k in buyer_keywords) and not any(k in lower_ev for k in ["vendor", "seller", "supplier", "from"]):
                return True

        elif field_name == "invoice_number":
            disq_num = ["gstin", "pan", "phone", "bank", "account", "ifsc", "pin code"]
            if any(k in lower_ev for k in disq_num) and not any(k in lower_ev for k in ["inv", "bill"]):
                return True

        return False

    @classmethod
    def reconcile(
        cls,
        rule_candidates: Dict[str, List[Any]],
        ai_result: Optional[Union[AIExtractionResponse, AIExtractedFields, Dict[str, Any]]] = None,
    ) -> Tuple[Dict[str, Optional[Any]], Dict[str, List[Any]], Dict[str, str]]:
        """
        Reconciles rule-based candidates with AI extraction output.
        """
        reconciled_cands_map: Dict[str, List[Any]] = {}
        selected_fields: Dict[str, Optional[Any]] = {}
        field_sources: Dict[str, str] = {}

        # 1. Normalize AI input into AIExtractedFields
        ai_fields: Optional[AIExtractedFields] = None
        if isinstance(ai_result, AIExtractionResponse):
            ai_fields = ai_result.fields
        elif isinstance(ai_result, AIExtractedFields):
            ai_fields = ai_result
        elif hasattr(ai_result, "to_invoice_fields"):
            ai_fields = ai_result.to_invoice_fields()
        elif hasattr(ai_result, "to_ai_response"):
            ai_fields = ai_result.to_ai_response().fields
        elif isinstance(ai_result, dict):
            if "fields" in ai_result and isinstance(ai_result["fields"], dict):
                inner_fields = ai_result["fields"]
                flat_data: Dict[str, Any] = {}
                conf_data: Dict[str, Any] = {}
                ev_data: Dict[str, Any] = {}
                for k, v in inner_fields.items():
                    if isinstance(v, dict):
                        flat_data[k] = v.get("value")
                        if "confidence" in v:
                            conf_data[k] = v["confidence"]
                        if "evidence" in v:
                            ev_data[k] = v["evidence"]
                    else:
                        flat_data[k] = v
                if "confidence" in ai_result and isinstance(ai_result["confidence"], dict):
                    conf_data.update(ai_result["confidence"])
                if "evidence" in ai_result and isinstance(ai_result["evidence"], dict):
                    ev_data.update(ai_result["evidence"])
                flat_data["confidence"] = conf_data
                flat_data["evidence"] = ev_data
                ai_fields = AIExtractedFields(**flat_data)
            else:
                ai_fields = AIExtractedFields(**ai_result)

        for field_name in TARGET_FIELDS:
            r_cands = list(rule_candidates.get(field_name, []))

            ai_val = getattr(ai_fields, field_name, None) if ai_fields else None
            ai_conf = 0.85
            ai_ev = ""
            if ai_fields and ai_fields.confidence:
                ai_conf = ai_fields.confidence.get(field_name, 0.85)
            if ai_fields and ai_fields.evidence:
                ai_ev = ai_fields.evidence.get(field_name, "Extracted by AI provider")

            has_ai_val = ai_val is not None and bool(str(ai_val).strip()) and str(ai_val).strip().lower() != "null"

            # Get best rule candidate
            best_rule_cand: Optional[Any] = None
            if r_cands:
                valid_rule_cands = [c for c in r_cands if getattr(c, "confidence", 0.0) >= 0.35]
                if valid_rule_cands:
                    best_rule_cand = max(valid_rule_cands, key=lambda c: (c.confidence, -getattr(c, "line_num", 0) if getattr(c, "line_num", None) else 0))

            # --- Case 1: Both Null ---
            if not has_ai_val and not best_rule_cand:
                reconciled_cands_map[field_name] = r_cands
                selected_fields[field_name] = None
                field_sources[field_name] = "none"
                continue

            # Create AI Candidate if AI provided a value
            ai_cand: Optional[Any] = None
            if has_ai_val:
                ai_val_clean = str(ai_val).strip()
                ai_conf_clamped = round(max(0.0, min(1.0, float(ai_conf))), 2)
                ai_cand = ReconciledCandidate(
                    field_name=field_name,
                    value=ai_val_clean,
                    confidence=ai_conf_clamped,
                    source="ai",
                    matched_keyword="ai_provider",
                    matched_text="AI extraction output",
                    evidence=f"Extracted by AI (confidence={ai_conf_clamped:.2f}; {ai_ev})",
                    score=ai_conf_clamped,
                )

            # --- Case 2: Rule Valid + AI Null ---
            if best_rule_cand and not has_ai_val:
                reconciled_cands_map[field_name] = r_cands
                selected_fields[field_name] = best_rule_cand
                field_sources[field_name] = best_rule_cand.source if best_rule_cand.source in ["rule", "keyword", "positional"] else "rule"
                continue

            # --- Case 3: Rule Null + AI Valid ---
            if not best_rule_cand and ai_cand:
                all_cands = list(r_cands) + [ai_cand]
                reconciled_cands_map[field_name] = all_cands
                selected_fields[field_name] = ai_cand
                field_sources[field_name] = "ai"
                continue

            # --- Case 4: Both have values (Agreement vs Disagreement) ---
            assert best_rule_cand is not None
            assert ai_cand is not None

            norm_rule = normalize_token(best_rule_cand.value)
            norm_ai = normalize_token(ai_cand.value)

            # Check Agreement
            is_agree = (norm_rule == norm_ai) or (best_rule_cand.value.strip().lower() == ai_cand.value.strip().lower())

            if is_agree:
                # Mutual Agreement: Boost confidence and set field source = 'rule+ai'
                boosted_conf = min(1.0, max(best_rule_cand.confidence, ai_cand.confidence) + 0.05)
                best_rule_cand.confidence = boosted_conf
                if hasattr(best_rule_cand, "score"):
                    try:
                        best_rule_cand.score = boosted_conf
                    except (ValueError, AttributeError):
                        pass
                prev_ev = getattr(best_rule_cand, "evidence", "") or ""
                best_rule_cand.evidence = (prev_ev + " | " if prev_ev else "") + f"Reinforced by AI agreement (AI value='{ai_cand.value}', AI conf={ai_cand.confidence:.2f})"

                all_cands = list(r_cands) + [ai_cand]
                reconciled_cands_map[field_name] = all_cands
                selected_fields[field_name] = best_rule_cand
                field_sources[field_name] = "rule+ai"
                continue

            # Check Disagreement
            # Evaluate field-specific negative evidence / contextual disqualification
            rule_ev = getattr(best_rule_cand, "evidence", "") or ""
            ai_ev = getattr(ai_cand, "evidence", "") or ""
            rule_disqualified = cls._is_disqualified_by_context(field_name, best_rule_cand.value, rule_ev)
            ai_disqualified = cls._is_disqualified_by_context(field_name, ai_cand.value, ai_ev)

            winner: FieldCandidate
            winner_source: str

            if ai_disqualified and not rule_disqualified:
                winner = best_rule_cand
                winner_source = "rule"
                best_rule_cand.evidence = (rule_ev + " | " if rule_ev else "") + f"Disagreement resolved in favor of Rule (AI candidate '{ai_cand.value}' disqualified by context)"
            elif rule_disqualified and not ai_disqualified:
                winner = ai_cand
                winner_source = "ai"
                ai_cand.evidence = (ai_ev + " | " if ai_ev else "") + f"Disagreement resolved in favor of AI (Rule candidate '{best_rule_cand.value}' disqualified by context)"
            else:
                # Disagreement where neither candidate was explicitly disqualified by negative context.
                # Compare calibrated rule score vs model-reported AI score.
                rule_weight = best_rule_cand.confidence
                ai_weight = ai_cand.confidence

                if rule_weight >= ai_weight:
                    winner = best_rule_cand
                    winner_source = "rule"
                    disagree_ev = f"Disagreement: Rule preferred (rule conf={rule_weight:.2f} >= ai conf={ai_weight:.2f}; AI value='{ai_cand.value}')"
                else:
                    winner = ai_cand
                    winner_source = "ai"
                    disagree_ev = f"Disagreement: AI preferred (ai conf={ai_weight:.2f} > rule conf={rule_weight:.2f}; Rule value='{best_rule_cand.value}')"

                # Safe disagreement handling:
                # A true value conflict occurs when distinct, non-overlapping values disagree (e.g. INV-1001 vs INV-1002).
                # If one is a clean substring of the other (e.g. AI extracting vendor name from a raw text line),
                # it is an entity refinement rather than an irreconcilable conflict.
                is_substring = (
                    (len(norm_rule) >= 3 and len(norm_ai) >= 3)
                    and (norm_rule in norm_ai or norm_ai in norm_rule)
                )
                if not is_substring and (min(rule_weight, ai_weight) >= 0.70 or abs(rule_weight - ai_weight) <= 0.15):
                    dampened_conf = round(max(0.35, min(winner.confidence - 0.20, 0.75)), 2)
                    winner.confidence = dampened_conf
                    if hasattr(winner, "score"):
                        winner.score = dampened_conf
                    disagree_ev += f" - Active conflict between Rule ('{best_rule_cand.value}') and AI ('{ai_cand.value}') dampened confidence to {dampened_conf:.2f} (flagged for review)"

                base_ev = rule_ev if winner_source == "rule" else ai_ev
                winner.evidence = (base_ev + " | " if base_ev else "") + disagree_ev

            all_cands = list(r_cands) + [ai_cand]
            reconciled_cands_map[field_name] = all_cands
            selected_fields[field_name] = winner
            field_sources[field_name] = winner_source

        return selected_fields, reconciled_cands_map, field_sources


# Convenience module-level functional alias
reconcile_rule_and_ai = ReconciliationEngine.reconcile
reconcile_candidates = ReconciliationEngine.reconcile

__all__ = ["ReconciliationEngine", "reconcile_rule_and_ai", "reconcile_candidates"]
