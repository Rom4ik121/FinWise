"""SQLite database backup and restore."""

from __future__ import annotations

import logging
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from lib.core.config import AppConfig, get_default_config
from lib.infrastructure.services.secret_box import master_key_path

logger = logging.getLogger("finanse.infrastructure.services.backup")

# Single rolling file updated at most once per local calendar day on every device.
DAILY_BACKUP_NAME = "finanse_daily.db"
DAILY_STAMP_NAME = "finanse_daily.day"
# Embedded in the backup copy only so a single shared .db can restore exchange keys
# when the companion ``.key`` sidecar is missing (typical on iOS share/Files).
SECRET_BOX_TABLE = "_finanse_secret_box"


class BackupServiceError(Exception):
    """Raised when backup or restore fails."""


class BackupService:
    """Copy the SQLite DB file to / from the configured backup directory.

    When a ``.secret_box_key`` exists, it is copied next to the backup as
    ``<backup>.db.key`` **and** embedded in a tiny SQLite table inside the
    backup copy. The live database does not keep that table; it is re-added
    on each backup so a single shared ``.db`` can restore exchange credentials
    on iPhone when the sidecar file is not picked.
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

    def backup(self, *, label: Optional[str] = None) -> Path:
        """Create a timestamped copy of the database.

        Args:
            label: Optional suffix added to the filename.

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

    def restore(self, backup_path: Path | str, *, make_safety_copy: bool = True) -> Path:
        """Restore the database from a backup file.

        Args:
            backup_path: Path to a ``.db`` backup.
            make_safety_copy: When True, backup the current DB first.

        Returns:
            Path to the restored database file.
        """
        source = Path(backup_path)
        if not source.exists():
            raise BackupServiceError(f"Backup file not found: {source}")
        try:
            header = source.read_bytes()[:16]
        except OSError as exc:
            raise BackupServiceError(f"Cannot read backup: {exc}") from exc
        if not header.startswith(b"SQLite format 3"):
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
        """Return backup files newest first (includes daily rolling file)."""
        return sorted(
            self.backup_dir.glob("finanse_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

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

    def _embed_secret_key(self, backup_db: Path) -> None:
        """Copy the device master key into the backup SQLite file (not the live DB)."""
        key = master_key_path(self._config)
        if not key.is_file():
            return
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
        dest = master_key_path(self._config)
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                row = conn.execute(
                    f"SELECT key FROM {SECRET_BOX_TABLE} WHERE id = 1"
                ).fetchone()
                if row and row[0]:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(bytes(row[0]))
                    try:
                        import os

                        os.chmod(dest, 0o600)
                    except OSError:
                        pass
                conn.execute(f"DROP TABLE IF EXISTS {SECRET_BOX_TABLE}")
                conn.commit()
            finally:
                conn.close()
        except sqlite3.Error:
            logger.debug("Backup has no embedded secret_box key", exc_info=True)

    def _copy_secret_key(self, backup_db: Path) -> None:
        key = master_key_path(self._config)
        if not key.is_file():
            return
        shutil.copy2(key, Path(str(backup_db) + ".key"))

    def _restore_secret_key(self, backup_db: Path) -> None:
        key_src = Path(str(backup_db) + ".key")
        if not key_src.is_file():
            logger.warning(
                "Backup has no companion key file; exchange credentials may not decrypt"
            )
            return
        dest = master_key_path(self._config)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(key_src, dest)
        try:
            import os

            os.chmod(dest, 0o600)
        except OSError:
            pass

    @staticmethod
    def _copy_sqlite_bundle(source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        for sidecar_suffix in ("-wal", "-shm"):
            src_side = Path(str(source) + sidecar_suffix)
            dst_side = Path(str(target) + sidecar_suffix)
            if src_side.exists():
                shutil.copy2(src_side, dst_side)
            elif dst_side.exists():
                dst_side.unlink()

    @staticmethod
    def _remove_sqlite_sidecars(db_path: Path) -> None:
        for sidecar_suffix in ("-wal", "-shm"):
            side = Path(str(db_path) + sidecar_suffix)
            if side.exists():
                side.unlink()
