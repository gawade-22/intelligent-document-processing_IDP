"""Security utility module for the IDP backend.

Provides defensive path traversal checks, secret masking, log sanitization,
and safe filename normalization without introducing unnecessary external
dependencies.
"""

from pathlib import Path
import re
from typing import Optional

# Regex pattern for database URLs containing user:password@host
_DB_URL_PATTERN = re.compile(
    r":\/\/(?P<user>[^:]+):(?P<password>[^@]+)@(?P<host>[^\/:]+)",
    re.IGNORECASE,
)

# Regex pattern for Authorization Bearer tokens
_BEARER_PATTERN = re.compile(
    r"(Bearer\s+)[a-zA-Z0-9_\-\.]{8,}",
    re.IGNORECASE,
)

# Regex pattern for common API keys (OpenAI sk-..., Google AIza...)
_API_KEY_PATTERN = re.compile(
    r"\b(sk-[a-zA-Z0-9_\-]{16,}|AIza[0-9A-Za-z-_]{35})\b",
    re.IGNORECASE,
)


def mask_secret(secret: Optional[str], visible_chars: int = 4) -> str:
    """Masks a secret string preserving only a few edge characters."""
    if not secret:
        return "[NOT_CONFIGURED]"
    stripped = secret.strip()
    length = len(stripped)
    if length <= (visible_chars * 2):
        return "***"
    prefix = stripped[:visible_chars]
    suffix = stripped[-visible_chars:]
    return f"{prefix}...{suffix}"


def sanitize_log_text(text: str) -> str:
    """Sanitizes sensitive information from strings before logging.

    Redacts:
    - Passwords inside database connection URLs
    - Bearer tokens
    - OpenAI/Google API keys
    """
    if not text:
        return ""

    sanitized = str(text)

    # Redact database connection passwords
    sanitized = _DB_URL_PATTERN.sub(
        r"://\g<user>:***@\g<host>",
        sanitized,
    )

    # Redact Bearer tokens
    sanitized = _BEARER_PATTERN.sub(
        r"\g<1>[REDACTED_TOKEN]",
        sanitized,
    )

    # Redact API keys
    sanitized = _API_KEY_PATTERN.sub(
        r"[REDACTED_API_KEY]",
        sanitized,
    )

    return sanitized


def sanitize_filename(filename: Optional[str]) -> str:
    """Strips path traversal sequences and null bytes from a filename."""
    if not filename or not filename.strip():
        return "unnamed_document"

    clean = filename.replace("\x00", "").strip()
    # Normalize separators
    clean = clean.replace("\\", "/")
    # Extract only the final basename component
    clean = clean.split("/")[-1]
    # Remove leading dots to prevent hidden files
    clean = clean.lstrip(".")

    return clean if clean else "unnamed_document"


def is_path_traversal_safe(
    target_path: Path,
    allowed_roots: Optional[object] = None,
) -> bool:
    """Checks whether target_path resides strictly within allowed roots."""
    roots: list[Path]
    if allowed_roots is None:
        import tempfile
        from app.utils.file_utils import get_upload_dir
        roots = [
            get_upload_dir(),
            Path(tempfile.gettempdir()),
        ]
    elif isinstance(allowed_roots, Path):
        roots = [allowed_roots]
    elif isinstance(allowed_roots, (list, tuple, set)):
        roots = list(allowed_roots)
    else:
        roots = [Path(str(allowed_roots))]

    try:
        resolved_target = target_path.resolve()
        for root in roots:
            resolved_root = root.resolve()
            if (
                resolved_target == resolved_root
                or resolved_target.is_relative_to(resolved_root)
            ):
                return True
        return False
    except (ValueError, RuntimeError, AttributeError):
        target_str = str(target_path.resolve())
        for root in roots:
            root_str = str(root.resolve())
            if target_str.startswith(root_str):
                return True
        return False
