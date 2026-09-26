"""Universal Human-in-the-Loop (HITL) document verification service.

Provides universal review, correction tracking, re-normalization,
re-validation, and audit logging across all supported document types
(invoices, forms, marksheets, certificates, employee records, etc.).
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.document_record import DocumentRecord
from app.schemas.document import DocumentStatus
from app.schemas.review import (
    FieldCorrectionAudit,
    ReviewFieldItem,
    VerifyDocumentRequest,
)
from app.services.normalizer import InvoiceNormalizer
from app.services.validator import InvoiceValidator

logger = logging.getLogger(__name__)

# Keys reserved for pipeline metadata, skipped when parsing flat extracted_data
METADATA_KEYS = {
    "validation",
    "normalization",
    "field_confidence",
    "errors",
    "processing_errors",
    "missing_fields",
    "fields_found",
    "context",
    "summary",
    "sheets",
}

# Substrings indicating date or amount semantics for universal re-normalization
DATE_FIELD_SUBSTRINGS = ("date", "dob", "birth", "joining", "validity")
AMOUNT_FIELD_SUBSTRINGS = (
    "amount",
    "total",
    "price",
    "fee",
    "salary",
    "balance",
    "cost",
    "percentage",
    "marks",
)


class DocumentAlreadyVerifiedError(ValueError):
    """Raised when attempting to modify an already verified document."""

    pass


class DocumentFailedError(ValueError):
    """Raised when attempting to verify a document in FAILED state."""

    pass


class HITLVerificationService:
    """Service handling universal review, editing, and verification."""

    @classmethod
    def extract_review_fields(
        cls,
        record: Optional[DocumentRecord],
        document: Optional[Document] = None,
    ) -> Dict[str, ReviewFieldItem]:
        """Universally extract field-level details from a DocumentRecord."""
        if not record or not record.extracted_data:
            return {}

        extracted = record.extracted_data
        field_conf_map: Dict[str, float] = (
            extracted.get("field_confidence", {})
        )
        val_block = extracted.get("validation", {})
        field_err_map: Dict[str, Any] = val_block.get("field_errors", {})

        results: Dict[str, ReviewFieldItem] = {}

        # 1. Structured "fields" dictionary format
        if "fields" in extracted and isinstance(extracted["fields"], dict):
            raw_fields = extracted["fields"]
            for field_name, f_val in raw_fields.items():
                if isinstance(f_val, dict):
                    v = f_val.get("value")
                    if v is None:
                        v = f_val.get("original_value")
                    norm_v = f_val.get("normalized_value")
                    conf = f_val.get("confidence")
                    if conf is None and field_name in field_conf_map:
                        conf = field_conf_map[field_name]
                    src = f_val.get("source")
                    errs = list(f_val.get("validation_errors", []))
                    if field_name in field_err_map:
                        fe = field_err_map[field_name]
                        if isinstance(fe, list):
                            errs.extend(fe)
                        elif fe:
                            errs.append(str(fe))

                    results[field_name] = ReviewFieldItem(
                        value=str(v) if v is not None else None,
                        normalized_value=(
                            str(norm_v) if norm_v is not None else None
                        ),
                        confidence=conf,
                        source=src,
                        validation_errors=sorted(list(set(errs))),
                    )
                else:
                    v_str = str(f_val) if f_val is not None else None
                    conf = field_conf_map.get(field_name)
                    errs = []
                    if field_name in field_err_map:
                        fe = field_err_map[field_name]
                        if isinstance(fe, list):
                            errs.extend(fe)
                        elif fe:
                            errs.append(str(fe))

                    results[field_name] = ReviewFieldItem(
                        value=v_str,
                        normalized_value=v_str,
                        confidence=conf,
                        source=None,
                        validation_errors=sorted(list(set(errs))),
                    )
            return results

        # 2. Flat dictionary format
        if isinstance(extracted, dict):
            for field_name, f_val in extracted.items():
                if field_name in METADATA_KEYS:
                    continue
                v_str = str(f_val) if f_val is not None else None
                conf = field_conf_map.get(field_name)
                errs = []
                if field_name in field_err_map:
                    fe = field_err_map[field_name]
                    if isinstance(fe, list):
                        errs.extend(fe)
                    elif fe:
                        errs.append(str(fe))

                results[field_name] = ReviewFieldItem(
                    value=v_str,
                    normalized_value=v_str,
                    confidence=conf,
                    source=None,
                    validation_errors=sorted(list(set(errs))),
                )

        return results

    @classmethod
    def extract_validation_errors(
        cls,
        record: Optional[DocumentRecord],
        document: Optional[Document] = None,
    ) -> List[str]:
        """Extract top-level validation error messages."""
        errors: List[str] = []
        if record and record.extracted_data:
            val_block = record.extracted_data.get("validation", {})
            if isinstance(val_block, dict):
                v_errs = val_block.get("errors", [])
                if isinstance(v_errs, list):
                    errors.extend(str(e) for e in v_errs if e)

        # Fallback to document error_message if status is NEEDS_REVIEW
        if (
            not errors
            and document
            and document.status == "NEEDS_REVIEW"
            and document.error_message
        ):
            parts = [
                p.strip()
                for p in document.error_message.split(";")
                if p.strip()
            ]
            errors.extend(parts)

        return sorted(list(set(errors)))

    @classmethod
    def normalize_field_value(
        cls,
        field_name: str,
        raw_value: Optional[str],
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Universal re-normalization for field values.

        Returns:
            Tuple of (original_value, normalized_value, error_message)
        """
        if raw_value is None:
            return None, None, None

        raw_str = str(raw_value).strip()
        if not raw_str:
            return "", "", None

        fname_lower = field_name.lower()

        # Date normalization
        if any(sub in fname_lower for sub in DATE_FIELD_SUBSTRINGS):
            norm_res = InvoiceNormalizer.normalize_date(raw_str)
            if norm_res.success and norm_res.normalized_value:
                return raw_str, norm_res.normalized_value, None
            else:
                return raw_str, raw_str, norm_res.error

        # Amount / Number normalization
        if any(sub in fname_lower for sub in AMOUNT_FIELD_SUBSTRINGS):
            norm_res = InvoiceNormalizer.normalize_amount(raw_str)
            if norm_res.success and norm_res.normalized_value:
                return raw_str, norm_res.normalized_value, None
            else:
                return raw_str, raw_str, norm_res.error

        # Standard text fields
        return raw_str, raw_str, None

    @classmethod
    def revalidate_document(
        cls,
        document_type: Optional[str],
        fields: Dict[str, ReviewFieldItem],
    ) -> Tuple[bool, List[str]]:
        """Re-validate the complete data set after human additions/corrections.

        Supports both standard invoice rules and universal document rules.
        """
        validation_errors: List[str] = []

        # 1. Collect any field-level errors produced during normalization
        for fname, fitem in fields.items():
            for err in fitem.validation_errors:
                if err not in validation_errors:
                    validation_errors.append(err)

        # 2. Document-specific validation
        doc_type_clean = (document_type or "").lower()
        is_invoice = (
            doc_type_clean == "invoice"
            or all(
                k in fields
                for k in (
                    "vendor_name",
                    "invoice_number",
                    "invoice_date",
                    "total_amount",
                )
            )
        )

        if is_invoice:
            vendor = fields.get("vendor_name")
            inv_num = fields.get("invoice_number")
            inv_date = fields.get("invoice_date")
            total = fields.get("total_amount")

            val_res = InvoiceValidator.validate_invoice(
                vendor_name=vendor.normalized_value if vendor else None,
                invoice_number=inv_num.normalized_value if inv_num else None,
                invoice_date=inv_date.normalized_value if inv_date else None,
                total_amount=total.normalized_value if total else None,
            )
            for err in val_res.errors:
                if err not in validation_errors:
                    validation_errors.append(err)
        else:
            # Universal document validation:
            # Submitted fields must not have empty values if provided
            for fname, fitem in fields.items():
                if fitem.value is None or not str(fitem.value).strip():
                    err = f"{fname} is required and cannot be empty"
                    if err not in validation_errors:
                        validation_errors.append(err)
                    if err not in fitem.validation_errors:
                        fitem.validation_errors.append(err)

        is_valid = len(validation_errors) == 0
        return is_valid, validation_errors

    @classmethod
    def verify_document(
        cls,
        db: Session,
        document_id: int,
        request: VerifyDocumentRequest,
    ) -> Tuple[
        Document, DocumentRecord, List[FieldCorrectionAudit], List[str]
    ]:
        """Execute the Human-In-The-Loop verification and correction workflow.

        - Atomic transaction: rolls back all changes on any database failure.
        - Re-normalizes corrected/added fields.
        - Re-validates the complete data set.
        - Records HUMAN_CORRECTION audit entries only for actual changes.
        - Updates confidence to 1.0 and source to 'human' for edited fields.
        - Preserves existing fields and extraction metadata.
        - Transitions to VERIFIED if valid, or keeps NEEDS_REVIEW if invalid.
        """
        try:
            return cls._execute_verification(
                db=db,
                document_id=document_id,
                request=request,
            )
        except Exception as e:
            db.rollback()
            logger.exception(
                f"HITL: Verification transaction rolled back for "
                f"document ID {document_id}: {e}"
            )
            raise

    @classmethod
    def _execute_verification(
        cls,
        db: Session,
        document_id: int,
        request: VerifyDocumentRequest,
    ) -> Tuple[
        Document, DocumentRecord, List[FieldCorrectionAudit], List[str]
    ]:
        """Internal atomic verification implementation."""
        document = (
            db.query(Document).filter(Document.id == document_id).first()
        )
        if not document:
            from app.services.processing_pipeline import DocumentNotFoundError

            raise DocumentNotFoundError(
                f"Document with ID {document_id} not found."
            )

        if document.status == DocumentStatus.VERIFIED.value:
            raise DocumentAlreadyVerifiedError(
                f"Document with ID {document_id} is already verified and "
                f"cannot be modified."
            )

        if document.status == DocumentStatus.FAILED.value:
            raise DocumentFailedError(
                f"Document with ID {document_id} is in FAILED state and "
                f"cannot be verified through HITL review."
            )

        record = (
            db.query(DocumentRecord)
            .filter(DocumentRecord.document_id == document.id)
            .first()
        )

        if not record:
            doc_type_val = (
                "invoice" if document.file_type == "PDF" else "document"
            )
            record = DocumentRecord(
                document_id=document.id,
                document_type=doc_type_val,
                extraction_status="PENDING",
                extracted_data={"fields": {}},
            )
            db.add(record)
            db.flush()

        # Existing field data
        existing_fields = cls.extract_review_fields(record, document)

        corrections_made: List[FieldCorrectionAudit] = []
        updated_fields: Dict[str, ReviewFieldItem] = {}

        # Merge and evaluate submitted fields
        # First retain existing fields not modified in the request
        for f_name, f_item in existing_fields.items():
            if f_name not in request.fields:
                updated_fields[f_name] = f_item

        # Now process each field in request.fields
        for f_name, f_input in request.fields.items():
            # Support both {"field": "val"} and {"field": {"value": "val"}}
            if isinstance(f_input, dict):
                raw_val = f_input.get("value")
                if raw_val is None:
                    raw_val = f_input.get("original_value")
            else:
                raw_val = f_input

            raw_str, norm_str, norm_err = cls.normalize_field_value(
                f_name, str(raw_val) if raw_val is not None else None
            )

            field_errs: List[str] = [norm_err] if norm_err else []

            old_item = existing_fields.get(f_name)
            old_val = old_item.value if old_item else None
            old_norm = old_item.normalized_value if old_item else None

            # Distinguish new/missing manual entry from existing field
            is_new = (
                old_item is None
                or (
                    (old_val is None or str(old_val).strip() == "")
                    and (old_norm is None or str(old_norm).strip() == "")
                )
            )

            is_actual_change = False
            change_old_val: Optional[str] = None
            change_new_val: Optional[str] = None

            if is_new:
                # New or previously missing field
                if raw_str is not None and str(raw_str).strip() != "":
                    is_actual_change = True
                    change_old_val = None
                    change_new_val = raw_str
            else:
                # Existing field: check if an actual change occurred
                # Section 18: No audit record if old value == new normalized
                raw_clean = (
                    str(raw_str).strip() if raw_str is not None else None
                )
                norm_clean = (
                    str(norm_str).strip() if norm_str is not None else None
                )
                old_val_clean = (
                    str(old_val).strip() if old_val is not None else None
                )
                old_norm_clean = (
                    str(old_norm).strip() if old_norm is not None else None
                )

                matches = False
                if (
                    norm_clean is not None
                    and old_norm_clean is not None
                    and norm_clean == old_norm_clean
                ):
                    matches = True
                elif (
                    raw_clean is not None
                    and old_val_clean is not None
                    and raw_clean == old_val_clean
                ):
                    matches = True
                elif (
                    norm_clean is not None
                    and old_val_clean is not None
                    and norm_clean == old_val_clean
                ):
                    matches = True

                if not matches:
                    is_actual_change = True
                    change_old_val = old_val
                    change_new_val = raw_str

            if is_actual_change:
                # Record HUMAN_CORRECTION audit entry
                corrections_made.append(
                    FieldCorrectionAudit(
                        field=f_name,
                        action="HUMAN_CORRECTION",
                        old_value=change_old_val,
                        new_value=change_new_val,
                    )
                )
                audit_entry = AuditLog(
                    document_id=document.id,
                    action="HUMAN_CORRECTION",
                    actor=request.reviewer_id or "reviewer",
                    details={
                        "document_id": document.id,
                        "field_name": f_name,
                        "old_value": change_old_val,
                        "new_value": change_new_val,
                        "action": "HUMAN_CORRECTION",
                        "normalized_value": norm_str,
                        "notes": request.notes,
                    },
                )
                db.add(audit_entry)
                new_conf = 1.0
                new_src = "human"
            else:
                # Value unchanged: preserve existing extraction metadata
                new_conf = old_item.confidence if old_item else 1.0
                new_src = old_item.source if old_item else "human"
                if old_item and old_item.normalized_value:
                    norm_str = old_item.normalized_value

            updated_fields[f_name] = ReviewFieldItem(
                value=raw_str,
                normalized_value=norm_str,
                confidence=new_conf,
                source=new_src,
                validation_errors=field_errs,
            )

        # 3. Re-validate complete data set
        is_valid, validation_errors = cls.revalidate_document(
            document_type=record.document_type,
            fields=updated_fields,
        )

        # 4. Determine final status
        if is_valid:
            final_status = DocumentStatus.VERIFIED.value
            document.status = final_status
            document.error_message = None
            record.extraction_status = final_status
            record.error_message = None

            # Audit log for document verification
            db.add(
                AuditLog(
                    document_id=document.id,
                    action="DOCUMENT_VERIFIED",
                    actor=request.reviewer_id or "reviewer",
                    details={
                        "corrections_count": len(corrections_made),
                        "verified_fields": list(updated_fields.keys()),
                        "notes": request.notes,
                    },
                )
            )
            logger.info(
                f"HITL: Document ID {document_id} marked VERIFIED by "
                f"{request.reviewer_id}."
            )
        else:
            final_status = DocumentStatus.NEEDS_REVIEW.value
            document.status = final_status
            err_summary = "; ".join(validation_errors)
            document.error_message = err_summary
            record.extraction_status = final_status
            record.error_message = err_summary

            db.add(
                AuditLog(
                    document_id=document.id,
                    action="ROUTED_TO_REVIEW",
                    actor=request.reviewer_id or "reviewer",
                    details={
                        "reason": (
                            "Validation errors remain after human review"
                        ),
                        "validation_errors": validation_errors,
                        "notes": request.notes,
                    },
                )
            )
            logger.info(
                f"HITL: Document ID {document_id} kept in NEEDS_REVIEW. "
                f"Errors: {err_summary}"
            )

        # 5. Persist updated extracted_data payload in record
        fields_payload = {}
        for fname, fitem in updated_fields.items():
            fields_payload[fname] = {
                "field": fname,
                "original_value": fitem.value,
                "value": fitem.value,
                "normalized_value": fitem.normalized_value,
                "confidence": fitem.confidence,
                "source": fitem.source,
                "validation_errors": fitem.validation_errors,
            }

        conf_scores = [
            f.confidence
            for f in updated_fields.values()
            if f.confidence is not None
        ]
        overall_conf = (
            sum(conf_scores) / len(conf_scores) if conf_scores else 1.0
        )
        record.confidence_score = round(overall_conf, 4)

        record.extracted_data = {
            "fields": fields_payload,
            "field_confidence": {
                fname: fitem.confidence or 1.0
                for fname, fitem in updated_fields.items()
            },
            "validation": {
                "is_valid": is_valid,
                "errors": validation_errors,
                "field_errors": {
                    fname: fitem.validation_errors
                    for fname, fitem in updated_fields.items()
                    if fitem.validation_errors
                },
            },
        }

        db.commit()
        db.refresh(document)
        db.refresh(record)

        return document, record, corrections_made, validation_errors


# Global singleton instance
hitl_service = HITLVerificationService()
