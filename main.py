import sys

from PySide6.QtWidgets import QApplication

from ui.main_window import App


def main() -> None:
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
