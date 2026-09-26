"""Pydantic schemas for data normalization."""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class NormalizedField(BaseModel):
    """Schema representing the normalization outcome of a single extracted field."""

    model_config = ConfigDict(from_attributes=True)

    original_value: Optional[str] = Field(
        default=None,
        description="Original unnormalized extracted raw value string",
    )
    normalized_value: Optional[str] = Field(
        default=None,
        description="Normalized machine-readable representation (e.g., YYYY-MM-DD or decimal string)",
    )
    success: bool = Field(
        default=True,
        description="Whether normalization succeeded without error",
    )
    error: Optional[str] = Field(
        default=None,
        description="Reason for failure if normalization was unsuccessful",
    )


class InvoiceNormalizationResult(BaseModel):
    """Schema representing normalization results for invoice target fields."""

    model_config = ConfigDict(from_attributes=True)

    success: bool = Field(
        default=True,
        description="Overall normalization status (True if all present fields normalized successfully)",
    )
    invoice_date: NormalizedField = Field(
        default_factory=lambda: NormalizedField(
            original_value=None, normalized_value=None, success=True, error=None
        ),
        description="Normalized invoice date (YYYY-MM-DD)",
    )
    total_amount: NormalizedField = Field(
        default_factory=lambda: NormalizedField(
            original_value=None, normalized_value=None, success=True, error=None
        ),
        description="Normalized total amount (2-decimal financial string)",
    )
    errors: List[str] = Field(
        default_factory=list,
        description="Aggregated list of error messages across all fields",
    )

    def to_dict(self) -> dict:
        """Convert result to standard Python dictionary."""
        return self.model_dump()
