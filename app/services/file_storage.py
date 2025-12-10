from pathlib import Path
from typing import Final
from uuid import uuid4

from fastapi import UploadFile


class InvoiceFileStorage:
    """Simple file storage helper for invoice uploads."""

    def __init__(self, base_directory: Path) -> None:
        self._base_directory: Final[Path] = base_directory
        self._base_directory.mkdir(parents=True, exist_ok=True)

    async def save(self, file: UploadFile) -> str:
        """Persist the uploaded file and return its relative path."""

        suffix = Path(file.filename or "").suffix
        target = self._base_directory / f"{uuid4()}{suffix}"
        content = await file.read()
        target.write_bytes(content)
        await file.close()
        # Return a path string that can be stored in the database.
        return target.as_posix()
