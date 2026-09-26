import logging
from pathlib import Path
from typing import Tuple
from fastapi import HTTPException, UploadFile, status

from app.core.security import sanitize_filename, sanitize_log_text
from app.utils.file_utils import (
    MAX_FILE_SIZE,
    generate_safe_filename,
    get_upload_dir,
    is_allowed_file,
)

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024  # 1 MB chunk size for streaming file writes


class UploadService:
    """Handles file validation, safe filesystem storage, streaming writes,

    size enforcement, and filesystem cleanup.
    """

    @staticmethod
    def validate_file_metadata(file: UploadFile) -> None:
        """Validates that the file has a filename and an allowed type."""
        if not file.filename or not file.filename.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename cannot be empty.",
            )

        # Check for null-byte injection
        if "\x00" in file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename contains invalid characters.",
            )

        clean_name = sanitize_filename(file.filename)
        if not is_allowed_file(clean_name, file.content_type):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Unsupported file type. Allowed types: "
                    "PDF, PNG, JPG, JPEG, CSV, XLSX."
                ),
            )

    @classmethod
    async def save_uploaded_file(
        cls, file: UploadFile
    ) -> Tuple[str, Path, int]:
        """Saves an uploaded file to uploads directory using chunked streaming.

        Enforces maximum size limit and rejects empty files.

        Returns:
            Tuple[str, Path, int]: (safe_filename, full_file_path, size_bytes)
        """
        cls.validate_file_metadata(file)

        upload_dir = get_upload_dir()
        safe_filename = generate_safe_filename(file.filename)
        destination_path = upload_dir / safe_filename

        total_bytes_written = 0

        try:
            with open(destination_path, "wb") as destination_file:
                while True:
                    chunk = await file.read(CHUNK_SIZE)
                    if not chunk:
                        break

                    total_bytes_written += len(chunk)

                    # Enforce maximum size limit while streaming
                    if total_bytes_written > MAX_FILE_SIZE:
                        cls.cleanup_file(destination_path)
                        max_mb = MAX_FILE_SIZE // (1024 * 1024)
                        raise HTTPException(
                            status_code=(
                                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
                            ),
                            detail=(
                                f"File size exceeds maximum allowed limit "
                                f"of {max_mb} MB."
                            ),
                        )

                    destination_file.write(chunk)

            # Reject empty files
            if total_bytes_written == 0:
                cls.cleanup_file(destination_path)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uploaded file is empty.",
                )

            return safe_filename, destination_path, total_bytes_written

        except HTTPException:
            # Re-raise explicit HTTP exceptions
            raise
        except Exception as exc:
            cls.cleanup_file(destination_path)
            clean_err = sanitize_log_text(str(exc))
            logger.error(
                f"Filesystem storage error while saving "
                f"{sanitize_filename(file.filename)}: {clean_err}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An error occurred while saving the uploaded file.",
            )
        finally:
            await file.close()

    @staticmethod
    def cleanup_file(file_path: Path | str) -> None:
        """Safely removes a file from disk if it exists."""
        try:
            path = Path(file_path)
            if path.exists() and path.is_file():
                path.unlink()
                logger.info(f"Cleaned up file: {path.name}")
        except Exception as exc:
            logger.warning(
                f"Failed to remove file during cleanup: {file_path}. "
                f"Error: {exc}"
            )


upload_service = UploadService()
