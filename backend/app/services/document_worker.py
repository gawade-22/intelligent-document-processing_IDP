"""
Document Execution Worker for Dynamic IDP v2.
Manages the observable state machine across pipeline stages:
UPLOADED -> INGESTION -> CLASSIFYING -> SCHEMA_DISCOVERY ->
EXTRACTING -> GROUNDING -> VALIDATING -> GENERATING_INSIGHTS ->
NEEDS_REVIEW / VERIFIED / FAILED.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
import time
from typing import Optional

from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.models.document import Document
from app.models.extracted_field import ExtractedField
from app.models.extraction_run import ExtractionRun
from app.schemas.universal import RunMetadata, UniversalExtractionResult
from app.services.classification.classifier import document_classifier_v2
from app.services.confidence_v2.evaluator import confidence_evaluator_v2
from app.services.extraction_v2.engine import universal_extractor
from app.services.ingestion.engine import ingestion_engine
from app.services.insights_v2.engine import insights_engine_v2
from app.services.normalization_v2.normalizer import generic_normalizer
from app.services.schema_registry.service import schema_registry
from app.services.validation_v2.engine import dsl_validation_engine

logger = logging.getLogger(__name__)


def process_document_v2_async(document_id: int, run_id: str) -> None:
    """
    Entry point for asynchronous background execution of document processing.
    Executes within an isolated database session.
    """
    db: Session = SessionLocal()
    start_time = time.time()
    try:
        run = db.query(ExtractionRun).filter(ExtractionRun.id == run_id).first()
        document = db.query(Document).filter(Document.id == document_id).first()

        if not run or not document:
            logger.error(f"Cannot process run_id={run_id}, doc_id={document_id}: Record not found.")
            return

        file_path = Path(document.file_path)
        if not file_path.exists():
            run.status = "FAILED"
            run.stage = "INGESTION"
            run.error_message = f"File not found on disk: {document.file_path}"
            document.status = "FAILED"
            db.commit()
            return

        metrics = run.metrics or {}

        # ---------------------------------------------------------------------
        # STAGE 1: INGESTION (Physical Layout, Blocks, Tables, Reading Order)
        # ---------------------------------------------------------------------
        run.status = "PROCESSING"
        run.stage = "INGESTION"
        document.status = "PROCESSING"
        db.commit()

        logger.info(f"[Run {run_id}] Stage: INGESTION for '{document.file_name}'")
        stage_start = time.time()
        universal_doc = ingestion_engine.ingest(
            file_path=file_path,
            document_id=document.id,
            file_name=document.file_name,
        )
        ingest_duration = round(time.time() - stage_start, 3)

        # Store UniversalDocument JSONB
        run.universal_document = universal_doc.model_dump()
        metrics["ingestion_seconds"] = ingest_duration

        if not document.file_hash and universal_doc.document.hash:
            document.file_hash = universal_doc.document.hash

        # ---------------------------------------------------------------------
        # STAGE 2: CLASSIFYING (Open-Label Taxonomy + Family + Confidence)
        # ---------------------------------------------------------------------
        run.stage = "CLASSIFYING"
        db.commit()

        logger.info(f"[Run {run_id}] Stage: CLASSIFYING for '{document.file_name}'")
        class_start = time.time()
        classification = document_classifier_v2.classify(universal_doc)
        class_duration = round(time.time() - class_start, 3)

        metrics["classification_seconds"] = class_duration
        metrics["classification"] = classification.model_dump()
        logger.info(
            f"[Run {run_id}] Classified as '{classification.primary_type}' "
            f"({classification.family}) conf={classification.confidence} in {class_duration}s"
        )

        # ---------------------------------------------------------------------
        # STAGE 3: SCHEMA_DISCOVERY (Registry Lookup -> Reuse / Discover)
        # ---------------------------------------------------------------------
        run.stage = "SCHEMA_DISCOVERY"
        db.commit()

        logger.info(f"[Run {run_id}] Stage: SCHEMA_DISCOVERY for '{classification.primary_type}'")
        schema_start = time.time()
        schema_obj = schema_registry.resolve_schema(
            udoc=universal_doc,
            classification=classification,
            db=db,
        )
        schema_duration = round(time.time() - schema_start, 3)

        run.schema_id = schema_obj.id
        metrics["schema_discovery_seconds"] = schema_duration
        metrics["schema_id"] = schema_obj.id
        metrics["schema_origin"] = schema_obj.origin
        run.metrics = metrics

        logger.info(
            f"[Run {run_id}] Resolved schema '{schema_obj.name}' "
            f"(id={schema_obj.id}, origin={schema_obj.origin}) in {schema_duration}s"
        )

        # ---------------------------------------------------------------------
        # STAGE 4: EXTRACTING & GROUNDING (Sectioned extraction + Evidence bbox)
        # ---------------------------------------------------------------------
        run.stage = "EXTRACTING"
        db.commit()

        logger.info(f"[Run {run_id}] Stage: EXTRACTING with schema '{schema_obj.name}'")
        ext_start = time.time()
        fields, tables = universal_extractor.extract_document(
            udoc=universal_doc,
            schema=schema_obj,
            db=db,
        )
        ext_duration = round(time.time() - ext_start, 3)
        metrics["extraction_seconds"] = ext_duration

        # Stage 5: GROUNDING verification
        run.stage = "GROUNDING"
        db.commit()

        # ---------------------------------------------------------------------
        # STAGE 6: NORMALIZATION & SAFE DSL VALIDATION
        # ---------------------------------------------------------------------
        run.stage = "VALIDATING"
        db.commit()

        val_start = time.time()
        schema_def = schema_obj.schema_definition or {}
        rules_def = schema_def.get("validation_rules", [])

        # 6a. Normalize each field
        for f in fields:
            norm_val, is_valid, norm_err = generic_normalizer.normalize_field(
                raw_value=f.value,
                data_type=f.data_type,
            )
            f.normalized_value = norm_val
            if not is_valid and norm_err:
                f.validation.status = "warn"
                f.validation.messages.append(norm_err)

        # 6b. Evaluate DSL rules
        dsl_outcomes = dsl_validation_engine.evaluate_rules(
            rules=rules_def,
            fields=fields,
            tables=tables,
        )
        dsl_errors = [r["message"] for r in dsl_outcomes if r.get("status") == "fail"]

        # 6c. Calibrated Confidence Scoring & Field-level Routing
        for f in fields:
            # Check if this field failed any DSL rule
            field_rule_fails = sum(
                1 for r in dsl_outcomes
                if r.get("status") == "fail" and (r.get("target") == f.key or f.key.endswith(f".{r.get('target', '')}"))
            )
            is_valid_type = len(f.validation.messages) == 0

            cal_conf, f_status = confidence_evaluator_v2.evaluate_field(
                field=f,
                is_type_valid=is_valid_type,
                rule_failures_for_field=field_rule_fails,
                ocr_confidence=f.evidence.match_score if f.evidence else 1.0,
            )
            f.confidence = cal_conf
            f.status = f_status

        # 6d. Document-Level Confidence & Routing
        doc_conf, doc_status, review_reasons = confidence_evaluator_v2.evaluate_document(
            fields=fields,
            dsl_errors=dsl_errors,
        )
        metrics["validation_seconds"] = round(time.time() - val_start, 3)

        # ---------------------------------------------------------------------
        # STAGE 7: GENERATING INSIGHTS (Exact Mathematical Aggregations)
        # ---------------------------------------------------------------------
        run.stage = "GENERATING_INSIGHTS"
        db.commit()

        insight_defs = schema_def.get("insight_definitions", [])
        insights = insights_engine_v2.generate_insights(
            definitions=insight_defs,
            fields=fields,
            tables=tables,
            validation_results=dsl_outcomes,
        )

        # ---------------------------------------------------------------------
        # Persist Extracted Fields to Database
        # ---------------------------------------------------------------------
        db.query(ExtractedField).filter(ExtractedField.run_id == run.id).delete()

        ungrounded_count = 0
        for f in fields:
            if not f.evidence or not f.evidence.grounded:
                ungrounded_count += 1

            db_field = ExtractedField(
                run_id=run.id,
                document_id=document.id,
                canonical_key=f.key,
                field_key=f.label.lower().replace(" ", "_"),
                label=f.label,
                section=f.section,
                data_type=f.data_type,
                raw_value=str(f.value) if f.value is not None else None,
                normalized_value=str(f.normalized_value) if f.normalized_value is not None else None,
                confidence=f.confidence,
                status=f.status,
                grounded=f.evidence.grounded if f.evidence else False,
                evidence=f.evidence.model_dump() if f.evidence else None,
                passes=[p.model_dump() for p in f.passes],
                validation_messages=f.validation.messages,
            )
            db.add(db_field)

        db.commit()

        # ---------------------------------------------------------------------
        # Assemble Final Universal Extraction Result
        # ---------------------------------------------------------------------
        run_metadata = RunMetadata(
            run_id=run.id,
            provider=run.provider or "gemini",
            model=run.model_name or "gemini-2.5-flash",
            prompt_version="2.0.0",
            pipeline_version="v2",
        )

        extraction_result = UniversalExtractionResult(
            document_id=document.id,
            classification=classification,
            schema_info={
                "schema_id": schema_obj.id,
                "name": schema_obj.name,
                "version": schema_obj.version,
                "origin": schema_obj.origin,
                "sections": schema_obj.schema_definition.get("sections", []),
            },
            fields=fields,
            tables=tables,
            insights=insights,
            validation={
                "status": "fail" if dsl_errors else "pass",
                "rules": dsl_outcomes,
                "errors": dsl_errors,
            },
            review={"required": doc_status == "NEEDS_REVIEW", "reasons": review_reasons},
            run=run_metadata,
        )

        run.result = extraction_result.model_dump()
        run.status = doc_status
        run.stage = "COMPLETED"
        metrics["total_seconds"] = round(time.time() - start_time, 3)
        metrics["doc_confidence"] = doc_conf
        metrics["fields_count"] = len(fields)
        metrics["ungrounded_count"] = ungrounded_count
        metrics["insights_count"] = len(insights)
        run.metrics = metrics
        run.completed_at = datetime.now(timezone.utc)

        document.status = doc_status
        db.commit()

        logger.info(
            f"[Run {run_id}] Execution complete: {len(fields)} fields ({doc_status}), "
            f"confidence={doc_conf}, {len(insights)} insights in {metrics['total_seconds']}s"
        )

    except Exception as exc:
        logger.exception(f"[Run {run_id}] Pipeline execution failed: {exc}")
        db.rollback()
        run = db.query(ExtractionRun).filter(ExtractionRun.id == run_id).first()
        document = db.query(Document).filter(Document.id == document_id).first()
        if run:
            run.status = "FAILED"
            run.error_message = str(exc)
        if document:
            document.status = "FAILED"
        db.commit()
    finally:
        db.close()
