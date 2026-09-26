"""
Pydantic schemas for AI / LLM Configuration and Document Extraction Breakdown endpoints.
Ensures clean, typed responses without secret leakage.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AIConfigUpdateRequest(BaseModel):
    """Payload for updating runtime AI configuration."""
    provider: Optional[str] = Field(default=None, description="AI Provider identifier (gemini, openai_compatible, mock, noop)")
    model: Optional[str] = Field(default=None, description="Model identifier (e.g. gemini-1.5-flash, gpt-4o-mini)")
    enabled: Optional[bool] = Field(default=None, description="Whether LLM extraction is actively enabled in processing")
    api_key: Optional[str] = Field(default=None, description="Secure API key (never returned back in responses)")
    clear_api_key: bool = Field(default=False, description="Set to True to remove the active API key")
    custom_prompt: Optional[str] = Field(default=None, description="Custom prompt template overriding defaults")
    timeout: Optional[int] = Field(default=None, description="Request timeout in seconds")
    max_input_characters: Optional[int] = Field(default=None, description="Max document characters passed to LLM")


class AIConnectionTestRequest(BaseModel):
    """Payload to test AI connectivity."""
    provider: Optional[str] = Field(default=None, description="Optional provider override to test")
    model: Optional[str] = Field(default=None, description="Optional model override to test")
    api_key: Optional[str] = Field(default=None, description="Optional temporary key to test before saving")


class AIConnectionTestResponse(BaseModel):
    """Safe diagnostic result of an AI connectivity check (zero secret leakage)."""
    success: bool
    status: str  # CONNECTED, CONNECTION_FAILED, NOT_CONFIGURED
    provider: str
    model: str
    message: str
    details: Optional[Dict[str, Any]] = None


class AIPromptPreviewRequest(BaseModel):
    """Request to preview how the extraction prompt is constructed."""
    document_type: str = Field(default="invoice", description="Target document category ('invoice', 'resume', etc.)")
    custom_prompt: Optional[str] = Field(default=None, description="Optional custom instructions to embed")
    sample_text: Optional[str] = Field(default=None, description="Optional custom text snippet to embed in DOCUMENT CONTENT")


class AIPromptPreviewResponse(BaseModel):
    """Transparent breakdown of the 5 prompt tiers for UI inspection."""
    document_type: str
    system_instructions: str
    extraction_requirements: str
    expected_json_format: str
    document_content_preview: str
    full_prompt: str
    security_warning: str = (
        "Document content will be sent to the configured LLM provider for extraction. "
        "Sensitive information within the document will be processed by the model."
    )


class FieldExtractionDetail(BaseModel):
    """Representation of an individual field extraction with confidence and source."""
    value: Optional[Any] = None
    confidence: float = 0.0
    source: str = "none"  # rule, ai, rule+ai, human, none
    evidence: Optional[str] = None
    status: Optional[str] = None  # AGREED, REVIEW REQUIRED, REFINED, SINGLE_SOURCE
    reason: Optional[str] = None


class DocumentExtractionResponse(BaseModel):
    """
    Comprehensive multi-tier extraction comparison payload for Document Details UI.
    Contains Rule Extraction, LLM Extraction, Reconciliation, and Final Result.
    """
    document_id: int
    file_name: str
    status: str
    document_type: str = "invoice"
    confidence_score: Optional[float] = None
    extraction_method_used: str = "rule+ai"  # rule, llm, rule+ai
    rule_extraction: Dict[str, FieldExtractionDetail] = Field(default_factory=dict)
    llm_extraction: Dict[str, FieldExtractionDetail] = Field(default_factory=dict)
    reconciliation: Dict[str, FieldExtractionDetail] = Field(default_factory=dict)
    final_result: Dict[str, Optional[Any]] = Field(default_factory=dict)
    validation_errors: List[str] = Field(default_factory=list)
    review_reasons: List[str] = Field(default_factory=list)
    raw_text: Optional[str] = None
    viewer_url: str
