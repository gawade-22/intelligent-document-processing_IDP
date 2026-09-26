"""
LLM Document Extraction Service.
Orchestrates document content extraction, prompt building, LLM communication,
robust JSON sanitization, Pydantic validation, and pipeline reconciliation.
Supports multi-class documents (Invoice, Resume, Student Document, Custom).
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from app.core.config import settings
from app.prompts.extraction_prompt import (
    DOCUMENT_TYPE_REGISTRY,
    INVOICE_CONFIG,
    build_extraction_prompt,
    get_document_type_config,
)
from app.schemas.llm import (
    DocumentTypeConfig,
    FieldExtractionValue,
    FieldSpecification,
    LLMExtractionResult,
    LLMExtractionStatus,
)
from app.services.ai.base import (
    AIExtractionProvider,
    LLMProvider,
    MockAIExtractionProvider,
    NoOpAIExtractionProvider,
)
from app.services.ai.factory import get_ai_provider

logger = logging.getLogger(__name__)


def clean_markdown_fences(raw_text: str) -> str:
    """
    Strips markdown code blocks, conversational greetings, and preamble
    to isolate the raw JSON substring.
    """
    if not raw_text or not isinstance(raw_text, str):
        return ""

    cleaned = raw_text.strip()

    # 1. Remove markdown code fences like ```json ... ``` or ```text ... ```
    cleaned = re.sub(r"^```(?:json|text)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    cleaned = cleaned.strip()

    # 2. If conversational text still surrounds the JSON, extract the outer bracketed JSON object
    if not (cleaned.startswith("{") and cleaned.endswith("}")):
        match = re.search(r"(\{[\s\S]*\})", cleaned)
        if match:
            cleaned = match.group(1).strip()

    return cleaned


class LLMExtractor:
    """
    Primary LLM Extraction Service.

    Workflow:
    document_text + document_type + context
                    ↓
        build_extraction_prompt()
                    ↓
         Gemini / Configured LLM
                    ↓
               raw response
                    ↓
          clean_markdown_fences()
                    ↓
            JSON parsing
                    ↓
          Pydantic validation
                    ↓
          LLMExtractionResult
    """

    def __init__(
        self,
        provider: Optional[AIExtractionProvider] = None,
        default_document_type: str = "invoice",
    ) -> None:
        self._provider = provider
        self.default_document_type = default_document_type

    @property
    def provider(self) -> AIExtractionProvider:
        """Lazily resolve the configured AI provider if not explicitly injected."""
        if self._provider is None:
            self._provider = get_ai_provider()
        return self._provider

    def extract(
        self,
        document_text: str,
        document_type: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        custom_fields: Optional[List[FieldSpecification]] = None,
        provider_override: Optional[AIExtractionProvider] = None,
    ) -> LLMExtractionResult:
        """
        Execute end-to-end LLM extraction from document text.

        Args:
            document_text: Text extracted from PDF, OCR, Excel, CSV, or Image.
            document_type: Classification label ('invoice', 'resume', 'student_document', etc.).
            context: Non-binding hints, preliminary vendor keys, or OCR metrics.
            custom_fields: Optional custom field definitions overriding registry defaults.
            provider_override: Optional explicit AI provider instance.

        Returns:
            Validated LLMExtractionResult model.
        """
        effective_type = (document_type or self.default_document_type).lower().strip()
        active_provider = provider_override or self.provider

        # 1. Check for empty or non-existent document text
        if not document_text or not str(document_text).strip():
            logger.warning("Empty document text passed to LLMExtractor.")
            return self._build_empty_result(
                document_type=effective_type,
                custom_fields=custom_fields,
                errors=["Document content is empty or contains no extractable text"],
                provider_name=getattr(active_provider, "provider_name", "unknown"),
            )

        # 2. Check if AI Provider is NoOp (not configured)
        if isinstance(active_provider, NoOpAIExtractionProvider):
            logger.info("AI provider is not configured. Returning unconfigured status.")
            return self._build_empty_result(
                document_type=effective_type,
                custom_fields=custom_fields,
                status=LLMExtractionStatus.AI_NOT_CONFIGURED.value,
                errors=["AI provider is not configured in settings or environment"],
                provider_name="noop",
            )

        # 3. Build Extraction Prompt with explicit 5-tier architecture
        max_chars = getattr(active_provider, "max_input_characters", None) or settings.AI_MAX_INPUT_CHARACTERS
        sys_prompt, user_content, prompt_meta = build_extraction_prompt(
            document_text=document_text,
            document_type=effective_type,
            custom_fields=custom_fields,
            context=context,
            max_chars=max_chars,
        )
        prompt_meta["max_chars"] = max_chars

        # 4. Invoke LLM Provider
        raw_response: Optional[str] = None
        status = LLMExtractionStatus.SUCCESS.value
        errors: List[str] = []
        model_name = getattr(active_provider, "model", "unknown")
        provider_name = getattr(active_provider, "provider_name", "llm")

        try:
            # Check if provider has modern extract_document method
            if hasattr(active_provider, "extract_document"):
                ai_resp = active_provider.extract_document(
                    text=document_text,
                    document_type=effective_type,
                    context=context,
                    custom_fields=custom_fields,
                )
            elif hasattr(active_provider, "extract_invoice"):
                ai_resp = active_provider.extract_invoice(
                    text=document_text,
                    context=context,
                )
            else:
                ai_resp = active_provider.extract(document_text)

            # Standardize response structure from provider
            if hasattr(ai_resp, "status") and ai_resp.status != "SUCCESS":
                status = ai_resp.status
                errors.extend(getattr(ai_resp, "errors", []))
                raw_response = getattr(ai_resp, "raw_response", None)

                return LLMExtractionResult(
                    document_type=effective_type,
                    fields={},
                    status=status,
                    raw_response=raw_response,
                    model=model_name,
                    provider=provider_name,
                    errors=errors or [f"AI provider failed with status {status}"],
                    metadata=prompt_meta,
                )

            # Extract structured data or raw response text
            parsed_data: Optional[Dict[str, Any]] = None

            if hasattr(ai_resp, "fields") and ai_resp.fields is not None:
                if hasattr(ai_resp.fields, "to_dict"):
                    parsed_data = ai_resp.fields.to_dict()
                elif isinstance(ai_resp.fields, dict):
                    parsed_data = ai_resp.fields
                else:
                    parsed_data = dict(ai_resp.fields)
                raw_response = getattr(ai_resp, "raw_response", None) or json.dumps(parsed_data)
            elif isinstance(ai_resp, dict) and "fields" in ai_resp:
                parsed_data = ai_resp
                raw_response = ai_resp.get("raw_response") or json.dumps(parsed_data)
            elif hasattr(ai_resp, "raw_response") and ai_resp.raw_response:
                raw_response = ai_resp.raw_response
            elif isinstance(ai_resp, dict):
                parsed_data = ai_resp
                raw_response = json.dumps(ai_resp)
            else:
                raw_response = str(ai_resp or "")

        except Exception as exc:
            err_msg = f"Exception invoking LLM provider '{provider_name}': {str(exc)}"
            logger.error(err_msg, exc_info=True)
            return LLMExtractionResult(
                document_type=effective_type,
                fields={},
                status=LLMExtractionStatus.API_ERROR.value,
                raw_response=None,
                model=model_name,
                provider=provider_name,
                errors=[err_msg],
                metadata=prompt_meta,
            )

        # 5. Parse Structured JSON if not already provided as structured dict
        if parsed_data is None:
            parsed_data, parse_errors = self.parse_json_response(raw_response)
            if parse_errors:
                logger.warning(f"Failed to parse JSON from LLM: {parse_errors}")
                return LLMExtractionResult(
                    document_type=effective_type,
                    fields={},
                    status=LLMExtractionStatus.PARSING_ERROR.value,
                    raw_response=raw_response,
                    model=model_name,
                    provider=provider_name,
                    errors=parse_errors,
                    metadata=prompt_meta,
                )

        # 6. Validate Response Structure using Pydantic
        validated_result = self.validate_response(
            parsed_data=parsed_data or {},
            document_type=effective_type,
            custom_fields=custom_fields,
            raw_response=raw_response,
            model=model_name,
            provider=provider_name,
            metadata=prompt_meta,
        )

        if prompt_meta.get("is_truncated"):
            trunc_notice = f"Document content exceeded AI_MAX_INPUT_CHARACTERS ({prompt_meta.get('max_chars', 12000)} chars) and was safely truncated preserving header and footer."
            if trunc_notice not in validated_result.errors:
                validated_result.errors.append(trunc_notice)

        return validated_result

    def parse_json_response(
        self,
        raw_response: Optional[str],
    ) -> Tuple[Optional[Dict[str, Any]], List[str]]:
        """
        Robustly parses JSON from LLM output.
        Handles markdown fences, leading/trailing whitespace, and preamble text.
        """
        if not raw_response or not str(raw_response).strip():
            return None, ["LLM returned an empty response"]

        cleaned = clean_markdown_fences(raw_response)
        if not cleaned:
            return None, ["No valid JSON content could be identified in LLM response"]

        try:
            parsed = json.loads(cleaned)
            if not isinstance(parsed, dict):
                return None, [f"Expected JSON object (dict), but received {type(parsed).__name__}"]
            return parsed, []
        except json.JSONDecodeError as jde:
            # Fallback attempt: find any {...} block using bracket depth counter
            extracted_obj = self._extract_first_valid_json_object(raw_response)
            if extracted_obj is not None:
                return extracted_obj, []
            return None, [f"JSON syntax error in LLM output: {jde.msg} at line {jde.lineno}, col {jde.colno}"]

    def _extract_first_valid_json_object(self, text: str) -> Optional[Dict[str, Any]]:
        """Secondary regex/bracket scanner for resilient JSON extraction."""
        start_idx = text.find("{")
        while start_idx != -1:
            depth = 0
            in_quote = False
            escape = False
            for idx in range(start_idx, len(text)):
                char = text[idx]
                if char == '"' and not escape:
                    in_quote = not in_quote
                elif not in_quote:
                    if char == "{":
                        depth += 1
                    elif char == "}":
                        depth -= 1
                        if depth == 0:
                            candidate_str = text[start_idx : idx + 1]
                            try:
                                obj = json.loads(candidate_str)
                                if isinstance(obj, dict):
                                    return obj
                            except json.JSONDecodeError:
                                break
                escape = (char == "\\" and not escape)
            start_idx = text.find("{", start_idx + 1)
        return None

    def validate_response(
        self,
        parsed_data: Dict[str, Any],
        document_type: str = "invoice",
        custom_fields: Optional[List[FieldSpecification]] = None,
        raw_response: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LLMExtractionResult:
        """
        Validates parsed JSON against target field specifications.
        Supports both:
          Nested schema: {"fields": {"<field>": {"value": ..., "confidence": ...}}}
          Flat schema: {"<field>": ..., "confidence": {...}, "evidence": {...}}
        """
        doc_cfg = get_document_type_config(document_type)
        expected_fields: List[FieldSpecification] = (
            custom_fields
            if custom_fields
            else (doc_cfg.fields if doc_cfg else INVOICE_CONFIG.fields)
        )

        extracted_field_values: Dict[str, FieldExtractionValue] = {}
        validation_errors: List[str] = []

        # Determine if payload is nested under 'fields' key
        fields_container = parsed_data.get("fields")
        is_nested = isinstance(fields_container, dict)

        global_confidence = parsed_data.get("confidence") if isinstance(parsed_data.get("confidence"), dict) else {}
        global_evidence = parsed_data.get("evidence") if isinstance(parsed_data.get("evidence"), dict) else {}

        for spec in expected_fields:
            fname = spec.name
            val: Optional[Any] = None
            conf: float = 0.85  # Default confidence for LLM extraction
            ev: Optional[str] = None

            if is_nested and fname in fields_container:
                item = fields_container[fname]
                if isinstance(item, dict):
                    val = item.get("value")
                    conf = item.get("confidence", 0.85)
                    ev = item.get("evidence")
                else:
                    val = item
                    conf = global_confidence.get(fname, 0.85)
                    ev = global_evidence.get(fname)

            elif fname in parsed_data:
                val = parsed_data[fname]
                conf = global_confidence.get(fname, 0.85)
                ev = global_evidence.get(fname)

            # Normalize 'null', 'none', 'n/a' strings into Python None
            if isinstance(val, str) and val.strip().lower() in ("null", "none", "n/a", "not found", "undefined", ""):
                val = None

            # If value is None, confidence is 0.0
            if val is None:
                conf = 0.0

            try:
                field_val_obj = FieldExtractionValue(
                    value=val,
                    confidence=conf,
                    evidence=ev,
                )
                extracted_field_values[fname] = field_val_obj
            except Exception as exc:
                validation_errors.append(f"Field '{fname}' failed validation: {str(exc)}")
                extracted_field_values[fname] = FieldExtractionValue(value=None, confidence=0.0)

        # Include any extra fields returned by the LLM that were not in expected_fields
        source_dict = fields_container if is_nested else parsed_data
        for k, v in source_dict.items():
            if k not in extracted_field_values and k not in ("confidence", "evidence", "fields", "status", "metadata"):
                if isinstance(v, dict) and "value" in v:
                    extracted_field_values[k] = FieldExtractionValue(
                        value=v.get("value"),
                        confidence=v.get("confidence", 0.80),
                        evidence=v.get("evidence"),
                    )
                else:
                    extracted_field_values[k] = FieldExtractionValue(
                        value=v,
                        confidence=global_confidence.get(k, 0.80),
                        evidence=global_evidence.get(k),
                    )

        return LLMExtractionResult(
            document_type=document_type,
            fields=extracted_field_values,
            status=LLMExtractionStatus.SUCCESS.value if not validation_errors else LLMExtractionStatus.VALIDATION_ERROR.value,
            raw_response=raw_response,
            model=model,
            provider=provider,
            errors=validation_errors,
            metadata=metadata or {},
        )

    def _build_empty_result(
        self,
        document_type: str,
        custom_fields: Optional[List[FieldSpecification]] = None,
        status: str = LLMExtractionStatus.SUCCESS.value,
        errors: Optional[List[str]] = None,
        provider_name: str = "none",
    ) -> LLMExtractionResult:
        """Generates an empty extraction result initialized with null values."""
        doc_cfg = get_document_type_config(document_type)
        specs = custom_fields or (doc_cfg.fields if doc_cfg else INVOICE_CONFIG.fields)

        empty_fields = {
            s.name: FieldExtractionValue(value=None, confidence=0.0, evidence="Not extracted")
            for s in specs
        }

        return LLMExtractionResult(
            document_type=document_type,
            fields=empty_fields,
            status=status,
            raw_response=None,
            model="none",
            provider=provider_name,
            errors=errors or [],
            metadata={},
        )


# =============================================================================
# Singleton / Factory Accessor
# =============================================================================

_global_llm_extractor: Optional[LLMExtractor] = None


def get_llm_extractor(
    provider: Optional[AIExtractionProvider] = None,
    document_type: str = "invoice",
) -> LLMExtractor:
    """
    Returns an LLMExtractor instance. If provider is provided, creates a new instance;
    otherwise returns a cached global instance.
    """
    global _global_llm_extractor
    if provider is not None:
        return LLMExtractor(provider=provider, default_document_type=document_type)

    if _global_llm_extractor is None:
        _global_llm_extractor = LLMExtractor(default_document_type=document_type)
    return _global_llm_extractor
