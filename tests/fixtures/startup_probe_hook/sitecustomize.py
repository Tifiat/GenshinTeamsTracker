"""Opt-in smoke hook: real launcher/constructors, then close its visible window.

Only the diagnostic command adds this directory to PYTHONPATH. Nothing replaces
profile selection, migration, domain imports or widget construction. The
supervised AppShell child inherits the same hook, so the normal CLI is tested.
"""
import json
import os


_entry = os.environ.get("GTT_STARTUP_PROBE_ENTRY")
if _entry in {"main", "app_shell"}:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    _original_init = QApplication.__init__
    _expected_class = "App" if _entry == "main" else "AppShell"
    _checks = 0

    def _report_and_close():
        global _checks
        _checks += 1
        app = QApplication.instance()
        windows = [w for w in app.topLevelWidgets()
                   if type(w).__name__ == _expected_class and w.isVisible()]
        passed = len(windows) == 1
        if not passed and _checks < 45:
            return
        _startup_timer.stop()
        print("GTT_STARTUP_PROBE " + json.dumps({
            "entry": _entry, "pid": os.getpid(), "window_ready": passed,
            "window_class": _expected_class, "visible_windows": len(windows),
            "window_title": windows[0].windowTitle() if passed else "",
            "bootstrap_and_constructors_unmodified": True,
        }, ensure_ascii=False), flush=True)
        if passed:
            windows[0].close()
        else:
            app.exit(2)

    def _probe_init(self, *args, **kwargs):
        global _startup_timer
        _original_init(self, *args, **kwargs)
        _startup_timer = QTimer(self)
        _startup_timer.timeout.connect(_report_and_close)
        _startup_timer.start(1000)

    QApplication.__init__ = _probe_init
