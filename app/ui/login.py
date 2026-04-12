from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.storage.session import login, logout, get_current_user


class LoginDialog(QDialog):
    login_successful = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Login")
        self.setModal(True)
        self.setFixedSize(350, 180)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setSpacing(12)

        self._username_edit = QLineEdit()
        self._username_edit.setPlaceholderText("Username")
        self._username_edit.setMinimumWidth(200)

        self._password_edit = QLineEdit()
        self._password_edit.setPlaceholderText("Password")
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_edit.setMinimumWidth(200)

        form.addRow("Username:", self._username_edit)
        form.addRow("Password:", self._password_edit)

        layout.addLayout(form)

        self._login_btn = QPushButton("Login")
        self._login_btn.setDefault(True)
        self._login_btn.clicked.connect(self._on_login)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self._login_btn)
        btn_layout.addWidget(self._cancel_btn)

        layout.addLayout(btn_layout)

        self._username_edit.returnPressed.connect(self._on_login)
        self._password_edit.returnPressed.connect(self._on_login)

    def _on_login(self):
        username = self._username_edit.text().strip()
        password = self._password_edit.text()

        if not username or not password:
            QMessageBox.warning(self, "Error", "Please enter username and password")
            return

        session = login(username, password)
        if session:
            self.accept()
            self.login_successful.emit()
        else:
            QMessageBox.warning(self, "Login Failed", "Invalid username or password")

    def get_username(self):
        return self._username_edit.text().strip()


def show_login_dialog(parent=None) -> bool:
    dialog = LoginDialog(parent)
    result = dialog.exec()
    return result == QDialog.DialogCode.Accepted


def show_logout_dialog(parent=None) -> bool:
    user = get_current_user()
    if not user:
        return False

    reply = QMessageBox.question(
        parent,
        "Logout",
        f"Logout as {user.username}?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )

    if reply == QMessageBox.StandardButton.Yes:
        logout()
        return True
    return False