import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

from app.ui.main_window import MainWindow
from app.ui.styles import STYLESHEET


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)

    font = QFont()
    font.setPointSize(10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
