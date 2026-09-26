import logging
import math
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session

from app.core.security import (
    is_path_traversal_safe,
    sanitize_filename,
    sanitize_log_text,
)
from app.database.connection import get_db
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.document_record import DocumentRecord
from app.schemas.dashboard import (
    DashboardDocumentItem,
    DashboardDocumentListResponse,
    DashboardStatsResponse,
)
from app.schemas.document import DocumentStatus, DocumentUploadResponse
from app.schemas.processing import ProcessingResult, to_processing_result
from app.schemas.review import (
    DocumentViewerInfo,
    ReviewDocumentDetailResponse,
    ReviewDocumentSummary,
    ReviewListResponse,
    VerifyDocumentRequest,
    VerifyDocumentResponse,
)
from app.services.detection import file_detection_service
from app.services.hitl_service import (
    DocumentAlreadyVerifiedError,
    DocumentFailedError,
    hitl_service,
)
from app.services.processing_pipeline import DocumentNotFoundError, pipeline
from app.services.upload_service import upload_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a single document",
    description=(
        "Upload a single document file (PDF, PNG, JPG, JPEG, CSV, XLSX) "
        "up to 10 MB. The file is securely stored on disk, inspected by the "
        "File Detection layer, and a metadata record is created in PostgreSQL."
    ),
    response_description=(
        "Basic metadata of the uploaded and detected document"
    ),
)
async def upload_document(
    file: UploadFile = File(..., description="Document file to upload"),
    db: Session = Depends(get_db),
):
    """Handles single document upload and file detection."""
    # 1. Store file securely on disk via UploadService
    safe_filename, stored_path, file_size = (
        await upload_service.save_uploaded_file(file)
    )

    clean_filename = (
        sanitize_filename(file.filename) if file.filename else safe_filename
    )

    # 2. Inspect file signature & classify document type
    detection_result = file_detection_service.detect_file_type(
        file_path=stored_path,
        original_filename=clean_filename,
        content_type=file.content_type,
    )

    logger.info(
        f"File detection for {clean_filename}: "
        f"category={detection_result.category.value}"
    )

    # 3. Persist metadata and audit log to database with rollback safety
    try:
        document = Document(
            file_name=clean_filename,
            file_path=str(stored_path),
            file_type=detection_result.category.value,
            file_size=file_size,
            status=DocumentStatus.UPLOADED.value,
            error_message=(
                None
                if detection_result.is_supported
                else detection_result.details
            ),
        )

        db.add(document)
        db.flush()

        upload_audit = AuditLog(
            document_id=document.id,
            action="DOCUMENT_UPLOADED",
            actor="system",
            details={
                "file_name": clean_filename,
                "file_size": file_size,
                "file_type": document.file_type,
            },
        )
        db.add(upload_audit)
        db.commit()
        db.refresh(document)

        logger.info(
            f"Document uploaded: ID={document.id}, name={document.file_name}"
        )
        return document

    except Exception as db_exc:
        db.rollback()
        upload_service.cleanup_file(stored_path)
        safe_db_err = sanitize_log_text(str(db_exc))
        logger.error(
            f"Database error during document upload: {safe_db_err}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record document metadata in database.",
        )


