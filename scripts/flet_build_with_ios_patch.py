#!/usr/bin/env python3
"""Run ``flet build`` while keeping iOS AppDelegate / willPresent patched.

Codemagic and local IPA builds must not ship Flet's stock AppDelegate:
without ``UNUserNotificationCenter.delegate`` + ``willPresent``, iOS drops
foreground banners and often hides FinWise under Settings → Notifications.

Usage::

    python3 scripts/flet_build_with_ios_patch.py -- flet build ipa ...
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PATCH = _ROOT / "scripts" / "patch_ios_appdelegate.py"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        default="build/flutter",
        help="Flet Flutter project root (default: build/flutter)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=7200.0,
        help="Watch timeout in seconds (default: 7200; must outlive flet build)",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Build command (put -- before it)",
    )
    args = parser.parse_args(argv)
    cmd = list(args.command)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("Missing build command after --", file=sys.stderr)
        return 2

    python = sys.executable
    watch = subprocess.Popen(
        [
            python,
            str(_PATCH),
            "--watch",
            "--project-root",
            args.project_root,
            "--timeout",
            str(args.timeout),
        ]
    )
    try:
        result = subprocess.call(cmd)
    finally:
        watch.terminate()
        try:
            watch.wait(timeout=8)
        except subprocess.TimeoutExpired:
            watch.kill()
            watch.wait(timeout=3)

    patch_once = subprocess.call(
        [python, str(_PATCH), "--project-root", args.project_root]
    )
    verify = subprocess.call(
        [python, str(_PATCH), "--verify", "--project-root", args.project_root]
    )
    if result != 0:
        return result
    if patch_once != 0:
        return patch_once
    return verify


if __name__ == "__main__":
    raise SystemExit(main())
