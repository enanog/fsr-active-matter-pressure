import sys

from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1:
        win.open_video(sys.argv[1])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
