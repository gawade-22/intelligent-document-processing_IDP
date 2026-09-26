from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class FileCategory(str, Enum):
    """Primary document categories supported by the IDP pipeline."""
    PDF = "PDF"
    IMAGE = "IMAGE"
    CSV = "CSV"
    EXCEL = "EXCEL"
    UNSUPPORTED = "UNSUPPORTED"


class DetectionResult(BaseModel):
    """
    Structured outcome of the file detection layer.
    Provides deterministic categorization based on file signatures, MIME types, and contents.
    """
    category: FileCategory = Field(..., description="Determined file category")
    extension: Optional[str] = Field(default=None, description="Sanitized file extension")
    mime_type: Optional[str] = Field(default=None, description="MIME content type")
    is_supported: bool = Field(..., description="Whether this file category can be processed by the IDP pipeline")
    details: Optional[str] = Field(default=None, description="Technical rationale or notes regarding detection")

    model_config = ConfigDict(from_attributes=True)
