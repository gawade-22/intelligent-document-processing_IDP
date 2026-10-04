"""
Dedicated Google Gemini LLM Provider implementation.
Uses Google's OpenAI-compatible REST endpoint (zero third-party SDK dependencies).
Inherits from OpenAICompatibleProvider and implements the LLMProvider interface.

Workflow:
LLMExtractor
     ↓
LLMProvider
     ↓
GeminiProvider

Configuration is sourced from backend/.env:
- AI_PROVIDER=gemini
- AI_MODEL=gemini-1.5-flash (or gemini-2.0-flash, gemini-1.5-pro)
- AI_API_KEY=YOUR_GEMINI_API_KEY (or GEMINI_API_KEY)
- AI_TIMEOUT=30
- AI_MAX_INPUT_CHARACTERS=12000
"""

import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.ai.providers.openai_compatible import OpenAICompatibleProvider

logger = logging.getLogger(__name__)

GEMINI_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
GEMINI_DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiProvider(OpenAICompatibleProvider):
    """
    Dedicated Gemini Provider for Intelligent Document Processing.
    Isolated behind the LLMProvider / AIExtractionProvider interface.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
        max_input_characters: Optional[int] = None,
    ) -> None:
        resolved_api_key = (
            api_key
            if api_key is not None
            else (settings.AI_API_KEY or settings.GEMINI_API_KEY)
        )
        resolved_base_url = (
            base_url
            if base_url is not None
            else (settings.AI_BASE_URL or GEMINI_DEFAULT_BASE_URL)
        )
        resolved_model = (
            model
            if model is not None
            else (settings.AI_MODEL or GEMINI_DEFAULT_MODEL)
        )
        resolved_timeout = (
            timeout
            if timeout is not None
            else settings.AI_TIMEOUT
        )
        resolved_max_input = (
            max_input_characters
            if max_input_characters is not None
            else settings.AI_MAX_INPUT_CHARACTERS
        )

        super().__init__(
            api_key=resolved_api_key,
            base_url=resolved_base_url,
            model=resolved_model,
            timeout=resolved_timeout,
            max_input_characters=resolved_max_input,
            provider_name="gemini",
        )
        logger.info(
            "Initialized GeminiProvider (model=%s, base_url=%s, timeout=%ds, max_chars=%d)",
            self.model,
            self.base_url,
            self.timeout,
            self.max_input_characters,
        )
