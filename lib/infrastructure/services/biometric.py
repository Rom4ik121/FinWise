"""Platform biometric / Windows Hello / mobile local_auth verification."""

from __future__ import annotations

import logging
import os
import sys
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    import flet as ft

logger = logging.getLogger("finanse.infrastructure.services.biometric")


class BiometricStatus(str, Enum):
    """Whether the OS can present a biometric / Hello prompt."""

    AVAILABLE = "available"
    DEVICE_NOT_PRESENT = "device_not_present"
    NOT_CONFIGURED = "not_configured"
    DISABLED_BY_POLICY = "disabled_by_policy"
    DEVICE_BUSY = "device_busy"
    UNSUPPORTED = "unsupported"


class BiometricResult(str, Enum):
    """Outcome of a verification attempt."""

    VERIFIED = "verified"
    CANCELED = "canceled"
    DEVICE_NOT_PRESENT = "device_not_present"
    NOT_CONFIGURED = "not_configured"
    DISABLED_BY_POLICY = "disabled_by_policy"
    DEVICE_BUSY = "device_busy"
    RETRIES_EXHAUSTED = "retries_exhausted"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


class LocalAuthBridge(Protocol):
    """Subset of :class:`flet_local_auth.FinanseLocalAuth` used by Finanse."""

    async def is_device_supported(self) -> bool: ...

    async def can_check_biometrics(self) -> bool: ...

    async def get_available_biometrics(self) -> list[str]: ...

    async def authenticate(
        self, *, reason: str, biometric_only: bool = True
    ) -> dict[str, Any]: ...


_local_auth_service: LocalAuthBridge | None = None


def set_local_auth_service(service: LocalAuthBridge | None) -> None:
    """Register the Flet local_auth service (Android / iOS builds)."""
    global _local_auth_service
    _local_auth_service = service


def get_local_auth_service() -> LocalAuthBridge | None:
    """Return the registered mobile auth service, if any."""
    return _local_auth_service


