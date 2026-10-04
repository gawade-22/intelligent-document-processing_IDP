from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.database.connection import Base


class ExtractedField(Base):
    """
    SQLAlchemy ORM model representing individual extracted field occurrences
    per run, enabling indexed queries, analytics, and field-level review.
    """
    __tablename__ = "extracted_fields"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    run_id = Column(String(100), ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    canonical_key = Column(String(100), nullable=False, index=True)
    field_key = Column(String(100), nullable=False, index=True)
    label = Column(String(255), nullable=False)
    section = Column(String(100), nullable=True)
    data_type = Column(String(50), default="string", nullable=False)
    raw_value = Column(Text, nullable=True)
    normalized_value = Column(Text, nullable=True)
    confidence = Column(Float, default=0.0, nullable=False)
    status = Column(String(50), default="verified", nullable=False, index=True)  # verified | needs_review | edited
    grounded = Column(Boolean, default=True, nullable=False)

    # Evidence details: {"page": 1, "quote": "...", "bbox": [x0, y0, x1, y1], "grounded": true}
    evidence = Column(JSON, nullable=True)

    # Multi-pass extractions: [{"engine": "text-llm", "value": "..."}, {"engine": "vision-llm", "value": "..."}]
    passes = Column(JSON, nullable=True)

    # Validation outcome messages: ["Tolerance exceeded: 0.05 vs 0.01", ...]
    validation_messages = Column(JSON, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    run = relationship("ExtractionRun", back_populates="fields")
    review_corrections = relationship("ReviewCorrection", back_populates="field")

    def __repr__(self) -> str:
        return f"<ExtractedField key='{self.canonical_key}' value='{self.normalized_value}' conf={self.confidence}>"
