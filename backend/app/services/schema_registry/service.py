"""
Schema Registry Service.
Coordinates fingerprinting, schema lookup, seeding templates,
canonical key mapping, and dynamic schema discovery.
"""

import hashlib
import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.document_schema import DocumentSchema
from app.models.schema_alias import SchemaAlias
from app.schemas.universal import ClassificationResult, SchemaDefinition, UniversalDocument
from app.services.ai.base import AIExtractionProvider
from app.services.schema_registry.discovery import schema_discovery
from app.services.schema_registry.seed_data import SEED_CANONICAL_ALIASES, SEED_SCHEMAS

logger = logging.getLogger(__name__)


class SchemaRegistryService:
    """Manages the versioned registry of document schemas and canonical key aliases."""

    def seed_registry(self, db: Session) -> None:
        """
        Populates initial templates and canonical aliases into PostgreSQL if they do not exist.
        Ensures zero hardcoding in application code.
        """
        # 1. Seed canonical aliases
        existing_aliases = {a.alias: a for a in db.query(SchemaAlias).all()}
        for item in SEED_CANONICAL_ALIASES:
            if item["alias"] not in existing_aliases:
                db.add(SchemaAlias(**item))

        # 2. Seed template schemas
        existing_schemas = {s.id: s for s in db.query(DocumentSchema).all()}
        for s_data in SEED_SCHEMAS:
            s_id = s_data["id"]
            if s_id not in existing_schemas:
                db.add(
                    DocumentSchema(
                        id=s_id,
                        name=s_data["name"],
                        family=s_data["family"],
                        version=s_data.get("version", 1),
                        origin="template",
                        description=s_data.get("description"),
                        schema_definition=s_data["schema_definition"],
                        is_active=True,
                    )
                )

        db.commit()
        logger.info("Schema Registry seed check completed successfully.")

    def compute_fingerprint(
        self,
        udoc: UniversalDocument,
        classification: ClassificationResult,
    ) -> str:
        """
        Computes a stable fingerprint hash based on structural characteristics:
        family, document type, top headings, and table column names.
        """
        headings = sorted(b.text.lower().strip() for b in udoc.blocks if b.type == "heading")[:4]
        table_cols = []
        for t in udoc.tables[:2]:
            table_cols.extend(sorted(c.lower().strip() for c in t.headers[:6]))

        sheet_cols = []
        for s in udoc.sheets[:2]:
            sheet_cols.extend(sorted(c.lower().strip() for c in s.columns[:6]))

        sig_tokens = [
            classification.family.lower(),
            classification.primary_type.lower(),
            ",".join(headings),
            ",".join(table_cols),
            ",".join(sheet_cols),
        ]
        sig_str = "|".join(sig_tokens)
        return hashlib.sha256(sig_str.encode("utf-8")).hexdigest()[:16]

    def resolve_canonical_key(
        self,
        field_key: str,
        family: str,
        db: Session,
    ) -> str:
        """Maps a field key to a canonical key using the schema_aliases table."""
        normalized_key = field_key.lower().strip()
        alias_record = (
            db.query(SchemaAlias)
            .filter(SchemaAlias.alias == normalized_key)
            .first()
        )
        if alias_record:
            return alias_record.canonical_key

        return normalized_key

    def resolve_schema(
        self,
        udoc: UniversalDocument,
        classification: ClassificationResult,
        db: Session,
        ai_provider: Optional[AIExtractionProvider] = None,
    ) -> DocumentSchema:
        """
        Resolves or discovers a schema for the document:
        1. Checks for fingerprint match in registry.
        2. Checks for template schema matching primary_type or family.
        3. If not found, runs dynamic LLM schema discovery and registers the new schema.
        """
        # Ensure registry is initialized
        self.seed_registry(db)

        fingerprint = self.compute_fingerprint(udoc, classification)

        # 1. Check exact fingerprint match (must have fields)
        fp_match = (
            db.query(DocumentSchema)
            .filter(DocumentSchema.fingerprint == fingerprint, DocumentSchema.is_active == True)
            .first()
        )
        if fp_match and fp_match.schema_definition and fp_match.schema_definition.get("fields"):
            logger.info(f"Reusing schema by fingerprint match: '{fp_match.name}' (id={fp_match.id})")
            return fp_match

        # 2. Check name/type match in active templates
        type_norm = classification.primary_type.lower().strip()
        all_schemas = db.query(DocumentSchema).filter(DocumentSchema.is_active == True).all()

        for s in all_schemas:
            s_name_norm = s.name.lower().strip()
            if s_name_norm == type_norm or (type_norm in s_name_norm) or (s_name_norm in type_norm):
                logger.info(f"Reusing schema by type match: '{s.name}' (id={s.id})")
                return s

        # 3. Not found -> Discover dynamically via LLM
        logger.info(
            f"No existing schema match for '{classification.primary_type}'. "
            "Triggering Dynamic LLM Schema Discovery..."
        )
        discovered_def: SchemaDefinition = schema_discovery.discover_schema(
            udoc=udoc,
            classification=classification,
            ai_provider=ai_provider,
        )

        # Fallback fields if discovery produced empty fields
        if not discovered_def.fields:
            from app.schemas.universal import SchemaFieldDefinition
            discovered_def.fields = [
                SchemaFieldDefinition(key="document_title", label="Document Title", data_type="string", section="Overview"),
                SchemaFieldDefinition(key="document_date", label="Document Date", data_type="date", section="Overview"),
                SchemaFieldDefinition(key="total_amount", label="Total Amount", data_type="money", section="Overview"),
            ]

        # Canonicalize discovered fields
        for f in discovered_def.fields:
            if not f.canonical_key:
                f.canonical_key = self.resolve_canonical_key(f.key, classification.family, db)

        schema_id = f"sch_disc_{uuid.uuid4().hex[:10]}"
        new_schema = DocumentSchema(
            id=schema_id,
            name=classification.primary_type,
            family=classification.family,
            version=1,
            fingerprint=fingerprint,
            origin="discovered",
            description=f"Dynamically discovered schema for '{classification.primary_type}'",
            schema_definition=discovered_def.model_dump(),
            is_active=True,
        )
        db.add(new_schema)
        db.commit()
        db.refresh(new_schema)

        logger.info(
            f"Registered newly discovered schema: '{new_schema.name}' (id={new_schema.id}) "
            f"with {len(discovered_def.fields)} fields and {len(discovered_def.tables)} tables"
        )
        return new_schema


# Singleton instance
schema_registry = SchemaRegistryService()
