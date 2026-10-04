"""
Spreadsheet and Tabular Ingestion Service (CSV, TSV, XLSX, XLS).
Extracts sheets, inferred columns, dtypes, basic statistics, and sample rows.
Also produces ContentBlocks representing summary structure.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple
import pandas as pd

from app.schemas.universal import ContentBlock, ExtractedTable, PageMeta, SheetProfile

logger = logging.getLogger(__name__)


def ingest_spreadsheet_file(
    file_path: Path,
    ext: str,
) -> Tuple[List[PageMeta], List[ContentBlock], List[ExtractedTable], List[SheetProfile]]:
    """
    Ingests spreadsheet workbooks or CSV files into SheetProfiles, tables, and content blocks.
    """
    sheets: List[SheetProfile] = []
    tables: List[ExtractedTable] = []
    blocks: List[ContentBlock] = []

    ext_lower = ext.lower().lstrip(".")

    try:
        if ext_lower in ("csv", "tsv", "txt"):
            delimiter = "\t" if ext_lower == "tsv" else ","
            # Read first few lines or entire df
            df = pd.read_csv(file_path, sep=delimiter, nrows=5000)
            sheet_name = file_path.stem
            sheet_profile, table = _profile_dataframe(df, sheet_name, page_num=1)
            sheets.append(sheet_profile)
            tables.append(table)
        else:
            # Excel workbook (.xlsx, .xls)
            excel_file = pd.ExcelFile(file_path)
            for idx, sheet_name in enumerate(excel_file.sheet_names):
                df = pd.read_excel(excel_file, sheet_name=sheet_name, nrows=5000)
                sheet_profile, table = _profile_dataframe(df, str(sheet_name), page_num=idx + 1)
                sheets.append(sheet_profile)
                tables.append(table)

    except Exception as exc:
        logger.error(f"Spreadsheet parsing failed for '{file_path}': {exc}")
        # Graceful fallback: produce empty sheet
        sheets.append(
            SheetProfile(
                name="Error",
                columns=[],
                dtypes={},
                row_count=0,
                stats={"error": str(exc)},
            )
        )

    # Build ContentBlocks summarizing the sheets for LLM consumption
    order = 0
    for s_idx, s in enumerate(sheets):
        summary_text = (
            f"Sheet: {s.name}\n"
            f"Row count: {s.row_count}\n"
            f"Columns: {', '.join(s.columns)}\n"
            f"Statistics: {s.stats}"
        )
        blocks.append(
            ContentBlock(
                id=f"blk_sheet_{s_idx}",
                page=s_idx + 1,
                type="table_cell",
                text=summary_text,
                reading_order=order,
                ocr_conf=1.0,
            )
        )
        order += 1

    pages = [
        PageMeta(
            n=i + 1,
            width=1000.0,
            height=1000.0,
            source="tabular",
        )
        for i in range(max(1, len(sheets)))
    ]

    return pages, blocks, tables, sheets


def _profile_dataframe(
    df: pd.DataFrame,
    sheet_name: str,
    page_num: int,
) -> Tuple[SheetProfile, ExtractedTable]:
    """Computes summary statistics and extracts table representation from dataframe."""
    columns = [str(col).strip() for col in df.columns]
    dtypes = {str(col): str(dtype) for col, dtype in df.dtypes.items()}
    row_count = len(df)

    # Basic stats
    stats: Dict[str, Any] = {
        "total_rows": row_count,
        "total_columns": len(columns),
        "missing_values": int(df.isna().sum().sum()),
        "duplicate_rows": int(df.duplicated().sum()),
    }

    # Numeric summary
    numeric_df = df.select_dtypes(include=["number"])
    if not numeric_df.empty:
        stats["numeric_columns"] = {}
        for col in numeric_df.columns:
            stats["numeric_columns"][str(col)] = {
                "min": float(numeric_df[col].min()) if not pd.isna(numeric_df[col].min()) else None,
                "max": float(numeric_df[col].max()) if not pd.isna(numeric_df[col].max()) else None,
                "mean": round(float(numeric_df[col].mean()), 2) if not pd.isna(numeric_df[col].mean()) else None,
            }

    # Sample rows (first 10)
    sample_records = (
        df.head(10).fillna("").to_dict(orient="records")
    )
    # Sanitized records
    sanitized_samples = [
        {str(k): str(v) for k, v in row.items()}
        for row in sample_records
    ]

    # Convert head rows for ExtractedTable
    table_rows = []
    for _, row in df.head(50).iterrows():
        table_rows.append([str(v) if not pd.isna(v) else "" for v in row.values])

    extracted_table = ExtractedTable(
        id=f"tbl_sheet_{sheet_name}",
        page=page_num,
        headers=columns,
        rows=table_rows,
        ocr_conf=1.0,
    )

    sheet_profile = SheetProfile(
        name=sheet_name,
        columns=columns,
        dtypes=dtypes,
        row_count=row_count,
        stats=stats,
        sample_rows=sanitized_samples,
    )

    return sheet_profile, extracted_table
