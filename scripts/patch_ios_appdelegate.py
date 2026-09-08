"""Patch Flet's iOS AppDelegate so local notifications can prompt and display.

Flet's template never sets ``UNUserNotificationCenter.current().delegate``.
Without that, iOS often never lists FinWise under Settings → Notifications and
drops banners while the app is open.

Idempotent. Safe to re-run. Use ``--watch`` during ``flet build ipa`` so the
file is patched after the template is copied and before Xcode compiles.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

MARKER = "FinWiseLocalNotifications"

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


def patch_text(text: str) -> str:
    """Return AppDelegate.swift with notification hooks inserted."""
    if MARKER in text:
        return text
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
    return out


def patch_file(path: Path) -> bool:
    """Patch ``path`` in place. Return True if the file changed."""
    original = path.read_text(encoding="utf-8")
    updated = patch_text(original)
    if updated == original:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def watch(path: Path, *, timeout: float = 600.0, interval: float = 0.4) -> int:
    """Patch ``path`` whenever Flet rewrites it, until ``timeout`` seconds."""
    deadline = time.monotonic() + timeout
    patched_once = False
    while time.monotonic() < deadline:
        if path.is_file():
            try:
                if patch_file(path):
                    print(f"Patched: {path}", flush=True)
                patched_once = True
            except OSError as exc:
                print(f"Watch skip: {exc}", file=sys.stderr, flush=True)
        time.sleep(interval)
    return 0 if patched_once else 1


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
        default=900.0,
        help="Watch timeout in seconds (default: 900)",
    )
    args = parser.parse_args()
    path = Path(args.project_root) / "ios" / "Runner" / "AppDelegate.swift"
    if args.watch:
        return watch(path, timeout=args.timeout)
    if not path.is_file():
        print(f"No AppDelegate.swift at {path}", file=sys.stderr)
        return 1
    changed = patch_file(path)
    print(("Patched" if changed else "Already patched") + f": {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
