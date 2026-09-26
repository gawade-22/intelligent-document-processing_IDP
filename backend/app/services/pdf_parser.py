import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Union
import pypdf
from pypdf.errors import FileNotDecryptedError, PdfReadError

from app.schemas.pdf import PDFPageData, PDFParseResult

logger = logging.getLogger(__name__)

# =============================================================================
# Configurable Text Extraction Quality Thresholds
# =============================================================================
# Why these thresholds exist:
# Simply checking `combined_text == ""` is insufficient because scanned PDFs
# frequently contain isolated noise, OCR stamps, or single page numbers ("1", "P.1")
# embedded as digital text elements.
#
# A legitimate invoice contains coherent text: vendor names, invoice numbers,
# line items, and totals. A single threshold cannot be a 100% perfect detector
# for every scanned document, but setting a configurable baseline provides a
# reliable, transparent heuristic to route documents between the digital
# extraction pipeline and downstream OCR processing.

MIN_MEANINGFUL_CHARACTERS: int = 25  # Minimum total alphanumeric characters [a-zA-Z0-9]
MIN_PAGE_MEANINGFUL_CHARACTERS: int = 10  # A page has usable text if it has >= 10 alphanumeric chars


class PdfParserError(Exception):
    """
    Custom exception raised when PDF parsing encounters an unrecoverable failure.
    """
    pass


