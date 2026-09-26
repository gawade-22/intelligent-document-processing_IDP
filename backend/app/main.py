from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import ai, documents
from app.core.config import settings
from app.core.security import sanitize_log_text
from app.database.connection import Base, check_db_connection, engine
import app.models as _models  # noqa: F401 # Ensures ORM models register

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Ensure database tables exist on startup
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Intelligent Document Processing (IDP) API",
    description=(
        "Backend API foundation for the Intelligent Document "
        "Processing system."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# 1. CORS Configuration for frontend clients (React Dashboard / HITL)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 2. Centralized Unhandled Exception Handler
# Guarantees consistent JSON error payloads and prevents traceback leakage
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    safe_msg = sanitize_log_text(str(exc))
    logger.error(
        f"Unhandled server error on {request.method} {request.url.path}: "
        f"{safe_msg}",
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": (
                "An unexpected server error occurred. Please try again or "
                "contact system administration."
            )
        },
    )


# 3. Register API routers
app.include_router(
    documents.router,
    prefix="/api/documents",
    tags=["Documents"],
)
app.include_router(
    ai.router,
    prefix="/api/ai",
    tags=["AI"],
)


@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint to verify API server status."""
    return {"status": "ok"}


@app.get("/api/health/database", tags=["Health"])
def database_health_check():
    """Tests the PostgreSQL database connection and returns connectivity."""
    is_connected = check_db_connection()
    if is_connected:
        return {
            "status": "ok",
            "database": "connected",
        }
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "error",
            "database": "disconnected",
        },
    )
