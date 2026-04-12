from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QWidget,
    QComboBox,
)

from app.storage.session import login, logout, get_current_user, is_admin
from app.storage.database import user_exists, create_user, verify_user, admin_exists, get_all_users, update_user_password, delete_user


class LoginDialog(QDialog):
    login_successful = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Authentication")
        self.setModal(True)
        self.setFixedSize(400, 300)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        title = QLabel("VISION")
        title.setObjectName("appTitle")
        title.setAlignment(QVBoxLayout().alignment())
        layout.addWidget(title)

        subtitle = QLabel("Enter your credentials")
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(subtitle)

        layout.addSpacing(20)

        self._stack = QStackedWidget()

        username_page = self._build_username_page()
        self._stack.addWidget(username_page)

        login_page = self._build_login_page()
        self._stack.addWidget(login_page)

        register_page = self._build_register_page()
        self._stack.addWidget(register_page)

        layout.addWidget(self._stack)

    def _build_username_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        self._username_edit = QLineEdit()
        self._username_edit.setPlaceholderText("Username")
        self._username_edit.setMinimumWidth(200)
        layout.addWidget(self._username_edit)

        self._next_btn = QPushButton("NEXT")
        self._next_btn.setObjectName("primaryButton")
        self._next_btn.clicked.connect(self._on_username_next)
        layout.addWidget(self._next_btn)

        self._username_edit.returnPressed.connect(self._on_username_next)
        
        return page

    def _build_login_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        self._login_username_label = QLabel()
        self._login_username_label.setObjectName("pageSubtitle")
        layout.addWidget(self._login_username_label)

        self._password_edit = QLineEdit()
        self._password_edit.setPlaceholderText("Password")
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self._password_edit)

        btn_layout = QHBoxLayout()
        
        back_btn = QPushButton("BACK")
        back_btn.setObjectName("secondaryButton")
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        btn_layout.addWidget(back_btn)

        self._login_btn = QPushButton("LOGIN")
        self._login_btn.setObjectName("primaryButton")
        self._login_btn.clicked.connect(self._on_login)
        btn_layout.addWidget(self._login_btn)

        layout.addLayout(btn_layout)

        self._password_edit.returnPressed.connect(self._on_login)

        return page

    def _build_register_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        self._register_username_label = QLabel()
        self._register_username_label.setObjectName("pageSubtitle")
        layout.addWidget(self._register_username_label)

        self._role_combo = QComboBox()
        self._role_combo.addItems(["user", "operator", "viewer"])
        layout.addWidget(self._role_combo)

        self._new_password_edit = QLineEdit()
        self._new_password_edit.setPlaceholderText("Create Password")
        self._new_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self._new_password_edit)

        self._confirm_password_edit = QLineEdit()
        self._confirm_password_edit.setPlaceholderText("Confirm Password")
        self._confirm_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self._confirm_password_edit)

        btn_layout = QHBoxLayout()
        
        back_btn = QPushButton("BACK")
        back_btn.setObjectName("secondaryButton")
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        btn_layout.addWidget(back_btn)

        self._register_btn = QPushButton("CREATE USER")
        self._register_btn.setObjectName("primaryButton")
        self._register_btn.clicked.connect(self._on_register)
        btn_layout.addWidget(self._register_btn)

        layout.addLayout(btn_layout)

        self._confirm_password_edit.returnPressed.connect(self._on_register)

        return page

    def _on_username_next(self):
        username = self._username_edit.text().strip()
        
        if not username:
            QMessageBox.warning(self, "Error", "Please enter a username")
            return

        self._current_username = username

        if user_exists(username):
            self._login_username_label.setText(f"Welcome back, {username}")
            self._password_edit.clear()
            self._stack.setCurrentIndex(1)
        else:
            if not admin_exists():
                self._register_username_label.setText(f"First admin: {username}\nCreate password to continue")
                self._role_combo.setCurrentText("admin")
                self._role_combo.setEnabled(False)
            else:
                user = get_current_user()
                if user and user.get("role") == "admin":
                    self._register_username_label.setText(f"Create new user: {username}")
                    self._role_combo.setCurrentText("user")
                    self._role_combo.setEnabled(True)
                else:
                    QMessageBox.warning(self, "Error", "User not found. Contact admin to create your account.")
                    return
            
            self._new_password_edit.clear()
            self._confirm_password_edit.clear()
            self._stack.setCurrentIndex(2)

    def _on_login(self):
        password = self._password_edit.text()

        if not password:
            QMessageBox.warning(self, "Error", "Please enter your password")
            return

        session = login(self._current_username, password)
        if session:
            self.accept()
            self.login_successful.emit()
        else:
            QMessageBox.warning(self, "Login Failed", "Invalid password")

    def _on_register(self):
        password = self._new_password_edit.text()
        confirm = self._confirm_password_edit.text()
        role = self._role_combo.currentText()

        if not password:
            QMessageBox.warning(self, "Error", "Please enter a password")
            return

        if len(password) < 4:
            QMessageBox.warning(self, "Error", "Password must be at least 4 characters")
            return

        if password != confirm:
            QMessageBox.warning(self, "Error", "Passwords do not match")
            return

        user = get_current_user()
        admin_id = user["id"] if user and user.get("role") == "admin" else None

        new_user = create_user(self._current_username, password, role, admin_id)
        if new_user:
            if role == "admin" or admin_id is None:
                session = login(self._current_username, password)
                if session:
                    self.accept()
                    self.login_successful.emit()
            else:
                QMessageBox.information(self, "Success", f"User '{self._current_username}' created with role '{role}'")
                self._stack.setCurrentIndex(0)
                self._username_edit.clear()
        else:
            QMessageBox.warning(self, "Error", "Failed to create user. Username may already exist.")

    def get_username(self):
        return getattr(self, '_current_username', '')


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
        f"Logout as {user.get('username', 'user')}?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )

    if reply == QMessageBox.StandardButton.Yes:
        logout()
        return True
    return False


