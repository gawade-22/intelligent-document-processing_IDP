from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.database.connection import Base


class DocumentSchema(Base):
    """
    SQLAlchemy ORM model representing a versioned schema in the Dynamic IDP Schema Registry.
    Schemas define sections, target fields, table columns, DSL validation rules,
    and insight definitions.
    """
    __tablename__ = "document_schemas"

    id = Column(String(100), primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    family = Column(String(100), nullable=False, default="general", index=True)
    version = Column(Integer, default=1, nullable=False)
    fingerprint = Column(String(255), nullable=True, index=True)
    origin = Column(String(50), default="discovered", nullable=False)  # template | discovered | user
    is_active = Column(Boolean, default=True, nullable=False)
    description = Column(Text, nullable=True)

    # schema_definition structure:
    # {
    #   "sections": [{"name": "Header", "description": ""}],
    #   "fields": [{"key": "invoice_number", "label": "Invoice Number", "data_type": "string", "section": "Header"}],
    #   "tables": [{"key": "line_items", "title": "Items", "columns": ["description", "quantity", "unit_price", "total"]}],
    #   "validation_rules": [{"rule": "sum_equals", "target": "total", "terms": ["line_items.total", "tax"]}],
    #   "insight_definitions": [{"id": "total_spend", "kind": "metric", "agg": "sum", "table": "line_items", "column": "total"}]
    # }
    schema_definition = Column(JSON, nullable=False, default=dict)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    extraction_runs = relationship("ExtractionRun", back_populates="document_schema")

    def __repr__(self) -> str:
        return f"<DocumentSchema id='{self.id}' name='{self.name}' version={self.version} origin='{self.origin}'>"
