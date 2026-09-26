"""
Factory for creating and resolving AI extraction providers based on environment configuration.
"""

import logging
from typing import Any, Optional

from app.core.config import settings
from app.services.ai.base import (
    AIExtractionProvider,
    MockAIExtractionProvider,
    NoOpAIExtractionProvider,
)
from app.services.ai.providers.gemini import GeminiProvider
from app.services.ai.providers.openai_compatible import OpenAICompatibleProvider

logger = logging.getLogger(__name__)

OPENAI_COMPATIBLE_ALIASES = {
    "openai",
    "openai_compatible",
    "openrouter",
    "groq",
    "together",
    "ollama",
}


def get_ai_provider(
    provider_type: Optional[str] = None,
    **kwargs: Any,
) -> AIExtractionProvider:
    """
    Factory to instantiate an AIExtractionProvider based on configuration or explicit parameter.

    Provider Resolution:
    - Empty / None / 'noop' -> NoOpAIExtractionProvider (zero network, safe default)
    - 'mock' -> MockAIExtractionProvider (deterministic testing without API key)
    - 'gemini' -> GeminiProvider (Google Gemini via REST)
    - 'openai', 'openai_compatible', 'openrouter', 'groq', 'together', 'ollama' ->
      OpenAICompatibleProvider configured with API key, model, and base URL
    - Unknown provider -> raises ValueError with supported options

    Args:
        provider_type: Optional explicit provider identifier override.
        **kwargs: Optional constructor arguments passed to provider.

    Returns:
        Configured instance of AIExtractionProvider / LLMProvider.
    """
    chosen = provider_type if provider_type is not None else settings.AI_PROVIDER
    if not chosen or not str(chosen).strip():
        return NoOpAIExtractionProvider()

    normalized = str(chosen).strip().lower()

    if normalized == "noop":
        return NoOpAIExtractionProvider()

    if normalized == "mock":
        return MockAIExtractionProvider(**kwargs)

    if normalized == "gemini":
        return GeminiProvider(**kwargs)

    if normalized in OPENAI_COMPATIBLE_ALIASES:
        return OpenAICompatibleProvider(provider_name=normalized, **kwargs)

    supported = ["gemini", "noop", "mock"] + sorted(list(OPENAI_COMPATIBLE_ALIASES))
    err_msg = (
        f"Unknown or unsupported AI provider: '{chosen}'. "
        f"Supported providers are: {', '.join(supported)}"
    )
    logger.error(err_msg)
    raise ValueError(err_msg)
