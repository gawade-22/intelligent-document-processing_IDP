"""
Base provider abstractions for the AI/LLM Invoice Extraction layer.
Defines the abstract interface AIExtractionProvider, along with NoOp and Mock implementations.
Supports bidirectional compatibility between extract_invoice(text, context) and legacy extract(text).
"""

from abc import ABC, abstractmethod
import json
import re
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

        response = self.extract_invoice(text=text, context=None)
        if response and response.fields:
            return response.fields.to_dict()
        return {}

    def complete_json(
        self,
        messages: List[Dict[str, str]],
        system_instruction: Optional[str] = None,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Generic completion returning structured JSON dict.
        Subclasses override to invoke chat completion with response_format=json_object.
        """
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

    def complete_json(
        self,
        messages: List[Dict[str, str]],
        system_instruction: Optional[str] = None,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        prompt_text = " ".join(m.get("content", "") for m in messages).lower()

        # 1. Classification
        if "classify" in prompt_text or "classification" in prompt_text:
            # Isolate document excerpt and file name from schema prompt instructions
            if "--- document first page excerpt ---" in prompt_text:
                doc_part = prompt_text.split("--- document first page excerpt ---")[-1]
                if "file name:" in prompt_text:
                    doc_part += " " + prompt_text.split("file name:")[1].split("\n")[0]
            elif "file name:" in prompt_text:
                doc_part = prompt_text.split("file name:")[-1]
            else:
                doc_part = prompt_text

            if any(k in doc_part for k in ("soil", "drone", "agriculture", "survey", "crop", "farm")):
                return {
                    "primary_type": "Agricultural Drone Soil Survey",
                    "family": "agriculture",
                    "confidence": 0.96,
                    "alternatives": [{"type": "Environmental Survey", "confidence": 0.82}],
                }
            if any(k in doc_part for k in ("resume", "curriculum vitae", "work experience", "skills", "candidate")):
                return {
                    "primary_type": "Resume / CV",
                    "family": "employment",
                    "confidence": 0.98,
                    "alternatives": [{"type": "Professional Profile", "confidence": 0.85}],
                }
            if any(k in doc_part for k in ("bank", "statement", "debit", "credit", "account", "balance")):
                return {
                    "primary_type": "Bank Statement",
                    "family": "financial",
                    "confidence": 0.96,
                    "alternatives": [{"type": "Ledger Sheet", "confidence": 0.80}],
                }
            if any(k in doc_part for k in ("patient", "blood", "doctor", "hospital", "clinic", "diagnosis", "prescription", "clinical")):
                return {
                    "primary_type": "Medical Report",
                    "family": "medical",
                    "confidence": 0.95,
                    "alternatives": [],
                }
            if any(k in doc_part for k in ("certificate", "certified", "credential", "award", "diploma", "degree")):
                return {
                    "primary_type": "Certificate",
                    "family": "academic",
                    "confidence": 0.96,
                    "alternatives": [{"type": "Credential", "confidence": 0.85}],
                }
            if any(k in doc_part for k in ("mission", "spaceflight", "orbital", "payload", "mars")):
                return {
                    "primary_type": "Spaceflight Mission Log",
                    "family": "general",
                    "confidence": 0.94,
                    "alternatives": [{"type": "Technical Report", "confidence": 0.80}],
                }
            if any(k in doc_part for k in ("invoice", "bill", "vendor", "tax amount", "due", "globex", "acme", "subtotal", "total amount")):
                return {
                    "primary_type": "Commercial Invoice",
                    "family": "financial",
                    "confidence": 0.95,
                    "alternatives": [{"type": "Bill / Receipt", "confidence": 0.82}],
                }
            if "noise" in doc_part or "corrupted" in doc_part or not any(c.isalnum() for c in doc_part):
                return {
                    "primary_type": "Unknown Document",
                    "family": "general",
                    "confidence": 0.30,
                    "alternatives": [],
                }
            return {
                "primary_type": "Commercial Invoice",
                "family": "financial",
                "confidence": 0.90,
                "alternatives": [],
            }

        # 2. Schema Discovery
        if "schema" in prompt_text or "discovery" in prompt_text:
            if "soil" in prompt_text or "drone" in prompt_text or "agriculture" in prompt_text:
                return {
                    "sections": ["Survey Area", "Soil Metrics", "Observations"],
                    "fields": [
                        {"key": "field_id", "label": "Field ID", "data_type": "id", "section": "Survey Area"},
                        {"key": "survey_date", "label": "Survey Date", "data_type": "date", "section": "Survey Area"},
                        {"key": "ph_level", "label": "Soil pH", "data_type": "number", "section": "Soil Metrics"},
                        {"key": "moisture_pct", "label": "Moisture Percentage", "data_type": "percent", "section": "Soil Metrics"},
                        {"key": "nitrogen_ppm", "label": "Nitrogen (PPM)", "data_type": "number", "section": "Soil Metrics"},
                    ],
                    "tables": [],
                    "validation_rules": [
                        {"rule": "in_range", "value": "ph_level", "min": 0, "max": 14}
                    ],
                    "insight_definitions": [],
                }
            if "spaceflight" in prompt_text or "mission" in prompt_text:
                return {
                    "sections": ["Mission Overview", "Orbital Telemetry", "Payload"],
                    "fields": [
                        {"key": "mission_name", "label": "Mission Name", "data_type": "string", "section": "Mission Overview"},
                        {"key": "launch_date", "label": "Launch Date", "data_type": "date", "section": "Mission Overview"},
                        {"key": "apogee_km", "label": "Apogee (km)", "data_type": "number", "section": "Orbital Telemetry"},
                        {"key": "payload_mass_kg", "label": "Payload Mass", "data_type": "number", "section": "Payload"},
                    ],
                    "tables": [],
                    "validation_rules": [
                        {"rule": "in_range", "value": "apogee_km", "min": 100, "max": 50000}
                    ],
                    "insight_definitions": [],
                }
            return {
                "sections": ["General Information", "Details", "Financials"],
                "fields": [
                    {"key": "title", "label": "Document Title", "data_type": "string", "section": "General Information"},
                    {"key": "date", "label": "Document Date", "data_type": "date", "section": "General Information"},
                    {"key": "total", "label": "Total Amount", "data_type": "money", "section": "Financials"},
                ],
                "tables": [
                    {"key": "items", "title": "Line Items", "columns": ["description", "quantity", "amount"]}
                ],
                "validation_rules": [
                    {"rule": "sum_equals", "target": "total", "terms": ["items.amount"]}
                ],
                "insight_definitions": [
                    {"id": "sum_metric", "title": "Total Spend", "kind": "metric", "agg": "sum", "table": "items", "column": "amount"}
                ],
            }

        # 3. Dynamic Sectioned Extraction
        if "target fields to extract" in prompt_text or "extract the target fields" in prompt_text:
            extracted_fields = {}
            raw_content = messages[0].get("content", "")
            if "Document Content:" in raw_content:
                doc_content = raw_content.split("Document Content:", 1)[1]
            else:
                doc_content = raw_content

            # Simple keyword quote extractor for lines in document content
            for line in doc_content.splitlines():
                if ":" in line:
                    parts = line.split(":", 1)
                    k_cand = parts[0].strip().lower().replace(" ", "_")
                    v_cand = parts[1].strip()
                    if v_cand and len(v_cand) < 100:
                        extracted_fields[k_cand] = {"value": v_cand, "quote": v_cand, "page": 1}

            # Predefined standard fields matched by regex patterns on document content
            patterns = [
                # Invoice
                ("vendor_name", r"\b(?:Vendor|Billed By|Supplier):\s*([^\r\n]+)", 1),
                ("invoice_number", r"\b(?:Invoice\s*(?:Number|#|No\.?)|Reference\s*(?:#|No\.?)):\s*([^\r\n]+)", 1),
                ("invoice_date", r"\b(?:(?:Invoice\s*)?Date|Dated):\s*([^\r\n]+)", 1),
                ("subtotal_amount", r"\bSubtotal:\s*([^\r\n]+)", 1),
                ("tax_amount", r"\b(?:Tax(?:\s*Amount)?|VAT):\s*([^\r\n]+)", 1),
                ("total_amount", r"\b(?:Total(?:\s*Due|\s*Amount)?|Grand\s*Total):\s*([^\r\n]+)", 1),
                
                # Resume
                ("candidate_name", r"(?:Name|Candidate):\s*([^\r\n]+)", 1),
                ("email", r"(?:Email|E-mail):\s*([^\r\n]+)", 1),
                ("phone", r"(?:Phone|Tel|Mobile):\s*([^\r\n]+)", 1),
                ("summary", r"Summary:\s*([^\r\n]+)", 1),
                ("skills", r"Skills:\s*([^\r\n]+)", 1),
                ("education", r"Education:\s*([^\r\n]+)", 1),
                ("experience", r"Experience:\s*([^\r\n]+)", 1),
                ("projects", r"Projects:\s*([^\r\n]+)", 1),

                # Bank Statement
                ("account_holder", r"Account\s*Holder:\s*([^\r\n]+)", 1),
                ("account_number", r"Account(?:\s*Number|#)?:\s*([^\r\n]+)", 1),
                ("statement_period", r"(?:Statement\s*)?Period:\s*([^\r\n]+)", 1),
                ("opening_balance", r"Opening\s*Balance:\s*([^\r\n]+)", 1),
                ("closing_balance", r"Closing\s*Balance:\s*([^\r\n]+)", 1),

                # Medical Report
                ("patient_name", r"Patient(?:\s*Name)?:\s*([^\r\n]+)", 1),
                ("patient_age_gender", r"(?:Age\s*/\s*Gender|Age):\s*([^\r\n]+)", 1),
                ("referring_doctor", r"(?:Referring\s*)?Doctor:\s*([^\r\n]+)", 1),
                ("report_date", r"(?:Report\s*)?Date:\s*([^\r\n]+)", 1),
                ("diagnosis", r"Diagnosis:\s*([^\r\n]+)", 1),

                # Certificate
                ("recipient_name", r"Recipient:\s*([^\r\n]+)", 1),
                ("credential_title", r"Credential:\s*([^\r\n]+)", 1),
                ("issuing_organization", r"(?:Issuing\s*Authority|Issuer|Organization):\s*([^\r\n]+)", 1),
                ("issue_date", r"Issue\s*Date:\s*([^\r\n]+)", 1),
                ("certificate_id", r"(?:Certificate\s*ID|Reg\s*ID):\s*([^\r\n]+)", 1),

                # Novel / Drone Soil Survey
                ("field_id", r"Field\s*(?:ID|#):\s*([^\r\n]+)", 1),
                ("survey_date", r"Survey\s*Date:\s*([^\r\n]+)", 1),
                ("ph_level", r"(?:Soil\s*)?pH:\s*([^\r\n]+)", 1),
                ("moisture_pct", r"Moisture:\s*([^\r\n]+)", 1),
                ("nitrogen_ppm", r"Nitrogen:\s*([^\r\n]+)", 1),

                # Spaceflight
                ("mission_name", r"Mission:\s*([^\r\n]+)", 1),
                ("launch_date", r"Launch\s*Date:\s*([^\r\n]+)", 1),
                ("apogee_km", r"Apogee:\s*([^\r\n]+)", 1),
                ("payload_mass_kg", r"Payload(?:\s*Mass)?:\s*([^\r\n]+)", 1),
            ]
            for f_k, f_pat, grp in patterns:
                m = re.search(f_pat, doc_content, re.IGNORECASE)
                if m:
                    extracted_fields[f_k] = {
                        "value": m.group(grp).strip(),
                        "quote": m.group(grp).strip(),
                        "page": 1,
                    }

            return {"fields": extracted_fields}

        # 4. Table Extraction
        if "extract the table" in prompt_text or "table" in prompt_text:
            if "transaction" in prompt_text:
                return {
                    "tables": {
                        "transactions": [
                            {"date": "2026-08-05", "description": "Client Wire Inflow", "debit": "", "credit": "5000.00", "balance": "15000.00"},
                            {"date": "2026-08-12", "description": "Cloud Services Inc", "debit": "500.00", "credit": "", "balance": "14500.00"},
                        ]
                    }
                }
            if "item" in prompt_text or "line" in prompt_text:
                return {
                    "tables": {
                        "items": [
                            {"description": "Enterprise Platform License", "quantity": "1", "unit_price": "1000.00", "amount": "1000.00"},
                            {"description": "Integration Support", "quantity": "1", "unit_price": "150.00", "amount": "150.00"},
                        ]
                    }
                }

        return {"status": "success"}

