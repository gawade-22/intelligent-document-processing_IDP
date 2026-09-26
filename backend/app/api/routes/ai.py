"""
FastAPI router for AI / LLM Configuration, Connectivity Testing, Prompt Inspection,
and Multi-tier Extraction Breakdowns.
"""

import json
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.ai_config import AIConfigState, ai_config_manager
from app.core.config import settings
from app.database.connection import get_db
from app.models.document import Document
from app.models.document_record import DocumentRecord
from app.prompts.extraction_prompt import (
    build_extraction_prompt,
    build_full_prompt,
    get_document_type_config,
)
from app.schemas.ai import (
    AIConfigUpdateRequest,
    AIConnectionTestRequest,
    AIConnectionTestResponse,
    AIPromptPreviewRequest,
    AIPromptPreviewResponse,
    DocumentExtractionResponse,
    FieldExtractionDetail,
)
from app.schemas.processing import ProcessingResult, to_processing_result
from app.services.ai.base import (
    AIExtractionStatus,
    MockAIExtractionProvider,
    NoOpAIExtractionProvider,
)
from app.services.ai.factory import get_ai_provider
from app.services.ai.providers.gemini import GeminiProvider
from app.services.processing_pipeline import DocumentNotFoundError, pipeline

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# 1. Configuration Endpoints
# =============================================================================

@router.get(
    "/config",
    response_model=AIConfigState,
    summary="Get current AI/LLM configuration",
    description="Returns active AI provider, model, enabled status, and masked API key info. Zero secret leakage.",
)
def get_ai_config() -> AIConfigState:
    """Returns safe, client-facing AI configuration."""
    return ai_config_manager.get_state()


@router.put(
    "/config",
    response_model=AIConfigState,
    summary="Update AI/LLM configuration",
    description="Updates provider, model, enabled toggle, and API key securely on the backend.",
)
def update_ai_config(payload: AIConfigUpdateRequest) -> AIConfigState:
    """Updates runtime AI settings without leaking secrets."""
    updated = ai_config_manager.update_config(
        provider=payload.provider,
        model=payload.model,
        enabled=payload.enabled,
        api_key=payload.api_key,
        clear_api_key=payload.clear_api_key,
        custom_prompt=payload.custom_prompt,
        timeout=payload.timeout,
        max_input_characters=payload.max_input_characters,
    )
    return updated


# =============================================================================
# 2. Connection Testing
# =============================================================================

@router.post(
    "/test-connection",
    response_model=AIConnectionTestResponse,
    summary="Test LLM connection",
    description="Validates that the configured LLM provider and model respond properly. Never leaks credentials.",
)
def test_ai_connection(payload: Optional[AIConnectionTestRequest] = None) -> AIConnectionTestResponse:
    """Tests connectivity to the active or requested AI provider."""
    provider_name = (payload.provider if payload and payload.provider else ai_config_manager.provider).lower()
    model_name = payload.model if payload and payload.model else ai_config_manager.model
    api_key_override = payload.api_key if payload and payload.api_key else None

    # Check key configuration if not mock/noop
    effective_has_key = bool(api_key_override) or ai_config_manager.has_api_key()
    if provider_name in ["gemini", "openai", "openai_compatible"] and not effective_has_key:
        return AIConnectionTestResponse(
            success=False,
            status="NOT_CONFIGURED",
            provider=provider_name,
            model=model_name,
            message=f"{provider_name.capitalize()} API key is not configured. Please provide an API key in AI Settings.",
        )

    try:
        if provider_name == "mock":
            mock_prov = MockAIExtractionProvider(model=model_name)
            res = mock_prov.extract_invoice("Test invoice connectivity check")
            return AIConnectionTestResponse(
                success=True,
                status="CONNECTED",
                provider="mock",
                model=model_name,
                message="Mock provider connection successful. Ready for deterministic testing.",
            )

        if provider_name == "noop":
            return AIConnectionTestResponse(
                success=True,
                status="CONNECTED",
                provider="noop",
                model="noop",
                message="NoOp provider active (zero network calls, safe offline default).",
            )

        # For real Gemini / OpenAI Compatible
        test_prov = get_ai_provider(
            provider_type=provider_name,
            model=model_name,
            api_key=api_key_override if api_key_override else (settings.AI_API_KEY or settings.GEMINI_API_KEY),
            timeout=10,
        )

        # Ping provider with a minimal verification prompt
        response = test_prov.extract_invoice("Minimal test ping for connection verification")

        if response.status == AIExtractionStatus.AI_NOT_CONFIGURED.value:
            return AIConnectionTestResponse(
                success=False,
                status="NOT_CONFIGURED",
                provider=provider_name,
                model=model_name,
                message="API key is missing or not configured.",
            )

        if response.status == AIExtractionStatus.RATE_LIMITED.value:
            return AIConnectionTestResponse(
                success=False,
                status="CONNECTION_FAILED",
                provider=provider_name,
                model=model_name,
                message="Rate limit reached with the provider. Please try again shortly.",
            )

        if response.status == AIExtractionStatus.API_ERROR.value:
            err_detail = response.errors[0] if response.errors else "Provider returned an error."
            # Sanitize away raw tokens
            safe_err = err_detail.replace(settings.AI_API_KEY or "___", "[REDACTED]")
            return AIConnectionTestResponse(
                success=False,
                status="CONNECTION_FAILED",
                provider=provider_name,
                model=model_name,
                message=f"Connection failed: {safe_err}",
            )

        return AIConnectionTestResponse(
            success=True,
            status="CONNECTED",
            provider=provider_name,
            model=model_name,
            message=f"Connection successful. {provider_name.capitalize()} model '{model_name}' is responsive.",
        )

    except Exception as exc:
        logger.warning("AI Connection test exception: %s", exc)
        return AIConnectionTestResponse(
            success=False,
            status="CONNECTION_FAILED",
            provider=provider_name,
            model=model_name,
            message="Connection attempt failed. Please check network connectivity and API key validity.",
        )


