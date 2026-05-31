from __future__ import annotations

import ctypes
import math
import os
import sys
from dataclasses import dataclass
from typing import Callable, MutableMapping


REFERENCE_SCREEN_WIDTH = 1920
MIN_AUTO_SCALE = 0.60
UI_SCALE_ENV = "GTT_UI_SCALE"
QT_SCALE_FACTOR_ENV = "QT_SCALE_FACTOR"
_PERF_TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class StartupScaleResult:
    detected_monitor_width: int | None
    reference_width: int
    scale: float | None
    action: str
    reason: str
    qt_scale_factor: str | None


def configure_startup_ui_scale(
    env: MutableMapping[str, str] | None = None,
    *,
    platform: str | None = None,
    monitor_width_detector: Callable[[], int | None] | None = None,
) -> StartupScaleResult:
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    override = env.get(UI_SCALE_ENV, "").strip()

    if override and override.casefold() != "auto":
        result = _configure_forced_scale(env, override)
        _log_scale_result(env, result)
        return result

    if not override and env.get(QT_SCALE_FACTOR_ENV, "").strip():
        result = StartupScaleResult(
            detected_monitor_width=None,
            reference_width=REFERENCE_SCREEN_WIDTH,
            scale=None,
            action="skipped",
            reason="existing_qt_scale_factor",
            qt_scale_factor=env.get(QT_SCALE_FACTOR_ENV),
        )
        _log_scale_result(env, result)
        return result

    if platform != "win32":
        result = StartupScaleResult(
            detected_monitor_width=None,
            reference_width=REFERENCE_SCREEN_WIDTH,
            scale=None,
            action="skipped",
            reason="unsupported_platform",
            qt_scale_factor=env.get(QT_SCALE_FACTOR_ENV),
        )
        _log_scale_result(env, result)
        return result

    detector = monitor_width_detector or detect_windows_monitor_width
    detected_width = detector()
    if not detected_width or detected_width <= 0:
        result = StartupScaleResult(
            detected_monitor_width=None,
            reference_width=REFERENCE_SCREEN_WIDTH,
            scale=None,
            action="skipped",
            reason="monitor_detection_failed",
            qt_scale_factor=env.get(QT_SCALE_FACTOR_ENV),
        )
        _log_scale_result(env, result)
        return result

    scale = max(
        MIN_AUTO_SCALE,
        min(1.0, detected_width / REFERENCE_SCREEN_WIDTH),
    )
    if scale >= 1.0:
        result = StartupScaleResult(
            detected_monitor_width=detected_width,
            reference_width=REFERENCE_SCREEN_WIDTH,
            scale=scale,
            action="skipped",
            reason="auto_no_downscale",
            qt_scale_factor=env.get(QT_SCALE_FACTOR_ENV),
        )
        _log_scale_result(env, result)
        return result

    qt_scale_factor = _format_scale(scale)
    env[QT_SCALE_FACTOR_ENV] = qt_scale_factor
    result = StartupScaleResult(
        detected_monitor_width=detected_width,
        reference_width=REFERENCE_SCREEN_WIDTH,
        scale=scale,
        action="set",
        reason="auto",
        qt_scale_factor=qt_scale_factor,
    )
    _log_scale_result(env, result)
    return result


def detect_windows_monitor_width() -> int | None:
    if sys.platform != "win32":
        return None

    try:
        user32 = ctypes.windll.user32
        _configure_user32_signatures(user32)
        point = _Point()
        if not user32.GetCursorPos(ctypes.byref(point)):
            point = _Point(0, 0)

        monitor = user32.MonitorFromPoint(point, _MONITOR_DEFAULTTOPRIMARY)
        if not monitor:
            return None

        info = _MonitorInfoExW()
        info.cbSize = ctypes.sizeof(_MonitorInfoExW)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None

        width = _display_mode_width(user32, info.szDevice)
        if width:
            return width

        # Fallback is sufficient for systems where display mode lookup is unavailable.
        fallback_width = info.rcMonitor.right - info.rcMonitor.left
        return fallback_width if fallback_width > 0 else None
    except (AttributeError, OSError):
        return None


def _configure_forced_scale(
    env: MutableMapping[str, str],
    override: str,
) -> StartupScaleResult:
    try:
        scale = float(override)
    except ValueError:
        scale = math.nan

    if not math.isfinite(scale) or scale <= 0:
        return StartupScaleResult(
            detected_monitor_width=None,
            reference_width=REFERENCE_SCREEN_WIDTH,
            scale=None,
            action="skipped",
            reason="invalid_forced_scale",
            qt_scale_factor=env.get(QT_SCALE_FACTOR_ENV),
        )

    scale = min(1.0, scale)
    qt_scale_factor = _format_scale(scale)
    env[QT_SCALE_FACTOR_ENV] = qt_scale_factor
    return StartupScaleResult(
        detected_monitor_width=None,
        reference_width=REFERENCE_SCREEN_WIDTH,
        scale=scale,
        action="set",
        reason="forced",
        qt_scale_factor=qt_scale_factor,
    )


