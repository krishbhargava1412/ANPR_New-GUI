STYLESHEET = """
* {
    font-family: 'Segoe UI', 'SF Pro Display', 'Helvetica Neue', sans-serif;
}

QMainWindow {
    background-color: #0d0d0d;
}

QWidget#centralWidget {
    background-color: #0d0d0d;
}

/* Sidebar */
QWidget#sidebar {
    background-color: #111111;
    border-right: 1px solid #1e1e1e;
}

QLabel#appTitle {
    color: #ffffff;
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 2px;
    padding: 0px;
}

QLabel#appSubtitle {
    color: #444444;
    font-size: 10px;
    letter-spacing: 3px;
    font-weight: 400;
}

QPushButton#navButton {
    background-color: transparent;
    color: #555555;
    border: none;
    border-radius: 6px;
    padding: 10px 14px;
    text-align: left;
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.5px;
}

QPushButton#navButton:hover {
    background-color: #1a1a1a;
    color: #cccccc;
}

QPushButton#navButton[active="true"] {
    background-color: #1a1a1a;
    color: #ffffff;
    border-left: 2px solid #e8ff00;
}

QLabel#sectionLabel {
    color: #2a2a2a;
    font-size: 9px;
    letter-spacing: 2px;
    font-weight: 600;
    padding: 0px 14px;
}

/* Main content */
QWidget#contentArea {
    background-color: #0d0d0d;
}

QLabel#pageTitle {
    color: #ffffff;
    font-size: 22px;
    font-weight: 700;
    letter-spacing: -0.5px;
}

QLabel#pageSubtitle {
    color: #3a3a3a;
    font-size: 12px;
    letter-spacing: 0.3px;
}

/* Drop zone */
QLabel#dropZone {
    background-color: #111111;
    border: 1px solid #1e1e1e;
    border-radius: 12px;
    color: #2e2e2e;
    font-size: 13px;
    letter-spacing: 0.5px;
}

QLabel#dropZone:hover {
    border-color: #2a2a2a;
    color: #444444;
}

/* Action button */
QPushButton#primaryButton {
    background-color: #e8ff00;
    color: #0d0d0d;
    border: none;
    border-radius: 8px;
    padding: 12px 28px;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1px;
}

QPushButton#primaryButton:hover {
    background-color: #f0ff33;
}

QPushButton#primaryButton:pressed {
    background-color: #c8dd00;
}

QPushButton#secondaryButton {
    background-color: transparent;
    color: #444444;
    border: 1px solid #1e1e1e;
    border-radius: 8px;
    padding: 12px 20px;
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.5px;
}

QPushButton#secondaryButton:hover {
    border-color: #333333;
    color: #888888;
}

/* Status bar */
QStatusBar {
    background-color: #111111;
    color: #333333;
    font-size: 11px;
    border-top: 1px solid #1a1a1a;
}

/* Stats card */
QWidget#statCard {
    background-color: #111111;
    border: 1px solid #1a1a1a;
    border-radius: 10px;
}

QLabel#statValue {
    color: #ffffff;
    font-size: 26px;
    font-weight: 700;
}

QLabel#statLabel {
    color: #333333;
    font-size: 10px;
    letter-spacing: 1.5px;
    font-weight: 500;
}

QLabel#statAccent {
    color: #e8ff00;
    font-size: 10px;
    font-weight: 600;
}

/* Log panel */
QWidget#logPanel {
    background-color: #111111;
    border: 1px solid #1a1a1a;
    border-radius: 8px;
}

QWidget#logHeader {
    background-color: #141414;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}

QLabel#logHeaderTitle {
    color: #333333;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
}

QLabel#logCount {
    color: #e8ff00;
    font-size: 11px;
    font-weight: 700;
    padding-left: 6px;
}

QPushButton#logClearButton {
    background-color: transparent;
    color: #333333;
    border: 1px solid #1e1e1e;
    border-radius: 3px;
    padding: 0px 8px;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.5px;
}

QPushButton#logClearButton:hover {
    border-color: #444444;
    color: #888888;
}

QWidget#logColHeader {
    background-color: #0f0f0f;
}

QLabel#logColLabel {
    color: #2a2a2a;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 1.5px;
}

QWidget#logEntry {
    background-color: #111111;
    border-bottom: 1px solid #161616;
}

QWidget#logEntry:hover {
    background-color: #141414;
}

QLabel#logTime {
    color: #333333;
    font-size: 11px;
    font-family: monospace;
}

QLabel#logCam {
    color: #444444;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.5px;
}

QLabel#logPlate {
    color: #e8ff00;
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 2px;
    font-family: monospace;
}

QLabel#logConf {
    color: #2a2a2a;
    font-size: 10px;
}

QScrollArea#logScroll {
    background-color: transparent;
    border: none;
}

QWidget#logList {
    background-color: transparent;
}

/* Feed widget */
QLabel#feedWidget {
    background-color: #0a0a0a;
    color: #222222;
    font-size: 12px;
    letter-spacing: 1px;
    border: 1px solid #1a1a1a;
    border-radius: 12px;
}

/* Detection box styling */
QFrame#detectionBox {
    background-color: transparent;
    border: 2px solid #1a1a1a;
    border-radius: 8px;
}

QFrame#detectionBox[state="scanning"] {
    border-color: #e8a800;
    border-radius: 10px;
}

QFrame#detectionBox[state="confirmed"] {
    border-color: #00e676;
    border-radius: 10px;
}

/* Detection splitter handle */
QSplitter#detectionSplitter::handle {
    background-color: #1a1a1a;
    width: 1px;
}

/* Camera tile */
QWidget#cameraTile {
    background-color: #111111;
    border: 1px solid #1e1e1e;
    border-radius: 8px;
}

QWidget#cameraTile[selected="true"] {
    border: 1px solid #e8ff00;
}

QWidget#cameraTileBar {
    background-color: #161616;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    border-bottom: 1px solid #1e1e1e;
}

QLabel#cameraTileTitle {
    color: #555555;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.5px;
}

QLabel#cameraFrameLabel {
    background-color: #0a0a0a;
    color: #222222;
    font-size: 11px;
    letter-spacing: 1px;
    border-bottom-left-radius: 8px;
    border-bottom-right-radius: 8px;
}

QPushButton#tileSelectButton {
    background-color: transparent;
    color: #333333;
    border: 1px solid #1e1e1e;
    border-radius: 3px;
    padding: 0px 6px;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.5px;
}

QPushButton#tileSelectButton:hover {
    border-color: #e8ff00;
    color: #e8ff00;
}

QPushButton#tileRemoveButton {
    background-color: transparent;
    color: #2a2a2a;
    border: 1px solid #1e1e1e;
    border-radius: 3px;
    font-size: 9px;
    font-weight: 700;
}

QPushButton#tileRemoveButton:hover {
    background-color: #2a0000;
    border-color: #5a0000;
    color: #ff4444;
}

/* Status dots */
QLabel#statusDotActive {
    background-color: #00e676;
    border-radius: 3px;
}

QLabel#statusDotInactive {
    background-color: #2a2a2a;
    border-radius: 3px;
}

QLabel#statusDotError {
    background-color: #ff4444;
    border-radius: 3px;
}

/* Camera combo */
QComboBox#cameraCombo {
    background-color: #111111;
    color: #888888;
    border: 1px solid #1e1e1e;
    border-radius: 6px;
    padding: 0px 12px;
    font-size: 12px;
    selection-background-color: #1a1a1a;
}

QComboBox#cameraCombo:hover {
    border-color: #2a2a2a;
}

QComboBox#cameraCombo::drop-down {
    border: none;
    padding-right: 10px;
}

QComboBox QAbstractItemView {
    background-color: #141414;
    color: #888888;
    border: 1px solid #1e1e1e;
    selection-background-color: #1e1e1e;
    outline: none;
}

/* Camera grid scroll */
QScrollArea#cameraScroll {
    background-color: transparent;
    border: none;
}

QWidget#cameraGridContainer {
    background-color: transparent;
}

/* Scrollbar */
QScrollBar:vertical {
    background: #0d0d0d;
    width: 4px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #222222;
    border-radius: 2px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background: #333333;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Divider */
QFrame#divider {
    background-color: #1a1a1a;
    max-height: 1px;
}
"""
