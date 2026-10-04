from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Integer, String, Text

from app.database.connection import Base


class SchemaAlias(Base):
    """
    SQLAlchemy ORM model for mapping discovered or alternate field names
    to stable canonical keys (e.g. 'candidate_name' / 'applicant' -> 'person.full_name').
    """
    __tablename__ = "schema_aliases"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    canonical_key = Column(String(100), nullable=False, index=True)
    alias = Column(String(100), nullable=False, index=True)
    data_type = Column(String(50), default="string", nullable=False)
    family = Column(String(100), nullable=True, index=True)
    description = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<SchemaAlias alias='{self.alias}' -> canonical='{self.canonical_key}'>"