@router.get(
    "",
    response_model=DashboardDocumentListResponse,
    summary="List and filter documents for dashboard",
    description=(
        "Returns a paginated list of documents with database-level searching "
        "and filtering by status, document type, vendor name, and invoice "
        "number.\n\n"
        "**Swagger / API Query Examples:**\n"
        "- List documents: `/api/documents?page=1&page_size=20`\n"
        "- Search vendor: `/api/documents?vendor_name=ABC`\n"
        "- Search invoice: `/api/documents?invoice_number=INV-1001`\n"
        "- Filter status: `/api/documents?status=NEEDS_REVIEW`\n"
        "- Filter type: `/api/documents?document_type=PDF`\n"
        "- Combined: `/api/documents?page=1&page_size=10&status=VERIFIED&"
        "document_type=PDF`"
    ),
)
def list_dashboard_documents(
    page: int = Query(
        default=1,
        ge=1,
        description="Page number (1-indexed, minimum 1)",
        examples=[1],
    ),
    page_size: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Number of items per page (1 to 100)",
        examples=[20],
    ),
    vendor_name: Optional[str] = Query(
        default=None,
        description="Search documents by vendor name (case-insensitive)",
        examples=["ABC"],
    ),
    invoice_number: Optional[str] = Query(
        default=None,
        description="Search documents by invoice number (case-insensitive)",
        examples=["INV-1001"],
    ),
    doc_status: Optional[str] = Query(
        default=None,
        alias="status",
        description=(
            "Filter by status (UPLOADED, PROCESSING, VERIFIED, "
            "NEEDS_REVIEW, FAILED)"
        ),
        examples=["NEEDS_REVIEW"],
    ),
    document_type: Optional[str] = Query(
        default=None,
        description="Filter by document format (PDF) or type (invoice)",
        examples=["PDF"],
    ),
    db: Session = Depends(get_db),
) -> DashboardDocumentListResponse:
    """Lists documents with pagination, searching, and filtering."""
    query = db.query(Document)

    has_rec_filter = bool(vendor_name or invoice_number or document_type)
    if has_rec_filter:
        query = query.outerjoin(
            DocumentRecord, Document.id == DocumentRecord.document_id
        )

    if doc_status is not None:
        clean_status = doc_status.strip().upper()
        valid_statuses = {
            DocumentStatus.UPLOADED.value,
            DocumentStatus.PROCESSING.value,
            DocumentStatus.VERIFIED.value,
            DocumentStatus.NEEDS_REVIEW.value,
            DocumentStatus.FAILED.value,
        }
        if clean_status not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Invalid status '{doc_status}'. Must be one of: "
                    f"{sorted(list(valid_statuses))}"
                ),
            )
        query = query.filter(func.upper(Document.status) == clean_status)

    if document_type:
        type_clean = document_type.strip().upper()
        query = query.filter(
            or_(
                func.upper(Document.file_type) == type_clean,
                func.upper(DocumentRecord.document_type) == type_clean,
            )
        )

    if vendor_name:
        v_term = f"%{vendor_name.strip()}%"
        query = query.filter(
            or_(
                cast(DocumentRecord.extracted_data, String).ilike(v_term),
                DocumentRecord.raw_text.ilike(v_term),
                Document.file_name.ilike(v_term),
            )
        )

    if invoice_number:
        inv_term = f"%{invoice_number.strip()}%"
        query = query.filter(
            or_(
                cast(DocumentRecord.extracted_data, String).ilike(inv_term),
                DocumentRecord.raw_text.ilike(inv_term),
                Document.file_name.ilike(inv_term),
            )
        )

    if has_rec_filter:
        query = query.distinct()

    total_count = query.count()
    total_pages = (
        math.ceil(total_count / page_size) if total_count > 0 else 0
    )

    offset = (page - 1) * page_size
    documents_list = (
        query.order_by(Document.uploaded_at.desc(), Document.id.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    doc_ids = [d.id for d in documents_list]
    records = (
        db.query(DocumentRecord)
        .filter(DocumentRecord.document_id.in_(doc_ids))
        .all()
        if doc_ids
        else []
    )
    records_map = {r.document_id: r for r in records}

    items: List[DashboardDocumentItem] = []
    for doc in documents_list:
        rec = records_map.get(doc.id)
        review_fields = (
            hitl_service.extract_review_fields(rec, doc) if rec else {}
        )

        fields_dict: Dict[str, Any] = {}
        for fname, fitem in review_fields.items():
            fields_dict[fname] = (
                fitem.normalized_value
                if fitem.normalized_value is not None
                else fitem.value
            )

        v_name = (
            fields_dict.get("vendor_name")
            or fields_dict.get("vendor")
            or fields_dict.get("company_name")
        )
        inv_num = (
            fields_dict.get("invoice_number")
            or fields_dict.get("invoice_id")
            or fields_dict.get("invoice_no")
        )
        tot_amt = (
            fields_dict.get("total_amount")
            or fields_dict.get("amount")
            or fields_dict.get("total")
        )
        inv_date = fields_dict.get("invoice_date") or fields_dict.get("date")

        items.append(
            DashboardDocumentItem(
                document_id=doc.id,
                id=doc.id,
                file_name=doc.file_name,
                file_type=doc.file_type,
                file_size=doc.file_size,
                status=doc.status,
                document_type=rec.document_type if rec else None,
                vendor_name=v_name,
                invoice_number=inv_num,
                total_amount=tot_amt,
                invoice_date=inv_date,
                confidence=rec.confidence_score if rec else None,
                confidence_score=rec.confidence_score if rec else None,
                uploaded_at=doc.uploaded_at,
                updated_at=rec.created_at if rec else None,
                error_message=doc.error_message,
                fields=fields_dict,
            )
        )

    return DashboardDocumentListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total_count,
        total_pages=total_pages,
    )


@router.get(
    "/review",
    response_model=ReviewListResponse,
    summary="List documents awaiting human-in-the-loop review",
    description="Returns all documents currently in NEEDS_REVIEW status.",
)
def list_documents_for_review(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> ReviewListResponse:
    """Lists documents requiring human verification."""
    query = (
        db.query(Document)
        .filter(Document.status == DocumentStatus.NEEDS_REVIEW.value)
        .order_by(Document.uploaded_at.desc())
    )
    total_count = query.count()
    documents_list = query.offset(skip).limit(limit).all()

    items: List[ReviewDocumentSummary] = []
    for doc in documents_list:
        record = (
            db.query(DocumentRecord)
            .filter(DocumentRecord.document_id == doc.id)
            .first()
        )
        fields = hitl_service.extract_review_fields(record, doc)
        validation_errors = hitl_service.extract_validation_errors(record, doc)

        updated_at = (
            record.created_at
            if record and record.created_at
            else doc.uploaded_at
        )

        items.append(
            ReviewDocumentSummary(
                document_id=doc.id,
                file_name=doc.file_name,
                file_type=doc.file_type,
                status=doc.status,
                uploaded_at=doc.uploaded_at,
                updated_at=updated_at,
                fields=fields,
                validation_errors=validation_errors,
            )
        )

    return ReviewListResponse(items=items, count=total_count)


@router.post(
    "/{document_id}/process",
    response_model=ProcessingResult,
    status_code=status.HTTP_200_OK,
    summary="Process a document through the central pipeline",
    description="Synchronously executes the full processing pipeline.",
    response_description="Structured processing results and routing status",
)
def process_document_endpoint(
    document_id: int,
    db: Session = Depends(get_db),
) -> ProcessingResult:
    """Synchronously executes the document processing pipeline."""
    try:
        pipeline_result = pipeline.process_document(
            document_id=document_id,
            db=db,
        )
        return to_processing_result(pipeline_result)
    except DocumentNotFoundError:
        logger.warning(
            f"Processing rejected: Document ID {document_id} not found."
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found.",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"Unhandled exception processing document ID {document_id}: {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal processing failure occurred.",
        )


@router.get(
    "/{id}/file",
    summary="View original uploaded document file",
    description="Streams original, immutable uploaded document file safely.",
)
def get_document_file(
    id: int,
    db: Session = Depends(get_db),
):
    """Streams original document file without exposing internal paths."""
    document = db.query(Document).filter(Document.id == id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {id} not found.",
        )

    file_path = Path(document.file_path)

    # 1. Verify file exists on server
    if not file_path.is_file():
        logger.error(f"Original file for doc ID {id} not found on disk.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Original document file not found on server.",
        )

    # 2. Strict path traversal protection: verify file within allowed dirs
    if not is_path_traversal_safe(file_path):
        logger.warning(
            f"Path traversal detected and blocked for doc ID {id}: "
            f"{file_path}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to the requested file path is forbidden.",
        )

    media_type, _ = mimetypes.guess_type(document.file_name)
    if not media_type:
        media_type = "application/octet-stream"

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=document.file_name,
        content_disposition_type="inline",
    )


@router.get(
    "/stats",
    response_model=DashboardStatsResponse,
    summary="Get dashboard summary statistics",
    description=(
        "Returns aggregate metrics including total processed (VERIFIED + "
        "NEEDS_REVIEW), total verified, total needing review, and average "
        "confidence.\n\n"
        "**Swagger / API Example:**\n"
        "- Statistics: `/api/documents/stats`"
    ),
)
def get_dashboard_stats(
    db: Session = Depends(get_db),
) -> DashboardStatsResponse:
    """Calculates summary dashboard statistics across all documents.

    total_processed represents successfully processed documents:
    VERIFIED + NEEDS_REVIEW. Documents in UPLOADED or PROCESSING state
    are not counted as processed.
    """
    total_docs = db.query(func.count(Document.id)).scalar() or 0

    status_counts = (
        db.query(Document.status, func.count(Document.id))
        .group_by(Document.status)
        .all()
    )
    by_status: Dict[str, int] = {s: cnt for s, cnt in status_counts if s}

    total_verified = by_status.get(DocumentStatus.VERIFIED.value, 0)
    total_needing_review = by_status.get(DocumentStatus.NEEDS_REVIEW.value, 0)
    total_failed = by_status.get(DocumentStatus.FAILED.value, 0)
    processing_count = by_status.get(DocumentStatus.PROCESSING.value, 0)
    uploaded_count = by_status.get(DocumentStatus.UPLOADED.value, 0)

    # Total processed: VERIFIED + NEEDS_REVIEW
    total_processed = total_verified + total_needing_review

    type_counts = (
        db.query(Document.file_type, func.count(Document.id))
        .group_by(Document.file_type)
        .all()
    )
    by_doc_type: Dict[str, int] = {
        (t if t else "UNKNOWN"): cnt for t, cnt in type_counts
    }

    avg_conf = (
        db.query(func.avg(DocumentRecord.confidence_score))
        .filter(DocumentRecord.confidence_score.isnot(None))
        .scalar()
    )
    avg_conf_val = (
        round(float(avg_conf), 4) if avg_conf is not None else None
    )

    accuracy = (
        round((total_verified / total_processed) * 100.0, 2)
        if total_processed > 0
        else 0.0
    )

    return DashboardStatsResponse(
        total_processed=total_processed,
        total_verified=total_verified,
        total_needing_review=total_needing_review,
        average_confidence=avg_conf_val,
        total_failed=total_failed,
        total_documents=total_docs,
        verified_count=total_verified,
        needs_review_count=total_needing_review,
        failed_count=total_failed,
        processing_count=processing_count,
        uploaded_count=uploaded_count,
        by_status=by_status,
        by_document_type=by_doc_type,
        accuracy_rate=accuracy,
    )


@router.get(
    "/{id}",
    response_model=ReviewDocumentDetailResponse,
    summary="Get complete document review data",
    description="Returns metadata, extracted fields, viewer URL, and errors.",
)
def get_document_review_detail(
    id: int,
    db: Session = Depends(get_db),
) -> ReviewDocumentDetailResponse:
    """Returns complete review payload for human verification."""
    doc = db.query(Document).filter(Document.id == id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {id} not found.",
        )

    record = (
        db.query(DocumentRecord)
        .filter(DocumentRecord.document_id == doc.id)
        .first()
    )

    fields = hitl_service.extract_review_fields(record, doc)
    validation_errors = hitl_service.extract_validation_errors(record, doc)

    processing_errors = []
    if doc.status == DocumentStatus.FAILED.value and doc.error_message:
        processing_errors.append(doc.error_message)

    return ReviewDocumentDetailResponse(
        document_id=doc.id,
        file_name=doc.file_name,
        file_type=doc.file_type,
        status=doc.status,
        document=DocumentViewerInfo(
            viewer_url=f"/api/documents/{doc.id}/file"
        ),
        fields=fields,
        validation_errors=validation_errors,
        processing_errors=processing_errors,
        raw_text=record.raw_text if record else None,
        confidence_score=record.confidence_score if record else None,
    )


@router.post(
    "/{id}/verify",
    response_model=VerifyDocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit human corrections and verify document",
    description=(
        "Submits human corrections and additions for document review. "
        "Re-normalizes and re-validates the complete data set. "
        "Every change is audited in audit_logs. Marks VERIFIED when valid, "
        "or keeps NEEDS_REVIEW if required info remains invalid."
    ),
)
def verify_document_endpoint(
    id: int,
    request: VerifyDocumentRequest,
    db: Session = Depends(get_db),
) -> VerifyDocumentResponse:
    """Processes human verification, edits, validation, and audit logging."""
    try:
        doc, record, corrections, validation_errors = (
            hitl_service.verify_document(
                db=db,
                document_id=id,
                request=request,
            )
        )
        fields = hitl_service.extract_review_fields(record, doc)

        msg = (
            "Document successfully verified and marked VERIFIED."
            if doc.status == DocumentStatus.VERIFIED.value
            else "Document remains in NEEDS_REVIEW due to validation errors."
        )

        return VerifyDocumentResponse(
            document_id=doc.id,
            status=doc.status,
            fields=fields,
            validation_errors=validation_errors,
            corrections_made=corrections,
            message=msg,
        )
    except DocumentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {id} not found.",
        )
    except (DocumentAlreadyVerifiedError, DocumentFailedError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as exc:
        logger.error(
            f"Error during document verification for doc ID {id}: {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error during document verification.",
        )


@router.get(
    "/{id}/extraction",
    summary="Get multi-tier document extraction breakdown",
    description="Returns Rule Extraction, LLM Extraction, Reconciliation, and Final Result comparison for a document.",
)
def get_document_extraction_endpoint(
    id: int,
    db: Session = Depends(get_db),
):
    """Direct alias on documents router for extraction comparison data."""
    from app.api.routes.ai import get_document_extraction_breakdown
    return get_document_extraction_breakdown(document_id=id, db=db)


@router.post(
    "/{id}/ai-extract",
    response_model=ProcessingResult,
    summary="Process document using AI / LLM extraction",
    description="Executes the full pipeline with AI extraction enabled, reconciling rule and LLM output.",
)
def extract_document_with_ai_endpoint(
    id: int,
    method: str = Query(default="rule_plus_llm", description="Method: 'rule', 'llm', or 'rule_plus_llm'"),
    document_type: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> ProcessingResult:
    """Direct alias on documents router for processing with AI."""
    from app.api.routes.ai import extract_document_with_ai
    return extract_document_with_ai(document_id=id, method=method, document_type=document_type, db=db)
