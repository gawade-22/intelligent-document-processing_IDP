"""
Runtime AI / LLM Configuration Manager.
Maintains in-memory and persistent settings for AI extraction:
- Provider selection (gemini, openai_compatible, mock, noop)
- Model selection
- Masked API key management (never returned to clients)
- Enable/disable toggle
- Custom prompt templates
- Supported providers and models registry
"""

import logging
import os
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = ["gemini", "openai_compatible", "mock", "noop"]

SUPPORTED_MODELS = {
    "gemini": [
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-pro",
    ],
    "openai_compatible": [
        "gpt-4o-mini",
        "gpt-4o",
        "claude-3-5-sonnet",
        "meta-llama/llama-3-70b-instruct",
    ],
    "mock": ["mock-model-v1"],
    "noop": ["noop-disabled"],
}

SUPPORTED_DOCUMENT_TYPES = [
    {"id": "invoice", "name": "Invoice / Bill", "default_fields": ["vendor_name", "invoice_number", "invoice_date", "total_amount"]},
    {"id": "resume", "name": "Resume / CV", "default_fields": ["candidate_name", "email", "phone", "skills"]},
    {"id": "student_document", "name": "Student Document / Marksheet", "default_fields": ["student_name", "roll_number", "percentage", "college"]},
    {"id": "general", "name": "General Document", "default_fields": ["document_title", "entity_name", "reference_number", "date"]},
    {"id": "custom", "name": "Custom Schema", "default_fields": []},
]


class AIConfigState(BaseModel):
    """Configuration state model exposed securely to API clients (zero secret leakage)."""
    provider: str = Field(default="gemini")
    model: str = Field(default="gemini-1.5-flash")
    enabled: bool = Field(default=True)
    api_key_configured: bool = Field(default=False)
    masked_api_key: Optional[str] = Field(default=None)
    status: str = Field(default="READY")  # READY, NOT_CONFIGURED, DISABLED, ERROR
    timeout: int = Field(default=30)
    max_input_characters: int = Field(default=12000)
    custom_prompt: Optional[str] = Field(default=None)
    supported_providers: List[str] = Field(default_factory=lambda: SUPPORTED_PROVIDERS)
    supported_models: Dict[str, List[str]] = Field(default_factory=lambda: SUPPORTED_MODELS)
    supported_document_types: List[Dict[str, Any]] = Field(default_factory=lambda: SUPPORTED_DOCUMENT_TYPES)


class AIConfigManager:
    """Singleton configuration manager ensuring runtime mutations and secure secrets isolation."""

    def __init__(self) -> None:
        self._provider = settings.AI_PROVIDER or "gemini"
        self._model = settings.AI_MODEL or "gemini-1.5-flash"
        self._enabled = bool(settings.AI_PROVIDER and settings.AI_PROVIDER.lower() != "noop")
        self._custom_prompt: Optional[str] = None
        self._timeout = settings.AI_TIMEOUT
        self._max_chars = settings.AI_MAX_INPUT_CHARACTERS

    @property
    def provider(self) -> str:
        return self._provider or settings.AI_PROVIDER or "gemini"

    @property
    def model(self) -> str:
        return self._model or settings.AI_MODEL or "gemini-1.5-flash"

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def custom_prompt(self) -> Optional[str]:
        return self._custom_prompt

    def has_api_key(self) -> bool:
        """Returns True if an API key is configured either in environment or runtime settings."""
        key = settings.AI_API_KEY or settings.GEMINI_API_KEY
        return bool(key and str(key).strip())

    def get_masked_api_key(self) -> Optional[str]:
        """Returns a non-sensitive masked representation of the active API key."""
        if not self.has_api_key():
            return None
        return "************configured"

    def get_state(self) -> AIConfigState:
        """Assembles client-safe configuration state without secrets."""
        has_key = self.has_api_key()
        active_provider = self.provider.lower()

        if not self._enabled:
            current_status = "DISABLED"
        elif active_provider in ["mock", "noop"]:
            current_status = "READY"
        elif has_key:
            current_status = "READY"
        else:
            current_status = "NOT_CONFIGURED"

        return AIConfigState(
            provider=self.provider,
            model=self.model,
            enabled=self._enabled,
            api_key_configured=has_key,
            masked_api_key=self.get_masked_api_key(),
            status=current_status,
            timeout=self._timeout,
            max_input_characters=self._max_chars,
            custom_prompt=self._custom_prompt,
            supported_providers=SUPPORTED_PROVIDERS,
            supported_models=SUPPORTED_MODELS,
            supported_document_types=SUPPORTED_DOCUMENT_TYPES,
        )

    def update_config(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        enabled: Optional[bool] = None,
        api_key: Optional[str] = None,
        clear_api_key: bool = False,
        custom_prompt: Optional[str] = None,
        timeout: Optional[int] = None,
        max_input_characters: Optional[int] = None,
    ) -> AIConfigState:
        """
        Updates runtime AI configuration securely.
        Never returns or logs the raw API key.
        """
        if provider is not None and provider.strip():
            clean_prov = provider.strip().lower()
            if clean_prov in SUPPORTED_PROVIDERS:
                self._provider = clean_prov
                settings.AI_PROVIDER = clean_prov
                os.environ["AI_PROVIDER"] = clean_prov
                logger.info("Updated AI provider to '%s'", clean_prov)

        if model is not None and model.strip():
            self._model = model.strip()
            settings.AI_MODEL = self._model
            os.environ["AI_MODEL"] = self._model
            logger.info("Updated AI model to '%s'", self._model)

        if enabled is not None:
            self._enabled = enabled
            logger.info("Updated AI extraction enabled state to %s", enabled)

        if clear_api_key:
            settings.AI_API_KEY = None
            settings.GEMINI_API_KEY = None
            os.environ.pop("AI_API_KEY", None)
            os.environ.pop("GEMINI_API_KEY", None)
            logger.info("Cleared AI API key from runtime configuration")
        elif api_key is not None and api_key.strip():
            clean_key = api_key.strip()
            settings.AI_API_KEY = clean_key
            settings.GEMINI_API_KEY = clean_key
            os.environ["AI_API_KEY"] = clean_key
            os.environ["GEMINI_API_KEY"] = clean_key
            logger.info("Saved new AI API key to runtime configuration (masked for security)")

        if custom_prompt is not None:
            self._custom_prompt = custom_prompt if custom_prompt.strip() else None

        if timeout is not None and timeout > 0:
            self._timeout = timeout
            settings.AI_TIMEOUT = timeout

        if max_input_characters is not None and max_input_characters > 100:
            self._max_chars = max_input_characters
            settings.AI_MAX_INPUT_CHARACTERS = max_input_characters

        return self.get_state()


# Global Singleton Manager
ai_config_manager = AIConfigManager()
