"""
AI/LLM Extraction Layer for Intelligent Document Processing.
Provides provider abstractions, 3-tier prompt building, vendor-specific prompting,
OpenAI-compatible REST integration, and factory instantiation.
"""

from app.services.ai.base import (
    AIExtractionProvider,
    LLMProvider,
    MockAIExtractionProvider,
    NoOpAIExtractionProvider,
)
from app.services.ai.factory import get_ai_provider
from app.services.ai.prompt import GLOBAL_SYSTEM_PROMPT, build_prompt, protect_input_size
from app.services.ai.providers.gemini import GeminiProvider
from app.services.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.services.ai.schemas import (
    AIExtractedFields,
    AIExtractionResponse,
    AIExtractionStatus,
)
from app.services.ai.vendor_prompts import (
    get_vendor_prompt,
    list_vendor_prompts,
    normalize_vendor_key,
    register_vendor_prompt,
    unregister_vendor_prompt,
)
from app.services.llm_extractor import LLMExtractor, get_llm_extractor

__all__ = [
    "AIExtractionProvider",
    "LLMProvider",
    "GeminiProvider",
    "NoOpAIExtractionProvider",
    "MockAIExtractionProvider",
    "OpenAICompatibleProvider",
    "get_ai_provider",
    "LLMExtractor",
    "get_llm_extractor",
    "AIExtractedFields",
    "AIExtractionResponse",
    "AIExtractionStatus",
    "GLOBAL_SYSTEM_PROMPT",
    "build_prompt",
    "protect_input_size",
    "get_vendor_prompt",
    "register_vendor_prompt",
    "unregister_vendor_prompt",
    "list_vendor_prompts",
    "normalize_vendor_key",
]
