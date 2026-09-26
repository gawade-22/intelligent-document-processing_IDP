from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DocumentStatus(str, Enum):
    """Lifecycle status of a document in the IDP pipeline."""
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    VERIFIED = "VERIFIED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"

    # Backward compatibility aliases
    PENDING = "pending"
    COMPLETED = "completed"
    PROCESSING_LOWER = "processing"
    FAILED_LOWER = "failed"


class DocumentBase(BaseModel):
    """Shared properties across document schemas."""
    file_name: str = Field(
        ...,
        max_length=255,
        description="Original filename of the document",
    )
    file_type: str = Field(
        ...,
        max_length=100,
        description="MIME type (e.g., application/pdf, image/png)",
    )
    file_size: int = Field(
        ...,
        gt=0,
        description="File size in bytes",
    )


class DocumentCreate(DocumentBase):
    """Schema for creating a new document record."""
    file_path: str = Field(
        ...,
        description="Server storage path for the uploaded file",
    )


class DocumentUpdate(BaseModel):
    """Schema for updating document processing status or failure notes."""
    status: Optional[str] = Field(
        default=None,
        description="Updated processing status",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error reason if processing failed",
    )


class DocumentUploadResponse(BaseModel):
    """Clean metadata response returned immediately after document upload."""
    id: int = Field(
        ...,
        description="Unique database document ID",
    )
    file_name: str = Field(
        ...,
        description="Original filename of the uploaded document",
    )
    file_type: str = Field(
        ...,
        description="MIME content type of the file",
    )
    file_size: int = Field(
        ...,
        description="Size of the file in bytes",
    )
    status: str = Field(
        default="UPLOADED",
        description="Initial processing status",
    )

    model_config = ConfigDict(from_attributes=True)


class DocumentResponse(DocumentBase):
    """Standard response schema returned by the API for document objects.

    Maps directly from SQLAlchemy Document model using from_attributes=True.
    """
    id: int = Field(
        ...,
        description="Unique document database ID",
    )
    status: str = Field(
        default="UPLOADED",
        description="Current processing status",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error explanation if processing failed",
    )
    uploaded_at: datetime = Field(
        ...,
        description="Timestamp when the document was uploaded",
    )

    # Pydantic v2 configuration to allow reading ORM models directly
    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    """Paginated or grouped list of documents."""
    total: int = Field(
        ...,
        ge=0,
        description="Total count of documents matching criteria",
    )
    items: List[DocumentResponse] = Field(
        default_factory=list,
        description="List of document response items",
    )
