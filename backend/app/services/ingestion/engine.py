"""
Universal Ingestion Engine.
Coordinates physical document extraction across all supported file formats:
- PDF (digital & scanned with per-page routing)
- Images (PNG, JPG, TIFF, WEBP)
- Spreadsheets (CSV, TSV, XLSX, XLS)
- Word Documents (DOCX)

Outputs a pure physical UniversalDocument with no semantic assumptions.
"""

import hashlib
import logging
from pathlib import Path
from typing import List, Optional

from app.schemas.universal import (
    ContentBlock,
    DocumentMeta,
    ExtractedTable,
    PageMeta,
    SheetProfile,
    UniversalDocument,
)
from app.services.ingestion.docx_ingest import ingest_docx_file
from app.services.ingestion.image_ingest import ingest_image_file
from app.services.ingestion.pdf_ingest import ingest_pdf_file
from app.services.ingestion.spreadsheet_ingest import ingest_spreadsheet_file

logger = logging.getLogger(__name__)


class UniversalIngestionEngine:
    """Master orchestrator for transforming arbitrary physical files into UniversalDocument."""

    def compute_file_hash(self, file_path: Path) -> str:
        """Calculates SHA-256 hash of the file for deduplication and caching."""
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        return sha.hexdigest()

    def ingest(
        self,
        file_path: Path,
        document_id: Optional[int] = None,
        file_name: Optional[str] = None,
    ) -> UniversalDocument:
        """
        Parses the physical file into a structured UniversalDocument.
        """
        resolved_path = Path(file_path)
        if not resolved_path.exists():
            raise FileNotFoundError(f"File not found: {resolved_path}")

        name = file_name or resolved_path.name
        file_hash = self.compute_file_hash(resolved_path)
        file_size = resolved_path.stat().st_size
        suffix = resolved_path.suffix.lower().lstrip(".")

        pages: List[PageMeta] = []
        blocks: List[ContentBlock] = []
        tables: List[ExtractedTable] = []
        sheets: List[SheetProfile] = []
        detected_format = suffix

        logger.info(f"Ingesting file '{name}' (ext={suffix}, size={file_size} bytes)")

        if suffix in ("pdf",):
            detected_format = "pdf"
            pages, blocks, tables = ingest_pdf_file(resolved_path)

        elif suffix in ("png", "jpg", "jpeg", "tiff", "tif", "bmp", "webp"):
            detected_format = "image"
            pages, blocks, tables = ingest_image_file(resolved_path)

        elif suffix in ("csv", "tsv", "xlsx", "xls"):
            detected_format = "spreadsheet"
            pages, blocks, tables, sheets = ingest_spreadsheet_file(resolved_path, ext=suffix)

        elif suffix in ("docx",):
            detected_format = "docx"
            pages, blocks, tables = ingest_docx_file(resolved_path)

        else:
            # Fallback text ingestion
            detected_format = "text"
            try:
                raw_text = resolved_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                raw_text = ""

            blocks = [
                ContentBlock(
                    id="blk_fallback_0",
                    page=1,
                    type="raw",
                    text=raw_text,
                    reading_order=0,
                    ocr_conf=1.0,
                )
            ]
            pages = [PageMeta(n=1, width=612.0, height=792.0, source="native")]

        meta = DocumentMeta(
            id=document_id,
            file_name=name,
            format=detected_format,
            page_count=len(pages),
            language="eng",
            hash=file_hash,
            file_size=file_size,
        )

        universal_doc = UniversalDocument(
            document=meta,
            pages=pages,
            blocks=blocks,
            tables=tables,
            sheets=sheets,
        )

        logger.info(
            f"Successfully ingested '{name}': {len(pages)} pages, "
            f"{len(blocks)} blocks, {len(tables)} tables, {len(sheets)} sheets"
        )
        return universal_doc


# Singleton instance
ingestion_engine = UniversalIngestionEngine()
