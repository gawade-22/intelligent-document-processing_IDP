"""
Pydantic v2 data models defining the Universal IDP contracts.
Strictly decoupled from any specific document type.
"""

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# 1. UniversalDocument (Physical Ingestion Contract)
# -----------------------------------------------------------------------------

class DocumentMeta(BaseModel):
    id: Optional[int] = None
    file_name: str
    format: str  # pdf, image, docx, csv, xlsx
    page_count: int = 1
    language: str = "eng"
    hash: Optional[str] = None
    file_size: Optional[int] = None


class PageMeta(BaseModel):
    n: int  # 1-indexed page number
    width: float
    height: float
    image_ref: Optional[str] = None  # path/url to rendered page image if OCR/vision needed
    source: Literal["native", "ocr", "mixed", "tabular", "docx"] = "native"


class ContentBlock(BaseModel):
    id: str
    page: int
    type: Literal["heading", "paragraph", "list", "kv", "figure", "footer", "table_cell", "raw"] = "paragraph"
    text: str
    # Bounding box coordinates: [x0, y0, x1, y1] normalized or absolute points
    bbox: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    reading_order: int = 0
    ocr_conf: float = 1.0


class ExtractedTable(BaseModel):
    id: str
    page: int
    bbox: List[float] = Field(default_factory=list)
    headers: List[str] = Field(default_factory=list)
    rows: List[List[Any]] = Field(default_factory=list)
    ocr_conf: float = 1.0


class SheetProfile(BaseModel):
    name: str
    columns: List[str] = Field(default_factory=list)
    dtypes: Dict[str, str] = Field(default_factory=dict)
    row_count: int = 0
    stats: Dict[str, Any] = Field(default_factory=dict)
    sample_rows: List[Dict[str, Any]] = Field(default_factory=list)


class UniversalDocument(BaseModel):
    """
    Physical structure representation of any document.
    No semantic meaning is assigned at this layer.
    """
    document: DocumentMeta
    pages: List[PageMeta] = Field(default_factory=list)
    blocks: List[ContentBlock] = Field(default_factory=list)
    tables: List[ExtractedTable] = Field(default_factory=list)
    sheets: List[SheetProfile] = Field(default_factory=list)

    @property
    def full_text(self) -> str:
        """Returns ordered readable text compiled from all content blocks."""
        sorted_blocks = sorted(self.blocks, key=lambda b: (b.page, b.reading_order))
        return "\n\n".join(b.text.strip() for b in sorted_blocks if b.text.strip())

    def page_text(self, page_number: int) -> str:
        """Returns ordered text for a specific page."""
        page_blocks = [b for b in self.blocks if b.page == page_number]
        sorted_blocks = sorted(page_blocks, key=lambda b: b.reading_order)
        return "\n".join(b.text.strip() for b in sorted_blocks if b.text.strip())


# -----------------------------------------------------------------------------
# 2. Dynamic Schema Definition Contracts (Schema Registry)
# -----------------------------------------------------------------------------

class SchemaFieldDefinition(BaseModel):
    key: str  # internal schema key, e.g. "invoice_number"
    label: str  # human readable label, e.g. "Invoice Number"
    section: str = "General"
    data_type: Literal[
        "string", "number", "date", "money", "percent",
        "email", "phone", "id", "text", "bool"
    ] = "string"
    description: Optional[str] = None
    required: bool = False
    repeating: bool = False
    canonical_key: Optional[str] = None  # mapped canonical key, e.g. "financial.invoice_number"


class SchemaTableDefinition(BaseModel):
    key: str
    title: str
    columns: List[str]
    description: Optional[str] = None


