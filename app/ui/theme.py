from __future__ import annotations

from enum import Enum
from typing import Literal


class Theme(Enum):
    DARK = "dark"
    LIGHT = "light"

def get_theme_colors(theme: Theme | str) -> dict[str, str]:
    """Material + Neumorphic grayscale palette with correct elevation (background darker than components)."""
    if isinstance(theme, str):
        theme = Theme(theme)

    if theme == Theme.DARK:
        return {
            # Base (background darkest → components lighter)
            "bg_primary": "#000000",
            "bg_secondary": "#0a0a0a",
            "bg_tertiary": "#121212",
            "bg_hover": "#1a1a1a",

            # Text
            "text_primary": "#ffffff",
            "text_secondary": "#d4d4d4",
            "text_tertiary": "#a3a3a3",
            "text_muted": "#737373",

            # Borders
            "border_primary": "#1c1c1c",
            "border_secondary": "#262626",
            "border_tertiary": "#141414",

            # Accent (neutral grayscale)
            "accent": "#2e2e2e",
            "accent_hover": "#3a3a3a",
            "accent_pressed": "#242424",

            # Semantic (still neutral)
            "success": "#3a3a3a",
            "warning": "#4a4a4a",
            "error": "#2a2a2a",
            "error_hover": "#1a1a1a",

            # Status
            "status_active": "#4a4a4a",
            "status_inactive": "#2a2a2a",
            "status_error": "#2a2a2a",

            # Surfaces (lighter than bg → correct elevation)
            "input_bg": "#141414",
            "card_bg": "#181818",
            "log_bg": "#101010",

            # Neumorphic shadows (inset contrast)
            "shadow_light": "rgba(255,255,255,0.05)",
            "shadow_dark": "rgba(0,0,0,0.95)",
        }

    else:
        return {
            # Base (background light → components slightly darker)
            "bg_primary": "#f5f5f5",
            "bg_secondary": "#eeeeee",
            "bg_tertiary": "#e4e4e4",
            "bg_hover": "#dadada",

            # Text
            "text_primary": "#0f0f0f",
            "text_secondary": "#404040",
            "text_tertiary": "#6b6b6b",
            "text_muted": "#9a9a9a",

            # Borders
            "border_primary": "#dcdcdc",
            "border_secondary": "#cfcfcf",
            "border_tertiary": "#e8e8e8",

            # Accent
            "accent": "#3a3a3a",
            "accent_hover": "#2a2a2a",
            "accent_pressed": "#1f1f1f",

            # Semantic
            "success": "#4a4a4a",
            "warning": "#6a6a6a",
            "error": "#2a2a2a",
            "error_hover": "#1a1a1a",

            # Status
            "status_active": "#4a4a4a",
            "status_inactive": "#cfcfcf",
            "status_error": "#2a2a2a",

            # Surfaces (darker than background → elevation)
            "input_bg": "#ffffff",
            "card_bg": "#ffffff",
            "log_bg": "#fafafa",

            # Neumorphic shadows
            "shadow_light": "rgba(255,255,255,0.9)",
            "shadow_dark": "rgba(0,0,0,0.08)",
        }

