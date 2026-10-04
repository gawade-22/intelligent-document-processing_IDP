"""
API v2 Document Routes for Dynamic Intelligent Document Processing.
Implements the universal dynamic contract, observable job states,
physical structure inspection, dynamic extraction results, and human review.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
import mimetypes
import re
import shutil
import uuid
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.database.connection import get_db
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.document_schema import DocumentSchema
from app.models.extracted_field import ExtractedField
from app.models.extraction_run import ExtractionRun
from app.models.review_correction import ReviewCorrection
from app.models.schema_alias import SchemaAlias
from app.services.document_worker import process_document_v2_async
from app.services.ingestion.engine import ingestion_engine
from app.services.normalization_v2.normalizer import generic_normalizer

logger = logging.getLogger(__name__)

router = APIRouter()

UPLOAD_DIR = Path(getattr(settings, "UPLOAD_DIR", "uploads")).resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# -----------------------------------------------------------------------------
# Request & Response Schemas
# -----------------------------------------------------------------------------

class DocumentUploadResponse(BaseModel):
    document_id: int
    run_id: str
    file_name: str
    file_type: str
    file_size: int
    file_hash: Optional[str] = None
    status: str
    stage: str
    message: str


class FieldUpdateRequest(BaseModel):
    value: Any
    reviewer_id: str = "human"


class CreateFieldRequest(BaseModel):
    label: str
    section: str = "General"
    value: Any
    data_type: str = "string"
    canonical_key: Optional[str] = None
    reviewer_id: str = "human"


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------

@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document_v2(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    run_async: bool = Query(True, description="Process in background if true"),
    db: Session = Depends(get_db),
):
    """
    Intake and register document. Computes file hash, creates document record,
    initializes an ExtractionRun, and kicks off asynchronous ingestion.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")

    # Generate safe unique filename
    unique_suffix = uuid.uuid4().hex[:8]
    sanitized_name = Path(file.filename).name
    stored_filename = f"{unique_suffix}_{sanitized_name}"
    file_path = UPLOAD_DIR / stored_filename

    # Save to disk
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as exc:
        logger.error(f"Failed to save uploaded file '{file.filename}': {exc}")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file to disk.")

    file_size = file_path.stat().st_size
    file_hash = ingestion_engine.compute_file_hash(file_path)
    file_ext = file_path.suffix.lower().lstrip(".")

    # 1. Create Document Record
    document = Document(
        file_name=sanitized_name,
        file_path=str(file_path),
        file_type=file_ext,
        file_size=file_size,
        file_hash=file_hash,
        status="UPLOADED",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    # 2. Create Initial ExtractionRun
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    run = ExtractionRun(
        id=run_id,
        document_id=document.id,
        pipeline_version="v2",
        status="QUEUED",
        stage="UPLOADED",
        metrics={"file_size": file_size, "hash": file_hash},
    )
    db.add(run)

    # 3. Audit Log
    audit = AuditLog(
        document_id=document.id,
        action="DOCUMENT_UPLOADED_V2",
        actor="user",
        details={"file_name": sanitized_name, "run_id": run_id, "size": file_size},
    )
    db.add(audit)
    db.commit()

    # 4. Trigger Ingestion (Async Background Task or Synchronous)
    if run_async:
        background_tasks.add_task(process_document_v2_async, document.id, run_id)
    else:
        process_document_v2_async(document.id, run_id)
        db.refresh(run)

    return DocumentUploadResponse(
        document_id=document.id,
        run_id=run.id,
        file_name=document.file_name,
        file_type=document.file_type,
        file_size=document.file_size,
        file_hash=document.file_hash,
        status=run.status,
        stage=run.stage,
        message="Document uploaded successfully and queued for processing.",
    )


@router.get("", response_model=List[Dict[str, Any]])
def list_documents_v2(
    skip: int = 0,
    limit: int = 50,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Lists documents with their latest extraction run info."""
    query = db.query(Document).order_by(Document.uploaded_at.desc())
    if status_filter and status_filter.upper() != "ALL":
        query = query.filter(Document.status == status_filter.upper())

    docs = query.offset(skip).limit(limit).all()
    results = []
    for doc in docs:
        latest_run = (
            db.query(ExtractionRun)
            .filter(ExtractionRun.document_id == doc.id)
            .order_by(ExtractionRun.created_at.desc())
            .first()
        )
        results.append({
            "id": doc.id,
            "file_name": doc.file_name,
            "file_type": doc.file_type,
            "file_size": doc.file_size,
            "file_hash": doc.file_hash,
            "status": latest_run.status if latest_run else doc.status,
            "stage": latest_run.stage if latest_run else "UPLOADED",
            "latest_run_id": latest_run.id if latest_run else None,
            "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        })
    return results


@router.get("/{document_id}")
def get_document_v2(document_id: int, db: Session = Depends(get_db)):
    """Retrieves document detail with latest run."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

    latest_run = (
        db.query(ExtractionRun)
        .filter(ExtractionRun.document_id == document.id)
        .order_by(ExtractionRun.created_at.desc())
        .first()
    )

    return {
        "id": document.id,
        "file_name": document.file_name,
        "file_type": document.file_type,
        "file_size": document.file_size,
        "file_hash": document.file_hash,
        "status": latest_run.status if latest_run else document.status,
        "stage": latest_run.stage if latest_run else "UPLOADED",
        "uploaded_at": document.uploaded_at.isoformat() if document.uploaded_at else None,
        "latest_run": {
            "run_id": latest_run.id,
            "status": latest_run.status,
            "stage": latest_run.stage,
            "pipeline_version": latest_run.pipeline_version,
            "model_name": latest_run.model_name,
            "provider": latest_run.provider,
            "created_at": latest_run.created_at.isoformat() if latest_run.created_at else None,
            "completed_at": latest_run.completed_at.isoformat() if latest_run.completed_at else None,
            "metrics": latest_run.metrics,
        } if latest_run else None,
    }


@router.get("/{document_id}/file")
def get_document_file_v2(document_id: int, db: Session = Depends(get_db)):
    """Stream raw document file for preview/inspection."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document or not document.file_path:
        raise HTTPException(status_code=404, detail="Document file not found.")

    file_path = Path(document.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on server disk.")

    media_type, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(
        path=str(file_path),
        filename=document.file_name,
        media_type=media_type or "application/octet-stream",
    )


@router.get("/{document_id}/runs")
def list_document_runs_v2(document_id: int, db: Session = Depends(get_db)):
    """Lists all historical and current extraction runs for a document."""
    runs = (
        db.query(ExtractionRun)
        .filter(ExtractionRun.document_id == document_id)
        .order_by(ExtractionRun.created_at.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "document_id": r.document_id,
            "pipeline_version": r.pipeline_version,
            "status": r.status,
            "stage": r.stage,
            "model_name": r.model_name,
            "provider": r.provider,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "metrics": r.metrics or {},
        }
        for r in runs
    ]


@router.get("/{document_id}/compare-runs")
def compare_document_runs_v2(
    document_id: int,
    run_a: str = Query(..., description="First run ID (baseline)"),
    run_b: str = Query(..., description="Second run ID (comparison)"),
    db: Session = Depends(get_db),
):
    """Compares metrics, latency, field values, and confidence differences between two extraction runs."""
    r_a = db.query(ExtractionRun).filter(ExtractionRun.id == run_a, ExtractionRun.document_id == document_id).first()
    r_b = db.query(ExtractionRun).filter(ExtractionRun.id == run_b, ExtractionRun.document_id == document_id).first()
    if not r_a or not r_b:
        raise HTTPException(status_code=404, detail="One or both runs not found for this document.")

    res_a = r_a.result or {}
    res_b = r_b.result or {}
    fields_a = {f["key"]: f for f in res_a.get("fields", []) if isinstance(f, dict)}
    fields_b = {f["key"]: f for f in res_b.get("fields", []) if isinstance(f, dict)}

    all_keys = sorted(set(fields_a.keys()) | set(fields_b.keys()))
    field_diffs = []
    for k in all_keys:
        fa = fields_a.get(k)
        fb = fields_b.get(k)
        val_a = fa.get("value") if fa else None
        val_b = fb.get("value") if fb else None
        conf_a = fa.get("confidence") if fa else None
        conf_b = fb.get("confidence") if fb else None
        changed = (val_a != val_b) or (conf_a != conf_b)
        field_diffs.append({
            "key": k,
            "label": (fb or fa or {}).get("label", k),
            "run_a": {"value": val_a, "confidence": conf_a},
            "run_b": {"value": val_b, "confidence": conf_b},
            "changed": changed,
        })

    return {
        "document_id": document_id,
        "run_a": {
            "id": r_a.id,
            "pipeline_version": r_a.pipeline_version,
            "status": r_a.status,
            "model_name": r_a.model_name,
            "metrics": r_a.metrics,
            "field_count": len(fields_a),
        },
        "run_b": {
            "id": r_b.id,
            "pipeline_version": r_b.pipeline_version,
            "status": r_b.status,
            "model_name": r_b.model_name,
            "metrics": r_b.metrics,
            "field_count": len(fields_b),
        },
        "field_diffs": field_diffs,
    }



@router.get("/{document_id}/status")
def get_document_status_v2(document_id: int, db: Session = Depends(get_db)):
    """Observable status check: stage, status, progress, error details."""
    latest_run = (
        db.query(ExtractionRun)
        .filter(ExtractionRun.document_id == document_id)
        .order_by(ExtractionRun.created_at.desc())
        .first()
    )
    if not latest_run:
        raise HTTPException(status_code=404, detail="No run found for this document.")

    return {
        "document_id": document_id,
        "run_id": latest_run.id,
        "status": latest_run.status,
        "stage": latest_run.stage,
        "error_message": latest_run.error_message,
        "metrics": latest_run.metrics,
        "created_at": latest_run.created_at.isoformat() if latest_run.created_at else None,
        "completed_at": latest_run.completed_at.isoformat() if latest_run.completed_at else None,
    }


@router.get("/{document_id}/structure")
def get_document_structure_v2(document_id: int, db: Session = Depends(get_db)):
    """Returns the UniversalDocument physical structure (pages, blocks, tables, sheets)."""
    latest_run = (
        db.query(ExtractionRun)
        .filter(ExtractionRun.document_id == document_id)
        .order_by(ExtractionRun.created_at.desc())
        .first()
    )
    if not latest_run or not latest_run.universal_document:
        # If run has no universal_doc yet, attempt on-the-fly ingestion if document exists
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document or not Path(document.file_path).exists():
            raise HTTPException(status_code=404, detail="Document file not available on disk.")

        udoc = ingestion_engine.ingest(
            Path(document.file_path),
            document_id=document.id,
            file_name=document.file_name,
        )
        if latest_run:
            latest_run.universal_document = udoc.model_dump()
            db.commit()
        return udoc.model_dump()

    return latest_run.universal_document


@router.get("/{document_id}/extraction")
def get_document_extraction_v2(document_id: int, db: Session = Depends(get_db)):
    """Returns the dynamic extraction result matching the UniversalExtractionResult contract."""
    latest_run = (
        db.query(ExtractionRun)
        .filter(ExtractionRun.document_id == document_id)
        .order_by(ExtractionRun.created_at.desc())
        .first()
    )
    if not latest_run:
        raise HTTPException(status_code=404, detail="No extraction run found for document.")

    if not latest_run.result:
        return {
            "document_id": document_id,
            "status": latest_run.status,
            "stage": latest_run.stage,
            "message": "Extraction is pending or in progress.",
            "fields": [],
            "tables": [],
            "insights": [],
        }

    res = dict(latest_run.result)
    res["status"] = latest_run.status
    if latest_run.metrics and "doc_confidence" in latest_run.metrics:
        res["doc_confidence"] = latest_run.metrics["doc_confidence"]
    elif res.get("fields"):
        confs = [f.get("confidence", 0.9) for f in res["fields"] if isinstance(f, dict)]
        res["doc_confidence"] = round(sum(confs) / max(1, len(confs)), 2)
    else:
        res["doc_confidence"] = 0.95

    if "run" in res and isinstance(res["run"], dict):
        res["run"]["status"] = latest_run.status
        res["run"]["doc_confidence"] = res["doc_confidence"]
    return res


@router.get("/{document_id}/evidence")
def get_document_evidence_v2(document_id: int, db: Session = Depends(get_db)):
    """Returns evidence quote and bounding box highlights for all extracted fields."""
    latest_run = (
        db.query(ExtractionRun)
        .filter(ExtractionRun.document_id == document_id)
        .order_by(ExtractionRun.created_at.desc())
        .first()
    )
    if not latest_run:
        raise HTTPException(status_code=404, detail="No run found.")

    fields = db.query(ExtractedField).filter(ExtractedField.run_id == latest_run.id).all()
    evidence_list = []
    for f in fields:
        if f.evidence:
            evidence_list.append({
                "field_id": f.id,
                "canonical_key": f.canonical_key,
                "label": f.label,
                "evidence": f.evidence,
                "grounded": f.grounded,
                "confidence": f.confidence,
            })
    return evidence_list


@router.get("/{document_id}/insights")
def get_document_insights_v2(document_id: int, db: Session = Depends(get_db)):
    """Returns dynamic schema-driven and document-wide analytics and insights."""
    latest_run = (
        db.query(ExtractionRun)
        .filter(ExtractionRun.document_id == document_id)
        .order_by(ExtractionRun.created_at.desc())
        .first()
    )
    if not latest_run:
        raise HTTPException(status_code=404, detail="No run found.")

    if not latest_run.result:
        return []

    return latest_run.result.get("insights", [])


@router.get("/{document_id}/pdf-report")
def download_document_pdf_report(document_id: int, db: Session = Depends(get_db)):
    """Generates and streams a professional PDF extraction summary report."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

    latest_run = (
        db.query(ExtractionRun)
        .filter(ExtractionRun.document_id == document_id)
        .order_by(ExtractionRun.created_at.desc())
        .first()
    )
    if not latest_run or not latest_run.result:
        raise HTTPException(status_code=400, detail="Document extraction is not yet completed.")

    res = latest_run.result
    fields = res.get("fields", [])
    tables = res.get("tables", [])
    insights = res.get("insights", [])
    classification = res.get("classification", {})
    confidence = latest_run.metrics.get("doc_confidence", 0.90) if latest_run.metrics else 0.90

    from app.services.reporting.pdf_report import generate_document_pdf_report
    pdf_bytes = generate_document_pdf_report(
        document_name=document.file_name,
        doc_format=document.file_type or "PDF",
        classification=classification,
        fields=fields,
        tables=tables,
        insights=insights,
        run_id=latest_run.id,
        status=latest_run.status or "COMPLETED",
        confidence=confidence,
    )

    clean_name = re.sub(r"[^\w\-_\.]", "_", document.file_name.rsplit(".", 1)[0])
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=\"{clean_name}_report.pdf\"",
        },
    )



