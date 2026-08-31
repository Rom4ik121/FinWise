# Build FinWise APK on Windows (PowerShell).
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

chcp 65001 | Out-Null
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$flutter = "$env:USERPROFILE\flutter\3.44.8"
if (-not (Test-Path "$flutter\bin\flutter.bat")) {
    $flutter = "C:\flutter"
}
$env:FLUTTER_ROOT = $flutter
$env:PATH = "$flutter\bin;" + $env:PATH
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME

$flet = "$env:LOCALAPPDATA\Packages\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\LocalCache\local-packages\Python312\Scripts\flet.exe"
if (-not (Test-Path $flet)) {
    $flet = (Get-Command flet -ErrorAction SilentlyContinue).Source
}
if (-not $flet) {
    Write-Host "flet CLI not found. Run: python -m pip install -U flet[all]" -ForegroundColor Red
    exit 1
}

# Install desugar init script into the default Gradle user home (keeps wrapper cache).
$defaultGradleHome = Join-Path $env:USERPROFILE ".gradle"
$initDir = Join-Path $defaultGradleHome "init.d"
New-Item -ItemType Directory -Force -Path $initDir | Out-Null
Copy-Item -Force "scripts\desugar.init.gradle" (Join-Path $initDir "finanse_desugar.init.gradle")
# Do NOT override GRADLE_USER_HOME - that forces a full Gradle re-download and lock fights.

function Invoke-AndroidPatches {
    param([string]$FlutterRoot = "build\flutter")
    if (-not (Test-Path $FlutterRoot)) {
        return
    }
    Write-Host "Patching Android notifications + desugaring..." -ForegroundColor Cyan
    python -m flet_android_notifications.patcher --project-root $FlutterRoot
    python scripts\patch_android_desugar.py --project-root $FlutterRoot
}

Write-Host "Flutter: $flutter" -ForegroundColor Cyan
Write-Host "Android SDK: $env:ANDROID_HOME" -ForegroundColor Cyan
Write-Host "Building APK (arm64 only; first run may take 20-40 min)..." -ForegroundColor Yellow

# Do not treat a stale APK from an older build as success.
$buildStarted = Get-Date
python -m pip install -U "flet[all]" -r requirements.txt -q

if (-not (Test-Path "vendor\ccxt\pyproject.toml")) {
    Write-Host "Generating mobile-safe vendor/ccxt..." -ForegroundColor Cyan
    python scripts\vendor_ccxt_mobile.py
}

# If a previous shell exists, patch before rebuild (helps incremental paths).
Invoke-AndroidPatches

# serious_python copies the whole tree then compileall's it. Keep packaging
# lean (also mirrored in pyproject.toml / flet.toml [tool.flet.app].exclude).
$exclude = @(
    "build",
    "dist",
    "storage",
    "secrets",
    ".venv",
    "venv",
    ".git",
    ".github",
    ".cursor",
    ".claude",
    ".flet",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".hypothesis",
    "htmlcov",
    "__pycache__",
    "tests",
    "docs",
    "scripts",
    "agent-transcripts",
    "agent-tools",
    "AGENTS.md",
    "pytest.ini",
    "codemagic.yaml",
    "vendor/wheels",
    "vendor"
)

$fletExit = 0
try {
    & $flet build apk `
        --org com.finanse.app `
        --product FinWise `
        --build-version 0.1.0 `
        --build-number 1 `
        --arch arm64-v8a `
        --exclude @exclude `
        --android-adaptive-icon-background "#000000" `
        --splash-color "#000000" `
        --splash-dark-color "#000000" `
        --yes `
        --no-rich-output `
        -v
    $fletExit = $LASTEXITCODE
} catch {
    $fletExit = 1
}

# Flet recreates the Android project mid-build; patch again and finish with Flutter
# if the APK is still missing (typical desugar / notification failures).
Invoke-AndroidPatches

$apk = $null
if ($fletExit -eq 0) {
    $apk = Get-ChildItem -Path build -Recurse -Filter "*.apk" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.LastWriteTime -ge $buildStarted -and (
                $_.FullName -match '\\(apk|outputs)\\' -or
                $_.DirectoryName -match 'flutter\\build\\app'
            )
        } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

if ((-not $apk) -and ($fletExit -ne 0)) {
    Write-Host "flet build apk failed (exit $fletExit). Trying flutter assembleRelease fallback..." -ForegroundColor Yellow
}

if (-not $apk) {
    Write-Host "Finishing APK via flutter build apk (with desugar patches)..." -ForegroundColor Yellow
    if (-not (Test-Path "build\flutter")) {
        Write-Host "No build\flutter project - cannot finish APK." -ForegroundColor Red
        if ($fletExit -ne 0) { exit $fletExit }
        exit 1
    }
    $buildDir = (Resolve-Path "build").Path
    $env:SERIOUS_PYTHON_SITE_PACKAGES = Join-Path $buildDir "site-packages"
    $env:SERIOUS_PYTHON_APP = Join-Path $buildDir "python-app"
    if (-not $env:SERIOUS_PYTHON_VERSION) {
        $env:SERIOUS_PYTHON_VERSION = "3.14"
    }
    Push-Location "build\flutter"
    try {
        & "$flutter\bin\flutter.bat" build apk `
            --release `
            --target-platform android-arm64 `
            --build-number 1 `
            --build-name 0.1.0 `
            --no-version-check `
            --suppress-analytics
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Flutter assembleRelease failed." -ForegroundColor Red
            exit $LASTEXITCODE
        }
    } finally {
        Pop-Location
    }
    New-Item -ItemType Directory -Force -Path "build\apk" | Out-Null
    $built = @(
        Get-ChildItem -Path "build\flutter\build\app\outputs" -Recurse -Filter "app-release.apk" -ErrorAction SilentlyContinue
    ) | Where-Object { $_.LastWriteTime -ge $buildStarted } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($built) {
        Copy-Item -Force $built.FullName "build\apk\FinWise-0.1.0.apk"
        $apk = Get-Item "build\apk\FinWise-0.1.0.apk"
    }
}

if ($apk -and ($apk.LastWriteTime -ge $buildStarted)) {
    Write-Host ""
    Write-Host "APK ready: $($apk.FullName)" -ForegroundColor Green
    Write-Host ("Size: {0:N1} MB  modified: {1}" -f ($apk.Length / 1MB), $apk.LastWriteTime)
    exit 0
}

Write-Host "Build failed - no fresh APK (ignoring stale files from older builds)." -ForegroundColor Red
if ($fletExit -ne 0) { exit $fletExit }
exit 1
