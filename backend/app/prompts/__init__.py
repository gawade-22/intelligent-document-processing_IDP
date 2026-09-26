"""
Prompts package for Intelligent Document Processing (IDP).
Provides structured extraction prompt builders, document type registries, and anti-injection defenses.
"""

from app.prompts.extraction_prompt import (
    INVOICE_CONFIG,
    RESUME_CONFIG,
    STUDENT_DOCUMENT_CONFIG,
    build_extraction_prompt,
    build_full_prompt,
    get_document_type_config,
    list_supported_document_types,
    protect_document_size,
    register_document_type,
)

__all__ = [
    "build_extraction_prompt",
    "build_full_prompt",
    "get_document_type_config",
    "register_document_type",
    "list_supported_document_types",
    "protect_document_size",
    "INVOICE_CONFIG",
    "RESUME_CONFIG",
    "STUDENT_DOCUMENT_CONFIG",
]
