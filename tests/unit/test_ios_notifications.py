"""iOS AppDelegate patch for local notifications."""

from __future__ import annotations

from lib.infrastructure.services.biometric import is_mobile_platform
from scripts.patch_ios_appdelegate import MARKER, patch_text


FLET_APPDELEGATE = """import UIKit
import Flutter

@main
@objc class AppDelegate: FlutterAppDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    GeneratedPluginRegistrant.register(with: self)
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }
}
"""


def test_patch_inserts_notification_delegate() -> None:
    patched = patch_text(FLET_APPDELEGATE)
    assert MARKER in patched
    assert "import flutter_local_notifications" in patched
    assert "UNUserNotificationCenter.current().delegate" in patched
    assert "setPluginRegistrantCallback" in patched
    assert patched.count("return super.application") == 1


def test_patch_is_idempotent() -> None:
    once = patch_text(FLET_APPDELEGATE)
    twice = patch_text(once)
    assert once == twice


def test_is_mobile_platform_from_ios_string(monkeypatch) -> None:
    monkeypatch.setattr(
        "lib.infrastructure.services.biometric.mobile_runtime",
        lambda: False,
    )
    page = type("Page", (), {"web": False, "platform": "ios"})()
    assert is_mobile_platform(page) is True