# =============================================================================
# 3. Prompt Preview
# =============================================================================

@router.post(
    "/prompt/preview",
    response_model=AIPromptPreviewResponse,
    summary="Preview LLM extraction prompt",
    description="Inspect the exact 5-tier prompt structure generated for a given document type. Zero secret leakage.",
)
def preview_ai_prompt(payload: AIPromptPreviewRequest) -> AIPromptPreviewResponse:
    """Generates the transparent breakdown of the extraction prompt for UI preview."""
    doc_type = payload.document_type or "invoice"
    sample_text = payload.sample_text or (
        "Acme Industrial Solutions Inc\n"
        "100 Tech Way, Suite 400, Austin TX\n"
        "Invoice Number: INV-2026-9041\n"
        "Billing Date: September 15, 2026\n"
        "Description: Cloud Infrastructure Services - $15,400.00\n"
        "Grand Total Due: $15,400.00\n"
        "Payment Terms: Net 30"
    )

    sys_prompt, user_content, meta = build_extraction_prompt(
        document_text=sample_text,
        document_type=doc_type,
    )

    full_prompt = build_full_prompt(
        document_text=sample_text,
        document_type=doc_type,
    )

    # Extract clean subsections for dedicated UI display
    doc_cfg = get_document_type_config(doc_type)
    req_fields = doc_cfg.get_field_names() if doc_cfg else ["vendor_name", "invoice_number", "invoice_date", "total_amount"]

    return AIPromptPreviewResponse(
        document_type=doc_type,
        system_instructions=sys_prompt,
        extraction_requirements=f"Target Fields for {doc_type}: {', '.join(req_fields)}",
        expected_json_format="{\n  \"fields\": {\n    \"field_name\": {\n      \"value\": \"...\",\n      \"confidence\": 0.95,\n      \"evidence\": \"...\"\n    }\n  }\n}",
        document_content_preview=user_content,
        full_prompt=full_prompt,
    )


# =============================================================================
# 4. Document Multi-Tier Extraction Breakdown
# =============================================================================

