"""Share exports and pick restore files on desktop and mobile."""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

import flet as ft

from lib.infrastructure.services.flet_services import attach_page_service

logger = logging.getLogger("finanse.presentation.file_transfer")

SQLITE_MAGIC = b"SQLite format 3"
_UNSAFE_NAME = re.compile(r"[^\w.\-]+", re.UNICODE)


def file_picker(page: ft.Page) -> ft.FilePicker:
    for item in list(getattr(page, "services", None) or []):
        if isinstance(item, ft.FilePicker):
            return item
    picker = ft.FilePicker()
    attach_page_service(page, picker, native_extension=False)
    return picker


def share_service(page: ft.Page) -> ft.Share:
    for item in list(getattr(page, "services", None) or []):
        if isinstance(item, ft.Share):
            return item
    share = ft.Share()
    attach_page_service(page, share, native_extension=False)
    return share


def _mobile(page: ft.Page) -> bool:
    try:
        from lib.infrastructure.services.biometric import is_mobile_platform

        if is_mobile_platform(page):
            return True
        # Web preview of mobile still uses Share for sandbox paths.
        return bool(page.web)
    except Exception:  # noqa: BLE001
        return False


def safe_filename(name: str, *, default: str = "restore.bin") -> str:
    """Keep only the basename so a picker path cannot escape the backup dir."""
    base = Path(str(name).replace("\\", "/")).name.strip()
    cleaned = _UNSAFE_NAME.sub("_", base).strip("._")
    return cleaned or default


def classify_restore_payload(name: str, payload: bytes) -> str:
    """Return ``db``, ``fwbackup``, ``json``, ``enc``, or ``unknown``."""
    if payload.startswith(b"FWBK"):
        return "fwbackup"
    if payload.startswith(SQLITE_MAGIC):
        return "db"
    if payload.startswith(b"FWEX"):
        return "enc"
    lowered = (name or "").lower()
    stripped = payload.lstrip()
    if stripped.startswith(b"{") or stripped.startswith(b"[") or lowered.endswith(".json"):
        return "json"
    if lowered.endswith(".fwbackup"):
        return "fwbackup"
    if lowered.endswith((".fwexport", ".enc")):
        return "enc"
    if lowered.endswith((".db", ".sqlite", ".sqlite3")):
        return "db"
    return "unknown"


def is_restricted_save_path(path: Path | str | None) -> bool:
    """True when Python cannot write here (iCloud Drive, other app sandboxes)."""
    if path is None:
        return False
    text = str(path).replace("\\", "/")
    return any(
        marker in text
        for marker in (
            "com~apple~CloudDocs",
            "Mobile Documents",
            "/Android/data/",
        )
    )


def default_save_directory() -> Path:
    """Prefer Documents / Desktop so the save dialog opens where users look."""
    home = Path.home()
    if is_restricted_save_path(home):
        return home
    for name in ("Documents", "Документы", "Desktop", "Рабочий стол"):
        candidate = home / name
        if candidate.is_dir() and not is_restricted_save_path(candidate):
            return candidate
    return home


def materialize_saved_file(source: Path, dest: str | Path | None) -> Path | None:
    """Copy ``source`` to the path the user picked. ``None`` means cancelled."""
    if dest is None:
        return None
    raw = str(dest).strip()
    if not raw:
        return None
    source = Path(source)
    target = Path(raw)
    if target.is_dir() or raw.endswith(("/", "\\")):
        target = target / source.name
    if is_restricted_save_path(target) or is_restricted_save_path(target.parent):
        raise PermissionError(f"restricted path: {target}")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if (not target.exists()) or target.resolve() != source.resolve():
            shutil.copy2(source, target)
        if (not target.is_file()) or target.stat().st_size == 0:
            target.write_bytes(source.read_bytes())
    except OSError:
        logger.exception("Failed to write saved file to %s", target)
        raise
    return target


def _shareable_copy(source: Path) -> Path:
    """tmp is readable by the iOS/Android share sheet; Application Support is not."""
    import tempfile

    dest = Path(tempfile.gettempdir()) / source.name
    if dest.resolve() != source.resolve():
        shutil.copy2(source, dest)
    return dest