class ValidationRuleDefinition(BaseModel):
    rule: str  # sum_equals, running_balance, date_order, in_range, regex_match
    target: Optional[str] = None
    terms: Optional[List[str]] = None
    tolerance: Optional[float] = 0.01
    table: Optional[str] = None
    opening: Optional[str] = None
    debit: Optional[str] = None
    credit: Optional[str] = None
    balance: Optional[str] = None
    earlier: Optional[str] = None
    later: Optional[str] = None
    min: Optional[Any] = None
    max: Optional[Any] = None
    pattern: Optional[str] = None
    severity: Literal["fail", "warn"] = "fail"


class InsightDefinition(BaseModel):
    id: str
    title: str
    kind: Literal["metric", "chart", "flag", "text"] = "metric"
    agg: Optional[Literal["sum", "avg", "min", "max", "count", "trend"]] = None
    table: Optional[str] = None
    column: Optional[str] = None
    rule: Optional[str] = None
    description: Optional[str] = None


class SchemaDefinition(BaseModel):
    sections: List[str] = Field(default_factory=list)
    fields: List[SchemaFieldDefinition] = Field(default_factory=list)
    tables: List[SchemaTableDefinition] = Field(default_factory=list)
    validation_rules: List[ValidationRuleDefinition] = Field(default_factory=list)
    insight_definitions: List[InsightDefinition] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# 3. Extraction & Frontend Dynamic Output Contracts
# -----------------------------------------------------------------------------

class ClassificationResult(BaseModel):
    primary_type: str
    family: str  # financial, hr, identity, medical, legal, tabular, general
    confidence: float = 1.0
    alternatives: List[Dict[str, Any]] = Field(default_factory=list)


class FieldEvidence(BaseModel):
    page: int
    quote: str
    bbox: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    grounded: bool = True
    match_score: float = 1.0


class ExtractionPass(BaseModel):
    engine: str  # text-llm, vision-llm, regex-detector, rule-fallback
    value: Any


class FieldValidation(BaseModel):
    status: Literal["pass", "warn", "fail"] = "pass"
    messages: List[str] = Field(default_factory=list)


class DynamicFieldResult(BaseModel):
    id: str
    key: str  # canonical key, e.g. "person.full_name" or schema key
    label: str
    section: str = "General"
    value: Any = None
    normalized_value: Any = None
    data_type: str = "string"
    confidence: float = 0.0
    evidence: Optional[FieldEvidence] = None
    passes: List[ExtractionPass] = Field(default_factory=list)
    validation: FieldValidation = Field(default_factory=FieldValidation)
    status: Literal["verified", "needs_review", "edited"] = "verified"
    editable: bool = True


class DynamicTableResult(BaseModel):
    id: str
    key: str
    title: str
    headers: List[str] = Field(default_factory=list)
    rows: List[List[Any]] = Field(default_factory=list)
    confidence: float = 1.0
    source: Optional[Dict[str, Any]] = None


class DynamicInsightResult(BaseModel):
    id: str
    title: str
    kind: Literal["metric", "chart", "flag", "text"] = "metric"
    definition: Optional[Dict[str, Any]] = None
    value: Any = None


class RunMetadata(BaseModel):
    run_id: str
    provider: str
    model: str
    prompt_version: str = "2.0.0"
    pipeline_version: str = "v2"


class UniversalExtractionResult(BaseModel):
    """
    The definitive dynamic contract delivered to the React frontend.
    Rendered entirely by generic dynamic components.
    """
    document_id: int
    classification: ClassificationResult
    schema_info: Dict[str, Any] = Field(default_factory=dict)
    fields: List[DynamicFieldResult] = Field(default_factory=list)
    tables: List[DynamicTableResult] = Field(default_factory=list)
    entities: List[Dict[str, Any]] = Field(default_factory=list)
    relationships: List[Dict[str, Any]] = Field(default_factory=list)
    summary: Optional[str] = None
    insights: List[DynamicInsightResult] = Field(default_factory=list)
    validation: Dict[str, Any] = Field(default_factory=dict)
    review: Dict[str, Any] = Field(default_factory=lambda: {"required": False, "reasons": []})
    run: RunMetadata
