import csv
import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Union
import numpy as np
import pandas as pd

from app.schemas.tabular import SheetData, TabularParseResult

logger = logging.getLogger(__name__)

# Ordered candidate encodings to attempt when reading CSV files
CANDIDATE_ENCODINGS: List[str] = ["utf-8", "utf-8-sig", "cp1252", "latin-1"]


class CsvExcelParserError(Exception):
    """
    Custom exception raised when CSV or Excel parsing fails due to corrupt data,
    decoding failures, security rejections, or unsupported file formats.
    """
    pass


class CsvExcelParser:
    """
    Production-grade, reusable parser service for CSV and XLSX files.

    Security & Reliability Guidelines:
    1. Strictly read-only: Never modifies, writes to, or overwrites source documents.
    2. Path validation: Resolves paths, rejects null bytes, and verifies file existence and readability.
    3. No formula execution: Uses openpyxl with data_only=True so formula expressions are not executed.
    4. No VBA/macro execution: Rejects macro-enabled workbooks (.xlsm) and processes without Excel runtimes.
    5. Single-pass performance: Reads all Excel worksheets in a single call without redundant file reloads.
    """

    @classmethod
    def parse_csv(cls, file_path: Union[Path, str]) -> TabularParseResult:
        """
        Parse a CSV file into a standardized TabularParseResult.

        Workflow:
        1. Validates that the file exists, is readable, and has a .csv extension.
        2. Detects encoding using a fallback hierarchy (UTF-8 -> UTF-8-BOM -> CP1252 -> Latin-1).
        3. Sniffs the delimiter (comma, semicolon, tab, or pipe).
        4. Cleans whitespace from headers and string cells without modifying meaningful internal spaces.
        5. Normalizes NaN/infinite values to None.
        6. Removes completely blank rows while preserving partial records.

        Args:
            file_path: The filesystem path to the .csv file (as a Path object or string).

        Returns:
            TabularParseResult: Standardized model containing columns, row_count,
                                records, and is_empty flag.

        Raises:
            CsvExcelParserError: If the file cannot be read, decoded, or does not exist.
        """
        path = cls._validate_file_path(file_path=file_path, expected_suffix=".csv")

        # 1. Handle empty (0-byte) files safely
        if path.stat().st_size == 0:
            logger.warning(f"CSV file is 0 bytes: {path.name}")
            return cls._create_empty_result(
                file_type="CSV",
                error_message="The CSV file is empty or contains no usable data.",
            )

        # 2. Attempt reading with candidate encodings sequentially
        df: Optional[pd.DataFrame] = None
        successful_encoding: Optional[str] = None
        delimiter: str = ","

        for encoding in CANDIDATE_ENCODINGS:
            try:
                delimiter = cls._sniff_delimiter(path=path, encoding=encoding)

                df = pd.read_csv(
                    path,
                    encoding=encoding,
                    sep=delimiter,
                    on_bad_lines="skip",
                    skipinitialspace=True,
                )
                successful_encoding = encoding
                logger.info(f"Successfully decoded '{path.name}' using encoding '{encoding}'.")
                break
            except (UnicodeDecodeError, LookupError) as decode_err:
                logger.debug(f"Encoding '{encoding}' failed for {path.name}: {decode_err}. Trying next...")
                continue
            except pd.errors.EmptyDataError:
                logger.warning(f"CSV file contains no columns or data: {path.name}")
                return cls._create_empty_result(
                    file_type="CSV",
                    error_message="The CSV file is empty or contains no usable data.",
                )
            except Exception as exc:
                logger.error(f"Unexpected parsing error for {path.name} with encoding {encoding}: {exc}")
                raise CsvExcelParserError(f"Failed to read CSV file: {exc}") from exc

        # 3. Ensure an encoding succeeded
        if df is None or successful_encoding is None:
            raise CsvExcelParserError(
                f"Unable to decode CSV file '{path.name}'. The file could not be decoded "
                f"using UTF-8, UTF-8-BOM (utf-8-sig), CP1252, or Latin-1."
            )

        # 4. Clean and normalize DataFrame into SheetData
        sheet_data: SheetData = cls._process_dataframe(df=df, sheet_name="default")

        # 5. Check if CSV contained only headers or empty rows
        if sheet_data.is_empty:
            logger.warning(f"CSV file contains headers but 0 data rows: {path.name}")
            return cls._create_empty_result(
                file_type="CSV",
                error_message="The CSV file is empty or contains no usable data.",
            )

        # 6. Return standardized CSV result
        return TabularParseResult(
            success=True,
            error=None,
            file_type="CSV",
            sheet_name=None,
            columns=sheet_data.columns,
            row_count=sheet_data.row_count,
            records=sheet_data.records,
            is_empty=sheet_data.is_empty,
            sheets=[sheet_data],
            total_sheets=1,
            total_rows=sheet_data.row_count,
            summary={
                "encoding_used": successful_encoding,
                "delimiter_used": delimiter,
            },
        )

    @classmethod
    def parse_excel(cls, file_path: Union[Path, str]) -> TabularParseResult:
        """
        Parse an Excel (.xlsx) workbook using openpyxl in a single, efficient pass.

        Security & Performance Notes:
        - Strict read-only mode: Source file is never modified or overwritten.
        - No formula execution: Uses data_only=True to extract static values without recalculating formulas.
        - No VBA/macro execution: Strictly rejects macro-enabled .xlsm and legacy .xls files.
        - Single-pass loading: Reads all sheets into memory once via sheet_name=None.

        Args:
            file_path: The filesystem path to the .xlsx file (as a Path object or string).

        Returns:
            TabularParseResult: Standardized model containing all parsed worksheets,
                                primary sheet metadata, and workbook-level metrics.

        Raises:
            CsvExcelParserError: If the workbook is corrupt or has an unsupported extension.
        """
        path = cls._validate_file_path(file_path=file_path, expected_suffix=".xlsx")

        if path.stat().st_size == 0:
            return cls._create_empty_result(
                file_type="XLSX",
                error_message="The Excel file is empty or contains no usable data.",
            )

        try:
            # Single-pass read: sheet_name=None loads all sheets in one operation.
            # engine_kwargs={"data_only": True} ensures openpyxl extracts static values
            # and prevents any formula evaluation/execution.
            sheets_dict: Dict[str, pd.DataFrame] = pd.read_excel(
                path,
                engine="openpyxl",
                sheet_name=None,
                engine_kwargs={"data_only": True},
            )
        except Exception as exc:
            logger.error(f"Error parsing Excel file {path}: {exc}")
            raise CsvExcelParserError(f"Failed to read Excel file: {exc}") from exc

        if not sheets_dict:
            return cls._create_empty_result(
                file_type="XLSX",
                error_message="The Excel workbook contains no usable sheets.",
            )

        parsed_sheets: List[SheetData] = []
        total_rows: int = 0

        for sheet_name, raw_df in sheets_dict.items():
            sheet_data: SheetData = cls._process_dataframe(df=raw_df, sheet_name=str(sheet_name))
            parsed_sheets.append(sheet_data)
            total_rows += sheet_data.row_count

        # If every sheet in the workbook has 0 rows, return structured failure
        if total_rows == 0:
            return cls._create_empty_result(
                file_type="XLSX",
                error_message="The Excel workbook contains no usable data across any worksheet.",
                sheets=parsed_sheets,
            )

        # Identify primary sheet (first sheet with data, or first sheet if all empty)
        primary_sheet = None
        for s in parsed_sheets:
            if not s.is_empty:
                primary_sheet = s
                break
        if primary_sheet is None and parsed_sheets:
            primary_sheet = parsed_sheets[0]

        return TabularParseResult(
            success=True,
            error=None,
            file_type="XLSX",
            sheet_name=primary_sheet.sheet_name if primary_sheet else None,
            columns=primary_sheet.columns if primary_sheet else [],
            row_count=primary_sheet.row_count if primary_sheet else 0,
            records=primary_sheet.records if primary_sheet else [],
            is_empty=(total_rows == 0),
            sheets=parsed_sheets,
            total_sheets=len(parsed_sheets),
            total_rows=total_rows,
            summary={
                "sheet_names": [s.sheet_name for s in parsed_sheets],
                "empty_sheets": [s.sheet_name for s in parsed_sheets if s.is_empty],
            },
        )

    @classmethod
    def parse_csv_or_excel(cls, file_path: Union[Path, str]) -> TabularParseResult:
        """
        Convenience dispatcher function that inspects the file extension
        and safely invokes the appropriate parser (CSV or Excel).

        Args:
            file_path: Path to the .csv or .xlsx file.

        Returns:
            TabularParseResult: Clean structured result.

        Raises:
            CsvExcelParserError: If the extension is unsupported or file cannot be parsed.
        """
        if isinstance(file_path, str) and ("\x00" in file_path or not file_path.strip()):
            raise CsvExcelParserError("Invalid file path provided.")

        path = Path(file_path).resolve()
        suffix: str = path.suffix.lower()

        if suffix == ".csv":
            return cls.parse_csv(file_path=path)
        elif suffix == ".xlsx":
            return cls.parse_excel(file_path=path)
        elif suffix in {".xls", ".xlsm", ".ods"}:
            raise CsvExcelParserError(
                f"Unsupported format '{suffix}'. Macro-enabled (.xlsm) and legacy (.xls) files are not allowed."
            )
        else:
            raise CsvExcelParserError(
                f"Unsupported file extension '{suffix}'. Expected '.csv' or '.xlsx'."
            )

    # -------------------------------------------------------------------------
    # Internal Cleaning and Helper Methods
    # -------------------------------------------------------------------------

    @classmethod
    def _process_dataframe(cls, df: pd.DataFrame, sheet_name: str) -> SheetData:
        """
        Internal helper to clean headers, strip cell whitespace, remove blank rows,
        convert NaNs to None, and build a SheetData model.
        """
        if df.empty:
            return SheetData(
                sheet_name=sheet_name,
                columns=[],
                row_count=0,
                records=[],
                is_empty=True,
                column_types={},
            )

        # 1. Clean, sanitize, and deduplicate column headers
        df.columns = cls._clean_column_names(columns=df.columns)

        # 2. Clean string cells: strip leading/trailing whitespace, preserve internal spaces
        for col in df.columns:
            df[col] = df[col].map(lambda x: x.strip() if isinstance(x, str) else x)

        # 3. Drop completely empty rows (where ALL values are None, NaN, or empty strings)
        is_row_empty = df.apply(
            lambda row: all(
                pd.isna(val) or val is None or (isinstance(val, str) and not val)
                for val in row
            ),
            axis=1,
        )
        df = df[~is_row_empty]

        if df.empty:
            return SheetData(
                sheet_name=sheet_name,
                columns=list(df.columns),
                row_count=0,
                records=[],
                is_empty=True,
                column_types={},
            )

        # 4. Infer column data types
        column_types: Dict[str, str] = {col: str(df[col].dtype) for col in df.columns}

        # 5. Replace NaN, NaT, and infinite values with None for JSON compliance
        df_clean = df.replace({np.nan: None, np.inf: None, -np.inf: None})
        df_clean = df_clean.where(pd.notnull(df_clean), None)

        # 6. Convert to list of record dictionaries
        records: List[Dict[str, Any]] = df_clean.to_dict(orient="records")
        is_empty: bool = len(records) == 0

        return SheetData(
            sheet_name=sheet_name,
            columns=list(df.columns),
            row_count=len(records),
            records=records,
            is_empty=is_empty,
            column_types=column_types,
        )

    @classmethod
    def _clean_column_names(cls, columns: pd.Index) -> List[str]:
        """
        Sanitizes column headers predictably:
        1. Strips leading and trailing whitespace ('  Vendor Name  ' -> 'Vendor Name').
        2. Replaces empty headers or pandas auto-generated 'Unnamed: N' with 'column_1', 'column_2', etc.
        3. Resolves duplicate headers predictably:
           First occurrence: 'Amount'
           Second occurrence: 'Amount_2'
           Third occurrence: 'Amount_3'
        """
        seen: Dict[str, int] = {}
        cleaned: List[str] = []

        for idx, col in enumerate(columns):
            col_str = str(col).strip()

            # Handle empty, None, or pandas auto-generated 'Unnamed: X' headers
            if not col_str or col_str.lower() == "none" or col_str.lower().startswith("unnamed:"):
                base_name = f"column_{idx + 1}"
            else:
                # If pandas mangled duplicate headers into 'Col .1', recover stripped base name
                match = re.match(r"^(.*?)\.(\d+)$", col_str)
                if match and match.group(1).strip() in seen:
                    base_name = match.group(1).strip()
                else:
                    base_name = col_str

            # Ensure predictable deduplication: 'Amount', 'Amount_2', 'Amount_3'
            if base_name in seen:
                seen[base_name] += 1
                unique_name = f"{base_name}_{seen[base_name]}"
            else:
                seen[base_name] = 1
                unique_name = base_name

            cleaned.append(unique_name)

        return cleaned

    @staticmethod
    def _validate_file_path(file_path: Union[Path, str], expected_suffix: str) -> Path:
        """
        Security verification for file paths:
        - Rejects null bytes and empty paths.
        - Resolves path to canonical form.
        - Verifies existence and ensures target is a regular file.
        - Verifies file readability.
        - Validates file suffix against expected format.
        - Explicitly rejects macro formats (.xlsm) and legacy files (.xls).
        """
        if isinstance(file_path, str) and ("\x00" in file_path or not file_path.strip()):
            raise CsvExcelParserError("Invalid file path provided.")

        try:
            path = Path(file_path).resolve()
        except Exception as exc:
            raise CsvExcelParserError(f"Invalid file path: {exc}") from exc

        if not path.exists():
            raise CsvExcelParserError(f"File does not exist: {path}")

        if not path.is_file():
            raise CsvExcelParserError(f"Path is not a regular file: {path}")

        if not os.access(path, os.R_OK):
            raise CsvExcelParserError(f"File is not readable: {path}")

        suffix: str = path.suffix.lower()

        # Block macro-enabled files and legacy formats
        if suffix in {".xlsm", ".xls", ".ods"}:
            raise CsvExcelParserError(
                f"Unsupported format '{suffix}'. Macro-enabled (.xlsm) and legacy (.xls) files are not allowed."
            )

        if suffix != expected_suffix:
            raise CsvExcelParserError(
                f"Invalid file extension '{path.suffix}'. Expected '{expected_suffix}'."
            )

        return path

    @staticmethod
    def _sniff_delimiter(path: Path, encoding: str) -> str:
        """
        Uses Python's csv.Sniffer to identify the delimiter (, ; \t |).
        Falls back to comma if sniffing is inconclusive.
        """
        try:
            with open(path, "r", encoding=encoding, errors="ignore") as f:
                sample = f.read(4096)
                if sample:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                    return dialect.delimiter
        except Exception:
            pass
        return ","

    @staticmethod
    def _create_empty_result(
        file_type: str,
        error_message: str,
        sheets: Optional[List[SheetData]] = None,
    ) -> TabularParseResult:
        """Builds a structured failure response without crashing."""
        if sheets is None:
            empty_sheet = SheetData(
                sheet_name="default" if file_type == "CSV" else "Sheet1",
                columns=[],
                row_count=0,
                records=[],
                is_empty=True,
                column_types={},
            )
            sheets = [empty_sheet]

        return TabularParseResult(
            success=False,
            error=error_message,
            file_type=file_type,
            sheet_name=None if file_type == "CSV" else "Sheet1",
            columns=[],
            row_count=0,
            records=[],
            is_empty=True,
            sheets=sheets,
            total_sheets=len(sheets),
            total_rows=0,
            summary={"status": "empty_file"},
        )


# Global service instance
csv_excel_parser = CsvExcelParser()

# Top-level convenience functions for clean, simple pipeline imports:
# from app.services.csv_excel_parser import parse_csv_or_excel
parse_csv = csv_excel_parser.parse_csv
parse_excel = csv_excel_parser.parse_excel
parse_csv_or_excel = csv_excel_parser.parse_csv_or_excel
