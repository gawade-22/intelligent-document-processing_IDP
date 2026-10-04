from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.database.connection import Base


class ExtractionRun(Base):
    """
    SQLAlchemy ORM model representing an immutable processing execution run
    for a document against a schema version.
    """
    __tablename__ = "extraction_runs"

    id = Column(String(100), primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    schema_id = Column(String(100), ForeignKey("document_schemas.id", ondelete="SET NULL"), nullable=True, index=True)
    pipeline_version = Column(String(50), default="v2", nullable=False)
    provider = Column(String(50), nullable=True)
    model_name = Column(String(100), nullable=True)
    status = Column(String(50), default="QUEUED", nullable=False, index=True)  # QUEUED, PROCESSING, VERIFIED, NEEDS_REVIEW, FAILED
    stage = Column(String(50), default="UPLOADED", nullable=False, index=True)  # INGESTION, CLASSIFYING, SCHEMA_DISCOVERY, EXTRACTING, GROUNDING, VALIDATING, GENERATING_INSIGHTS, COMPLETED
    error_message = Column(Text, nullable=True)

    # UniversalDocument: physical layout, blocks, reading order, tables, sheets
    universal_document = Column(JSON, nullable=True)

    # Final dynamic extraction result (matches frontend dynamic contract)
    result = Column(JSON, nullable=True)

    # Observability & latency/cost metrics
    metrics = Column(JSON, nullable=True, default=dict)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    document = relationship("Document", back_populates="extraction_runs")
    document_schema = relationship("DocumentSchema", back_populates="extraction_runs")
    fields = relationship("ExtractedField", back_populates="run", cascade="all, delete-orphan")
    review_corrections = relationship("ReviewCorrection", back_populates="run", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ExtractionRun id='{self.id}' doc_id={self.document_id} status='{self.status}' stage='{self.stage}'>"