@router.post("/{document_id}/fields")
def add_custom_field_v2(
    document_id: int,
    payload: CreateFieldRequest,
    db: Session = Depends(get_db),
):
    """Allows user to manually add a custom field if missing from extraction."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

    latest_run = (
        db.query(ExtractionRun)
        .filter(ExtractionRun.document_id == document_id)
        .order_by(ExtractionRun.created_at.desc())
        .first()
    )
    if not latest_run:
        raise HTTPException(status_code=400, detail="No active extraction run for document.")

    new_val_str = str(payload.value).strip()
    norm_val, is_valid, norm_err = generic_normalizer.normalize_field(
        raw_value=new_val_str,
        data_type=payload.data_type,
    )
    effective_norm = str(norm_val) if norm_val is not None else new_val_str
    canonical_key = payload.canonical_key or payload.label.lower().replace(" ", "_")

    # Create ExtractedField record
    new_field = ExtractedField(
        run_id=latest_run.id,
        document_id=document_id,
        canonical_key=canonical_key,
        field_key=canonical_key,
        label=payload.label,
        section=payload.section or "Custom Fields",
        data_type=payload.data_type,
        raw_value=new_val_str,
        normalized_value=effective_norm,
        confidence=1.0,
        status="edited",
        grounded=True,
        validation_messages=[norm_err] if (not is_valid and norm_err) else [],
    )
    db.add(new_field)
    db.flush()

    # Append to run.result["fields"]
    if latest_run.result and "fields" in latest_run.result:
        field_obj = {
            "id": f"fld_custom_{new_field.id}",
            "key": canonical_key,
            "label": payload.label,
            "section": payload.section or "Custom Fields",
            "value": new_val_str,
            "normalized_value": effective_norm,
            "data_type": payload.data_type,
            "confidence": 1.0,
            "evidence": {
                "page": 1,
                "quote": new_val_str,
                "bbox": [0, 0, 0, 0],
                "grounded": True,
                "match_score": 1.0,
            },
            "passes": [{"engine": "manual_entry", "value": new_val_str}],
            "validation": {
                "status": "warn" if (not is_valid and norm_err) else "pass",
                "messages": [norm_err] if (not is_valid and norm_err) else [],
            },
            "status": "edited",
            "editable": True,
        }
        latest_run.result["fields"].append(field_obj)
        flag_modified(latest_run, "result")

    # Record Audit Log
    audit = AuditLog(
        document_id=document_id,
        action="FIELD_ADDITION_V2",
        actor=payload.reviewer_id,
        details={
            "field_id": new_field.id,
            "key": canonical_key,
            "value": effective_norm,
        },
    )
    db.add(audit)
    db.commit()

    return {
        "success": True,
        "field_id": new_field.id,
        "id": f"fld_custom_{new_field.id}",
        "key": canonical_key,
        "label": payload.label,
        "section": payload.section or "Custom Fields",
        "value": new_val_str,
        "normalized_value": effective_norm,
        "status": "edited",
        "confidence": 1.0,
        "data_type": payload.data_type,
    }


@router.patch("/{document_id}/fields/{field_id}")
def update_field_v2(
    document_id: int,
    field_id: str,
    payload: FieldUpdateRequest,
    db: Session = Depends(get_db),
):
    """HITL Field edit: updates field value, normalizes it, records ReviewCorrection and AuditLog, updates run result, and marks status as edited."""
    latest_run = (
        db.query(ExtractionRun)
        .filter(ExtractionRun.document_id == document_id)
        .order_by(ExtractionRun.created_at.desc())
        .first()
    )

    field = None
    if field_id.isdigit():
        field = db.query(ExtractedField).filter(
            ExtractedField.id == int(field_id),
            ExtractedField.document_id == document_id,
        ).first()

    if not field:
        field = db.query(ExtractedField).filter(
            ExtractedField.document_id == document_id,
            (ExtractedField.canonical_key == field_id) | (ExtractedField.field_key == field_id),
        ).first()

    new_value = str(payload.value)
    data_type = field.data_type if field else "string"

    # 1. Normalize newly supplied value by field's data_type
    norm_val, is_valid, norm_err = generic_normalizer.normalize_field(
        raw_value=new_value,
        data_type=data_type,
    )
    effective_norm = str(norm_val) if norm_val is not None else new_value
    canonical_key = field.canonical_key if field else field_id

    # 2. Record or update ExtractedField
    if field:
        orig_value = field.normalized_value or field.raw_value
        correction = ReviewCorrection(
            field_id=field.id,
            run_id=field.run_id,
            canonical_key=field.canonical_key,
            original_value=orig_value,
            corrected_value=effective_norm,
            reviewer_id=payload.reviewer_id,
        )
        db.add(correction)
        field.raw_value = new_value
        field.normalized_value = effective_norm
        field.status = "edited"
        field.confidence = 1.0
        field.validation_messages = [norm_err] if (not is_valid and norm_err) else []
    elif latest_run:
        # Create record in DB
        field = ExtractedField(
            run_id=latest_run.id,
            document_id=document_id,
            canonical_key=canonical_key,
            field_key=canonical_key,
            label=canonical_key.replace("_", " ").title(),
            section="General",
            data_type=data_type,
            raw_value=new_value,
            normalized_value=effective_norm,
            status="edited",
            confidence=1.0,
            grounded=True,
            validation_messages=[norm_err] if (not is_valid and norm_err) else [],
        )
        db.add(field)
        db.flush()

    # 3. Update the extraction run JSONB result
    if latest_run and latest_run.result and "fields" in latest_run.result:
        updated_fields = []
        found_in_result = False
        for f_dict in latest_run.result.get("fields", []):
            if str(f_dict.get("id")) == str(field_id) or f_dict.get("key") == canonical_key:
                f_dict["value"] = new_value
                f_dict["normalized_value"] = effective_norm
                f_dict["status"] = "edited"
                f_dict["confidence"] = 1.0
                f_dict["validation"] = {
                    "status": "warn" if (not is_valid and norm_err) else "pass",
                    "messages": [norm_err] if (not is_valid and norm_err) else [],
                }
                found_in_result = True
            updated_fields.append(f_dict)
        if not found_in_result and field:
            updated_fields.append({
                "id": str(field.id),
                "key": canonical_key,
                "label": field.label,
                "section": field.section,
                "value": new_value,
                "normalized_value": effective_norm,
                "data_type": data_type,
                "confidence": 1.0,
                "status": "edited",
                "editable": True,
            })
        latest_run.result["fields"] = updated_fields
        flag_modified(latest_run, "result")

    # 4. Audit Log
    audit = AuditLog(
        document_id=document_id,
        action="FIELD_CORRECTION_V2",
        actor=payload.reviewer_id,
        details={
            "field_id": field.id if field else field_id,
            "key": canonical_key,
            "new_value": effective_norm,
        },
    )
    db.add(audit)
    db.commit()

    return {
        "success": True,
        "field_id": field.id if field else field_id,
        "canonical_key": canonical_key,
        "raw_value": new_value,
        "normalized_value": effective_norm,
        "status": "edited",
        "confidence": 1.0,
    }


@router.post("/{document_id}/verify")
def verify_document_v2(document_id: int, db: Session = Depends(get_db)):
    """Verifies and approves document extraction."""
    latest_run = (
        db.query(ExtractionRun)
        .filter(ExtractionRun.document_id == document_id)
        .order_by(ExtractionRun.created_at.desc())
        .first()
    )
    if not latest_run:
        raise HTTPException(status_code=404, detail="No run found.")

    latest_run.status = "VERIFIED"
    latest_run.stage = "COMPLETED"
    latest_run.completed_at = datetime.now(timezone.utc)

    doc = db.query(Document).filter(Document.id == document_id).first()
    if doc:
        doc.status = "VERIFIED"

    audit = AuditLog(
        document_id=document_id,
        action="DOCUMENT_VERIFIED_V2",
        actor="human",
        details={"run_id": latest_run.id},
    )
    db.add(audit)
    db.commit()

    return {"success": True, "document_id": document_id, "status": "VERIFIED"}


@router.post("/{document_id}/reprocess")
def reprocess_document_v2(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Spawns a new ExtractionRun and queues reprocessing."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    run_id = f"run_{uuid.uuid4().hex[:12]}"
    run = ExtractionRun(
        id=run_id,
        document_id=doc.id,
        pipeline_version="v2",
        status="QUEUED",
        stage="UPLOADED",
        metrics={"reprocessed_from": doc.status},
    )
    db.add(run)
    doc.status = "PROCESSING"
    db.commit()

    background_tasks.add_task(process_document_v2_async, doc.id, run_id)
    return {
        "success": True,
        "document_id": doc.id,
        "run_id": run_id,
        "status": "QUEUED",
    }


# -----------------------------------------------------------------------------
# Schema Registry Endpoints
# -----------------------------------------------------------------------------

@router.get("/schemas/list")
def list_schemas_v2(db: Session = Depends(get_db)):
    """Lists registered schemas from the Schema Registry."""
    schemas = db.query(DocumentSchema).filter(DocumentSchema.is_active == True).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "family": s.family,
            "version": s.version,
            "origin": s.origin,
            "description": s.description,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in schemas
    ]


@router.get("/schemas/{schema_id}")
def get_schema_v2(schema_id: str, db: Session = Depends(get_db)):
    """Retrieves full definition of a registered schema."""
    schema = db.query(DocumentSchema).filter(DocumentSchema.id == schema_id).first()
    if not schema:
        raise HTTPException(status_code=404, detail="Schema not found in registry.")

    return {
        "id": schema.id,
        "name": schema.name,
        "family": schema.family,
        "version": schema.version,
        "origin": schema.origin,
        "description": schema.description,
        "definition": schema.schema_definition,
    }


class SchemaUpdateRequest(BaseModel):
    name: Optional[str] = None
    family: Optional[str] = None
    description: Optional[str] = None
    schema_definition: Dict[str, Any]


class SchemaCreateRequest(BaseModel):
    name: str
    family: str = "general"
    description: Optional[str] = None
    schema_definition: Dict[str, Any]


@router.put("/schemas/{schema_id}")
def update_schema_v2(
    schema_id: str,
    payload: SchemaUpdateRequest,
    db: Session = Depends(get_db),
):
    """Updates a registered schema definition (fields, sections, validation rules, insight defs)."""
    schema = db.query(DocumentSchema).filter(DocumentSchema.id == schema_id).first()
    if not schema:
        raise HTTPException(status_code=404, detail="Schema not found in registry.")

    if payload.name:
        schema.name = payload.name
    if payload.family:
        schema.family = payload.family
    if payload.description is not None:
        schema.description = payload.description
    schema.schema_definition = payload.schema_definition
    schema.version += 1
    db.commit()

    return {
        "success": True,
        "schema_id": schema.id,
        "name": schema.name,
        "version": schema.version,
        "definition": schema.schema_definition,
    }


@router.post("/schemas", status_code=status.HTTP_201_CREATED)
def create_schema_v2(
    payload: SchemaCreateRequest,
    db: Session = Depends(get_db),
):
    """Registers a new custom document schema in the Schema Registry."""
    schema_id = f"sch_{payload.name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
    schema = DocumentSchema(
        id=schema_id,
        name=payload.name,
        family=payload.family,
        version=1,
        origin="custom",
        description=payload.description or "",
        schema_definition=payload.schema_definition,
    )
    db.add(schema)
    db.commit()
    db.refresh(schema)
    return {
        "success": True,
        "schema_id": schema.id,
        "name": schema.name,
        "version": schema.version,
        "definition": schema.schema_definition,
    }
