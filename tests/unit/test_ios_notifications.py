"""iOS AppDelegate / Info.plist patches for notifications and App Store privacy."""

from __future__ import annotations

from lib.infrastructure.services.biometric import is_mobile_platform
from scripts.patch_ios_appdelegate import (
    MARKER,
    PLIST_MARKER,
    PRESENT_MARKER,
    install_privacy_manifest,
    patch_info_plist_text,
    patch_text,
    verify_project,
)


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

FLET_INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDisplayName</key>
	<string>Flet</string>
	<key>ITSAppUsesNonExemptEncryption</key>
	<false/>
	<key>NSAppTransportSecurity</key>
	<dict>
		<key>NSAllowsArbitraryLoads</key>
		<true/>
	</dict>
	<key>NSPhotoLibraryUsageDescription</key>
	<string>The app needs access to photo library, so that photos can be selected.</string>
	<key>GADApplicationIdentifier</key>
	<string>ca-app-pub-3940256099942544~1458002511</string>
	<key>NSMicrophoneUsageDescription</key>
	<string>This app needs access to microphone.</string>
	<key>NSCameraUsageDescription</key>
	<string>This app uses the camera to capture photos and video.</string>
	<key>NSLocationWhenInUseUsageDescription</key>
	<string>This app needs access to location.</string>
</dict>
</plist>
"""


def test_patch_inserts_notification_delegate() -> None:
    patched = patch_text(FLET_APPDELEGATE)
    assert MARKER in patched
    assert "import flutter_local_notifications" in patched
    assert "UNUserNotificationCenter.current().delegate" in patched
    assert "setPluginRegistrantCallback" in patched
    assert PRESENT_MARKER in patched
    assert "willPresent" in patched
    assert patched.count("return super.application") == 1


def test_patch_is_idempotent() -> None:
    once = patch_text(FLET_APPDELEGATE)
    twice = patch_text(once)
    assert once == twice


def test_patch_adds_will_present_to_old_delegate_hook() -> None:
    old = patch_text(FLET_APPDELEGATE)
    # Strip the foreground presentation override (older IPA patch).
    start = old.find(f"  // {PRESENT_MARKER}")
    assert start != -1
    end = old.find("  }\n}", start)
    stripped = old[:start] + old[end + 4 :]
    assert PRESENT_MARKER not in stripped
    upgraded = patch_text(stripped)
    assert PRESENT_MARKER in upgraded
    assert "willPresent" in upgraded


def _ats_allows_arbitrary(text: str) -> bool:
    _, rest = text.split("NSAllowsArbitraryLoads", 1)
    chunk = rest.split("</dict>", 1)[0]
    return "<true/>" in chunk


def test_info_plist_strips_ads_and_unused_permissions() -> None:
    patched = patch_info_plist_text(FLET_INFO_PLIST)
    assert "GADApplicationIdentifier" not in patched
    assert "NSMicrophoneUsageDescription" not in patched
    assert "NSCameraUsageDescription" not in patched
    assert "NSLocationWhenInUseUsageDescription" not in patched
    assert "Unlock FinWise with Face ID" in patched
    assert "receipt photos" in patched
    assert "<key>CFBundleDisplayName</key>" in patched
    assert "<string>FinWise</string>" in patched
    assert PLIST_MARKER in patched
    assert "<key>ITSAppUsesNonExemptEncryption</key>" in patched
    assert _ats_allows_arbitrary(patched) is False
    once = patch_info_plist_text(patched)
    assert once == patched


def test_privacy_manifest_install(tmp_path) -> None:
    dest = tmp_path / "Runner" / "PrivacyInfo.xcprivacy"
    assert install_privacy_manifest(dest) is True
    body = dest.read_text(encoding="utf-8")
    assert "NSPrivacyTracking" in body
    assert "CA92.1" in body
    assert "C617.1" in body
    assert install_privacy_manifest(dest) is False


def test_is_mobile_platform_from_ios_string(monkeypatch) -> None:
    monkeypatch.setattr(
        "lib.infrastructure.services.biometric.mobile_runtime",
        lambda: False,
    )
    page = type("Page", (), {"web": False, "platform": "ios"})()
    assert is_mobile_platform(page) is True


def test_verify_project_requires_delegate_and_will_present(tmp_path) -> None:
    runner = tmp_path / "ios" / "Runner"
    runner.mkdir(parents=True)
    app = runner / "AppDelegate.swift"
    app.write_text(FLET_APPDELEGATE, encoding="utf-8")
    assert verify_project(tmp_path) == 1
    from scripts.patch_ios_appdelegate import patch_file

    assert patch_file(app) is True
    assert verify_project(tmp_path) == 0


def test_verify_project_missing_appdelegate(tmp_path) -> None:
    assert verify_project(tmp_path) == 1


def test_flet_build_wrapper_requires_command() -> None:
    from scripts.flet_build_with_ios_patch import main

    assert main([]) == 2
    assert main(["--timeout", "1"]) == 2