def show_change_password_dialog(parent=None) -> bool:
    user = get_current_user()
    if not user:
        return False

    dialog = QDialog(parent)
    dialog.setWindowTitle("Change Password")
    dialog.setModal(True)
    dialog.setFixedSize(350, 200)

    layout = QVBoxLayout(dialog)
    layout.setSpacing(12)

    layout.addWidget(QLabel(f"Change password for: {user.get('username', 'user')}"))

    current_pass = QLineEdit()
    current_pass.setPlaceholderText("Current Password")
    current_pass.setEchoMode(QLineEdit.EchoMode.Password)
    layout.addWidget(current_pass)

    new_pass = QLineEdit()
    new_pass.setPlaceholderText("New Password")
    new_pass.setEchoMode(QLineEdit.EchoMode.Password)
    layout.addWidget(new_pass)

    confirm_pass = QLineEdit()
    confirm_pass.setPlaceholderText("Confirm New Password")
    confirm_pass.setEchoMode(QLineEdit.EchoMode.Password)
    layout.addWidget(confirm_pass)

    btn_layout = QHBoxLayout()
    cancel_btn = QPushButton("CANCEL")
    cancel_btn.setObjectName("secondaryButton")
    cancel_btn.clicked.connect(dialog.reject)
    btn_layout.addWidget(cancel_btn)

    save_btn = QPushButton("SAVE")
    save_btn.setObjectName("primaryButton")
    btn_layout.addWidget(save_btn)

    layout.addLayout(btn_layout)

    def on_save():
        if not current_pass.text():
            QMessageBox.warning(dialog, "Error", "Enter current password")
            return
        if not new_pass.text() or len(new_pass.text()) < 4:
            QMessageBox.warning(dialog, "Error", "New password must be at least 4 characters")
            return
        if new_pass.text() != confirm_pass.text():
            QMessageBox.warning(dialog, "Error", "New passwords do not match")
            return

        result = verify_user(user.get("username"), current_pass.text())
        if not result:
            QMessageBox.warning(dialog, "Error", "Current password is incorrect")
            return

        if update_user_password(user.get("id"), new_pass.text()):
            QMessageBox.information(dialog, "Success", "Password changed successfully")
            dialog.accept()
        else:
            QMessageBox.warning(dialog, "Error", "Failed to update password")

    save_btn.clicked.connect(on_save)

    dialog.exec()


def show_user_management_dialog(parent=None):
    user = get_current_user()
    if not user or user.get("role") != "admin":
        QMessageBox.warning(parent, "Access Denied", "Only admins can manage users")
        return

    dialog = QDialog(parent)
    dialog.setWindowTitle("User Management")
    dialog.setModal(True)
    dialog.setMinimumSize(600, 400)

    layout = QVBoxLayout(dialog)
    layout.setSpacing(12)

    layout.addWidget(QLabel("User Management"))
    layout.addSpacing(10)

    from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView

    table = QTableWidget()
    table.setColumnCount(5)
    table.setHorizontalHeaderLabels(["ID", "Username", "Role", "Created", "Actions"])
    table.horizontalHeader().setStretchLastSection(True)
    layout.addWidget(table)

    users = get_all_users()
    admin_id = user.get("id")

    for u in users:
        if u.id == admin_id:
            continue
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QTableWidgetItem(str(u.id)))
        table.setItem(row, 1, QTableWidgetItem(u.username))
        table.setItem(row, 2, QTableWidgetItem(u.role))
        table.setItem(row, 3, QTableWidgetItem(u.created_at.strftime("%Y-%m-%d") if u.created_at else "-"))

    btn_layout = QHBoxLayout()
    close_btn = QPushButton("CLOSE")
    close_btn.setObjectName("secondaryButton")
    close_btn.clicked.connect(dialog.accept)
    btn_layout.addWidget(close_btn)
    layout.addLayout(btn_layout)

    dialog.exec()