"""Patch Flet's iOS AppDelegate, Info.plist, and privacy manifest.

Flet's template never sets ``UNUserNotificationCenter.current().delegate``.
Without that, iOS often never lists FinWise under Settings → Notifications and
drops banners while the app is open.

Also injects App Store privacy strings, strips leftover Flet AdMob / unused
permission keys, and copies ``ios/PrivacyInfo.xcprivacy``.

Idempotent. Safe to re-run. Use ``--watch`` during ``flet build ipa`` so files
are patched after the template is copied and before Xcode compiles.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
from pathlib import Path

MARKER = "FinWiseLocalNotifications"
PRESENT_MARKER = "FinWiseLocalNotificationsPresent"
PLIST_MARKER = "FinWiseInfoPlist"

IMPORT_BLOCK = """import flutter_local_notifications
import UserNotifications
"""

HOOK_BLOCK = f"""    // {MARKER}: required for iOS local notification permission + banners.
    FlutterLocalNotificationsPlugin.setPluginRegistrantCallback {{ (registry) in
      GeneratedPluginRegistrant.register(with: registry)
    }}
    if #available(iOS 10.0, *) {{
      UNUserNotificationCenter.current().delegate = self as UNUserNotificationCenterDelegate
    }}
"""

WILL_PRESENT_METHOD = f"""
  // {PRESENT_MARKER}: show banners while FinWise is in the foreground.
  override func userNotificationCenter(
    _ center: UNUserNotificationCenter,
    willPresent notification: UNNotification,
    withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
  ) {{
    if #available(iOS 14.0, *) {{
      completionHandler([.banner, .sound, .badge, .list])
    }} else {{
      completionHandler([.alert, .sound, .badge])
    }}
  }}
"""

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PRIVACY_SRC = _REPO_ROOT / "ios" / "PrivacyInfo.xcprivacy"

# Flet's stock Info.plist ships AdMob + unused mic/camera/location strings.
_REMOVE_PLIST_KEYS = (
    "GADApplicationIdentifier",
    "NSMicrophoneUsageDescription",
    "NSSpeechRecognitionUsageDescription",
    "NSCameraUsageDescription",
    "NSLocationWhenInUseUsageDescription",
    "NSLocationAlwaysAndWhenInUseUsageDescription",
    "NSLocationAlwaysUsageDescription",
    "NSLocationUsageDescription",
)

_REQUIRED_STRINGS = {
    "NSFaceIDUsageDescription": "Unlock FinWise with Face ID",
    "NSPhotoLibraryUsageDescription": (
        "FinWise attaches receipt photos you pick to transactions on this device."
    ),
    "NSPhotoLibraryAddUsageDescription": (
        "FinWise can share exported reports and backups through the system share sheet."
    ),
    "CFBundleDisplayName": "FinWise",
}


def patch_text(text: str) -> str:
    """Return AppDelegate.swift with notification hooks inserted."""
    out = text
    if "import flutter_local_notifications" not in out:
        if "import Flutter" in out:
            out = out.replace(
                "import Flutter\n",
                "import Flutter\n" + IMPORT_BLOCK,
                1,
            )
        else:
            out = IMPORT_BLOCK + out
    if MARKER not in out:
        needle = "    return super.application(application, didFinishLaunchingWithOptions: launchOptions)"
        if needle not in out:
            needle = "return super.application(application, didFinishLaunchingWithOptions: launchOptions)"
        if needle in out:
            out = out.replace(needle, HOOK_BLOCK + "    " + needle.lstrip(), 1)
        else:
            out += "\n" + HOOK_BLOCK
    if PRESENT_MARKER not in out:
        idx = out.rfind("}")
        if idx != -1:
            out = out[:idx] + WILL_PRESENT_METHOD + out[idx:]
        else:
            out += WILL_PRESENT_METHOD
    return out


def _remove_plist_key(text: str, key: str) -> str:
    pattern = re.compile(
        rf"[ \t]*<key>{re.escape(key)}</key>\s*"
        rf"(?:<string>[^<]*</string>|<true/>|<false/>|"
        rf"<integer>[^<]*</integer>|<real>[^<]*</real>|"
        rf"<dict>.*?</dict>|<array>.*?</array>)\s*",
        re.DOTALL,
    )
    return pattern.sub("", text, count=1)


def _set_plist_string(text: str, key: str, value: str) -> str:
    pattern = re.compile(
        rf"(<key>{re.escape(key)}</key>\s*)<string>[^<]*</string>",
        re.DOTALL,
    )
    replacement = rf"\1<string>{value}</string>"
    if pattern.search(text):
        return pattern.sub(replacement, text, count=1)
    insert = f"\t<key>{key}</key>\n\t<string>{value}</string>\n"
    return text.replace("</dict>\n</plist>", insert + "</dict>\n</plist>", 1)


def _set_plist_bool(text: str, key: str, value: bool) -> str:
    token = "<true/>" if value else "<false/>"
    pattern = re.compile(
        rf"(<key>{re.escape(key)}</key>\s*)(?:<true/>|<false/>)",
        re.DOTALL,
    )
    if pattern.search(text):
        return pattern.sub(rf"\1{token}", text, count=1)
    insert = f"\t<key>{key}</key>\n\t{token}\n"
    return text.replace("</dict>\n</plist>", insert + "</dict>\n</plist>", 1)


def patch_info_plist_text(text: str) -> str:
    """Sanitize Flet's stock Info.plist for App Store / FinWise privacy."""
    out = text
    for key in _REMOVE_PLIST_KEYS:
        out = _remove_plist_key(out, key)
    for key, value in _REQUIRED_STRINGS.items():
        out = _set_plist_string(out, key, value)
    out = _set_plist_bool(out, "ITSAppUsesNonExemptEncryption", False)
    # Prefer HTTPS-only ATS; Flet's template sets NSAllowsArbitraryLoads true.
    out = re.sub(
        r"(<key>NSAllowsArbitraryLoads</key>\s*)<true/>",
        r"\1<false/>",
        out,
        count=1,
    )
    if PLIST_MARKER not in out:
        out = out.replace(
            "</dict>\n</plist>",
            f"\t<!-- {PLIST_MARKER} -->\n</dict>\n</plist>",
            1,
        )
    return out


