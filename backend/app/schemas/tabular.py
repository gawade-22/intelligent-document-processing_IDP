from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class SheetData(BaseModel):
    """
    Structured data representation of an individual worksheet.
    Preserves sheet identity and explicitly indicates whether the sheet is empty.
    """
    sheet_name: str = Field(..., description="Name of the sheet (e.g., 'Sheet1', 'Invoices')")
    columns: List[str] = Field(default_factory=list, description="Sanitized list of column names")
    row_count: int = Field(..., ge=0, description="Total number of data rows in this sheet")
    records: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Row records as key-value dictionaries (NaNs converted to null)",
    )
    is_empty: bool = Field(default=False, description="True if this worksheet contains 0 data rows")
    column_types: Optional[Dict[str, str]] = Field(
        default=None,
        description="Inferred data types per column (e.g., int64, float64, object)",
    )

    model_config = ConfigDict(from_attributes=True)


class TabularParseResult(BaseModel):
    """
    Standardized top-level response for CSV and Excel files.
    - success: True if at least one sheet has usable data, False if the entire file/workbook is empty.
    - error: Clean descriptive error message when success is False.
    - sheets: List of SheetData representing each worksheet with is_empty flag.
    """
    success: bool = Field(default=True, description="Whether parsing extracted usable data")
    error: Optional[str] = Field(default=None, description="Error message if success is False")
    file_type: str = Field(..., description="Detected format: 'CSV' or 'XLSX'")
    sheet_name: Optional[str] = Field(
        default=None,
        description="Sheet name (always None for CSV, string for single-sheet Excel)",
    )
    columns: Optional[List[str]] = Field(
        default=None,
        description="Top-level columns list (populated directly for CSV)",
    )
    row_count: Optional[int] = Field(
        default=None,
        description="Top-level row count (populated directly for CSV)",
    )
    records: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Top-level row records (populated directly for CSV and primary sheet of XLSX)",
    )
    is_empty: bool = Field(
        default=False,
        description="True if no usable data rows exist in the file or workbook",
    )
    sheets: Optional[List[SheetData]] = Field(
        default=None,
        description="List of all worksheets (populated for XLSX and multi-sheet files)",
    )
    total_sheets: int = Field(default=1, ge=0, description="Number of sheets in the workbook")
    total_rows: int = Field(default=0, ge=0, description="Sum of row counts across all sheets")
    summary: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Metadata such as encoding, delimiter, or sheet names",
    )

    model_config = ConfigDict(from_attributes=True)