async def _share_sandbox_file(
    page: ft.Page,
    file_path: Path,
    *,
    title: str,
    extra: list[Path] | None = None,
) -> str | None:
    """Present the system share sheet. Returns the sandbox path, or None if dismissed."""
    name = file_path.name
    shared = _shareable_copy(file_path)
    files = [ft.ShareFile(path=str(shared), name=name)]
    for item in extra or []:
        if not item.is_file() or item.resolve() == file_path.resolve():
            continue
        copied = _shareable_copy(item)
        files.append(ft.ShareFile(path=str(copied), name=item.name))
    try:
        result = await share_service(page).share_files(
            files,
            title=title,
            text=name,
        )
    except Exception:  # noqa: BLE001
        logger.debug("share_files failed", exc_info=True)
        try:
            await share_service(page).share_text(str(file_path), title=title)
            return str(file_path)
        except Exception:  # noqa: BLE001
            logger.exception("Could not present share sheet for %s", file_path)
            return None
    status = str(getattr(getattr(result, "status", None), "value", result) or "").lower()
    if "dismiss" in status:
        return None
    return str(file_path)


def _tk_save_as(file_name: str) -> str | None:
    """Native Windows/macOS save dialog when Flet does not return a path."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:  # noqa: BLE001
        return None
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        chosen = filedialog.asksaveasfilename(
            title="FinWise",
            initialdir=str(default_save_directory()),
            initialfile=file_name,
        )
    finally:
        root.destroy()
    return chosen or None


async def offer_saved_file(
    page: ft.Page,
    path: Path | str,
    *,
    title: str = "FinWise",
    extra: list[Path | str] | None = None,
) -> str | None:
    """Let the user keep a generated file. Returns the written path, or None if cancelled."""
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(str(file_path))
    extras = [Path(item) for item in (extra or []) if Path(item).is_file()]
    # Phones cannot write to iCloud Drive / system Downloads. Share the sandbox file.
    if _mobile(page):
        return await _share_sandbox_file(page, file_path, title=title, extra=extras)

    data = file_path.read_bytes()
    name = file_path.name
    picker = file_picker(page)
    dest: str | None = None
    picker_failed = False
    try:
        dest = await picker.save_file(
            dialog_title=title,
            file_name=name,
            src_bytes=data,
            initial_directory=str(default_save_directory()),
        )
    except Exception:  # noqa: BLE001
        logger.exception("FilePicker.save_file failed")
        picker_failed = True
        dest = None

    if dest:
        if is_restricted_save_path(dest):
            logger.warning("Save picker returned a restricted path: %s", dest)
            return None
        try:
            written = materialize_saved_file(file_path, dest)
        except OSError:
            logger.exception("Could not copy export to %s", dest)
            raise
        return str(written) if written else None

    if not picker_failed:
        return None
    fallback = _tk_save_as(name)
    if not fallback or is_restricted_save_path(fallback):
        return None
    written = materialize_saved_file(file_path, fallback)
    return str(written) if written else None


async def pick_restore_bytes(
    page: ft.Page,
    *,
    title: str,
    extensions: list[str],
    images: bool = False,
) -> tuple[str, bytes] | None:
    """Pick a backup/export file and return ``(name, bytes)``."""
    picker = file_picker(page)
    kwargs: dict = {
        "dialog_title": title,
        "allow_multiple": False,
        "with_data": True,
    }
    if images:
        image_type = getattr(ft.FilePickerFileType, "IMAGE", None)
        if image_type is not None:
            kwargs["file_type"] = image_type
        elif extensions:
            kwargs["allowed_extensions"] = extensions
    elif extensions:
        kwargs["allowed_extensions"] = extensions
    try:
        files = await picker.pick_files(**kwargs)
    except Exception:  # noqa: BLE001
        logger.debug("pick_files with filter failed, retrying without filter", exc_info=True)
        files = await picker.pick_files(
            dialog_title=title,
            allow_multiple=False,
            with_data=True,
        )
    if not files:
        return None
    chosen = files[0]
    payload = chosen.bytes
    if payload is None and chosen.path:
        payload = Path(chosen.path).read_bytes()
    if payload is None:
        return None
    return safe_filename(chosen.name or "restore.bin"), payload
