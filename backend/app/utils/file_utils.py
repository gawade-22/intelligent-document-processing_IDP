from pathlib import Path
from typing import Optional, Set
import uuid

from app.core.config import settings
from app.core.security import sanitize_filename

# 1. Base and Upload Directory Calculation
# Resolves absolute path: file_utils.py -> utils -> app -> backend
BASE_DIR = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"

# 2. Upload Constants
MAX_FILE_SIZE = settings.MAX_FILE_SIZE_BYTES

ALLOWED_EXTENSIONS: Set[str] = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".csv",
    ".xlsx",
}

ALLOWED_MIME_TYPES = {
    ".pdf": {"application/pdf"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg", "image/pjpeg"},
    ".jpeg": {"image/jpeg", "image/pjpeg"},
    ".csv": {
        "text/csv",
        "application/csv",
        "text/plain",
        "application/vnd.ms-excel",
    },
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
        "application/octet-stream",
    },
}


def get_upload_dir() -> Path:
    """Returns the absolute path to the backend uploads directory."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR


def get_file_extension(filename: str) -> str:
    """Extracts the sanitized, lowercased file extension with leading dot."""
    clean_name = sanitize_filename(filename)
    return Path(clean_name).suffix.lower()


def generate_safe_filename(original_filename: str) -> str:
    """Generates a cryptographically random, collision-free UUID filename."""
    ext = get_file_extension(original_filename)
    unique_id = uuid.uuid4()
    return f"{unique_id}{ext}"


def is_allowed_file(filename: str, content_type: Optional[str] = None) -> bool:
    """Validates both filename extension and MIME content type."""
    ext = get_file_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        return False

    if content_type:
        expected_mimes = ALLOWED_MIME_TYPES.get(ext, set())
        if (
            expected_mimes
            and content_type not in expected_mimes
            and content_type != "application/octet-stream"
        ):
            return False

    return True
