from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class AuditLogBase(BaseModel):
    """Base schema for audit log entries tracking actions and pipeline events."""
    document_id: Optional[int] = Field(
        default=None,
        description="Associated document ID, if action is document-specific",
    )
    action: str = Field(
        ...,
        max_length=100,
        description="Action performed (e.g., 'DOCUMENT_UPLOADED', 'EXTRACTION_TRIGGERED', 'EXTRACTION_COMPLETED')",
    )
    actor: str = Field(
        default="system",
        max_length=100,
        description="Identifier of who or what performed the action (e.g., 'system', user email)",
    )
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Contextual JSON details regarding the action or event",
    )
    ip_address: Optional[str] = Field(
        default=None,
        max_length=45,
        description="Client IP address where the request originated",
    )


class AuditLogCreate(AuditLogBase):
    """Schema used internally when writing a new audit entry."""
    pass


class AuditLogResponse(AuditLogBase):
    """
    Standard response schema for audit log entries.
    Maps directly from SQLAlchemy AuditLog model using from_attributes=True.
    """
    id: int = Field(..., description="Unique audit log entry ID")
    created_at: datetime = Field(..., description="Timestamp when the event occurred")

    # Pydantic v2 configuration to serialize from ORM objects
    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    """Paginated list of audit log responses."""
    total: int = Field(..., ge=0, description="Total audit records found")
    items: List[AuditLogResponse] = Field(default_factory=list, description="List of audit log items")
