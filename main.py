import os
import sys
import warnings

# Clean up console output for professional presentation
os.environ["GLOG_minloglevel"] = "2"
os.environ["PD_LOG_LEVEL"] = "2"
warnings.filterwarnings("ignore", category=UserWarning, module="paddle")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

from app.storage import init_storage
from app.storage.database import init_db
from app.services.app_runtime import load_ui_settings
from app.ui.main_window import MainWindow
from app.ui.theme import generate_stylesheet, Theme


def main():
    init_storage()
    init_db()
    
    app = QApplication(sys.argv)
    
    # Load and apply saved theme
    settings = load_ui_settings()
    theme = settings.get("theme", "dark").lower()
    try:
        theme_enum = Theme(theme)
    except ValueError:
        theme_enum = Theme.DARK
    
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    stylesheet = generate_stylesheet(theme_enum)
    app.setStyleSheet(stylesheet)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
