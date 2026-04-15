from __future__ import annotations

from enum import Enum
from typing import Literal


class Theme(Enum):
    DARK = "dark"
    LIGHT = "light"


def get_theme_colors(theme: Theme | str) -> dict[str, str]:
    """Get color palette for the specified theme."""
    if isinstance(theme, str):
        theme = Theme(theme)
    
    if theme == Theme.DARK:
        return {
            # Base colors
            "bg_primary": "#0f172a",
            "bg_secondary": "#111c34",
            "bg_tertiary": "#1e293b",
            "bg_hover": "#263244",
            
            # Text colors
            "text_primary": "#f8fafc",
            "text_secondary": "#cbd5e1",
            "text_tertiary": "#94a3b8",
            "text_muted": "#64748b",
            
            # Border colors
            "border_primary": "#243145",
            "border_secondary": "#334155",
            "border_tertiary": "#182235",
            
            # Accent colors
            "accent": "#3b82f6",
            "accent_hover": "#60a5fa",
            "accent_pressed": "#2563eb",
            "success": "#22c55e",
            "warning": "#f59e0b",
            "error": "#ef4444",
            "error_hover": "#3b1215",
            
            # Status indicators
            "status_active": "#22c55e",
            "status_inactive": "#64748b",
            "status_error": "#ef4444",
            
            # Special
            "input_bg": "#0b1324",
            "card_bg": "#111c34",
            "log_bg": "#09111f",
        }
    else:  # LIGHT theme
        return {
            # Base colors
            "bg_primary": "#ffffff",
            "bg_secondary": "#f5f5f5",
            "bg_tertiary": "#efefef",
            "bg_hover": "#e8e8e8",
            
            # Text colors
            "text_primary": "#1a1a1a",
            "text_secondary": "#555555",
            "text_tertiary": "#777777",
            "text_muted": "#999999",
            
            # Border colors
            "border_primary": "#e0e0e0",
            "border_secondary": "#d0d0d0",
            "border_tertiary": "#dadada",
            
            # Accent colors
            "accent": "#0066cc",
            "accent_hover": "#0052a3",
            "accent_pressed": "#00539a",
            "success": "#00aa44",
            "warning": "#ff9900",
            "error": "#dd0000",
            "error_hover": "#cc0000",
            
            # Status indicators
            "status_active": "#00aa44",
            "status_inactive": "#cccccc",
            "status_error": "#dd0000",
            
            # Special
            "input_bg": "#ffffff",
            "card_bg": "#f9f9f9",
            "log_bg": "#fafafa",
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
    padding: 0;
}}

QPushButton#sidebarAccountTextButton:hover {{
    background-color: transparent;
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