def patch_file(path: Path) -> bool:
    """Patch ``path`` in place. Return True if the file changed."""
    original = path.read_text(encoding="utf-8")
    updated = patch_text(original)
    if updated == original:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def patch_info_plist(path: Path) -> bool:
    """Patch Info.plist in place. Return True if the file changed."""
    original = path.read_text(encoding="utf-8")
    updated = patch_info_plist_text(original)
    if updated == original:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def install_privacy_manifest(dest: Path, *, source: Path | None = None) -> bool:
    """Copy FinWise PrivacyInfo.xcprivacy over Flutter's placeholder."""
    src = source or _PRIVACY_SRC
    if not src.is_file():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    incoming = src.read_bytes()
    if dest.is_file() and dest.read_bytes() == incoming:
        return False
    shutil.copy2(src, dest)
    return True


def patch_project(project_root: Path) -> bool:
    """Patch AppDelegate, Info.plist, and privacy manifest under a Flutter root."""
    runner = project_root / "ios" / "Runner"
    changed = False
    app_delegate = runner / "AppDelegate.swift"
    if app_delegate.is_file() and patch_file(app_delegate):
        changed = True
    info = runner / "Info.plist"
    if info.is_file() and patch_info_plist(info):
        changed = True
    privacy = runner / "PrivacyInfo.xcprivacy"
    if install_privacy_manifest(privacy):
        changed = True
    return changed


def watch(path: Path, *, timeout: float = 7200.0, interval: float = 0.4) -> int:
    """Patch iOS Runner files whenever Flet rewrites them, until timeout."""
    project_root = path
    if path.name == "AppDelegate.swift":
        project_root = path.parents[2]  # …/ios/Runner/AppDelegate.swift
    deadline = time.monotonic() + timeout
    patched_once = False
    while time.monotonic() < deadline:
        try:
            if patch_project(project_root):
                print(f"Patched iOS Runner under: {project_root}", flush=True)
            if (project_root / "ios" / "Runner" / "AppDelegate.swift").is_file():
                patched_once = True
        except OSError as exc:
            print(f"Watch skip: {exc}", file=sys.stderr, flush=True)
        time.sleep(interval)
    return 0 if patched_once else 1


def verify_project(project_root: Path) -> int:
    """Return 0 when AppDelegate has delegate + willPresent hooks."""
    app_delegate = project_root / "ios" / "Runner" / "AppDelegate.swift"
    if not app_delegate.is_file():
        print(f"No AppDelegate.swift under {project_root}", file=sys.stderr)
        return 1
    text = app_delegate.read_text(encoding="utf-8")
    missing: list[str] = []
    if MARKER not in text:
        missing.append("UNUserNotificationCenter.delegate hook")
    if PRESENT_MARKER not in text and "willPresent" not in text:
        missing.append("willPresent (foreground banners)")
    if missing:
        print(
            "iOS AppDelegate missing: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 1
    print(f"Verified iOS notification hooks: {app_delegate}", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        default="build/flutter",
        help="Flet Flutter project root (default: build/flutter)",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Keep patching until timeout (for flet build ipa)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=7200.0,
        help="Watch timeout in seconds (default: 7200; must outlive flet build)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Fail if AppDelegate is missing willPresent / delegate hooks",
    )
    args = parser.parse_args()
    root = Path(args.project_root)
    if args.watch:
        return watch(root, timeout=args.timeout)
    if args.verify:
        patch_project(root)
        return verify_project(root)
    if not (root / "ios" / "Runner" / "AppDelegate.swift").is_file():
        print(f"No AppDelegate.swift under {root}", file=sys.stderr)
        return 1
    changed = patch_project(root)
    print(("Patched" if changed else "Already patched") + f": {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
