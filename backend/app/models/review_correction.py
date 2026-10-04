from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database.connection import Base


class ReviewCorrection(Base):
    """
    SQLAlchemy ORM model for recording human-in-the-loop corrections
    to extracted fields. Feeds directly into evaluation and golden sets.
    """
    __tablename__ = "review_corrections"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    field_id = Column(Integer, ForeignKey("extracted_fields.id", ondelete="SET NULL"), nullable=True, index=True)
    run_id = Column(String(100), ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    canonical_key = Column(String(100), nullable=False, index=True)
    original_value = Column(Text, nullable=True)
    corrected_value = Column(Text, nullable=False)
    reviewer_id = Column(String(100), default="human", nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    run = relationship("ExtractionRun", back_populates="review_corrections")
    field = relationship("ExtractedField", back_populates="review_corrections")

    def __repr__(self) -> str:
        return f"<ReviewCorrection key='{self.canonical_key}' '{self.original_value}' -> '{self.corrected_value}'>"
