"""Helpers for mobile export / restore files."""

from __future__ import annotations

from lib.presentation.file_transfer import (
    SQLITE_MAGIC,
    classify_restore_payload,
    safe_filename,
)


def test_safe_filename_strips_path_and_unsafe_chars() -> None:
    assert safe_filename(r"..\..\etc\passwd") == "passwd"
    assert safe_filename("finanse_2026.db") == "finanse_2026.db"
    assert safe_filename("") == "restore.bin"


def test_classify_sqlite_magic() -> None:
    payload = SQLITE_MAGIC + b"\x00rest"
    assert classify_restore_payload("notes.txt", payload) == "db"


def test_classify_fwbackup_magic() -> None:
    assert classify_restore_payload("notes.txt", b"FWBK\x01\x00rest") == "fwbackup"
    assert classify_restore_payload("finanse.fwbackup", b"not-magic") == "fwbackup"


def test_classify_json_and_db_names() -> None:
    assert classify_restore_payload("export.json", b'{"version": 1}') == "json"
    assert classify_restore_payload("finanse.db", b"not sqlite") == "db"
    assert classify_restore_payload("photo.jpg", b"\xff\xd8") == "unknown"


def test_materialize_saved_file_copies_to_chosen_path(tmp_path) -> None:
    from lib.presentation.file_transfer import materialize_saved_file

    source = tmp_path / "finanse_backup.db"
    source.write_bytes(b"sqlite-bytes")
    dest_dir = tmp_path / "picked"
    dest_dir.mkdir()
    dest = dest_dir / "copy.db"
    written = materialize_saved_file(source, dest)
    assert written == dest
    assert dest.read_bytes() == b"sqlite-bytes"


def test_materialize_saved_file_none_is_cancel() -> None:
    from lib.presentation.file_transfer import materialize_saved_file
    from pathlib import Path

    assert materialize_saved_file(Path("x.db"), None) is None
    assert materialize_saved_file(Path("x.db"), "  ") is None


def test_restricted_icloud_downloads_path() -> None:
    from lib.presentation.file_transfer import is_restricted_save_path, materialize_saved_file
    from pathlib import Path

    icloud = (
        "/private/var/mobile/Library/Mobile Documents/"
        "com~apple~CloudDocs/Downloads"
    )
    assert is_restricted_save_path(icloud) is True
    try:
        materialize_saved_file(Path("finanse.db"), icloud)
        raise AssertionError("expected PermissionError")
    except PermissionError:
        pass
