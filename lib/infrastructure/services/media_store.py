"""Store and resolve transaction attachment files under the app media dir."""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from uuid import uuid4

from lib.core.config import AppConfig, get_default_config

logger = logging.getLogger("finanse.infrastructure.services.media_store")

_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"}


def _ext_from_name(name: str, payload: bytes) -> str:
    suffix = Path(name or "").suffix.lower()
    if suffix in _IMAGE_EXT:
        return suffix
    guessed, _ = mimetypes.guess_type(name or "")
    if guessed == "image/png":
        return ".png"
    if guessed == "image/webp":
        return ".webp"
    if guessed == "image/gif":
        return ".gif"
    if payload[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if payload[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    return ".jpg"


class MediaStore:
    """Persist receipt images as files; DB keeps relative paths only."""

    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or get_default_config()
        self._config.ensure_directories()

    def absolute(self, relative: str) -> Path:
        rel = (relative or "").replace("\\", "/").lstrip("/")
        return (self._config.media_dir / rel).resolve()

    def save_receipt(
        self,
        *,
        transaction_id: str,
        filename: str,
        payload: bytes,
    ) -> str:
        """Write bytes and return a relative path under ``media/``."""
        if not payload:
            raise ValueError("Empty attachment")
        if len(payload) > 12 * 1024 * 1024:
            raise ValueError("Attachment is too large (max 12 MB)")
        ext = _ext_from_name(filename, payload)
        folder = self._config.receipts_dir / transaction_id
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{uuid4().hex}{ext}"
        path = folder / name
        path.write_bytes(payload)
        relative = f"receipts/{transaction_id}/{name}"
        logger.debug("Saved receipt %s (%s bytes)", relative, len(payload))
        return relative

    def delete_paths(self, relatives: list[str]) -> None:
        for rel in relatives or []:
            try:
                path = self.absolute(rel)
                if path.is_file() and self._config.media_dir in path.parents:
                    path.unlink(missing_ok=True)
            except OSError:
                logger.exception("Failed to delete media %s", rel)

    def delete_transaction_dir(self, transaction_id: str) -> None:
        folder = self._config.receipts_dir / transaction_id
        if not folder.is_dir():
            return
        try:
            for child in folder.iterdir():
                if child.is_file():
                    child.unlink(missing_ok=True)
            folder.rmdir()
        except OSError:
            logger.exception("Failed to clean receipt dir for %s", transaction_id)
