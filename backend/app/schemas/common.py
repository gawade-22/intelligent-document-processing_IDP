from typing import Any, Optional
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """
    Standardized API error response schema.
    Ensures errors returned across all endpoints have a consistent structure.
    """
    status: str = Field(default="error", description="Indicates response status")
    error_code: str = Field(..., description="Machine-readable error identifier")
    message: str = Field(..., description="Human-readable explanation of the error")
    details: Optional[Any] = Field(default=None, description="Optional extra error details or validation context")


class MessageResponse(BaseModel):
    """Generic message response for simple acknowledgments."""
    status: str = Field(default="ok", description="Status string")
    message: str = Field(..., description="Informational message")
