from datetime import datetime, timezone
from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database.connection import Base


class DocumentRecord(Base):
    """
    SQLAlchemy ORM model representing structured data extracted from a document.
    """
    __tablename__ = "document_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    document_type = Column(String(100), nullable=True)
    extraction_status = Column(String(50), default="PENDING", nullable=False)
    raw_text = Column(Text, nullable=True)
    extracted_data = Column(JSON, nullable=True)
    confidence_score = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationship back to document
    document = relationship("Document", back_populates="records")

    def __repr__(self) -> str:
        return f"<DocumentRecord id={self.id} document_id={self.document_id} status='{self.extraction_status}'>"
