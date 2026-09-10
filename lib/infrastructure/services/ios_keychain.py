"""Synchronous iOS Keychain access for the secret-box master key.

Uses Security.framework via ctypes so it works before Flet services start.
Desktop and Android never call into Keychain; tests can swap in a memory store.
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import (
    POINTER,
    byref,
    c_char_p,
    c_int32,
    c_long,
    c_uint32,
    c_void_p,
)
from typing import Optional

logger = logging.getLogger("finanse.infrastructure.services.ios_keychain")

SERVICE = "com.finanse.app.secret_box"
ACCOUNT = "master_key"

errSecSuccess = 0
errSecItemNotFound = -25300
errSecDuplicateItem = -25299

kCFStringEncodingUTF8 = 0x08000100

OSStatus = c_int32
CFTypeRef = c_void_p
CFIndex = c_long

# In-process store for unit tests (Linux CI cannot load Security.framework).
_memory_store: dict[str, bytes] | None = None
_libs: tuple[ctypes.CDLL, ctypes.CDLL] | None | bool = False


def use_memory_backend(enable: bool = True) -> dict[str, bytes] | None:
    """Install (or clear) a dict-backed Keychain for tests. Returns the store."""
    global _memory_store
    if enable:
        _memory_store = {}
        return _memory_store
    _memory_store = None
    return None


def _ios() -> bool:
    try:
        from lib.core.config import _is_ios

        return bool(_is_ios())
    except Exception:  # noqa: BLE001
        return False


def keychain_available() -> bool:
    """True when this process should persist the master key in iOS Keychain."""
    return _ios()


def _slot() -> str:
    return f"{SERVICE}:{ACCOUNT}"


def get_generic_password() -> bytes | None:
    """Return the stored key, or ``None`` if missing / unavailable."""
    if not keychain_available():
        return None
    if _memory_store is not None:
        data = _memory_store.get(_slot())
        return bytes(data) if data else None
    try:
        return _sec_copy()
    except Exception:  # noqa: BLE001
        logger.debug("Keychain read failed", exc_info=True)
        return None


def set_generic_password(data: bytes) -> bool:
    """Create or replace the Keychain item. ``False`` if Keychain is unusable."""
    if not data:
        return False
    if not keychain_available():
        return False
    payload = bytes(data)
    if _memory_store is not None:
        _memory_store[_slot()] = payload
        return True
    try:
        return _sec_set(payload)
    except Exception:  # noqa: BLE001
        logger.debug("Keychain write failed", exc_info=True)
        return False


def delete_generic_password() -> bool:
    """Remove the Keychain item. ``True`` when an item was deleted."""
    if not keychain_available():
        return False
    if _memory_store is not None:
        return _memory_store.pop(_slot(), None) is not None
    try:
        return _sec_delete()
    except Exception:  # noqa: BLE001
        logger.debug("Keychain delete failed", exc_info=True)
        return False


def _load_frameworks() -> tuple[ctypes.CDLL, ctypes.CDLL] | None:
    global _libs
    if _libs is False:
        try:
            sec = ctypes.cdll.LoadLibrary(
                "/System/Library/Frameworks/Security.framework/Security"
            )
            cf = ctypes.cdll.LoadLibrary(
                "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
            )
            _libs = (sec, cf)
        except OSError:
            logger.debug("Security/CoreFoundation not available", exc_info=True)
            _libs = None
    return _libs if isinstance(_libs, tuple) else None


def _bind() -> tuple[ctypes.CDLL, ctypes.CDLL]:
    libs = _load_frameworks()
    if libs is None:
        raise RuntimeError("Security.framework unavailable")
    return libs


def _cf_str(cf: ctypes.CDLL, text: str) -> CFTypeRef:
    cf.CFStringCreateWithCString.restype = CFTypeRef
    cf.CFStringCreateWithCString.argtypes = [c_void_p, c_char_p, c_uint32]
    ref = cf.CFStringCreateWithCString(None, text.encode("utf-8"), kCFStringEncodingUTF8)
    if not ref:
        raise RuntimeError("CFStringCreateWithCString failed")
    return ref


def _cf_data(cf: ctypes.CDLL, payload: bytes) -> CFTypeRef:
    cf.CFDataCreate.restype = CFTypeRef
    cf.CFDataCreate.argtypes = [c_void_p, c_char_p, CFIndex]
    buf = ctypes.create_string_buffer(payload, len(payload))
    ref = cf.CFDataCreate(None, buf, len(payload))
    if not ref:
        raise RuntimeError("CFDataCreate failed")
    return ref


def _cf_release(cf: ctypes.CDLL, ref: Optional[CFTypeRef]) -> None:
    if not ref:
        return
    cf.CFRelease.argtypes = [CFTypeRef]
    cf.CFRelease(ref)


def _cf_dict(cf: ctypes.CDLL, pairs: list[tuple[CFTypeRef, CFTypeRef]]) -> CFTypeRef:
    n = len(pairs)
    keys = (CFTypeRef * n)(*(k for k, _ in pairs))
    vals = (CFTypeRef * n)(*(v for _, v in pairs))
    cf.CFDictionaryCreate.restype = CFTypeRef
    cf.CFDictionaryCreate.argtypes = [
        c_void_p,
        POINTER(CFTypeRef),
        POINTER(CFTypeRef),
        CFIndex,
        c_void_p,
        c_void_p,
    ]
    # Exported CF callback tables are structs; take the symbol address.
    key_cb = ctypes.addressof(ctypes.c_char.in_dll(cf, "kCFTypeDictionaryKeyCallBacks"))
    val_cb = ctypes.addressof(ctypes.c_char.in_dll(cf, "kCFTypeDictionaryValueCallBacks"))
    ref = cf.CFDictionaryCreate(None, keys, vals, n, key_cb, val_cb)
    if not ref:
        raise RuntimeError("CFDictionaryCreate failed")
    return ref


def _bool_true(cf: ctypes.CDLL) -> CFTypeRef:
    return c_void_p.in_dll(cf, "kCFBooleanTrue")


def _query_pairs(
    cf: ctypes.CDLL,
    *,
    with_data: bool = False,
    with_value: bytes | None = None,
    accessible: bool = False,
) -> tuple[list[tuple[CFTypeRef, CFTypeRef]], list[CFTypeRef]]:
    """Build Keychain query pairs; caller CFReleases ``owned`` refs (not CFBoolean)."""
    owned: list[CFTypeRef] = []

    def s(text: str) -> CFTypeRef:
        ref = _cf_str(cf, text)
        owned.append(ref)
        return ref

    pairs: list[tuple[CFTypeRef, CFTypeRef]] = [
        (s("class"), s("genp")),
        (s("svce"), s(SERVICE)),
        (s("acct"), s(ACCOUNT)),
    ]
    if with_value is not None:
        data = _cf_data(cf, with_value)
        owned.append(data)
        pairs.append((s("v_Data"), data))
    if with_data:
        pairs.append((s("r_Data"), _bool_true(cf)))
        pairs.append((s("m_Limit"), s("m_LimitOne")))
    if accessible:
        # After first unlock, this device only — not synced via iCloud Keychain.
        pairs.append((s("pdmn"), s("cku")))
    return pairs, owned


def _sec_copy() -> bytes | None:
    sec, cf = _bind()
    pairs, owned = _query_pairs(cf, with_data=True)
    query = None
    result = CFTypeRef()
    try:
        query = _cf_dict(cf, pairs)
        sec.SecItemCopyMatching.restype = OSStatus
        sec.SecItemCopyMatching.argtypes = [CFTypeRef, POINTER(CFTypeRef)]
        status = int(sec.SecItemCopyMatching(query, byref(result)))
        if status == errSecItemNotFound:
            return None
        if status != errSecSuccess or not result:
            raise RuntimeError(f"SecItemCopyMatching status={status}")
        cf.CFDataGetLength.restype = CFIndex
        cf.CFDataGetLength.argtypes = [CFTypeRef]
        cf.CFDataGetBytePtr.restype = ctypes.POINTER(ctypes.c_ubyte)
        cf.CFDataGetBytePtr.argtypes = [CFTypeRef]
        length = int(cf.CFDataGetLength(result))
        ptr = cf.CFDataGetBytePtr(result)
        return bytes(ptr[:length]) if length else b""
    finally:
        _cf_release(cf, result)
        _cf_release(cf, query)
        for ref in owned:
            _cf_release(cf, ref)


def _sec_delete() -> bool:
    sec, cf = _bind()
    pairs, owned = _query_pairs(cf)
    query = None
    try:
        query = _cf_dict(cf, pairs)
        sec.SecItemDelete.restype = OSStatus
        sec.SecItemDelete.argtypes = [CFTypeRef]
        status = int(sec.SecItemDelete(query))
        if status == errSecItemNotFound:
            return False
        if status != errSecSuccess:
            raise RuntimeError(f"SecItemDelete status={status}")
        return True
    finally:
        _cf_release(cf, query)
        for ref in owned:
            _cf_release(cf, ref)


def _sec_set(payload: bytes) -> bool:
    sec, cf = _bind()
    sec.SecItemAdd.restype = OSStatus
    sec.SecItemAdd.argtypes = [CFTypeRef, POINTER(CFTypeRef)]
    sec.SecItemUpdate.restype = OSStatus
    sec.SecItemUpdate.argtypes = [CFTypeRef, CFTypeRef]
    add_pairs, add_owned = _query_pairs(cf, with_value=payload, accessible=True)
    query_pairs, query_owned = _query_pairs(cf)
    attrs_pairs, attrs_owned = _query_pairs(cf, with_value=payload)
    add_dict = query_dict = attrs_dict = None
    try:
        add_dict = _cf_dict(cf, add_pairs)
        status = int(sec.SecItemAdd(add_dict, None))
        if status == errSecSuccess:
            return True
        if status != errSecDuplicateItem:
            raise RuntimeError(f"SecItemAdd status={status}")
        query_dict = _cf_dict(cf, query_pairs)
        attrs_dict = _cf_dict(cf, attrs_pairs)
        updated = int(sec.SecItemUpdate(query_dict, attrs_dict))
        if updated != errSecSuccess:
            raise RuntimeError(f"SecItemUpdate status={updated}")
        return True
    finally:
        _cf_release(cf, add_dict)
        _cf_release(cf, query_dict)
        _cf_release(cf, attrs_dict)
        for ref in add_owned + query_owned + attrs_owned:
            _cf_release(cf, ref)