def biometric_env_override_ok() -> bool:
    """Test hook: ``FINANCE_BIOMETRIC_OK=1`` forces success."""
    return os.environ.get("FINANCE_BIOMETRIC_OK", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def mobile_runtime() -> bool:
    """True when Python runs inside a packaged Flet Android / iOS app."""
    try:
        from lib.core.config import _is_android, _is_ios

        if _is_ios() or _is_android():
            return True
    except Exception:  # noqa: BLE001
        pass
    platform = os.getenv("FLET_PLATFORM", "").strip().lower()
    if platform in {"android", "ios"}:
        return True
    if sys.platform in {"android", "ios"}:
        return True
    if sys.platform == "linux":
        try:
            import platform as py_platform

            if hasattr(py_platform, "android_ver"):
                info = py_platform.android_ver()
                if info and info.manufacturer:
                    return True
        except Exception:  # noqa: BLE001
            pass
    return False


def is_mobile_platform(page: "ft.Page | None" = None) -> bool:
    """Best-effort mobile detection (packaged runtime, env, or Flet page)."""
    if mobile_runtime():
        return True
    if page is None:
        return False
    try:
        if bool(getattr(page, "web", False)):
            # ``flet run --android`` is a web client — not a native mobile runtime.
            return False
    except Exception:  # noqa: BLE001
        pass
    try:
        from flet import PagePlatform

        platform = getattr(page, "platform", None)
        if platform in {
            PagePlatform.ANDROID,
            PagePlatform.ANDROID_TV,
            PagePlatform.IOS,
        }:
            return True
        token = str(getattr(platform, "value", platform) or "").strip().lower()
        return token in {"android", "android_tv", "ios"}
    except Exception:  # noqa: BLE001
        return False


def register_local_auth_service(page: "ft.Page") -> bool:
    """Attach the Flet local_auth bridge as a non-visual service."""
    if not is_mobile_platform(page):
        return False
    try:
        from flet_local_auth import FinanseLocalAuth

        from lib.infrastructure.services.flet_services import attach_page_service

        auth = FinanseLocalAuth()
        if not attach_page_service(page, auth):
            return False
        set_local_auth_service(auth)
        logger.info("Mobile biometric service registered (platform=%s)", page.platform)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Failed to register mobile biometric service")
        return False


def platform_supports_biometrics() -> bool:
    """True when this build can talk to an OS face/iris biometric API."""
    if biometric_env_override_ok():
        return True
    if _local_auth_service is not None:
        return True
    # Desktop: no face/iris bridge (Windows Hello may offer fingerprint).
    return False


def feature_biometrics_available() -> bool:
    """True when OS biometrics / Hello can be offered in Settings."""
    return platform_supports_biometrics()


def _map_mobile_auth_code(code: str | None) -> BiometricResult:
    """Map ``local_auth`` / PlatformException codes to :class:`BiometricResult`."""
    normalized = (code or "").strip().lower().replace("_", "")
    if normalized in {"usercanceled", "canceled", "cancel", "auth_in_progress"}:
        return BiometricResult.CANCELED
    if normalized in {
        "notavailable",
        "nobiometrichardware",
        "otheroperatingsystem",
        "nohardware",
    }:
        return BiometricResult.DEVICE_NOT_PRESENT
    if normalized in {"notenrolled", "passcodenotset", "biometricnotavailable"}:
        return BiometricResult.NOT_CONFIGURED
    if normalized in {"lockedout", "permanentlylockedout", "toomanyattempts"}:
        return BiometricResult.RETRIES_EXHAUSTED
    if normalized in {"systemcancel", "timeout"}:
        return BiometricResult.DEVICE_BUSY
    if normalized in {"notinteractive", "securityupdate_required"}:
        return BiometricResult.DISABLED_BY_POLICY
    return BiometricResult.FAILED


def _is_face_biometric(entry: str) -> bool:
    """True for Face ID / face / iris — fingerprint is intentionally excluded."""
    text = str(entry or "").strip().lower().replace("biometrictype.", "")
    if "fingerprint" in text or "finger" in text or "touch" in text:
        return False
    return "face" in text or "iris" in text


def has_face_unlock(biometrics: list[str] | None) -> bool:
    """Whether enrolled biometrics include Face ID (not fingerprint-only)."""
    return any(_is_face_biometric(item) for item in (biometrics or []))


async def _probe_mobile_status() -> BiometricStatus:
    service = _local_auth_service
    if service is None:
        return BiometricStatus.UNSUPPORTED
    try:
        if not await service.is_device_supported():
            return BiometricStatus.DEVICE_NOT_PRESENT
        if not await service.can_check_biometrics():
            return BiometricStatus.NOT_CONFIGURED
        biometrics = await service.get_available_biometrics()
        if not biometrics:
            return BiometricStatus.NOT_CONFIGURED
        # FinWise unlocks with Face ID + PIN only — ignore fingerprint-only devices.
        if not has_face_unlock(biometrics):
            logger.info(
                "Face unlock unavailable (enrolled=%s); PIN-only",
                biometrics,
            )
            return BiometricStatus.NOT_CONFIGURED
        return BiometricStatus.AVAILABLE
    except Exception:  # noqa: BLE001
        logger.exception("Mobile biometric availability check failed")
        return BiometricStatus.UNSUPPORTED


async def _request_mobile_verification(message: str) -> BiometricResult:
    service = _local_auth_service
    if service is None:
        return BiometricResult.UNSUPPORTED
    try:
        payload = await service.authenticate(reason=message, biometric_only=True)
    except Exception:  # noqa: BLE001
        logger.exception("Mobile biometric verification request failed")
        return BiometricResult.FAILED

    if payload.get("ok"):
        return BiometricResult.VERIFIED
    return _map_mobile_auth_code(payload.get("code"))


async def probe_biometric_status() -> BiometricStatus:
    """Ask the OS whether biometrics can be used."""
    if biometric_env_override_ok():
        return BiometricStatus.AVAILABLE
    if _local_auth_service is not None:
        status = await _probe_mobile_status()
        logger.info("Mobile biometric availability: %s", status.value)
        return status
    if mobile_runtime():
        logger.warning("Mobile runtime detected but local_auth service is missing")
        return BiometricStatus.UNSUPPORTED
    # Desktop (incl. Windows Hello): fingerprint can be offered by the OS.
    # FinWise policy is face/iris only — PIN unlock on desktop.
    return BiometricStatus.UNSUPPORTED


async def request_biometric_verification(message: str) -> BiometricResult:
    """Show the OS consent prompt (mobile Face ID / iris only)."""
    if biometric_env_override_ok():
        logger.info("Biometric accepted via FINANCE_BIOMETRIC_OK")
        return BiometricResult.VERIFIED

    if _local_auth_service is not None:
        result = await _request_mobile_verification(message)
        logger.info("Mobile biometric verification result: %s", result.value)
        return result

    if mobile_runtime():
        logger.warning("Mobile runtime detected but local_auth service is missing")
        return BiometricResult.UNSUPPORTED

    return BiometricResult.UNSUPPORTED


def status_is_usable(status: BiometricStatus) -> bool:
    """Whether we should auto-prompt / advertise biometrics as ready."""
    return status is BiometricStatus.AVAILABLE
