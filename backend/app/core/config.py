import logging
import os
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Define the base directory of the backend project
# backend/app/core/config.py -> core -> app -> backend
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"

# Load environment variables from backend/.env
load_dotenv(dotenv_path=ENV_PATH)


def _parse_int_env(key: str, default: int) -> int:
    val = os.getenv(key)
    if val is None or not str(val).strip():
        return default
    try:
        return int(str(val).strip())
    except ValueError:
        logger.warning(
            f"Invalid integer for env var {key}='{val}', "
            f"using default {default}"
        )
        return default


def _parse_float_env(key: str, default: float) -> float:
    val = os.getenv(key)
    if val is None or not str(val).strip():
        return default
    try:
        return float(str(val).strip())
    except ValueError:
        logger.warning(
            f"Invalid float for env var {key}='{val}', using default {default}"
        )
        return default


def _parse_list_env(key: str, default: List[str]) -> List[str]:
    val = os.getenv(key)
    if val is None or not str(val).strip():
        return default
    parsed = [x.strip() for x in str(val).split(",") if x.strip()]
    return parsed if parsed else default


class Settings:
    PROJECT_NAME: str = "Intelligent Document Processing (IDP) API"
    PROJECT_VERSION: str = "1.0.0"

    # Database connection URL loaded from .env
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # CORS Configuration
    CORS_ORIGINS: List[str] = _parse_list_env(
        "CORS_ORIGINS",
        [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ],
    )

    # Maximum file upload size in bytes (default: 10 MB = 10,485,760 bytes)
    MAX_FILE_SIZE_BYTES: int = _parse_int_env(
        "MAX_FILE_SIZE_BYTES",
        10 * 1024 * 1024,
    )

    # OCR Engine settings (optional paths for OS binaries on Windows)
    _raw_tesseract_cmd = os.getenv("TESSERACT_CMD")
    TESSERACT_CMD: Optional[str] = _raw_tesseract_cmd.strip() if _raw_tesseract_cmd and _raw_tesseract_cmd.strip() else None
    OCR_LANGUAGE: str = os.getenv("OCR_LANGUAGE", "eng").strip() or "eng"
    OCR_PSM: int = _parse_int_env("OCR_PSM", _parse_int_env("OCR_PSM_MODE", 6))
    OCR_PSM_MODE: int = OCR_PSM
    POPPLER_PATH: Optional[str] = os.getenv("POPPLER_PATH", None)
    OCR_PDF_DPI: int = _parse_int_env("OCR_PDF_DPI", 300)

    # AI / LLM Extraction Configuration (Optional - leave empty for rule-based)
    AI_PROVIDER: Optional[str] = os.getenv("AI_PROVIDER", None)
    AI_MODEL: Optional[str] = os.getenv("AI_MODEL", None)
    AI_API_KEY: Optional[str] = os.getenv("AI_API_KEY") or os.getenv("GEMINI_API_KEY", None)
    GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY", None)
    AI_BASE_URL: Optional[str] = os.getenv("AI_BASE_URL", None)
    AI_TIMEOUT: int = _parse_int_env("AI_TIMEOUT", 30)
    AI_MAX_INPUT_CHARACTERS: int = _parse_int_env(
        "AI_MAX_INPUT_CHARACTERS", 12000
    )

    # Confidence evaluation threshold (default: 0.85 / 85%)
    CONFIDENCE_THRESHOLD: float = _parse_float_env(
        "CONFIDENCE_THRESHOLD", 0.85
    )

    def __init__(self) -> None:
        self.DATABASE_URL: str = os.getenv("DATABASE_URL", "")
        self.CORS_ORIGINS: List[str] = _parse_list_env(
            "CORS_ORIGINS",
            [
                "http://localhost:3000",
                "http://localhost:5173",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5173",
            ],
        )
        self.MAX_FILE_SIZE_BYTES: int = _parse_int_env("MAX_FILE_SIZE_BYTES", 10 * 1024 * 1024)
        raw_tess = os.getenv("TESSERACT_CMD")
        self.TESSERACT_CMD: Optional[str] = raw_tess.strip() if raw_tess and raw_tess.strip() else None
        self.OCR_LANGUAGE: str = os.getenv("OCR_LANGUAGE", "eng").strip() or "eng"
        self.OCR_PSM: int = _parse_int_env("OCR_PSM", _parse_int_env("OCR_PSM_MODE", 6))
        self.OCR_PSM_MODE: int = self.OCR_PSM
        self.POPPLER_PATH: Optional[str] = os.getenv("POPPLER_PATH", None)
        self.OCR_PDF_DPI: int = _parse_int_env("OCR_PDF_DPI", 300)
        self.AI_PROVIDER: Optional[str] = os.getenv("AI_PROVIDER", None)
        self.AI_MODEL: Optional[str] = os.getenv("AI_MODEL", None)
        self.AI_API_KEY: Optional[str] = os.getenv("AI_API_KEY") or os.getenv("GEMINI_API_KEY", None)
        self.GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY", None)
        self.AI_BASE_URL: Optional[str] = os.getenv("AI_BASE_URL", None)
        self.AI_TIMEOUT: int = _parse_int_env("AI_TIMEOUT", 30)
        self.AI_MAX_INPUT_CHARACTERS: int = _parse_int_env("AI_MAX_INPUT_CHARACTERS", 12000)
        self.CONFIDENCE_THRESHOLD: float = _parse_float_env("CONFIDENCE_THRESHOLD", 0.85)


# Instantiate settings so other modules can import `settings` directly
settings = Settings()
