from __future__ import annotations


DARK_STYLESHEET = """
* {
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 14px;
}
QMainWindow, QWidget {
    background: #111318;
    color: #edf0f5;
}
QFrame#Sidebar {
    background: #171a21;
    border-right: 1px solid #272c36;
}
QPushButton {
    background: #242936;
    border: 1px solid #343b4a;
    border-radius: 6px;
    color: #edf0f5;
    padding: 8px 10px;
}
QPushButton:hover {
    background: #2d3444;
}
QPushButton:pressed {
    background: #3a4355;
}
QPushButton#PrimaryButton {
    background: #2f7cf6;
    border-color: #2f7cf6;
    font-weight: 600;
}
QPushButton#SuccessButton {
    background: #1f8f4d;
    border-color: #26d65b;
    font-weight: 600;
}
QPushButton#SuccessButton:hover {
    background: #26a85b;
}
QPushButton#DangerButton {
    background: #a63d4a;
    border-color: #bd4a58;
    font-weight: 600;
}
QLabel#Title {
    font-size: 22px;
    font-weight: 700;
}
QLabel#Subtitle {
    color: #aeb7c6;
}
QLabel#StatusPill {
    background: #202633;
    border: 1px solid #303849;
    border-radius: 6px;
    padding: 5px 8px;
    color: #cdd6e4;
}
QTabWidget::pane {
    background: #111318;
    border: 1px solid #303849;
    border-radius: 6px;
    top: -1px;
}
QTabBar::tab {
    background: #202633;
    border: 1px solid #303849;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    color: #cdd6e4;
    padding: 8px 14px;
    margin-right: 4px;
}
QTabBar::tab:selected {
    background: #2f7cf6;
    color: #ffffff;
    font-weight: 600;
}
QTabBar::tab:hover:!selected {
    background: #2d3444;
    color: #edf0f5;
}
QScrollArea {
    background: #111318;
    border: none;
}
QScrollArea > QWidget > QWidget {
    background: #111318;
}
QScrollBar:vertical {
    background: #151923;
    border: 1px solid #303849;
    border-radius: 6px;
    width: 14px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #566176;
    border-radius: 5px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover {
    background: #6b7890;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget, QTextEdit, QPlainTextEdit {
    background: #171b24;
    border: 1px solid #303849;
    border-radius: 6px;
    color: #edf0f5;
    padding: 6px;
    selection-background-color: #2f7cf6;
}
QListWidget::item {
    padding: 8px;
}
QListWidget::item:selected {
    background: #2f7cf6;
    color: white;
}
QTableWidget {
    background: #171b24;
    border: 1px solid #303849;
    border-radius: 6px;
    gridline-color: #2b3140;
}
QHeaderView::section {
    background: #202633;
    color: #cdd6e4;
    border: none;
    padding: 7px;
}
QGroupBox {
    border: 1px solid #303849;
    border-radius: 8px;
    margin-top: 18px;
    padding: 12px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}
"""
