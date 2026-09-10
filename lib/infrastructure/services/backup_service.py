"""SQLite database backup and restore, plus shareable ``.fwbackup`` bundles."""

from __future__ import annotations

import io
import json
import logging
import shutil
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from lib.core.config import AppConfig, get_default_config
from lib.infrastructure.services.fwbackup import (
    MAGIC as FWBACKUP_MAGIC,
    decrypt_bundle,
    encrypt_bundle,
    is_fwbackup,
    needs_password as fwbackup_needs_password,
)
from lib.infrastructure.services.secret_box import (
    export_master_key_bytes,
    master_key_path,
    store_master_key,
)

logger = logging.getLogger("finanse.infrastructure.services.backup")

# Single rolling file updated at most once per local calendar day on every device.
DAILY_BACKUP_NAME = "finanse_daily.db"
DAILY_STAMP_NAME = "finanse_daily.day"
# Embedded in the backup copy only so a single shared .db can restore exchange keys
# when the companion ``.key`` sidecar is missing (typical on iOS share/Files).
SECRET_BOX_TABLE = "_finanse_secret_box"
SQLITE_MAGIC = b"SQLite format 3"
# Below this size a "SQLite" header is treated as a stub (unit tests use fake files).
_MIN_SQLITE_BACKUP_BYTES = 512


class BackupServiceError(Exception):
    """Raised when backup or restore fails."""


