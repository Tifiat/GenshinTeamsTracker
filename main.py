import sys

if __name__ == "__main__":
    import atexit
    from run_workspace.profile_control import profile_supervisor_lock, profile_operation_lock
    _profile_supervisor_gate = profile_supervisor_lock()
    _profile_supervisor_gate.__enter__()
    atexit.register(lambda: _profile_supervisor_gate.__exit__(None, None, None))
    from run_workspace.profile_context import bootstrap_profile
    with profile_operation_lock():
        bootstrap_profile()

from PySide6.QtWidgets import QApplication

from ui.main_window import App


def main() -> None:
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
