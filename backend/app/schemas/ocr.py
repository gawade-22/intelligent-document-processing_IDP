from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class OCRBoundingBox(BaseModel):
    """
    Coordinates of a detected word bounding box in pixels.
    """
    left: int = Field(..., ge=0, description="X coordinate of top-left corner")
    top: int = Field(..., ge=0, description="Y coordinate of top-left corner")
    width: int = Field(..., ge=0, description="Width of bounding box")
    height: int = Field(..., ge=0, description="Height of bounding box")
    x2: int = Field(..., ge=0, description="X coordinate of bottom-right corner (left + width)")
    y2: int = Field(..., ge=0, description="Y coordinate of bottom-right corner (top + height)")

    model_config = ConfigDict(from_attributes=True)


class OCRWordData(BaseModel):
    """
    Word-level OCR information including text, bounding box, and confidence score.
    """
    text: str = Field(..., description="Recognized word text")
    confidence: float = Field(..., ge=0.0, le=100.0, description="Tesseract confidence score (0-100)")
    bounding_box: OCRBoundingBox = Field(..., description="Pixel bounding box coordinates")
    bbox: Optional[OCRBoundingBox] = Field(default=None, description="Alias for bounding_box")
    block_num: int = Field(default=1, ge=0, description="Block number within the page")
    paragraph_num: int = Field(default=1, ge=0, description="Paragraph number within the page")
    line_num: int = Field(default=1, ge=0, description="Line number within the page")
    word_num: int = Field(default=1, ge=0, description="Word number within the line")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class OCRPageData(BaseModel):
    """
    Page-level OCR extraction result.
    """
    page_number: int = Field(..., ge=1, description="1-indexed page number")
    raw_text: str = Field(default="", description="Raw OCR extracted text for this page")
    text: str = Field(default="", description="Cleaned/reconstructed text for this page")
    words: List[OCRWordData] = Field(default_factory=list, description="List of recognized words with bounding boxes")
    character_count: int = Field(default=0, ge=0, description="Total characters in page text")
    word_count: int = Field(default=0, ge=0, description="Total words detected on page")
    average_confidence: float = Field(default=0.0, ge=0.0, le=100.0, description="Average OCR confidence for this page")
    has_text: bool = Field(default=False, description="True if text was successfully recognized")
    error: Optional[str] = Field(default=None, description="Page-level error message if extraction failed on this page")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class OCRResult(BaseModel):
    """
    Standardized, structured result of the OCR processing engine.
    """
    success: bool = Field(default=True, description="Whether OCR processing completed successfully")
    status: str = Field(default="OCR_COMPLETED", description="Status code (e.g. 'OCR_COMPLETED', 'OCR_PARTIAL', 'OCR_FAILED', 'TESSERACT_NOT_FOUND', 'POPPLER_NOT_FOUND')")
    error: Optional[str] = Field(default=None, description="Document-level error message if success is False")
    errors: List[str] = Field(default_factory=list, description="List of non-fatal page-level extraction errors")
    file_type: str = Field(..., description="File format processed ('IMAGE' or 'PDF')")
    page_count: int = Field(default=0, ge=0, description="Total number of pages processed")
    pages: List[OCRPageData] = Field(default_factory=list, description="Per-page OCR extraction results")
    combined_text: str = Field(default="", description="Combined text across all pages joined by double newlines")
    total_characters: int = Field(default=0, ge=0, description="Total characters across the document")
    total_words: int = Field(default=0, ge=0, description="Total words detected across the document")
    total_word_count: Optional[int] = Field(default=None, description="Alias for total_words")
    average_confidence: float = Field(default=0.0, ge=0.0, le=100.0, description="Overall weighted or arithmetic average confidence score")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional document/image metadata")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
