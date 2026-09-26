"""
Base provider abstractions for the AI/LLM Invoice Extraction layer.
Defines the abstract interface AIExtractionProvider, along with NoOp and Mock implementations.
Supports bidirectional compatibility between extract_invoice(text, context) and legacy extract(text).
"""

from abc import ABC, abstractmethod
import json
from typing import Any, Dict, List, Optional, Union

from app.services.ai.schemas import (
    AIExtractedFields,
    AIExtractionResponse,
    AIExtractionStatus,
)


class AIExtractionProvider(ABC):
    """
    Abstract interface for AI/LLM invoice extraction providers.
    Supports both modern extract_invoice(text, context) -> AIExtractionResponse
    and legacy extract(text) -> Dict[str, Any].
    """

    @abstractmethod
    def extract_invoice(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AIExtractionResponse:
        """
        Extract invoice fields from document text with optional hints/evidence context.
        """
        pass

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # If subclass defines extract() but not extract_invoice(), synthesize extract_invoice
        # to fulfill the abstractmethod contract seamlessly for legacy subclasses
        if "extract" in cls.__dict__ and "extract_invoice" not in cls.__dict__:
            def _synthetic_extract_invoice(
                self: Any,
                text: str,
                context: Optional[Dict[str, Any]] = None,
            ) -> AIExtractionResponse:
                data = self.extract(text)
                if not data or not isinstance(data, dict):
                    return AIExtractionResponse(
                        status=AIExtractionStatus.AI_NOT_CONFIGURED.value,
                        fields=None,
                        raw_response=None,
                        model="legacy_model",
                        provider="legacy_provider",
                        errors=["AI provider returned empty or non-dict output"],
                    )
                try:
                    fields_obj = AIExtractedFields(**data)
                    return AIExtractionResponse(
                        status=AIExtractionStatus.SUCCESS.value,
                        fields=fields_obj,
                        raw_response=str(data),
                        model="legacy_model",
                        provider="legacy_provider",
                        errors=[],
                    )
                except Exception as exc:
                    return AIExtractionResponse(
                        status=AIExtractionStatus.PARSING_ERROR.value,
                        fields=None,
                        raw_response=str(data),
                        model="legacy_model",
                        provider="legacy_provider",
                        errors=[f"Failed to parse legacy dict to AIExtractedFields: {exc}"],
                    )

            cls.extract_invoice = _synthetic_extract_invoice  # type: ignore

    def extract_document(
        self,
        text: str,
        document_type: str = "invoice",
        context: Optional[Dict[str, Any]] = None,
        custom_fields: Optional[List[Any]] = None,
    ) -> Any:
        """
        Generic document extraction method supporting arbitrary document types
        (Invoice, Resume, Student Document, Custom).
        Subclasses can override to implement multi-document extraction.
        Default delegates to extract_invoice for backward compatibility.
        """
        return self.extract_invoice(text=text, context=context)

    def extract(self, text: str) -> Dict[str, Any]:
        """
        Backward compatibility method for legacy callers expecting a plain dictionary.
        Delegates to extract_invoice and formats fields as a dict.
        """
        response = self.extract_invoice(text=text, context=None)
        if response and response.fields:
            return response.fields.to_dict()
        return {}


# Alias representing the abstract LLM provider interface
LLMProvider = AIExtractionProvider


class NoOpAIExtractionProvider(AIExtractionProvider):
    """
    Default provider when AI extraction is not configured.
    Returns AI_NOT_CONFIGURED status gracefully without raising exceptions or network calls.
    """

    def extract_invoice(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AIExtractionResponse:
        return AIExtractionResponse(
            status=AIExtractionStatus.AI_NOT_CONFIGURED.value,
            fields=None,
            raw_response=None,
            model="noop",
            provider="noop",
            errors=["AI provider is not configured"],
        )

    def extract_document(
        self,
        text: str,
        document_type: str = "invoice",
        context: Optional[Dict[str, Any]] = None,
        custom_fields: Optional[List[Any]] = None,
    ) -> AIExtractionResponse:
        return self.extract_invoice(text, context)

    def extract(self, text: str) -> Dict[str, Any]:
        return {}


class MockAIExtractionProvider(AIExtractionProvider):
    """
    Deterministic mock provider for automated tests and offline simulation.
    Requires no API key, zero network connectivity, and returns preconfigured or default test fields.
    Supports multi-class documents (Invoice, Resume, Student Document, Custom).
    """

    def __init__(
        self,
        fields: Optional[Union[Dict[str, Any], AIExtractedFields]] = None,
        status: str = AIExtractionStatus.SUCCESS.value,
        errors: Optional[List[str]] = None,
        model: str = "mock-model",
        provider: str = "mock",
        max_input_characters: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        self.max_input_characters = max_input_characters
        if isinstance(fields, AIExtractedFields):
            self._fields = fields
        elif isinstance(fields, dict):
            self._fields = AIExtractedFields(**fields)
        else:
            self._fields = AIExtractedFields(
                vendor_name="ABC Suppliers",
                invoice_number="INV-001",
                invoice_date="2026-09-01",
                total_amount="15000.00",
                confidence={
                    "vendor_name": 0.95,
                    "invoice_number": 0.92,
                    "invoice_date": 0.94,
                    "total_amount": 0.97,
                },
                evidence={
                    "vendor_name": "Mock evidence: header",
                    "invoice_number": "Mock evidence: Inv No match",
                    "invoice_date": "Mock evidence: Date match",
                    "total_amount": "Mock evidence: Grand Total match",
                },
            )
        self.status = status
        self.errors = errors or []
        self.model = model
        self.provider_name = provider
        self.last_prompt: Optional[str] = None
        self.last_context: Optional[Dict[str, Any]] = None
        self.last_document_type: Optional[str] = None
        self.last_custom_fields: Optional[List[Any]] = None

    def extract_invoice(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AIExtractionResponse:
        self.last_prompt = text
        self.last_context = context
        self.last_document_type = "invoice"

        if self.status != AIExtractionStatus.SUCCESS.value:
            return AIExtractionResponse(
                status=self.status,
                fields=None,
                raw_response='{"error": "mock_failure"}',
                model=self.model,
                provider=self.provider_name,
                errors=self.errors or [f"Mock provider returned status {self.status}"],
            )

        return AIExtractionResponse(
            status=AIExtractionStatus.SUCCESS.value,
            fields=self._fields,
            raw_response='{"mock": "response"}',
            model=self.model,
            provider=self.provider_name,
            errors=self.errors,
        )

    def extract_document(
        self,
        text: str,
        document_type: str = "invoice",
        context: Optional[Dict[str, Any]] = None,
        custom_fields: Optional[List[Any]] = None,
    ) -> Any:
        self.last_prompt = text
        self.last_context = context
        self.last_document_type = document_type
        self.last_custom_fields = custom_fields

        if self.status != AIExtractionStatus.SUCCESS.value:
            return AIExtractionResponse(
                status=self.status,
                fields=None,
                raw_response='{"error": "mock_failure"}',
                model=self.model,
                provider=self.provider_name,
                errors=self.errors or [f"Mock provider returned status {self.status}"],
            )

        doc_norm = str(document_type).lower().strip()

        # Resume mock payload
        if doc_norm in ("resume", "cv"):
            mock_resume_payload = {
                "fields": {
                    "candidate_name": {"value": "Ayush Sharma", "confidence": 0.98, "evidence": "Resume Header line 1"},
                    "email": {"value": "ayush.sharma@example.com", "confidence": 0.96, "evidence": "Contact Info"},
                    "phone": {"value": "+91 9876543210", "confidence": 0.94, "evidence": "Contact Info"},
                    "skills": {"value": ["Python", "FastAPI", "React", "Machine Learning"], "confidence": 0.92, "evidence": "Technical Skills Section"},
                }
            }
            return {
                "status": "SUCCESS",
                "raw_response": json.dumps(mock_resume_payload),
                "fields": mock_resume_payload["fields"],
                "model": self.model,
                "provider": self.provider_name,
            }

        # Student document mock payload
        if doc_norm in ("student_document", "academic_record", "transcript", "marksheet"):
            mock_student_payload = {
                "fields": {
                    "student_name": {"value": "Prathamesh Gawade", "confidence": 0.97, "evidence": "Marksheet Header"},
                    "roll_number": {"value": "2023-CS-042", "confidence": 0.95, "evidence": "Student Details"},
                    "percentage": {"value": "88.5%", "confidence": 0.93, "evidence": "Aggregate Marks Summary"},
                    "college": {"value": "Mumbai Institute of Technology", "confidence": 0.96, "evidence": "University Banner"},
                }
            }
            return {
                "status": "SUCCESS",
                "raw_response": json.dumps(mock_student_payload),
                "fields": mock_student_payload["fields"],
                "model": self.model,
                "provider": self.provider_name,
            }

        # Default: invoice extraction
        return self.extract_invoice(text=text, context=context)

    def extract(self, text: str) -> Dict[str, Any]:
        resp = self.extract_invoice(text)
        if resp and resp.fields:
            return resp.fields.to_dict()
        return {}
