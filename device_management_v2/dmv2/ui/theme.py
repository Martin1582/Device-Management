import customtkinter as ctk


def apply_theme(theme_name):
    ctk.set_appearance_mode(theme_name)
    ctk.set_default_color_theme("blue")


PYSIDE_DARK_STYLESHEET = """
QMainWindow, QWidget {
    background: #071018;
    color: #d8e6f3;
    font-family: Segoe UI, Arial, sans-serif;
    font-size: 10pt;
}
QToolBar {
    background: #08131d;
    border: 0;
    border-bottom: 1px solid #1e3446;
    spacing: 6px;
    padding: 7px;
}
QToolButton, QPushButton {
    background: #10283a;
    color: #e6f6ff;
    border: 1px solid #25506a;
    border-radius: 5px;
    padding: 7px 11px;
}
QToolButton:hover, QPushButton:hover {
    background: #12364f;
    border-color: #30c7df;
}
QToolButton:pressed, QPushButton:pressed {
    background: #0b2233;
}
QToolButton:disabled, QPushButton:disabled {
    background: #111b24;
    border-color: #263544;
    color: #6d7f8e;
}
QLineEdit, QComboBox, QTextEdit, QTableView, QTableWidget {
    background: #0b1620;
    border: 1px solid #263f52;
    border-radius: 5px;
    color: #dceaf7;
    padding: 6px;
    selection-background-color: #0e7490;
    selection-color: #ffffff;
}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QTableView:focus, QTableWidget:focus {
    border-color: #31c6df;
}
QLineEdit::placeholder {
    color: #74889a;
}
QComboBox::drop-down {
    border: 0;
    width: 28px;
}
QComboBox QAbstractItemView {
    background: #0b1620;
    border: 1px solid #31c6df;
    selection-background-color: #12364f;
    color: #dceaf7;
}
QHeaderView::section {
    background: #102232;
    color: #9edff0;
    border: 0;
    border-right: 1px solid #22394b;
    border-bottom: 1px solid #22394b;
    padding: 8px;
    font-weight: 600;
}
QTableView, QTableWidget {
    gridline-color: #1b2f3f;
    alternate-background-color: #0e1b27;
}
QTableView::item, QTableWidget::item {
    padding: 5px;
}
QTableView::item:hover, QTableWidget::item:hover {
    background: #122b3d;
}
QTableView::item:selected, QTableWidget::item:selected {
    background: #0e7490;
    color: #ffffff;
}
QGroupBox {
    background: #0a141d;
    border: 1px solid #22394b;
    border-radius: 7px;
    margin-top: 20px;
    padding: 12px;
    font-weight: 600;
    color: #cfefff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 5px;
    color: #88dff0;
}
QTabWidget::pane {
    border: 1px solid #22394b;
    border-radius: 5px;
    background: #0b1620;
}
QTabBar::tab {
    background: #0c1a26;
    color: #8ba2b4;
    border: 1px solid #22394b;
    border-bottom: 0;
    padding: 7px 12px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #10283a;
    color: #e6f6ff;
    border-color: #31c6df;
}
QStatusBar {
    background: #071018;
    border-top: 1px solid #1e3446;
    color: #8ba2b4;
}
QSplitter::handle {
    background: #102232;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background: #08131d;
    border: 0;
    width: 12px;
    height: 12px;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #25445a;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: #31c6df;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
}
#pageTitle {
    font-size: 23pt;
    font-weight: 700;
    color: #e6f6ff;
}
#pageSubtitle {
    color: #7f98ac;
}
#metricCard {
    background: #0a141d;
    border: 1px solid #22394b;
    border-left: 3px solid #31c6df;
    border-radius: 7px;
}
#metricTitle {
    color: #8ba2b4;
    font-weight: 600;
}
#metricValue {
    color: #7ee7f4;
    font-size: 22pt;
    font-weight: 700;
}
#badge, #badgeOk, #badgeWarn, #notice {
    border-radius: 5px;
    padding: 6px 9px;
}
#badge {
    background: #102232;
    border: 1px solid #25445a;
    color: #cfefff;
}
#badgeOk {
    background: #09261f;
    border: 1px solid #16a34a;
    color: #8ff0b1;
}
#badgeWarn {
    background: #2a2110;
    border: 1px solid #d97706;
    color: #ffd48a;
}
#notice {
    background: #102232;
    border: 1px solid #25445a;
    color: #cfefff;
}
#emptyState {
    background: #0a141d;
    border: 1px dashed #31566e;
    border-radius: 7px;
}
#emptyTitle {
    color: #e6f6ff;
    font-size: 18pt;
    font-weight: 700;
}
#emptyBody {
    color: #8ba2b4;
    font-size: 10pt;
}
#primaryButton {
    background: #0f766e;
    border-color: #2dd4bf;
}
#primaryButton:hover {
    background: #115e59;
}
"""


def apply_pyside_theme(widget):
    widget.setStyleSheet(PYSIDE_DARK_STYLESHEET)
