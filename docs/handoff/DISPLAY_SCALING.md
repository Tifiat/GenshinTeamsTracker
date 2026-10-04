# System display scaling

<!-- handoff-current: display-scaling -->
Reviewed 2026-10-04. Worker3 implements the AppShell Settings switch
"Use system scaling", default OFF, as an independent local stage. The choice
is saved with existing app settings and read by `ui.app_shell_smoke` before
importing AppShell/creating `QApplication`. Changes require an app restart.
The physical-width adaptive downscale remains unchanged. The legacy launcher
is unchanged; a future approved production switch must reuse this bootstrap.

36 focused tests PASS on 2026-10-04 using temporary settings and offscreen Qt.
Automated checks do not accept the user's physical 2K/150%, 1K/100% or
1366px RDP display paths.
No Computer Use, visible application launch or live account/settings write.
Clean-target integration, migration to the separate default-settings store
being developed in another chat, and final pre-MVP display acceptance remain
open in the [shared TODO](../../TODO.md).
<!-- /handoff-current -->

## Contract

- `run_workspace/display_settings.py` owns the typed accessor for
  `ui_use_system_scaling`, Boolean default `false`. It uses existing
  `run_workspace/app_settings.py` storage in this checkout's `settings.json`.
  Startup reads neither create nor rewrite a missing/corrupt settings file.
  An explicit saved value survives restart and writes preserve other keys.
  There is no second settings/defaults store in this stage.
- The localized Settings block follows the language selector, uses the shared
  vector toggle, wraps long labels, and always explains restart. Changing it
  saves the next-startup choice without rescaling a running window. Failed
  writes revert the switch and display a localized save error.
- On Windows, OFF sets `QT_ENABLE_HIGHDPI_SCALING=0` and `QT_FONT_DPI=96`.
  The first controls Qt geometry/DPR conversion from Windows logical DPI; the
  second prevents point-sized fonts from retaining Windows' increased DPI.
  Qt's Windows per-monitor DPI-awareness mode is left unchanged.
- ON sets `QT_ENABLE_HIGHDPI_SCALING=1` and removes `QT_FONT_DPI`, restoring
  Qt's Windows-DPI handling. In both states the saved choice takes precedence
  over inherited `QT_SCREEN_SCALE_FACTORS` and `QT_USE_PHYSICAL_DPI` (removed).
  Existing `GTT_UI_SCALE`/`QT_SCALE_FACTOR` app-scale override precedence stays
  intact. Non-Windows OS-scaling behavior is untouched.
- Physical screen width is detected before Qt starts using the existing native
  detector. Adaptive factor is `clamp(width / 1920, 0.60, 1.0)`; 1920px+
  is never enlarged by this adaptation. A 1366px display retains `0.711458`
  with either toggle value. Detection failure keeps the prior fallback and
  still applies the OS-scaling choice.
- At Windows 150%, OFF is intended to remove the additional 1.5 contribution;
  ON includes it. Text, icons, hit targets, screen bounds and column capacity
  require the user's real-monitor acceptance. The adaptive factor still uses
  the launch monitor; moving to a physically narrower display/RDP reconnect
  may require restart, as before this setting.

## Qt compatibility

The mechanism is source-reviewed against PySide6/Qt 6.11.0. Qt's
[High DPI documentation](https://doc.qt.io/qt-6.11/highdpi.html) documents the
opt-out as testing-only and discourages desktop font-DPI overrides; this app
uses them for the expressly requested Windows OS-scaling opt-out. Recheck this
contract and the display smoke when updating Qt or packaging the production
launcher. Native Wayland/macOS high-DPI opt-out is not implemented.

Source details: [independent platform/global scaling](https://github.com/qt/qtbase/blob/v6.11.0/src/gui/kernel/qhighdpiscaling.cpp),
[logical/font DPI override](https://github.com/qt/qtbase/blob/v6.11.0/src/gui/kernel/qplatformscreen.cpp),
[Windows theme fonts](https://github.com/qt/qtbase/blob/v6.11.0/src/plugins/platforms/windows/qwindowstheme.cpp).
An all-1 `QT_SCREEN_SCALE_FACTORS` list is not a replacement: Qt 6.11 only
activates that override when a factor differs from 1.

## Automated evidence, 2026-10-04

Validated with Python 3.11.5 and PySide6/Qt 6.11.0, reusing the main checkout's
dependency environment read-only. The suite has 36 passing tests.
The focused suite covers shared settings, this setting's persistence, the
existing app-scale policy, launcher ordering, Settings wiring/localization,
save failure and adjacent optimizer Settings behavior. Fresh subprocess probes
use Qt's [official offscreen configuration](https://github.com/qt/qtbase/blob/v6.11.0/src/plugins/platforms/offscreen/qoffscreenintegration.cpp)
with simulated native logical DPI 96/144. They show OFF yields DPR 1 and equal
point-font metrics at either DPI on a 2560px fixture; ON at 144 DPI yields
DPR 1.5; both states at 1366px/96 DPI retain DPR 0.711458 and a 1920px logical
screen. These tests exercise Qt's scaling path, not the Windows platform plugin
or native monitor detection. Configuration/settings files are temporary and
removed automatically, including on failure. The initial probe could not use
an absolute Windows config path because Qt splits platform options at ':';
the test now passes a relative path.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.run_workspace.test_app_settings tests.run_workspace.test_display_settings tests.ui.utils.test_app_scaling tests.ui.utils.test_startup_display_scaling tests.ui.utils.test_startup_display_scaling_qt tests.ui.right_panel.test_display_settings tests.ui.right_panel.test_gcsim_optimizer_settings
```

## User smoke and pre-MVP gate

1. Launch this checkout through `python -m ui.app_shell_smoke`. In Settings,
   check the new switch is OFF when no saved choice exists. Restart fully.
2. On the user's 2K/150% display, compare the same maximized Artifact Browser
   panel with their 1K/100% layout: column capacity, readable text/icons,
   accessible controls, clipping, hover/click alignment and popup placement.
3. Turn ON, restart, confirm Windows enlargement returns and the choice stays
   saved. Turn OFF, restart, confirm the previous OFF presentation returns.
4. On the 1366px RDP display at its previous scale, confirm prior layout and
   adaptive downscale are preserved. Check monitor moves and RDP reconnect;
   relaunch on that screen if the launch-monitor adaptation needs refreshing.
5. Before MVP, integrate the other chat's defaults store and register
   `ui_use_system_scaling: false` there. Verify missing-key defaults, any reset
   feature, migration preserving saved ON/OFF, and that the actual final
   launcher reads the choice before Qt. Repeat steps 1-4 on the integrated
   version. Default-store integration and user acceptance are separate gates.
