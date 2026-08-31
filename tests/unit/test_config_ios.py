"""iOS/Android data-dir detection must not touch sandbox parent paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.core.config import _is_android, _is_ios


def test_is_ios_when_sys_platform_is_ios(monkeypatch) -> None:
    monkeypatch.setattr("lib.core.config.sys.platform", "ios")
    assert _is_ios() is True


def test_is_ios_from_env(monkeypatch) -> None:
    monkeypatch.setattr("lib.core.config.sys.platform", "linux")
    monkeypatch.setenv("FLET_IOS", "1")
    assert _is_ios() is True


def test_is_ios_from_sandbox_home(monkeypatch) -> None:
    monkeypatch.setattr("lib.core.config.sys.platform", "darwin")
    monkeypatch.delenv("FLET_IOS", raising=False)
    monkeypatch.delenv("FTC_DEVICE", raising=False)

    class _FakePath:
        @staticmethod
        def home() -> Path:
            return Path("/var/mobile/Containers/Data/Application/ABC")

    monkeypatch.setattr("lib.core.config.Path", _FakePath)
    assert _is_ios() is True


def test_is_ios_from_private_sandbox_home(monkeypatch) -> None:
    monkeypatch.setattr("lib.core.config.sys.platform", "darwin")
    monkeypatch.delenv("FLET_IOS", raising=False)
    monkeypatch.delenv("FTC_DEVICE", raising=False)

    class _FakePath:
        @staticmethod
        def home() -> Path:
            return Path("/private/var/mobile/Containers/Data/Application/ABC")

    monkeypatch.setattr("lib.core.config.Path", _FakePath)
    assert _is_ios() is True


def test_is_ios_false_on_macos(monkeypatch) -> None:
    monkeypatch.setattr("lib.core.config.sys.platform", "darwin")
    monkeypatch.delenv("FLET_IOS", raising=False)
    monkeypatch.delenv("FTC_DEVICE", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/Users/admin")))
    assert _is_ios() is False


def test_is_ios_false_on_windows(monkeypatch) -> None:
    monkeypatch.setattr("lib.core.config.sys.platform", "win32")
    monkeypatch.delenv("FLET_IOS", raising=False)
    monkeypatch.delenv("FTC_DEVICE", raising=False)
    assert _is_ios() is False


def test_is_android_from_env(monkeypatch) -> None:
    monkeypatch.setattr("lib.core.config.sys.platform", "linux")
    monkeypatch.setenv("FLET_PLATFORM", "android")
    assert _is_android() is True


def test_is_android_from_sandbox_home(monkeypatch) -> None:
    monkeypatch.setattr("lib.core.config.sys.platform", "linux")
    monkeypatch.delenv("FLET_PLATFORM", raising=False)
    monkeypatch.delenv("FLET_ANDROID", raising=False)

    class _FakePath:
        @staticmethod
        def home() -> Path:
            return Path("/data/user/0/com.finanse.app/files")

    monkeypatch.setattr("lib.core.config.Path", _FakePath)
    assert _is_android() is True


def test_android_data_dir_stays_in_sandbox(monkeypatch, tmp_path) -> None:
    from lib.core.config import _default_data_dir

    monkeypatch.setattr("lib.core.config.sys.platform", "linux")
    monkeypatch.setenv("FLET_PLATFORM", "android")
    monkeypatch.delenv("FLET_APP_STORAGE_DATA", raising=False)
    monkeypatch.delenv("FILESDIR", raising=False)
    monkeypatch.setattr("lib.core.config.Path.home", classmethod(lambda cls: tmp_path))
    # tmp_path is not an Android sandbox path — use env instead.
    storage = tmp_path / "storage_data"
    storage.mkdir()
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(storage))
    path = _default_data_dir()
    assert path == storage / "finanse"
    assert path.is_dir()
    assert ".local" not in path.as_posix()


def test_android_data_dir_rejects_bare_data_home(monkeypatch, tmp_path) -> None:
    from lib.core.config import _default_data_dir

    monkeypatch.setattr("lib.core.config.sys.platform", "linux")
    monkeypatch.setenv("FLET_PLATFORM", "android")
    monkeypatch.delenv("FLET_APP_STORAGE_DATA", raising=False)
    monkeypatch.delenv("FILESDIR", raising=False)
    monkeypatch.setattr(
        "lib.core.config.Path.home", classmethod(lambda cls: Path("/data"))
    )
    storage = tmp_path / "app_data"
    storage.mkdir()
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(storage))
    path = _default_data_dir()
    assert path == storage / "finanse"
    assert "/data/finanse" not in path.as_posix()


def test_android_data_dir_uses_sandbox_home(monkeypatch, tmp_path) -> None:
    from lib.core.config import _default_data_dir

    sandbox = tmp_path / "data" / "user" / "0" / "com.finanse.app" / "files"
    sandbox.mkdir(parents=True)
    monkeypatch.setattr("lib.core.config.sys.platform", "linux")
    monkeypatch.setenv("FLET_PLATFORM", "android")
    monkeypatch.delenv("FLET_APP_STORAGE_DATA", raising=False)
    monkeypatch.delenv("FILESDIR", raising=False)
    monkeypatch.setattr(
        "lib.core.config.Path.home", classmethod(lambda cls: sandbox)
    )
    path = _default_data_dir()
    assert path == sandbox / "finanse"
    assert path.is_dir()
