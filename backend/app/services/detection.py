import logging
import os
from pathlib import Path
from typing import Optional
import zipfile

from app.schemas.detection import DetectionResult, FileCategory
from app.utils.file_utils import get_file_extension

logger = logging.getLogger(__name__)

# Known File Signatures (Magic Bytes)
PDF_MAGIC_BYTES = b"%PDF-"
PNG_MAGIC_BYTES = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC_BYTES = b"\xff\xd8\xff"
ZIP_MAGIC_BYTES = b"PK\x03\x04"


class FileDetectionService:
    """
    Service responsible for detecting the true document type based on
    binary file signatures (magic bytes), file structure, MIME types, and extensions.
    """

    @classmethod
    def detect_file_type(
        cls,
        file_path: Path | str,
        original_filename: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> DetectionResult:
        """
        Inspects the file and returns a structured DetectionResult.
        Guaranteed not to raise uncaught exceptions or crash the server.
        """
        path = Path(file_path)

        # 1. Handle missing, inaccessible, or empty files safely
        if not path.exists() or not path.is_file():
            return DetectionResult(
                category=FileCategory.UNSUPPORTED,
                extension=get_file_extension(original_filename) if original_filename else None,
                mime_type=content_type,
                is_supported=False,
                details="File does not exist or is inaccessible on the filesystem.",
            )

        try:
            file_size = path.stat().st_size
            if file_size == 0:
                return DetectionResult(
                    category=FileCategory.UNSUPPORTED,
                    extension=get_file_extension(original_filename) if original_filename else None,
                    mime_type=content_type,
                    is_supported=False,
                    details="File is empty (0 bytes).",
                )
        except Exception as exc:
            logger.error(f"Error accessing file metadata for {path}: {exc}")
            return DetectionResult(
                category=FileCategory.UNSUPPORTED,
                extension=get_file_extension(original_filename) if original_filename else None,
                mime_type=content_type,
                is_supported=False,
                details=f"Could not read file metadata: {exc}",
            )

        # 2. Read file header (first 4096 bytes) for signature inspection
        try:
            with open(path, "rb") as f:
                header = f.read(4096)
        except Exception as exc:
            logger.error(f"Failed to read file header from {path}: {exc}")
            return DetectionResult(
                category=FileCategory.UNSUPPORTED,
                extension=get_file_extension(original_filename) if original_filename else None,
                mime_type=content_type,
                is_supported=False,
                details=f"Failed to open and read file content: {exc}",
            )

        declared_ext = get_file_extension(original_filename or path.name)

        # 3. Signature Check: PDF
        # PDF specifications allow %PDF- to appear anywhere within the first 1024 bytes
        if PDF_MAGIC_BYTES in header[:1024]:
            conflict_note = (
                f"Note: Original filename had extension '{declared_ext}' but content matches PDF."
                if declared_ext and declared_ext != ".pdf"
                else "Verified PDF file signature (%PDF-)."
            )
            return DetectionResult(
                category=FileCategory.PDF,
                extension=".pdf",
                mime_type="application/pdf",
                is_supported=True,
                details=conflict_note,
            )

        # 4. Signature Check: Images (PNG & JPEG)
        if header.startswith(PNG_MAGIC_BYTES) or header.startswith(b"\x89PNG"):
            return DetectionResult(
                category=FileCategory.IMAGE,
                extension=".png",
                mime_type="image/png",
                is_supported=True,
                details="Verified PNG image signature.",
            )

        if header.startswith(JPEG_MAGIC_BYTES):
            return DetectionResult(
                category=FileCategory.IMAGE,
                extension=".jpg",
                mime_type="image/jpeg",
                is_supported=True,
                details="Verified JPEG image signature.",
            )

        # 5. Structure Check: XLSX (Excel)
        # XLSX files are ZIP archives starting with 'PK\x03\x04' containing an 'xl/' workbook structure
        if header.startswith(ZIP_MAGIC_BYTES):
            is_excel, excel_details = cls._inspect_xlsx_archive(path)
            if is_excel:
                return DetectionResult(
                    category=FileCategory.EXCEL,
                    extension=".xlsx",
                    mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    is_supported=True,
                    details=excel_details,
                )
            else:
                return DetectionResult(
                    category=FileCategory.UNSUPPORTED,
                    extension=declared_ext or ".zip",
                    mime_type="application/zip",
                    is_supported=False,
                    details=f"ZIP archive detected, but it is not a valid Excel workbook ({excel_details}).",
                )

        # 6. Text & Sanity Check: CSV
        # CSV has no magic bytes, so we verify plain text encoding, absence of null bytes, and delimiter presence
        is_csv, csv_details = cls._inspect_csv_content(header, declared_ext, content_type)
        if is_csv:
            return DetectionResult(
                category=FileCategory.CSV,
                extension=".csv",
                mime_type="text/csv",
                is_supported=True,
                details=csv_details,
            )

        # 7. Fallback: Unrecognized or Unsupported Format
        return DetectionResult(
            category=FileCategory.UNSUPPORTED,
            extension=declared_ext,
            mime_type=content_type,
            is_supported=False,
            details="Unrecognized file signature or unsupported file format.",
        )

    @classmethod
    def _inspect_xlsx_archive(cls, path: Path) -> tuple[bool, str]:
        """
        Inspects a ZIP file to verify if it contains internal Excel OpenXML parts (e.g. xl/workbook.xml).
        """
        try:
            if not zipfile.is_zipfile(path):
                return False, "File is not a valid ZIP archive"

            with zipfile.ZipFile(path, "r") as zf:
                namelist = zf.namelist()
                has_content_types = "[Content_Types].xml" in namelist
                has_workbook = any(name.startswith("xl/") or name == "xl/workbook.xml" for name in namelist)

                if has_content_types and has_workbook:
                    return True, "Verified Office OpenXML Excel workbook structure."
                return False, "ZIP does not contain standard Excel xl/ structures."
        except zipfile.BadZipFile:
            return False, "Corrupted or invalid ZIP/XLSX file."
        except Exception as exc:
            return False, f"Error inspecting ZIP contents: {exc}"

    @classmethod
    def _inspect_csv_content(
        cls,
        header: bytes,
        declared_ext: str,
        content_type: Optional[str],
    ) -> tuple[bool, str]:
        """
        Sanity checks whether a byte sample is a valid plain text CSV.
        """
        # Binary files usually contain null bytes (\x00); CSV text files never should
        if b"\x00" in header:
            return False, "File contains binary null bytes, not plain text."

        # Attempt decoding text sample as UTF-8 or Latin-1
        try:
            text_sample = header.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text_sample = header.decode("latin-1")
            except Exception:
                return False, "File could not be decoded as text."

        # Check if declared extension or MIME type supports CSV
        is_declared_csv = declared_ext == ".csv" or (content_type and "csv" in content_type.lower())

        # Check for typical CSV delimiters in the text sample
        delimiters = [",", ";", "\t", "|"]
        has_delimiter = any(d in text_sample for d in delimiters)
        has_newlines = "\n" in text_sample or "\r" in text_sample

        if is_declared_csv and (has_delimiter or has_newlines):
            return True, "Verified plain text encoding with standard tabular/CSV delimiters."
        elif has_delimiter and has_newlines and declared_ext in {".txt", ".csv", ""}:
            return True, "Detected plain text structure with row breaks and column delimiters."

        return False, "Content lacks CSV structural characteristics."


file_detection_service = FileDetectionService()
