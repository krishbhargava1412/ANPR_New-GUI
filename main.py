import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

from app.storage import init_storage
from app.storage.database import init_db
from app.ui.main_window import MainWindow
from app.ui.styles import STYLESHEET


def main():
    init_storage()
    init_db()
    
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
