from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class PDFPageData(BaseModel):
    """
    Extracted textual data and metrics for an individual PDF page.
    """
    page_number: int = Field(..., ge=1, description="1-indexed page number in the document")
    text: str = Field(default="", description="Cleaned extracted text for this page")
    character_count: int = Field(default=0, ge=0, description="Number of characters in the extracted text")
    char_count: Optional[int] = Field(default=None, description="Alias for character_count")
    word_count: int = Field(default=0, ge=0, description="Number of words in the extracted text")
    has_text: bool = Field(default=False, description="True if this page contains extractable digital text")
    error: Optional[str] = Field(
        default=None,
        description="Error message if text extraction failed specifically on this page",
    )

    model_config = ConfigDict(from_attributes=True)


class PDFParseResult(BaseModel):
    """
    Standardized result for digital PDF text extraction.
    
    Attributes:
        success: True if the PDF was safely opened and parsed without critical failure.
        status: Structured status identifier ('TEXT_EXTRACTED', 'PASSWORD_PROTECTED', 'CORRUPTED', 'EMPTY_FILE', 'FAILED').
        error: Descriptive error message if success is False.
        file_type: Always 'PDF'.
        page_count: Total number of pages in the PDF document.
        total_pages: Alias for page_count.
        pages: List of PDFPageData with per-page text and metrics (page_number, text, character_count).
        combined_text: Aggregated text across all pages joined with double newlines.
        full_text: Alias for combined_text.
        total_character_count: Total characters across the document.
        total_char_count: Alias for total_character_count.
        total_word_count: Total word count across the document.
        likely_scanned: Flag indicating if the document has little or no extractable digital text (requiring OCR).
        is_encrypted: Flag indicating whether the document is password-protected or encrypted.
        metadata: Document metadata properties (e.g. Title, Author, Creator, Producer) if available.
    """
    success: bool = Field(default=True, description="Whether parsing succeeded")
    status: Optional[str] = Field(
        default=None,
        description="Structured status identifier (e.g. 'TEXT_EXTRACTED', 'PASSWORD_PROTECTED', 'CORRUPTED', 'EMPTY_FILE', 'FAILED')",
    )
    error: Optional[str] = Field(default=None, description="Error message if success is False")
    errors: List[str] = Field(
        default_factory=list,
        description="List of non-fatal page-level extraction error messages",
    )
    file_type: str = Field(default="PDF", description="Document type")
    page_count: int = Field(default=0, ge=0, description="Total number of pages in the PDF")
    total_pages: Optional[int] = Field(default=None, description="Alias for page_count")
    pages: List[PDFPageData] = Field(default_factory=list, description="Per-page extracted data")
    combined_text: str = Field(default="", description="Combined extracted text across all pages joined by double newlines")
    full_text: Optional[str] = Field(default=None, description="Alias for combined_text")
    total_characters: int = Field(default=0, ge=0, description="Total characters across the document")
    total_character_count: Optional[int] = Field(default=None, description="Alias for total_characters")
    total_char_count: Optional[int] = Field(default=None, description="Alias for total_characters")
    meaningful_characters: int = Field(
        default=0,
        ge=0,
        description="Total meaningful alphanumeric characters [a-zA-Z0-9] across the document",
    )
    alphanumeric_char_count: Optional[int] = Field(default=None, description="Alias for meaningful_characters")
    non_whitespace_char_count: int = Field(
        default=0,
        ge=0,
        description="Total count of non-whitespace characters across document",
    )
    pages_with_text: int = Field(
        default=0,
        ge=0,
        description="Count of pages containing usable digital text",
    )
    pages_without_text: int = Field(
        default=0,
        ge=0,
        description="Count of pages without extractable text",
    )
    has_extractable_text: bool = Field(
        default=True,
        description="True if the document contains usable digital text meeting quality threshold",
    )
    total_word_count: int = Field(default=0, ge=0, description="Total word count across all pages")
    likely_scanned: bool = Field(
        default=False,
        description="True if the PDF has little or no extractable digital text (requires OCR in a later step)",
    )
    is_encrypted: bool = Field(default=False, description="True if the PDF is password-protected or encrypted")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Document metadata if available")

    model_config = ConfigDict(from_attributes=True)
