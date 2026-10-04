"""
Generic REST OpenAI-compatible LLM extraction provider.
Uses Python standard library urllib.request (zero proprietary SDK dependencies).
Supports OpenAI, OpenRouter, Groq, Together, Ollama, and self-hosted endpoints.
"""

import json
import logging
import re
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple, Union

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
            self.model = "gemini-2.5-flash"
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

        # 4. Execute HTTP Request with Error Mapping and Automatic Retries
        raw_content, err_msg, status_code = self._execute_http_completion(endpoint_url, payload)
        if err_msg or not raw_content:
            status = (
                AIExtractionStatus.RATE_LIMITED.value
                if status_code == 429
                else (
                    AIExtractionStatus.TIMEOUT.value
                    if "timed out" in (err_msg or "").lower()
                    else AIExtractionStatus.API_ERROR.value
                )
            )
            return AIExtractionResponse(
                status=status,
                fields=None,
                raw_response=None,
                model=self.model,
                provider=self.provider_name,
                errors=[err_msg or "Model returned empty message content"],
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

    def _execute_http_completion(
        self,
        endpoint_url: str,
        payload: dict,
        max_retries: int = 3,
    ) -> Tuple[Optional[str], Optional[str], Optional[int]]:
        """
        Executes an HTTP POST completion with exponential backoff retry for transient errors
        (HTTP 429 rate limit, HTTP 500/502/503/504 server overload, socket timeouts).
        Returns:
            Tuple of (raw_content_str, error_message_or_None, status_code_or_None)
        """
        req_data = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key.strip()}",
            "Content-Type": "application/json",
            "User-Agent": "IDP-Document-Extractor/1.0",
        }

        last_err = ""
        last_code = None
        for attempt in range(max_retries):
            req = urllib.request.Request(endpoint_url, data=req_data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    resp_bytes = response.read()
                    resp_text = resp_bytes.decode("utf-8", errors="replace")

                data = json.loads(resp_text)
                choices = data.get("choices", [])
                if not choices:
                    return None, f"Response contained no choices: {resp_text[:200]}", 200
                raw_content = choices[0].get("message", {}).get("content", "")
                return raw_content, None, 200

            except urllib.error.HTTPError as http_err:
                last_code = http_err.code
                err_body = ""
                try:
                    err_body = http_err.read().decode("utf-8", errors="replace")
                except Exception:
                    pass

                if last_code == 429:
                    if any(term in err_body.lower() for term in ("quota", "resource_exhausted", "exceeded your current quota", "generativelanguage.googleapis.com")):
                        last_err = f"Gemini API quota exhausted (HTTP 429): {err_body[:200]}"
                        logger.warning(f"Fast-failing LLM call: {last_err}")
                        break
                if last_code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 1.5
                    logger.warning(
                        f"Transient HTTP {last_code} from {self.provider_name}. "
                        f"Retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})... Response: {err_body[:150]}"
                    )
                    time.sleep(wait_time)
                    continue

                if last_code == 429:
                    last_err = f"Rate limit exceeded (HTTP 429) from {self.provider_name}: {err_body or http_err.reason}"
                elif last_code == 401:
                    last_err = f"Authentication failed (HTTP 401) from {self.provider_name}: {err_body or http_err.reason}"
                else:
                    last_err = f"HTTP error {last_code} from {self.provider_name}: {err_body or http_err.reason}"
                logger.warning(last_err)
                break

            except (socket.timeout, TimeoutError) as timeout_err:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 1.0
                    logger.warning(f"Request timeout from {self.provider_name}. Retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
                    continue
                last_err = f"Request timed out after {self.timeout}s"
                break

            except urllib.error.URLError as url_err:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 1.0
                    logger.warning(f"Connection error to {self.provider_name}: {url_err.reason}. Retrying...")
                    time.sleep(wait_time)
                    continue
                last_err = f"Connection error to {self.provider_name}: {url_err.reason}"
                break

            except Exception as exc:
                last_err = f"Unexpected error during AI completion: {exc}"
                break

        return None, last_err, last_code

    def extract_document(
        self,
        text: str,
        document_type: str = "invoice",
        context: Optional[Dict[str, Any]] = None,
        custom_fields: Optional[List[Any]] = None,
    ) -> Any:
        """
        Generic multi-document extraction via LLM completions.
        Builds prompt using build_extraction_prompt and delegates to chat completions with retries.
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

        raw_content, err_msg, status_code = self._execute_http_completion(endpoint_url, payload)
        if err_msg or not raw_content:
            logger.warning(f"extract_document error: {err_msg}")
            # Fall back to extract_invoice only if invoice-like
            if document_type.lower() in ("invoice", "bill"):
                return self.extract_invoice(text=text, context=context)
            return {
                "status": "API_ERROR",
                "raw_response": raw_content,
                "fields": {},
                "model": self.model,
                "provider": self.provider_name,
                "error": err_msg,
            }

        cleaned = self._clean_markdown_fences(raw_content)
        try:
            parsed_data = json.loads(cleaned)
        except Exception as exc:
            return {
                "status": "PARSING_ERROR",
                "raw_response": raw_content,
                "fields": {},
                "model": self.model,
                "provider": self.provider_name,
                "error": f"Failed to parse JSON response: {exc}",
            }

        return {
            "status": "SUCCESS",
            "raw_response": raw_content,
            "fields": parsed_data.get("fields", parsed_data),
            "model": self.model,
            "provider": self.provider_name,
        }

    def complete_json(
        self,
        messages: List[Dict[str, str]],
        system_instruction: Optional[str] = None,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Executes an OpenAI-compatible completion returning structured JSON dict.
        Supports Gemini, OpenAI, Groq, Ollama, etc.
        """
        if not self.api_key or not self.api_key.strip():
            logger.warning(f"complete_json called but API key is not configured for {self.provider_name}.")
            return {}

        endpoint_url = f"{self.base_url}/chat/completions"
        payload_messages = []
        if system_instruction:
            payload_messages.append({"role": "system", "content": system_instruction})
        payload_messages.extend(messages)

        payload = {
            "model": self.model,
            "messages": payload_messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }

        raw_content, err_msg, status_code = self._execute_http_completion(endpoint_url, payload)
        if err_msg or not raw_content:
            logger.warning(f"complete_json error from {self.provider_name}: {err_msg}")
            return {}

        cleaned = self._clean_markdown_fences(raw_content)
        try:
            parsed = json.loads(cleaned)
            return parsed if isinstance(parsed, dict) else {"data": parsed}
        except Exception as exc:
            logger.warning(f"Failed to parse complete_json output as JSON: {exc} | Raw: {raw_content[:200]}")
            return {}