class PdfParser:
    """
    Production-grade, reusable service for digital PDF text extraction.

    Architecture & Safety:
    1. Safe File Handling: Verifies path existence, file validity, readability, and extension.
    2. Zero Application Crash: Corrupt or password-protected PDFs return structured failure results.
    3. Artifact Cleaning: Strips null bytes, normalizes line breaks, and trims trailing line spaces
       without destroying table columns or internal formatting.
    4. Scanned PDF Evaluation: Detects when a PDF contains little/no extractable text and flags
       it as `likely_scanned = True` for downstream OCR handling in subsequent steps.
    5. No OCR: OCR is strictly deferred to future steps as per project specifications.
    """

    @classmethod
    def parse_pdf(cls, file_path: Union[Path, str]) -> PDFParseResult:
        """
        Safely open a PDF file, extract digital text page-by-page, sanitize artifacts,
        evaluate digital vs. scanned status, and return a standardized PDFParseResult.

        Args:
            file_path: Filesystem path to the .pdf file (as Path or str).

        Returns:
            PDFParseResult: Structured result containing full text, per-page metrics,
                            scanned-flag evaluation, and document metadata.
        """
        # 1. Path safety verification
        try:
            path = cls._validate_file_path(file_path)
        except PdfParserError as val_err:
            logger.warning(f"PDF path validation error: {val_err}")
            return PDFParseResult(
                success=False,
                status="FAILED",
                error="File does not exist or is not a valid PDF file.",
                file_type="PDF",
                total_pages=0,
                pages=[],
            )

        # 2. Check for empty (0-byte) files
        if path.stat().st_size == 0:
            logger.warning(f"PDF file is 0 bytes: {path.name}")
            return PDFParseResult(
                success=False,
                status="EMPTY_FILE",
                error="The PDF file is empty (0 bytes) and contains no usable data.",
                file_type="PDF",
                total_pages=0,
                pages=[],
                likely_scanned=False,
            )

        # 3. Safely open PDF with pypdf
        try:
            with open(path, "rb") as pdf_file:
                reader = pypdf.PdfReader(pdf_file)

                # 4. Check for encryption / password protection
                # Security rules:
                # - Do NOT attempt password guessing
                # - Do NOT bypass PDF security
                # - Do NOT use hardcoded passwords
                if reader.is_encrypted:
                    logger.warning(f"PDF '{path.name}' is password-protected or encrypted.")
                    return PDFParseResult(
                        success=False,
                        status="PASSWORD_PROTECTED",
                        error="PDF is password protected and cannot be processed.",
                        file_type="PDF",
                        total_pages=0,
                        pages=[],
                        is_encrypted=True,
                    )

                total_pages: int = len(reader.pages)
                if total_pages == 0:
                    return PDFParseResult(
                        success=False,
                        status="EMPTY_FILE",
                        error="The PDF document contains 0 pages.",
                        file_type="PDF",
                        total_pages=0,
                        pages=[],
                    )

                # 5. Extract text page by page (fault-tolerant: page errors do not abort the document)
                pages_data: List[PDFPageData] = []
                page_errors: List[str] = []

                for idx, page in enumerate(reader.pages):
                    page_num = idx + 1
                    page_error: Optional[str] = None

                    try:
                        raw_text = page.extract_text() or ""
                    except Exception as page_err:
                        logger.warning(
                            f"Text extraction failed on page {page_num} of '{path.name}': {page_err}",
                            exc_info=True,
                        )
                        page_error = "Text extraction failed for this page."
                        page_errors.append(f"Page {page_num}: Text extraction failed.")
                        raw_text = ""

                    cleaned_page_text = cls._clean_extracted_text(raw_text)
                    char_count = len(cleaned_page_text)
                    word_count = len(cleaned_page_text.split())

                    pages_data.append(
                        PDFPageData(
                            page_number=page_num,
                            text=cleaned_page_text,
                            character_count=char_count,
                            char_count=char_count,
                            word_count=word_count,
                            has_text=char_count > 0,
                            error=page_error,
                        )
                    )

                # 6. Aggregate document metrics & extraction statistics
                total_char_count = sum(p.character_count for p in pages_data)
                total_word_count = sum(p.word_count for p in pages_data)

                # Combine all page texts preserving page breaks (double newline)
                combined_text = "\n\n".join(p.text for p in pages_data if p.text).strip()

                # Calculate non-whitespace and meaningful alphanumeric characters
                non_whitespace_count = sum(1 for c in combined_text if not c.isspace())
                meaningful_char_count = sum(1 for c in combined_text if c.isalnum())

                # Count pages with usable text vs pages without text
                pages_with_text = sum(
                    1 for p in pages_data
                    if sum(1 for c in p.text if c.isalnum()) >= MIN_PAGE_MEANINGFUL_CHARACTERS
                )
                pages_without_text = total_pages - pages_with_text

                # 7. Quality check: evaluate whether document has extractable text vs likely scanned
                has_extractable_text = bool(
                    total_pages > 0
                    and pages_with_text > 0
                    and meaningful_char_count >= MIN_MEANINGFUL_CHARACTERS
                )
                likely_scanned = not has_extractable_text

                # Status: TEXT_EXTRACTED for usable digital text, NO_USABLE_TEXT if likely scanned
                status = "TEXT_EXTRACTED" if has_extractable_text else "NO_USABLE_TEXT"

                # 8. Extract document metadata safely
                doc_metadata = cls._extract_metadata(reader)

                logger.info(
                    f"Parsed PDF '{path.name}': pages={total_pages}, total_chars={total_char_count}, "
                    f"meaningful_chars={meaningful_char_count}, pages_with_text={pages_with_text}, "
                    f"has_extractable_text={has_extractable_text}, likely_scanned={likely_scanned}"
                )

                return PDFParseResult(
                    success=True,
                    status=status,
                    error=None,
                    errors=page_errors,
                    file_type="PDF",
                    page_count=total_pages,
                    total_pages=total_pages,
                    pages=pages_data,
                    combined_text=combined_text,
                    full_text=combined_text,
                    total_characters=total_char_count,
                    total_character_count=total_char_count,
                    total_char_count=total_char_count,
                    meaningful_characters=meaningful_char_count,
                    alphanumeric_char_count=meaningful_char_count,
                    non_whitespace_char_count=non_whitespace_count,
                    pages_with_text=pages_with_text,
                    pages_without_text=pages_without_text,
                    has_extractable_text=has_extractable_text,
                    total_word_count=total_word_count,
                    likely_scanned=likely_scanned,
                    is_encrypted=False,
                    metadata=doc_metadata,
                )

        except (PdfReadError, FileNotDecryptedError) as pdf_err:
            logger.error(f"pypdf read error for '{path.name}': {pdf_err}", exc_info=True)
            if isinstance(pdf_err, FileNotDecryptedError) or "encrypt" in str(pdf_err).lower():
                return PDFParseResult(
                    success=False,
                    status="PASSWORD_PROTECTED",
                    error="PDF is password protected and cannot be processed.",
                    file_type="PDF",
                    total_pages=0,
                    pages=[],
                    is_encrypted=True,
                )
            return PDFParseResult(
                success=False,
                status="CORRUPTED",
                error="Unable to read the PDF file.",
                file_type="PDF",
                total_pages=0,
                pages=[],
            )
        except Exception as exc:
            logger.error(f"Unexpected error parsing PDF '{path.name}': {exc}", exc_info=True)
            return PDFParseResult(
                success=False,
                status="CORRUPTED",
                error="Unable to read the PDF file.",
                file_type="PDF",
                total_pages=0,
                pages=[],
            )

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------

    @classmethod
    def _clean_extracted_text(cls, text: str) -> str:
        """
        Cleans only obvious, unnecessary extraction artifacts without destroying
        meaningful layout or modifying the actual text:

        Strict Fidelity Rules:
        - Do NOT summarize, rewrite, or paraphrase text.
        - Do NOT correct spelling or infer missing words.
        - Do NOT remove or modify numbers, punctuation, dates, or invoice values.
        - Do NOT perform semantic extraction or entity mapping.

        Artifact Cleanup Performed:
        1. Strips null bytes (\x00) which disrupt database string storage.
        2. Normalizes \r\n and \r to standard \n.
        3. Collapses excessive consecutive blank lines (>= 3 newlines -> 2 newlines).
        4. Trims trailing whitespace from each line while preserving indentation & tabs.
        5. Trims leading/trailing whitespace of the page block.
        """
        if not text:
            return ""

        # Remove null bytes
        text = text.replace("\x00", "")

        # Normalize carriage returns
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Trim trailing whitespace on individual lines
        lines = [line.rstrip() for line in text.split("\n")]
        text = "\n".join(lines)

        # Collapse 3 or more consecutive blank lines into 2
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    @staticmethod
    def _extract_metadata(reader: pypdf.PdfReader) -> Dict[str, Any]:
        """
        Safely extracts standard metadata fields from the PdfReader.
        """
        metadata: Dict[str, Any] = {}
        try:
            raw_meta = reader.metadata
            if raw_meta:
                if raw_meta.title:
                    metadata["title"] = str(raw_meta.title).strip()
                if raw_meta.author:
                    metadata["author"] = str(raw_meta.author).strip()
                if raw_meta.creator:
                    metadata["creator"] = str(raw_meta.creator).strip()
                if raw_meta.producer:
                    metadata["producer"] = str(raw_meta.producer).strip()
                if raw_meta.creation_date:
                    metadata["creation_date"] = str(raw_meta.creation_date)
                if raw_meta.modification_date:
                    metadata["modification_date"] = str(raw_meta.modification_date)
        except Exception as exc:
            logger.debug(f"Could not read PDF metadata: {exc}")

        return metadata

    @staticmethod
    def _validate_file_path(file_path: Union[Path, str]) -> Path:
        """
        Validates path safety and existence:
        - Disallows null bytes or blank paths.
        - Resolves to canonical path.
        - Confirms path exists and is a regular file.
        - Verifies readable permissions.
        - Confirms .pdf extension.
        """
        if isinstance(file_path, str) and ("\x00" in file_path or not file_path.strip()):
            raise PdfParserError("Invalid file path provided.")

        try:
            path = Path(file_path).resolve()
        except Exception as exc:
            raise PdfParserError(f"Invalid file path syntax: {exc}") from exc

        if not path.exists():
            raise PdfParserError(f"File does not exist: {path}")

        if not path.is_file():
            raise PdfParserError(f"Path is not a regular file: {path}")

        if not os.access(path, os.R_OK):
            raise PdfParserError(f"File is not readable: {path}")

        if path.suffix.lower() != ".pdf":
            raise PdfParserError(
                f"Invalid file extension '{path.suffix}'. Expected '.pdf'."
            )

        return path


# Global singleton service instance
pdf_parser = PdfParser()

# Top-level convenience function for clean pipeline invocation:
# from app.services.pdf_parser import parse_pdf
parse_pdf = pdf_parser.parse_pdf