def _format_scale(scale: float) -> str:
    return f"{scale:.6f}".rstrip("0").rstrip(".")


def _log_scale_result(
    env: MutableMapping[str, str],
    result: StartupScaleResult,
) -> None:
    if env.get("GTT_PERF_LOG", "").strip().casefold() not in _PERF_TRUE_VALUES:
        return

    detected_width = (
        result.detected_monitor_width
        if result.detected_monitor_width is not None
        else "-"
    )
    scale = f"{result.scale:.3f}" if result.scale is not None else "-"
    qt_scale_factor = result.qt_scale_factor or "-"
    print(
        "[PERF] app_startup_ui_scale"
        f" detected_monitor_width={detected_width}"
        f" reference_width={result.reference_width}"
        f" computed_scale={scale}"
        f" action={result.action}"
        f" reason={result.reason}"
        f" qt_scale_factor={qt_scale_factor}",
        flush=True,
    )


_CCHDEVICENAME = 32
_CCHFORMNAME = 32
_MONITOR_DEFAULTTOPRIMARY = 1
_ENUM_CURRENT_SETTINGS = 0xFFFFFFFF


class _Point(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
    ]


class _Rect(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MonitorInfoExW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", _Rect),
        ("rcWork", _Rect),
        ("dwFlags", ctypes.c_ulong),
        ("szDevice", ctypes.c_wchar * _CCHDEVICENAME),
    ]


class _DevModeW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * _CCHDEVICENAME),
        ("dmSpecVersion", ctypes.c_ushort),
        ("dmDriverVersion", ctypes.c_ushort),
        ("dmSize", ctypes.c_ushort),
        ("dmDriverExtra", ctypes.c_ushort),
        ("dmFields", ctypes.c_ulong),
        ("dmOrientation", ctypes.c_short),
        ("dmPaperSize", ctypes.c_short),
        ("dmPaperLength", ctypes.c_short),
        ("dmPaperWidth", ctypes.c_short),
        ("dmScale", ctypes.c_short),
        ("dmCopies", ctypes.c_short),
        ("dmDefaultSource", ctypes.c_short),
        ("dmPrintQuality", ctypes.c_short),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", ctypes.c_wchar * _CCHFORMNAME),
        ("dmLogPixels", ctypes.c_ushort),
        ("dmBitsPerPel", ctypes.c_ulong),
        ("dmPelsWidth", ctypes.c_ulong),
        ("dmPelsHeight", ctypes.c_ulong),
        ("dmDisplayFlags", ctypes.c_ulong),
        ("dmDisplayFrequency", ctypes.c_ulong),
        ("dmICMMethod", ctypes.c_ulong),
        ("dmICMIntent", ctypes.c_ulong),
        ("dmMediaType", ctypes.c_ulong),
        ("dmDitherType", ctypes.c_ulong),
        ("dmReserved1", ctypes.c_ulong),
        ("dmReserved2", ctypes.c_ulong),
        ("dmPanningWidth", ctypes.c_ulong),
        ("dmPanningHeight", ctypes.c_ulong),
    ]


def _display_mode_width(user32, device_name: str) -> int | None:
    mode = _DevModeW()
    mode.dmSize = ctypes.sizeof(_DevModeW)
    if not user32.EnumDisplaySettingsW(
        device_name,
        _ENUM_CURRENT_SETTINGS,
        ctypes.byref(mode),
    ):
        return None
    return int(mode.dmPelsWidth) if mode.dmPelsWidth > 0 else None


def _configure_user32_signatures(user32) -> None:
    user32.GetCursorPos.argtypes = [ctypes.POINTER(_Point)]
    user32.GetCursorPos.restype = ctypes.c_bool
    user32.MonitorFromPoint.argtypes = [_Point, ctypes.c_ulong]
    user32.MonitorFromPoint.restype = ctypes.c_void_p
    user32.GetMonitorInfoW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_MonitorInfoExW),
    ]
    user32.GetMonitorInfoW.restype = ctypes.c_bool
    user32.EnumDisplaySettingsW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.POINTER(_DevModeW),
    ]
    user32.EnumDisplaySettingsW.restype = ctypes.c_bool
