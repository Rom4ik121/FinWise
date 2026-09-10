#!/usr/bin/env bash
# Build a signed IPA for physical iPhone testing.
# Run on macOS only (Xcode + CocoaPods + Apple Developer account required).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "ERROR: flet build ipa works only on macOS with Xcode."
  echo "This PC is $(uname -s). Copy the project to a Mac and re-run."
  exit 1
fi

TEAM_ID="${IOS_TEAM_ID:-}"
PROFILE="${IOS_PROVISIONING_PROFILE:-}"
EXPORT_METHOD="${IOS_EXPORT_METHOD:-release-testing}"
CERT="${IOS_SIGNING_CERTIFICATE:-Apple Distribution}"

if [[ -z "$TEAM_ID" ]]; then
  echo "Set IOS_TEAM_ID to your 10-character Apple Team ID."
  echo "Example:"
  echo "  export IOS_TEAM_ID=ABCDE12345"
  echo "  export IOS_PROVISIONING_PROFILE='Finanse Ad Hoc'"
  echo "  ./scripts/build_ipa.sh"
  exit 1
fi

python3 -m pip install -U "flet[all]" -r requirements.txt
python3 "$ROOT/scripts/vendor_ccxt_mobile.py"
test -f "$ROOT/vendor/ccxt/pyproject.toml"

# Keep tests/docs/scripts/caches out of the IPA (same list as pyproject / APK).
EXCLUDE=(
  --exclude build
  --exclude dist
  --exclude storage
  --exclude secrets
  --exclude .venv
  --exclude venv
  --exclude .git
  --exclude .github
  --exclude .cursor
  --exclude .claude
  --exclude .flet
  --exclude .pytest_cache
  --exclude .mypy_cache
  --exclude .ruff_cache
  --exclude .tox
  --exclude .hypothesis
  --exclude htmlcov
  --exclude __pycache__
  --exclude tests
  --exclude docs
  --exclude scripts
  --exclude agent-transcripts
  --exclude agent-tools
  --exclude AGENTS.md
  --exclude pytest.ini
  --exclude codemagic.yaml
  --exclude vendor
)

ARGS=(
  build ipa
  --org com.finanse.app
  --product FinWise
  --build-version 0.1.0
  --ios-team-id "$TEAM_ID"
  --ios-export-method "$EXPORT_METHOD"
  --ios-signing-certificate "$CERT"
  --splash-color "#0B1220"
  --splash-dark-color "#0B1220"
  --yes
  "${EXCLUDE[@]}"
)

if [[ -n "$PROFILE" ]]; then
  ARGS+=(--ios-provisioning-profile "$PROFILE")
fi

echo "Running: flet ${ARGS[*]}"
# Flet copies a stock AppDelegate; patch it before Xcode compiles.
python3 "$ROOT/scripts/patch_ios_appdelegate.py" --watch --project-root "$ROOT/build/flutter" &
WATCH_PID=$!
trap 'kill "$WATCH_PID" 2>/dev/null || true' EXIT
flet "${ARGS[@]}"
kill "$WATCH_PID" 2>/dev/null || true
python3 "$ROOT/scripts/patch_ios_appdelegate.py" --project-root "$ROOT/build/flutter" || true

echo
echo "IPA (if export succeeded): look under build/ipa/"
ls -la build/ipa 2>/dev/null || ls -la build/ 2>/dev/null || true
