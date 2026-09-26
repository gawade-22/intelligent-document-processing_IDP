"""
Generic REST OpenAI-compatible LLM extraction provider.
Uses Python standard library urllib.request (zero proprietary SDK dependencies).
Supports OpenAI, OpenRouter, Groq, Together, Ollama, and self-hosted endpoints.
"""

import json
import logging
import re
import socket
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Union

from app.core.config import settings
from app.services.ai.base import AIExtractionProvider
from app.services.ai.prompt import build_prompt
from app.services.ai.schemas import (
    AIExtractedFields,
    AIExtractionResponse,
    AIExtractionStatus,
)
from app.services.ai.vendor_prompts import get_vendor_prompt

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(AIExtractionProvider):
    """
    Provider for any OpenAI-compatible Chat Completions REST API.
    Does NOT require the openai library; communicates directly over HTTP.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
        max_input_characters: Optional[int] = None,
        provider_name: str = "openai_compatible",
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.AI_API_KEY
        self.provider_name = provider_name

        # Resolve Base URL
        if base_url is not None:
            self.base_url = base_url.rstrip("/")
        elif settings.AI_BASE_URL:
            self.base_url = settings.AI_BASE_URL.rstrip("/")
        elif provider_name == "gemini":
            self.base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
        else:
            self.base_url = "https://api.openai.com/v1"

        # Resolve Model
        if model is not None:
            self.model = model
        elif settings.AI_MODEL:
            self.model = settings.AI_MODEL
        elif provider_name == "gemini":
            self.model = "gemini-1.5-flash"
        else:
            self.model = "gpt-4o-mini"
        self.timeout = timeout if timeout is not None else settings.AI_TIMEOUT
        self.max_input_characters = (
            max_input_characters
            if max_input_characters is not None
            else settings.AI_MAX_INPUT_CHARACTERS
        )
        self.provider_name = provider_name

    def _clean_markdown_fences(self, raw_content: str) -> str:
        """Removes markdown code fences like ```json ... ``` or ``` ... ``` before parsing."""
        if not raw_content:
            return ""
        cleaned = raw_content.strip()
        # Remove opening ```json or ```
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
        # Remove closing ```
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)
        return cleaned.strip()

    def extract_invoice(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AIExtractionResponse:
        """
        Executes invoice extraction via OpenAI-compatible chat completions endpoint.
        """
        # 1. Validate API Key
        if not self.api_key or not self.api_key.strip():
            logger.info("AI extraction requested but API key is missing or not configured.")
            return AIExtractionResponse(
                status=AIExtractionStatus.AI_NOT_CONFIGURED.value,
                fields=None,
                raw_response=None,
                model=self.model,
                provider=self.provider_name,
                errors=["AI API key is not configured"],
            )

        # 2. Resolve Vendor-specific Prompt if available
        vendor_prompt_text: Optional[str] = None
        if context and isinstance(context, dict):
            vendor_target = (
                context.get("vendor_name")
                or context.get("detected_vendor")
                or context.get("vendor")
            )
            if vendor_target and isinstance(vendor_target, str):
                v_cfg = get_vendor_prompt(vendor_target)
                if v_cfg and "prompt" in v_cfg:
                    vendor_prompt_text = v_cfg["prompt"]

        # 3. Assemble Prompt
        sys_prompt, user_content, meta = build_prompt(
            text=text,
            vendor_prompt=vendor_prompt_text,
            context=context,
            max_chars=self.max_input_characters,
        )

        endpoint_url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }

        req_data = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key.strip()}",
            "Content-Type": "application/json",
            "User-Agent": "IDP-Invoice-Extractor/1.0",
        }

        req = urllib.request.Request(endpoint_url, data=req_data, headers=headers, method="POST")

        # 4. Execute HTTP Request with Error Mapping
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                resp_bytes = response.read()
                resp_text = resp_bytes.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as http_err:
            status_code = http_err.code
            err_body = ""
            try:
                err_body = http_err.read().decode("utf-8", errors="replace")
            except Exception:
                pass

            if status_code == 429:
                err_msg = f"Rate limit exceeded (HTTP 429) from {self.provider_name}"
                logger.warning(err_msg)
                return AIExtractionResponse(
                    status=AIExtractionStatus.RATE_LIMITED.value,
                    fields=None,
                    raw_response=err_body,
                    model=self.model,
                    provider=self.provider_name,
                    errors=[err_msg],
                )
            elif status_code in (401, 403):
                err_msg = f"Authentication failed (HTTP {status_code}) from {self.provider_name}"
                logger.warning(err_msg)
                return AIExtractionResponse(
                    status=AIExtractionStatus.API_ERROR.value,
                    fields=None,
                    raw_response=err_body,
                    model=self.model,
                    provider=self.provider_name,
                    errors=[err_msg],
                )
            else:
                err_msg = f"HTTP error {status_code} from {self.provider_name}: {http_err.reason}"
                logger.warning(err_msg)
                return AIExtractionResponse(
                    status=AIExtractionStatus.API_ERROR.value,
                    fields=None,
                    raw_response=err_body,
                    model=self.model,
                    provider=self.provider_name,
                    errors=[err_msg],
                )
        except (socket.timeout, TimeoutError) as timeout_err:
            err_msg = f"Request timed out after {self.timeout}s: {timeout_err}"
            logger.warning(err_msg)
            return AIExtractionResponse(
                status=AIExtractionStatus.TIMEOUT.value,
                fields=None,
                raw_response=None,
                model=self.model,
                provider=self.provider_name,
                errors=[err_msg],
            )
        except urllib.error.URLError as url_err:
            # Check if reason is a socket timeout
            if isinstance(url_err.reason, (socket.timeout, TimeoutError)):
                err_msg = f"Request timed out after {self.timeout}s"
                logger.warning(err_msg)
                return AIExtractionResponse(
                    status=AIExtractionStatus.TIMEOUT.value,
                    fields=None,
                    raw_response=None,
                    model=self.model,
                    provider=self.provider_name,
                    errors=[err_msg],
                )
            err_msg = f"Network/connection error connecting to {self.provider_name}: {url_err.reason}"
            logger.warning(err_msg)
            return AIExtractionResponse(
                status=AIExtractionStatus.API_ERROR.value,
                fields=None,
                raw_response=None,
                model=self.model,
                provider=self.provider_name,
                errors=[err_msg],
            )
        except Exception as exc:
            err_msg = f"Unexpected error during AI extraction request: {str(exc)}"
            logger.error(err_msg, exc_info=True)
            return AIExtractionResponse(
                status=AIExtractionStatus.API_ERROR.value,
                fields=None,
                raw_response=None,
                model=self.model,
                provider=self.provider_name,
                errors=[err_msg],
            )

        # 5. Parse Top-level Completion Payload
        try:
            data = json.loads(resp_text)
            choices = data.get("choices", [])
            if not choices:
                return AIExtractionResponse(
                    status=AIExtractionStatus.PARSING_ERROR.value,
                    fields=None,
                    raw_response=resp_text,
                    model=self.model,
                    provider=self.provider_name,
                    errors=["OpenAI response contained no choices"],
                )
            raw_content = choices[0].get("message", {}).get("content", "")
            if not raw_content or not str(raw_content).strip():
                return AIExtractionResponse(
                    status=AIExtractionStatus.PARSING_ERROR.value,
                    fields=None,
                    raw_response=resp_text,
                    model=self.model,
                    provider=self.provider_name,
                    errors=["Model returned empty message content"],
                )
        except Exception as exc:
            err_msg = f"Failed to parse outer JSON completion response: {str(exc)}"
            return AIExtractionResponse(
                status=AIExtractionStatus.PARSING_ERROR.value,
                fields=None,
                raw_response=resp_text,
                model=self.model,
                provider=self.provider_name,
                errors=[err_msg],
            )

        # 6. Clean Markdown Fences & Validate Structured Fields
        cleaned_json_str = self._clean_markdown_fences(raw_content)
        try:
            fields_data = json.loads(cleaned_json_str)
            if not isinstance(fields_data, dict):
                return AIExtractionResponse(
                    status=AIExtractionStatus.PARSING_ERROR.value,
                    fields=None,
                    raw_response=raw_content,
                    model=self.model,
                    provider=self.provider_name,
                    errors=["Model output parsed to non-dict JSON structure"],
                )

            # Adapt nested {"fields": {"vendor_name": {"value": ...}}} schema to AIExtractedFields
            if "fields" in fields_data and isinstance(fields_data["fields"], dict):
                inner_fields = fields_data["fields"]
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
                if "confidence" in fields_data and isinstance(fields_data["confidence"], dict):
                    conf_data.update(fields_data["confidence"])
                if "evidence" in fields_data and isinstance(fields_data["evidence"], dict):
                    ev_data.update(fields_data["evidence"])
                flat_data["confidence"] = conf_data
                flat_data["evidence"] = ev_data
                fields_data = flat_data

            extracted_fields = AIExtractedFields(**fields_data)
        except Exception as exc:
            err_msg = f"Failed to parse structured invoice fields from model content: {str(exc)}"
            logger.warning(err_msg)
            return AIExtractionResponse(
                status=AIExtractionStatus.PARSING_ERROR.value,
                fields=None,
                raw_response=raw_content,
                model=self.model,
                provider=self.provider_name,
                errors=[err_msg],
            )

        return AIExtractionResponse(
            status=AIExtractionStatus.SUCCESS.value,
            fields=extracted_fields,
            raw_response=raw_content,
            model=self.model,
            provider=self.provider_name,
            errors=[],
        )

    def extract_document(
        self,
        text: str,
        document_type: str = "invoice",
        context: Optional[Dict[str, Any]] = None,
        custom_fields: Optional[List[Any]] = None,
    ) -> Any:
        """
        Generic multi-document extraction via LLM completions.
        Builds prompt using build_extraction_prompt and delegates to chat completions.
        """
        if not self.api_key or not self.api_key.strip():
            return AIExtractionResponse(
                status=AIExtractionStatus.AI_NOT_CONFIGURED.value,
                fields=None,
                raw_response=None,
                model=self.model,
                provider=self.provider_name,
                errors=["AI API key is not configured"],
            )

        from app.prompts.extraction_prompt import build_extraction_prompt

        sys_prompt, user_content, _ = build_extraction_prompt(
            document_text=text,
            document_type=document_type,
            custom_fields=custom_fields,
            context=context,
            max_chars=self.max_input_characters,
        )

        endpoint_url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }

        req_data = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key.strip()}",
            "Content-Type": "application/json",
            "User-Agent": "IDP-Document-Extractor/1.0",
        }

        req = urllib.request.Request(endpoint_url, data=req_data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                resp_bytes = response.read()
                resp_text = resp_bytes.decode("utf-8", errors="replace")

            data = json.loads(resp_text)
            choices = data.get("choices", [])
            raw_content = choices[0].get("message", {}).get("content", "") if choices else ""
            cleaned = self._clean_markdown_fences(raw_content)
            parsed_data = json.loads(cleaned)

            return {
                "status": "SUCCESS",
                "raw_response": raw_content,
                "fields": parsed_data.get("fields", parsed_data),
                "model": self.model,
                "provider": self.provider_name,
            }
        except Exception as exc:
            logger.warning(f"extract_document error: {exc}")
            # Fall back to extract_invoice
            return self.extract_invoice(text=text, context=context)