def generate_stylesheet(theme: Theme | str) -> str:
    """Generate complete stylesheet for the specified theme."""
    if isinstance(theme, str):
        theme = Theme(theme)
    
    colors = get_theme_colors(theme)
    
    # Define stylesheet template with color placeholders
    stylesheet = f"""
* {{
    font-family: 'Segoe UI', 'SF Pro Display', 'Helvetica Neue', sans-serif;
}}

QMainWindow {{
    background-color: {colors['bg_primary']};
}}

QWidget#centralWidget {{
    background-color: {colors['bg_primary']};
}}

/* Sidebar */
QWidget#sidebar {{
    background-color: {colors['bg_secondary']};
    border-right: 1px solid {colors['border_primary']};
}}

QLabel#appTitle {{
    color: {colors['text_primary']};
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 2px;
    padding: 0px;
}}

QLabel#appSubtitle {{
    color: {colors['text_muted']};
    font-size: 10px;
    letter-spacing: 3px;
    font-weight: 400;
}}

QFrame#sidebarAccountButton {{
    background-color: {colors['bg_tertiary']};
    border: 1px solid {colors['border_primary']};
    border-radius: 10px;
}}

QPushButton#sidebarAccountTextButton {{
    background-color: transparent;
    border: none;
    text-align: left;
    padding: 2px 0;
}}

QPushButton#sidebarAccountTextButton:hover {{
    background-color: transparent;
}}

QFrame#sidebarAccountButton:hover {{
    border-color: {colors['border_secondary']};
    background-color: {colors['bg_hover']};
}}

QPushButton#avatarButton {{
    background-color: {colors['accent']};
    color: {colors['bg_primary']};
    border: none;
    border-radius: 19px;
    font-size: 12px;
    font-weight: 800;
}}

QPushButton#avatarButton:hover {{
    background-color: {colors['accent_hover']};
}}

QMenu {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_primary']};
    border: 1px solid {colors['border_primary']};
    border-radius: 12px;
    padding: 8px;
}}

QMenu::item {{
    padding: 10px 14px;
    border-radius: 8px;
    background-color: transparent;
}}

QMenu::item:selected {{
    background-color: {colors['bg_hover']};
    color: {colors['text_primary']};
}}

QMenu::item:disabled {{
    color: {colors['text_tertiary']};
    background-color: transparent;
}}

QMenu::separator {{
    height: 1px;
    background: {colors['border_primary']};
    margin: 6px 8px;
}}

QPushButton#navButton {{
    background-color: transparent;
    color: {colors['text_muted']};
    border: none;
    border-radius: 6px;
    padding: 10px 14px;
    text-align: left;
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.5px;
}}

QPushButton#navButton:hover {{
    background-color: {colors['bg_hover']};
    color: {colors['text_secondary']};
}}

QPushButton#navButton[active="true"] {{
    background-color: {colors['bg_hover']};
    color: {colors['text_primary']};
    border-left: 2px solid {colors['accent']};
}}

QLabel#sectionLabel {{
    color: {colors['text_tertiary']};
    font-size: 9px;
    letter-spacing: 2px;
    font-weight: 600;
    padding: 0px 14px;
}}

QLabel#settingsFieldLabel {{
    color: {colors['text_tertiary']};
    font-size: 11px;
    font-weight: 500;
}}

/* Main content */
QWidget#contentArea {{
    background-color: {colors['bg_primary']};
}}

QLabel#pageTitle {{
    color: {colors['text_primary']};
    font-size: 22px;
    font-weight: 700;
    letter-spacing: -0.5px;
}}

QLabel#pageSubtitle {{
    color: {colors['text_tertiary']};
    font-size: 12px;
    letter-spacing: 0.3px;
}}

QLabel#validationLabel {{
    color: {colors['warning']};
    font-size: 11px;
    font-weight: 600;
}}

QFrame#tickerBar {{
    background-color: {colors['bg_tertiary']};
    border: 1px solid {colors['border_primary']};
    border-radius: 8px;
}}

QLabel#tickerLabel {{
    color: {colors['text_secondary']};
    font-size: 12px;
    font-weight: 600;
}}

QLabel#alertBanner {{
    background-color: {colors['bg_tertiary']};
    border: 1px solid {colors['border_primary']};
    border-radius: 10px;
    color: {colors['text_primary']};
    padding: 0 14px;
    font-size: 12px;
    font-weight: 700;
}}

QLabel#alertBanner[state="alert"] {{
    background-color: rgba(239, 68, 68, 0.18);
    border-color: {colors['error']};
    color: #ffdede;
}}

QLabel#alertBanner[state="tracking"] {{
    background-color: rgba(34, 197, 94, 0.14);
    border-color: {colors['success']};
}}

QFrame#monitorPanel {{
    background-color: {colors['bg_secondary']};
    border: 1px solid {colors['border_primary']};
    border-radius: 8px;
}}

QLabel#panelTitle {{
    color: {colors['text_primary']};
    font-size: 14px;
    font-weight: 700;
}}

QFrame#monitorMetricCard {{
    background-color: {colors['bg_secondary']};
    border: 1px solid {colors['border_primary']};
    border-radius: 8px;
}}

QLabel#metricValue {{
    color: {colors['text_primary']};
    font-size: 20px;
    font-weight: 700;
}}

QLabel#metricLabel {{
    color: {colors['text_tertiary']};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.4px;
}}

/* Drop zone */
QLabel#dropZone {{
    background-color: {colors['bg_secondary']};
    border: 1px solid {colors['border_primary']};
    border-radius: 12px;
    color: {colors['text_tertiary']};
    font-size: 13px;
    letter-spacing: 0.5px;
}}

QLabel#dropZone:hover {{
    border-color: {colors['border_secondary']};
    color: {colors['text_muted']};
}}

/* Primary button */
QPushButton#primaryButton {{
    background-color: {colors['accent']};
    color: {colors['bg_primary']};
    border: none;
    border-radius: 8px;
    padding: 12px 28px;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1px;
}}

QPushButton#primaryButton:hover {{
    background-color: {colors['accent_hover']};
}}

QPushButton#primaryButton:pressed {{
    background-color: {colors['accent_pressed']};
}}

/* Secondary button */
QPushButton#secondaryButton {{
    background-color: transparent;
    color: {colors['text_muted']};
    border: 1px solid {colors['border_primary']};
    border-radius: 8px;
    padding: 12px 20px;
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.5px;
}}

QPushButton#secondaryButton:hover {{
    border-color: {colors['border_secondary']};
    color: {colors['text_secondary']};
}}

/* Status bar */
QStatusBar {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_tertiary']};
    font-size: 11px;
    border-top: 1px solid {colors['border_tertiary']};
}}

/* Stats card */
QWidget#statCard {{
    background-color: {colors['bg_secondary']};
    border: 1px solid {colors['border_tertiary']};
    border-radius: 10px;
}}

QLabel#statValue {{
    color: {colors['text_primary']};
    font-size: 26px;
    font-weight: 700;
}}

QLabel#statLabel {{
    color: {colors['text_tertiary']};
    font-size: 10px;
    letter-spacing: 1.5px;
    font-weight: 500;
}}

QLabel#statAccent {{
    color: {colors['accent']};
    font-size: 10px;
    font-weight: 600;
}}

/* Log panel */
QWidget#logPanel {{
    background-color: {colors['bg_secondary']};
    border: 1px solid {colors['border_tertiary']};
    border-radius: 8px;
}}

QWidget#logHeader {{
    background-color: {colors['bg_tertiary']};
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}}

QLabel#logHeaderTitle {{
    color: {colors['text_tertiary']};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
}}

QLabel#logCount {{
    color: {colors['accent']};
    font-size: 11px;
    font-weight: 700;
    padding-left: 6px;
}}

QPushButton#logClearButton {{
    background-color: transparent;
    color: {colors['text_tertiary']};
    border: 1px solid {colors['border_primary']};
    border-radius: 3px;
    padding: 0px 8px;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}

QPushButton#logClearButton:hover {{
    border-color: {colors['border_secondary']};
    color: {colors['text_secondary']};
}}

QWidget#logColHeader {{
    background-color: {colors['bg_primary']};
}}

QLabel#logColLabel {{
    color: {colors['text_tertiary']};
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 1.5px;
}}

QWidget#logEntry {{
    background-color: {colors['bg_secondary']};
    border-bottom: 1px solid {colors['border_tertiary']};
}}

QWidget#logEntry:hover {{
    background-color: {colors['bg_tertiary']};
}}

QWidget#logEntry[severity="alert"] {{
    background-color: rgba(239, 68, 68, 0.12);
}}

QWidget#logEntry[severity="warning"] {{
    background-color: rgba(245, 158, 11, 0.10);
}}

QLabel#logTime {{
    color: {colors['text_tertiary']};
    font-size: 11px;
    font-family: monospace;
}}

QLabel#logCam {{
    color: {colors['text_muted']};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}

QLabel#logPlate {{
    color: {colors['accent']};
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 2px;
    font-family: monospace;
}}

QLabel#logConf {{
    color: {colors['text_tertiary']};
    font-size: 10px;
}}

QWidget#logEntry[selected="true"] {{
    border-left: 3px solid {colors['accent']};
    background-color: {colors['bg_hover']};
}}

QScrollArea#logScroll {{
    background-color: transparent;
    border: none;
}}

QWidget#logList {{
    background-color: transparent;
}}

/* Feed widget */
QLabel#feedWidget {{
    background-color: {colors['log_bg']};
    color: {colors['text_tertiary']};
    font-size: 12px;
    letter-spacing: 1px;
    border: 1px solid {colors['border_tertiary']};
    border-radius: 12px;
}}

/* Detection box styling */
QFrame#detectionBox {{
    background-color: transparent;
    border: 2px solid {colors['border_tertiary']};
    border-radius: 8px;
}}

QFrame#detectionBox[state="scanning"] {{
    border-color: {colors['warning']};
    border-radius: 10px;
}}

QFrame#detectionBox[state="confirmed"] {{
    border-color: {colors['success']};
    border-radius: 10px;
}}

/* Detection splitter handle */
QSplitter#detectionSplitter::handle {{
    background-color: {colors['border_tertiary']};
    width: 1px;
}}

/* Camera tile */
QWidget#cameraTile {{
    background-color: {colors['bg_secondary']};
    border: 1px solid {colors['border_primary']};
    border-radius: 8px;
}}

QWidget#cameraTile[selected="true"] {{
    border: 1px solid {colors['accent']};
}}

QWidget#cameraTileBar {{
    background-color: {colors['bg_tertiary']};
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    border-bottom: 1px solid {colors['border_primary']};
}}

QLabel#cameraTileTitle {{
    color: {colors['text_muted']};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.5px;
}}

QLabel#cameraState {{
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 10px;
    font-weight: 700;
}}

QLabel#cameraState[status="live"] {{
    background-color: rgba(34, 197, 94, 0.16);
    color: {colors['success']};
}}

QLabel#cameraState[status="lost"] {{
    background-color: rgba(239, 68, 68, 0.16);
    color: {colors['error']};
}}

QLabel#cameraState[status="idle"] {{
    background-color: rgba(148, 163, 184, 0.16);
    color: {colors['text_tertiary']};
}}

QLabel#cameraFrameLabel {{
    background-color: {colors['log_bg']};
    color: {colors['text_tertiary']};
    font-size: 11px;
    letter-spacing: 1px;
}}

QWidget#cameraTileFooter {{
    background-color: {colors['bg_secondary']};
    border-top: 1px solid {colors['border_tertiary']};
    border-bottom-left-radius: 8px;
    border-bottom-right-radius: 8px;
}}

QLabel#cameraMeta {{
    color: {colors['text_secondary']};
    font-size: 10px;
    font-weight: 600;
}}

QPushButton#tileSelectButton {{
    background-color: transparent;
    color: {colors['text_tertiary']};
    border: 1px solid {colors['border_primary']};
    border-radius: 3px;
    padding: 0px 6px;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}

QPushButton#tileSelectButton:hover {{
    border-color: {colors['accent']};
    color: {colors['accent']};
}}

QPushButton#tileRemoveButton {{
    background-color: transparent;
    color: {colors['text_tertiary']};
    border: 1px solid {colors['border_primary']};
    border-radius: 3px;
    font-size: 9px;
    font-weight: 700;
}}

QPushButton#tileRemoveButton:hover {{
    background-color: {colors['error_hover']};
    border-color: {colors['error']};
    color: {colors['error']};
}}

QPushButton#gridToggle {{
    background-color: transparent;
    color: {colors['text_tertiary']};
    border: 1px solid {colors['border_primary']};
    border-radius: 6px;
    padding: 8px 10px;
    font-size: 11px;
    font-weight: 600;
}}

QPushButton#gridToggle:checked {{
    border-color: {colors['accent']};
    color: {colors['text_primary']};
    background-color: {colors['bg_hover']};
}}

/* Status dots */
QLabel#statusDotActive {{
    background-color: {colors['status_active']};
    border-radius: 3px;
}}

QLabel#statusDotInactive {{
    background-color: {colors['status_inactive']};
    border-radius: 3px;
}}

QLabel#statusDotError {{
    background-color: {colors['status_error']};
    border-radius: 3px;
}}

/* Camera combo */
QComboBox#cameraCombo {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_secondary']};
    border: 1px solid {colors['border_primary']};
    border-radius: 6px;
    padding: 0px 12px;
    font-size: 12px;
    selection-background-color: {colors['bg_hover']};
}}

QComboBox#cameraCombo:hover {{
    border-color: {colors['border_secondary']};
}}

QComboBox#cameraCombo::drop-down {{
    border: none;
    padding-right: 10px;
}}

QComboBox QAbstractItemView {{
    background-color: {colors['bg_tertiary']};
    color: {colors['text_secondary']};
    border: 1px solid {colors['border_primary']};
    selection-background-color: {colors['bg_hover']};
    outline: none;
}}

/* Camera grid scroll */
QScrollArea#cameraScroll {{
    background-color: transparent;
    border: none;
}}

QWidget#cameraGridContainer {{
    background-color: transparent;
}}

/* Scrollbar */
QScrollBar:vertical {{
    background: {colors['bg_primary']};
    width: 4px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {colors['border_secondary']};
    border-radius: 2px;
    min-height: 20px;
}}

QScrollBar::handle:vertical:hover {{
    background: {colors['text_muted']};
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* Divider */
QFrame#divider {{
    background-color: {colors['border_tertiary']};
    max-height: 1px;
}}

/* Input Fields */
QLineEdit {{
    background-color: {colors['input_bg']};
    border: 1px solid {colors['border_primary']};
    border-radius: 6px;
    padding: 10px 14px;
    color: {colors['text_secondary']};
    font-size: 12px;
}}

QLineEdit:focus {{
    border-color: {colors['accent']};
}}

QLineEdit[invalid="true"] {{
    border-color: {colors['error']};
}}

QSpinBox {{
    background-color: {colors['input_bg']};
    border: 1px solid {colors['border_primary']};
    border-radius: 6px;
    padding: 10px 14px;
    color: {colors['text_secondary']};
    font-size: 12px;
}}

QSpinBox:focus {{
    border-color: {colors['accent']};
}}

QDoubleSpinBox {{
    background-color: {colors['input_bg']};
    border: 1px solid {colors['border_primary']};
    border-radius: 6px;
    padding: 10px 14px;
    color: {colors['text_secondary']};
    font-size: 12px;
}}

QDoubleSpinBox:focus {{
    border-color: {colors['accent']};
}}

QTextEdit {{
    background-color: {colors['input_bg']};
    border: 1px solid {colors['border_primary']};
    border-radius: 6px;
    padding: 10px 14px;
    color: {colors['text_secondary']};
    font-size: 12px;
}}

QTextEdit:focus {{
    border-color: {colors['accent']};
}}

QTextEdit[invalid="true"] {{
    border-color: {colors['error']};
}}

QComboBox {{
    background-color: {colors['input_bg']};
    color: {colors['text_secondary']};
    border: 1px solid {colors['border_primary']};
    border-radius: 6px;
    padding: 10px 14px;
    font-size: 12px;
}}

QComboBox:hover {{
    border-color: {colors['border_secondary']};
}}

QComboBox:focus {{
    border-color: {colors['accent']};
}}

QComboBox::drop-down {{
    border: none;
    padding-right: 10px;
}}

QComboBox QAbstractItemView {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_secondary']};
    border: 1px solid {colors['border_primary']};
    selection-background-color: {colors['bg_hover']};
    selection-color: {colors['text_primary']};
    outline: none;
}}

QLineEdit#pathDisplay {{
    color: {colors['text_tertiary']};
    font-size: 11px;
}}

QGroupBox {{
    color: {colors['text_primary']};
    border: 1px solid {colors['border_primary']};
    border-radius: 8px;
    margin-top: 8px;
    padding-top: 10px;
    background-color: {colors['bg_secondary']};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: {colors['text_secondary']};
    background-color: {colors['bg_secondary']};
}}

QHeaderView::section {{
    background-color: {colors['bg_tertiary']};
    color: {colors['text_secondary']};
    border: none;
    border-bottom: 1px solid {colors['border_primary']};
    padding: 8px;
    font-size: 11px;
    font-weight: 600;
}}

QTableWidget {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_secondary']};
    border: 1px solid {colors['border_primary']};
    border-radius: 8px;
    gridline-color: {colors['border_tertiary']};
    selection-background-color: {colors['bg_hover']};
    selection-color: {colors['text_primary']};
}}

QTableWidget::item {{
    padding: 6px;
    border-bottom: 1px solid {colors['border_tertiary']};
}}

QTabWidget::pane {{
    border: 1px solid {colors['border_primary']};
    background-color: {colors['bg_secondary']};
    border-radius: 8px;
    top: -1px;
}}

QTabBar::tab {{
    background-color: {colors['bg_tertiary']};
    color: {colors['text_tertiary']};
    border: 1px solid {colors['border_primary']};
    padding: 10px 14px;
    margin-right: 6px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}}

QTabBar::tab:selected {{
    color: {colors['text_primary']};
    background-color: {colors['bg_secondary']};
    border-bottom-color: {colors['bg_secondary']};
}}

QSlider::groove:horizontal {{
    background: {colors['border_tertiary']};
    height: 6px;
    border-radius: 3px;
}}

QSlider::sub-page:horizontal {{
    background: {colors['accent']};
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background: {colors['text_primary']};
    border: 2px solid {colors['accent']};
    width: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}

/* Checkbox */
QCheckBox {{
    color: {colors['text_tertiary']};
    font-size: 12px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid {colors['border_secondary']};
    background-color: {colors['input_bg']};
}}

QCheckBox::indicator:checked {{
    background-color: {colors['accent']};
    border-color: {colors['accent']};
}}

QCheckBox::indicator:checked:disabled {{
    background-color: {colors['text_tertiary']};
    border-color: {colors['text_tertiary']};
}}

QCheckBox::indicator:unchecked:disabled {{
    background-color: {colors['text_tertiary']};
    border-color: {colors['text_tertiary']};
}}
"""
    
    return stylesheet
