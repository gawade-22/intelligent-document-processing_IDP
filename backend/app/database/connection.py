import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings
from app.core.security import sanitize_log_text

logger = logging.getLogger(__name__)

# 1. Create the SQLAlchemy Engine
# pool_pre_ping=True tests connection health before using a connection
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
)

# 2. Create SessionLocal factory
# autocommit=False ensures transactions are controlled explicitly
# autoflush=False prevents automatic flushing of pending changes before queries
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# 3. Create Base class for ORM models to inherit from
Base = declarative_base()


# 4. Dependency to yield a database session per API request
def get_db():
    """FastAPI dependency that creates a new database session for each request.

    Guarantees rollback on unhandled exceptions and ensures the session
    is closed cleanly after request termination.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# 5. Database connectivity test function
def check_db_connection() -> bool:
    """Tests database connectivity by executing a lightweight test query.

    Returns True if the connection succeeds, False otherwise.
    Logs sanitized connection errors without leaking credentials.
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        safe_msg = sanitize_log_text(str(exc))
        logger.error(f"Database connection check failed: {safe_msg}")
        return False