class BackupService:
    """Copy the SQLite DB file to / from the configured backup directory.

    User-facing share uses an encrypted ``.fwbackup`` zip (db + key + media).
    Daily / safety copies stay as ``.db`` plus ``.key`` sidecar and an embedded
    ``_finanse_secret_box`` table in the backup copy (never in the live DB).
    """

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        self._config = config or get_default_config()
        self._config.ensure_directories()

    @property
    def db_path(self) -> Path:
        return self._config.db_path

    @property
    def backup_dir(self) -> Path:
        return self._config.backup_dir

    @property
    def daily_backup_path(self) -> Path:
        """Fixed path for the once-per-day rolling backup."""
        return self.backup_dir / DAILY_BACKUP_NAME

    @property
    def daily_stamp_path(self) -> Path:
        """Sidecar with ``YYYY-MM-DD`` of the last successful daily backup."""
        return self.backup_dir / DAILY_STAMP_NAME

    def backup(self, *, label: Optional[str] = None, bundle: bool = False) -> Path:
        """Create a timestamped copy of the database.

        Args:
            label: Optional suffix added to the filename.
            bundle: When True, wrap db + key + media as ``.fwbackup``.

        Returns:
            Path to the created backup file.

        Raises:
            BackupServiceError: If the source DB is missing or copy fails.
        """
        source = self.db_path
        if not source.exists():
            logger.error("Cannot backup; database not found at %s", source)
            raise BackupServiceError(f"Database not found: {source}")

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        suffix = f"_{label}" if label else ""
        target = self.backup_dir / f"finanse_{stamp}{suffix}.db"

        try:
            self._copy_sqlite_bundle(source, target)
            self._copy_secret_key(target)
            self._embed_secret_key(target)
            logger.info("Database backed up to %s", target)
            if bundle:
                return self._wrap_fwbackup(target, stamp=stamp, suffix=suffix)
            return target
        except OSError as exc:
            logger.exception("Backup failed")
            raise BackupServiceError(f"Backup failed: {exc}") from exc

    def today_local(self) -> str:
        """Local calendar day used for the daily-backup gate."""
        return datetime.now().strftime("%Y-%m-%d")

    def last_daily_backup_day(self) -> Optional[str]:
        """Return the stamped day of the last daily backup, if any."""
        stamp = self.daily_stamp_path
        if not stamp.is_file():
            return None
        try:
            text = stamp.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return text or None

    def needs_daily_backup(self) -> bool:
        """True when today's rolling backup has not been written yet."""
        return self.last_daily_backup_day() != self.today_local()

    def ensure_daily_backup(self, *, force: bool = False) -> Optional[Path]:
        """Overwrite ``finanse_daily.db`` at most once per local day.

        Returns the backup path when a write happened, or ``None`` if skipped.
        Safe to call on every launch / hourly — does not create dated copies.
        """
        if not force and not self.needs_daily_backup():
            logger.debug(
                "Daily backup already done for %s — skip",
                self.today_local(),
            )
            return None

        source = self.db_path
        if not source.exists():
            logger.error("Cannot daily-backup; database not found at %s", source)
            raise BackupServiceError(f"Database not found: {source}")

        target = self.daily_backup_path
        try:
            self._remove_sqlite_sidecars(target)
            key_side = Path(str(target) + ".key")
            if key_side.exists():
                key_side.unlink()
            self._copy_sqlite_bundle(source, target)
            self._copy_secret_key(target)
            self._embed_secret_key(target)
            day = self.today_local()
            self.daily_stamp_path.write_text(day + "\n", encoding="utf-8")
            logger.info("Daily backup updated at %s (day=%s)", target, day)
            return target
        except OSError as exc:
            logger.exception("Daily backup failed")
            raise BackupServiceError(f"Daily backup failed: {exc}") from exc

    def restore(
        self,
        backup_path: Path | str,
        *,
        make_safety_copy: bool = True,
        password: str = "",
    ) -> Path:
        """Restore the database from a ``.db`` or ``.fwbackup`` file.

        Args:
            backup_path: Path to a SQLite backup or encrypted bundle.
            make_safety_copy: When True, backup the current DB first.
            password: Only used for password-wrapped ``.fwbackup`` files.

        Returns:
            Path to the restored database file.
        """
        source = Path(backup_path)
        if not source.exists():
            raise BackupServiceError(f"Backup file not found: {source}")
        try:
            header = source.read_bytes()[: max(16, len(FWBACKUP_MAGIC))]
        except OSError as exc:
            raise BackupServiceError(f"Cannot read backup: {exc}") from exc
        if header.startswith(FWBACKUP_MAGIC):
            return self._restore_fwbackup(
                source, make_safety_copy=make_safety_copy, password=password
            )
        if not header.startswith(SQLITE_MAGIC):
            raise BackupServiceError(
                f"Not a SQLite database backup: {source.name}"
            )

        target = self.db_path
        try:
            if make_safety_copy and target.exists():
                safety = self.backup(label="pre_restore")
                logger.info("Safety backup created at %s", safety)

            self._remove_sqlite_sidecars(target)
            self._copy_sqlite_bundle(source, target)
            self._restore_secret_key(source)
            self._extract_secret_key(target)
            logger.info("Database restored from %s to %s", source, target)
            return target
        except OSError as exc:
            logger.exception("Restore failed")
            raise BackupServiceError(f"Restore failed: {exc}") from exc

    def list_backups(self) -> list[Path]:
        """Return backup files newest first (db, daily rolling, fwbackup)."""
        items = list(self.backup_dir.glob("finanse_*.db"))
        items.extend(self.backup_dir.glob("finanse_*.fwbackup"))
        return sorted(items, key=lambda p: p.stat().st_mtime, reverse=True)

    def delete_backup(self, backup_path: Path | str) -> None:
        """Delete a backup file and any sidecars."""
        path = Path(backup_path)
        try:
            self._remove_sqlite_sidecars(path)
            key_side = Path(str(path) + ".key")
            if key_side.exists():
                key_side.unlink()
            if path.exists():
                path.unlink()
            if path.name == DAILY_BACKUP_NAME and self.daily_stamp_path.exists():
                self.daily_stamp_path.unlink()
            logger.info("Deleted backup %s", path)
        except OSError as exc:
            logger.exception("Failed to delete backup %s", path)
            raise BackupServiceError(f"Delete failed: {exc}") from exc

    def _wrap_fwbackup(
        self, db_copy: Path, *, stamp: str, suffix: str, password: str = ""
    ) -> Path:
        zip_bytes = self._build_bundle_zip(db_copy)
        blob = encrypt_bundle(zip_bytes, password)
        dest = self.backup_dir / f"finanse_{stamp}{suffix}.fwbackup"
        dest.write_bytes(blob)
        logger.info("Shareable backup written to %s", dest)
        return dest

    def _build_bundle_zip(self, db_copy: Path) -> bytes:
        created = datetime.now(timezone.utc).isoformat()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "manifest.json",
                json.dumps({"version": 1, "created_at": created}, ensure_ascii=False),
            )
            zf.write(db_copy, "finanse.db")
            key = export_master_key_bytes(self._config)
            if not key:
                key_side = Path(str(db_copy) + ".key")
                if key_side.is_file():
                    try:
                        key = key_side.read_bytes()
                    except OSError:
                        key = None
            if key:
                zf.writestr("secret_box.key", key)
            media = self._config.media_dir
            if media.is_dir():
                for path in sorted(media.rglob("*")):
                    if not path.is_file():
                        continue
                    rel = path.relative_to(media).as_posix()
                    if not rel or rel.startswith("../") or "/../" in f"/{rel}/":
                        continue
                    zf.write(path, f"media/{rel}")
        return buf.getvalue()

    def _restore_fwbackup(
        self,
        source: Path,
        *,
        make_safety_copy: bool = True,
        password: str = "",
    ) -> Path:
        try:
            blob = source.read_bytes()
        except OSError as exc:
            raise BackupServiceError(f"Cannot read backup: {exc}") from exc
        try:
            zip_bytes = decrypt_bundle(blob, password)
        except ValueError as exc:
            raise BackupServiceError(str(exc)) from exc
        import tempfile

        with tempfile.TemporaryDirectory(prefix="fwbackup_") as raw:
            root = Path(raw)
            try:
                with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                    self._safe_extract_zip(zf, root)
            except zipfile.BadZipFile as exc:
                raise BackupServiceError("Backup bundle is not a valid archive") from exc
            db_file = root / "finanse.db"
            if not db_file.is_file():
                raise BackupServiceError("Backup bundle is missing finanse.db")
            key_file = root / "secret_box.key"
            if key_file.is_file():
                sidecar = Path(str(db_file) + ".key")
                try:
                    shutil.copy2(key_file, sidecar)
                except OSError:
                    logger.debug("Could not stage secret_box sidecar from bundle")
            restored = self.restore(
                db_file, make_safety_copy=make_safety_copy, password=""
            )
            if key_file.is_file():
                try:
                    store_master_key(key_file.read_bytes(), self._config)
                except (OSError, ValueError):
                    logger.exception("Could not restore master key from bundle")
            media_src = root / "media"
            if media_src.is_dir():
                self._replace_media_from(media_src)
            return restored

    @staticmethod
    def _safe_extract_zip(zf: zipfile.ZipFile, dest: Path) -> None:
        dest = dest.resolve()
        for info in zf.infolist():
            name = (info.filename or "").replace("\\", "/")
            if not name or name.endswith("/"):
                continue
            if name.startswith("/") or name.startswith("../") or "/../" in f"/{name}/":
                raise BackupServiceError("Backup archive has an unsafe path")
            target = (dest / name).resolve()
            if target != dest and dest not in target.parents:
                raise BackupServiceError("Backup archive has an unsafe path")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)

    def _replace_media_from(self, source: Path) -> None:
        dest = self._config.media_dir
        try:
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(source, dest)
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "receipts").mkdir(parents=True, exist_ok=True)
            logger.info("Restored media from backup bundle")
        except OSError as exc:
            logger.exception("Media restore failed")
            raise BackupServiceError(f"Media restore failed: {exc}") from exc

    def _embed_secret_key(self, backup_db: Path) -> None:
        """Copy the device master key into the backup SQLite file (not the live DB)."""
        payload = export_master_key_bytes(self._config)
        if not payload:
            key = master_key_path(self._config)
            if key.is_file():
                try:
                    payload = key.read_bytes()
                except OSError:
                    logger.exception("Could not read secret_box key for backup embed")
                    return
        if not payload:
            return
        try:
            conn = sqlite3.connect(str(backup_db))
            try:
                conn.execute(
                    f"CREATE TABLE IF NOT EXISTS {SECRET_BOX_TABLE} "
                    "(id INTEGER PRIMARY KEY, key BLOB NOT NULL)"
                )
                conn.execute(f"DELETE FROM {SECRET_BOX_TABLE}")
                conn.execute(
                    f"INSERT INTO {SECRET_BOX_TABLE}(id, key) VALUES (1, ?)",
                    (payload,),
                )
                conn.commit()
            finally:
                conn.close()
        except sqlite3.Error:
            logger.debug("Could not embed secret_box key in backup", exc_info=True)

    def _extract_secret_key(self, db_path: Path) -> None:
        """Restore the master key from an embedded backup table, then drop it."""
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                row = conn.execute(
                    f"SELECT key FROM {SECRET_BOX_TABLE} WHERE id = 1"
                ).fetchone()
                if row and row[0]:
                    store_master_key(bytes(row[0]), self._config)
                conn.execute(f"DROP TABLE IF EXISTS {SECRET_BOX_TABLE}")
                conn.commit()
            finally:
                conn.close()
        except sqlite3.Error:
            logger.debug("Backup has no embedded secret_box key", exc_info=True)

    def _copy_secret_key(self, backup_db: Path) -> None:
        payload = export_master_key_bytes(self._config)
        if not payload:
            key = master_key_path(self._config)
            if key.is_file():
                shutil.copy2(key, Path(str(backup_db) + ".key"))
            return
        Path(str(backup_db) + ".key").write_bytes(payload)

    def _restore_secret_key(self, backup_db: Path) -> None:
        key_src = Path(str(backup_db) + ".key")
        if not key_src.is_file():
            logger.warning(
                "Backup has no companion key file; exchange credentials may not decrypt"
            )
            return
        try:
            store_master_key(key_src.read_bytes(), self._config)
        except (OSError, ValueError):
            logger.exception("Could not restore secret_box key sidecar")

    def _copy_sqlite_bundle(self, source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if self._online_sqlite_backup(source, target):
            for sidecar_suffix in ("-wal", "-shm"):
                dst_side = Path(str(target) + sidecar_suffix)
                if dst_side.exists():
                    dst_side.unlink()
            return
        shutil.copy2(source, target)
        for sidecar_suffix in ("-wal", "-shm"):
            src_side = Path(str(source) + sidecar_suffix)
            dst_side = Path(str(target) + sidecar_suffix)
            if src_side.exists():
                shutil.copy2(src_side, dst_side)
            elif dst_side.exists():
                dst_side.unlink()

    @staticmethod
    def _online_sqlite_backup(source: Path, target: Path) -> bool:
        """Copy a consistent snapshot via the SQLite backup API.

        Fake ``SQLite format 3`` stubs used in unit tests fall through to shutil.
        """
        try:
            if source.stat().st_size < _MIN_SQLITE_BACKUP_BYTES:
                return False
            header = source.read_bytes()[:16]
        except OSError:
            return False
        if not header.startswith(SQLITE_MAGIC):
            return False
        tmp = target.with_name(target.name + ".bak-tmp")
        try:
            if tmp.exists():
                tmp.unlink()
            src = sqlite3.connect(str(source))
            try:
                dst = sqlite3.connect(str(tmp))
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()
            tmp.replace(target)
            return True
        except sqlite3.Error:
            logger.debug("SQLite backup API unavailable; copying files", exc_info=True)
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            return False

    @staticmethod
    def _remove_sqlite_sidecars(db_path: Path) -> None:
        for sidecar_suffix in ("-wal", "-shm"):
            side = Path(str(db_path) + sidecar_suffix)
            if side.exists():
                side.unlink()


def bundle_needs_password(path: Path | str | bytes) -> bool:
    """True when a path or blob is a password-wrapped ``.fwbackup``."""
    if isinstance(path, (bytes, bytearray)):
        return fwbackup_needs_password(bytes(path))
    file = Path(path)
    try:
        header = file.read_bytes()[:8]
    except OSError:
        return False
    return fwbackup_needs_password(header)


def looks_like_fwbackup(path: Path | str | bytes) -> bool:
    """True when a path or blob is a FinWise ``.fwbackup`` container."""
    if isinstance(path, (bytes, bytearray)):
        return is_fwbackup(bytes(path))
    file = Path(path)
    try:
        header = file.read_bytes()[:4]
    except OSError:
        return False
    return is_fwbackup(header)
