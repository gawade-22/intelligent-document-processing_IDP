from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ocr import OCRBoundingBox


class ExtractedField(BaseModel):
    """
    Detailed candidate/extracted field representation including confidence,
    detection source, and spatial bounding box if available.
    """
    value: Optional[str] = Field(default=None, description="Extracted raw string value")
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Field extraction confidence score normalized between 0.0 and 1.0",
    )
    source: Optional[str] = Field(
        default=None,
        description="Candidate detection strategy: 'keyword', 'regex', 'positional', or 'combined'",
    )
    bounding_box: Optional[OCRBoundingBox] = Field(
        default=None,
        description="Spatial bounding box of the recognized field on the page",
    )
    page_number: Optional[int] = Field(
        default=None,
        ge=1,
        description="1-indexed page number where the field was detected",
    )

    model_config = ConfigDict(from_attributes=True)


class FieldCandidate(BaseModel):
    """
    Candidate representation holding extraction evidence, matched keyword,
    matched text, bounding box, and score for multi-candidate evaluation.
    """
    field_name: str = Field(..., description="Target invoice field (e.g. 'invoice_number', 'vendor_name')")
    value: str = Field(..., description="Candidate extracted raw string value")
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Candidate confidence score normalized between 0.0 and 1.0",
    )
    source: str = Field(
        default="keyword",
        description="Detection mechanism: 'keyword', 'regex', 'positional', or 'combined'",
    )
    matched_keyword: Optional[str] = Field(
        default=None,
        description="Exact keyword string matched (e.g. 'invoice number', 'bill no')",
    )
    matched_text: Optional[str] = Field(
        default=None,
        description="Contextual line or surrounding text snippet from which value was extracted",
    )
    bbox: Optional[OCRBoundingBox] = Field(
        default=None,
        description="Spatial bounding box of the candidate token on the page",
    )
    line_num: Optional[int] = Field(
        default=None,
        ge=1,
        description="1-indexed line number in the document text",
    )
    evidence: Optional[str] = Field(
        default=None,
        description="Diagnostic explanation of why this candidate was scored or selected",
    )

    model_config = ConfigDict(from_attributes=True)


class InvoiceExtractionResult(BaseModel):
    """
    Standardized, structured result of the Invoice Field Extraction layer.
    """
    success: bool = Field(
        default=True,
        description="Whether the extraction process executed without fatal pipeline errors",
    )
    vendor_name: Optional[str] = Field(
        default=None,
        description="Extracted name of the issuing vendor / business entity",
    )
    invoice_number: Optional[str] = Field(
        default=None,
        description="Extracted invoice identifier / bill number",
    )
    invoice_date: Optional[str] = Field(
        default=None,
        description="Extracted invoice issuance or billing date",
    )
    total_amount: Optional[str] = Field(
        default=None,
        description="Extracted grand total / total payable amount",
    )
    field_confidence: Dict[str, float] = Field(
        default_factory=lambda: {
            "vendor_name": 0.0,
            "invoice_number": 0.0,
            "invoice_date": 0.0,
            "total_amount": 0.0,
        },
        description="Confidence scores (0.0 to 1.0) for each of the target fields",
    )
    fields_found: List[str] = Field(
        default_factory=list,
        description="List of field names that were successfully extracted",
    )
    missing_fields: List[str] = Field(
        default_factory=list,
        description="List of target fields that could not be extracted",
    )
    errors: List[str] = Field(
        default_factory=list,
        description="Non-fatal extraction warnings or errors encountered during processing",
    )
    extracted_fields: Optional[Dict[str, ExtractedField]] = Field(
        default=None,
        description="Detailed metadata for each extracted field (source, confidence, bounding box)",
    )
    candidates: Optional[Dict[str, List[FieldCandidate]]] = Field(
        default=None,
        description="All evaluated candidates grouped by field name before selection",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional pipeline or document-level diagnostic metadata",
    )

    model_config = ConfigDict(from_attributes=True)