@router.get(
    "/documents/{document_id}/extraction",
    response_model=DocumentExtractionResponse,
    summary="Get multi-tier document extraction breakdown",
    description="Returns Rule Extraction, LLM Extraction, Reconciliation, and Final Result comparison for a document.",
)
def get_document_extraction_breakdown(
    document_id: int,
    db: Session = Depends(get_db),
) -> DocumentExtractionResponse:
    """Assembles transparent Rule vs LLM vs Reconciliation comparison for the UI."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found.",
        )

    rec = db.query(DocumentRecord).filter(DocumentRecord.document_id == doc.id).first()
    extracted_data = (rec.extracted_data or {}) if rec else {}
    fields_payload = extracted_data.get("fields", {})

    rule_extraction: Dict[str, FieldExtractionDetail] = {}
    llm_extraction: Dict[str, FieldExtractionDetail] = {}
    reconciliation: Dict[str, FieldExtractionDetail] = {}
    final_result: Dict[str, Optional[Any]] = {}

    candidates_map = extracted_data.get("candidates", {})

    for fname, fdata in fields_payload.items():
        fval = fdata.get("normalized_value") if fdata.get("normalized_value") is not None else fdata.get("value")
        fconf = float(fdata.get("confidence", 0.0) or 0.0)
        fsrc = str(fdata.get("source", "none")).lower()

        final_result[fname] = fval

        # Find candidate values from candidate list
        cands_for_field = candidates_map.get(fname, [])
        rule_cands = [c for c in cands_for_field if str(c.get("source", "")).lower() in ["keyword", "regex", "positional", "rule"]]
        ai_cands = [c for c in cands_for_field if str(c.get("source", "")).lower() == "ai"]

        # 1. Rule Extraction
        if rule_cands:
            best_rule = max(rule_cands, key=lambda c: float(c.get("confidence", 0.0) or 0.0))
            rule_extraction[fname] = FieldExtractionDetail(
                value=best_rule.get("value"),
                confidence=float(best_rule.get("confidence", 0.0) or 0.0),
                source="rule",
                evidence=best_rule.get("evidence"),
            )
        elif "rule" in fsrc:
            rule_extraction[fname] = FieldExtractionDetail(
                value=fval,
                confidence=fconf,
                source="rule",
                evidence="Rule candidate matched",
            )
        else:
            rule_extraction[fname] = FieldExtractionDetail(
                value=None,
                confidence=0.0,
                source="rule",
                evidence="No rule candidate found",
            )

        # 2. LLM Extraction
        if ai_cands:
            best_ai = max(ai_cands, key=lambda c: float(c.get("confidence", 0.0) or 0.0))
            llm_extraction[fname] = FieldExtractionDetail(
                value=best_ai.get("value"),
                confidence=float(best_ai.get("confidence", 0.0) or 0.0),
                source="ai",
                evidence=best_ai.get("evidence"),
            )
        elif "ai" in fsrc:
            llm_extraction[fname] = FieldExtractionDetail(
                value=fval,
                confidence=fconf,
                source="ai",
                evidence="Extracted by LLM",
            )
        else:
            llm_extraction[fname] = FieldExtractionDetail(
                value=None,
                confidence=0.0,
                source="ai",
                evidence="No AI extraction returned",
            )

        # 3. Reconciliation Status & Comparison
        rule_val_clean = str(rule_extraction[fname].value or "").strip().lower()
        ai_val_clean = str(llm_extraction[fname].value or "").strip().lower()

        if "rule+ai" in fsrc or (rule_val_clean and ai_val_clean and rule_val_clean == ai_val_clean):
            recon_status = "AGREED"
            reason = "Mutual agreement between Rule-based and LLM extraction (confidence reinforced)"
        elif rule_val_clean and ai_val_clean and rule_val_clean != ai_val_clean:
            recon_status = "REVIEW REQUIRED"
            reason = f"Disagreement: Rule found '{rule_extraction[fname].value}' vs LLM found '{llm_extraction[fname].value}'"
        elif ai_val_clean and not rule_val_clean:
            recon_status = "SINGLE_SOURCE"
            reason = "Extracted solely by LLM (no rule candidate)"
        elif rule_val_clean and not ai_val_clean:
            recon_status = "SINGLE_SOURCE"
            reason = "Extracted solely by Rule engine"
        else:
            recon_status = "MISSING"
            reason = "Field missing in document"

        reconciliation[fname] = FieldExtractionDetail(
            value=fval,
            confidence=fconf,
            source=fsrc,
            status=recon_status,
            reason=reason,
        )

    routing_info = extracted_data.get("routing", {})
    review_reasons = routing_info.get("review_reasons") or []
    if doc.error_message and doc.error_message not in review_reasons:
        review_reasons.append(doc.error_message)

    validation_errors = extracted_data.get("validation", {}).get("errors") or []

    return DocumentExtractionResponse(
        document_id=doc.id,
        file_name=doc.file_name,
        status=doc.status,
        document_type=rec.document_type if rec else "invoice",
        confidence_score=rec.confidence_score if rec else None,
        extraction_method_used="rule+ai" if any("ai" in str(d.get("source", "")).lower() for d in fields_payload.values()) else "rule",
        rule_extraction=rule_extraction,
        llm_extraction=llm_extraction,
        reconciliation=reconciliation,
        final_result=final_result,
        validation_errors=validation_errors,
        review_reasons=review_reasons,
        raw_text=rec.raw_text if rec else None,
        viewer_url=f"/api/documents/{doc.id}/file",
    )


# =============================================================================
# 5. Execute AI Extraction on Document
# =============================================================================

@router.post(
    "/documents/{document_id}/ai-extract",
    response_model=ProcessingResult,
    summary="Process document using AI / LLM extraction",
    description="Executes the full pipeline with AI extraction enabled, reconciling rule and LLM output.",
)
def extract_document_with_ai(
    document_id: int,
    method: str = Query(default="rule_plus_llm", description="Method: 'rule', 'llm', or 'rule_plus_llm'"),
    document_type: Optional[str] = Query(default=None, description="Optional document class override"),
    db: Session = Depends(get_db),
) -> ProcessingResult:
    """Executes pipeline with explicit AI provider and extraction method."""
    try:
        # Resolve provider based on method
        if method == "rule":
            provider_override = NoOpAIExtractionProvider()
        else:
            provider_override = get_ai_provider()

        pipeline_result = pipeline.process_document(
            document_id=document_id,
            db=db,
            ai_provider_override=provider_override,
        )
        return to_processing_result(pipeline_result)
    except DocumentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found.",
        )
    except Exception as exc:
        logger.error(f"Error during AI extraction on doc ID {document_id}: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extraction failure: {str(exc)}",
        )
