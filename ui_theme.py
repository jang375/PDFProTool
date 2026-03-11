from PyQt6.QtWidgets import QApplication


APP_LIGHT_QSS = """
/* Base */
QMainWindow, QDialog, QWidget#mainWindowShell {
    background: #F5F7FA;
    color: #1F2937;
}

QWidget {
    color: #1F2937;
    selection-background-color: #DBEAFE;
    selection-color: #111827;
    font-family: "Segoe UI";
}

/* Top area */
QWidget#topTabShell,
QWidget#topToolbarShell {
    background: #FFFFFF;
    border-bottom: 1px solid #E5E7EB;
}

QTabBar#topTabBar::tab {
    background: transparent;
    color: #6B7280;
    padding: 7px 12px;
    margin: 3px 2px 0 2px;
    border-radius: 8px 8px 0 0;
}

QTabBar#topTabBar::tab:selected {
    background: #FFFFFF;
    color: #111827;
    border: 1px solid #E5E7EB;
    border-bottom: 1px solid #FFFFFF;
}

QTabBar#topTabBar::tab:hover:!selected {
    background: #EEF2F7;
}

QToolButton#addTabButton {
    min-height: 30px;
    padding: 0 10px;
    border-radius: 8px;
    border: 1px solid #E5E7EB;
    background: #FFFFFF;
    color: #1F2937;
}

QToolButton#addTabButton:hover {
    background: #F3F6FB;
    border-color: #D6DEEA;
}

QWidget#searchBarShell {
    background: #F8FAFC;
    border-radius: 9px;
    border: 1px solid #E5E7EB;
}

QLineEdit#searchInput {
    border: none;
    background: transparent;
    font-size: 12px;
    color: #374151;
    min-height: 20px;
    padding: 0 2px;
}

QToolButton#searchIconButton {
    border: none;
    background: transparent;
    min-width: 20px;
    max-width: 20px;
    min-height: 20px;
    max-height: 20px;
    padding: 0;
    margin: 0;
    border-radius: 6px;
}

QToolButton#searchIconButton:hover {
    background: #EAF1FF;
}

QPushButton#searchNavButton {
    min-width: 22px;
    max-width: 22px;
    min-height: 22px;
    max-height: 22px;
    padding: 0;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: #6B7280;
}

QPushButton#searchNavButton:hover {
    background: #EAF1FF;
    color: #1E3A8A;
}

/* Generic controls */
QPushButton, QToolButton {
    min-height: 32px;
    padding: 6px 12px;
    border-radius: 8px;
    border: 1px solid #E5E7EB;
    background: #FFFFFF;
    color: #1F2937;
}

QPushButton:hover, QToolButton:hover {
    background: #F3F6FB;
    border-color: #D6DEEA;
}

QPushButton:pressed, QToolButton:pressed {
    background: #EAF1FF;
    border-color: #BFD3F6;
}

QToolButton#iconToolButton {
    min-width: 34px;
    max-width: 34px;
    min-height: 32px;
    max-height: 32px;
    padding: 0;
}

QPushButton#primaryButton, QToolButton#primaryButton {
    background: #2563EB;
    color: #FFFFFF;
    border: 1px solid #2563EB;
}

QPushButton#primaryButton:hover, QToolButton#primaryButton:hover {
    background: #1D4ED8;
    border: 1px solid #1D4ED8;
}

QPushButton#panelCloseButton, QToolButton#panelCloseButton {
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
    padding: 0;
    border-radius: 7px;
    background: transparent;
    border: none;
    color: #6B7280;
}

QPushButton#panelCloseButton:hover, QToolButton#panelCloseButton:hover {
    background: #F3F4F6;
    color: #111827;
}

QPushButton#panelNavButton {
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
    padding: 0;
}

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #FFFFFF;
    color: #1F2937;
    border: 1px solid #D1D5DB;
    border-radius: 8px;
    padding: 6px 10px;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #93C5FD;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

/* Sidebar + thumbnails */
QWidget#leftSidebarShell, QWidget#thumbnailPanel {
    background: #F7F8FA;
    border-right: 1px solid #E5E7EB;
}

QListWidget#thumbnailList {
    background: #F7F8FA;
    border: none;
    padding: 10px;
    outline: none;
}

QListWidget#thumbnailList::item {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 10px;
    padding: 8px;
    margin: 4px 0;
}

QListWidget#thumbnailList::item:hover {
    background: rgba(37, 99, 235, 0.05);
    border: 1px solid rgba(96, 165, 250, 0.35);
}

QListWidget#thumbnailList::item:selected {
    background: rgba(37, 99, 235, 0.08);
    border: 1px solid #60A5FA;
    color: #111827;
}

/* Lists and trees */
QListWidget, QTreeWidget {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 10px;
    outline: none;
}

QListWidget::item, QTreeWidget::item {
    padding: 6px 8px;
}

QListWidget::item:selected, QTreeWidget::item:selected {
    background: #EFF6FF;
    color: #111827;
    border-radius: 6px;
}

/* Center viewer */
QWidget#centerShell {
    background: #ECEFF3;
}

QScrollArea#pdfScrollArea {
    background: #ECEFF3;
    border: none;
}

QWidget#pdfCanvas {
    background: transparent;
}

/* Right panels */
QWidget#rightPanelHost {
    background: #FFFFFF;
    border-left: 1px solid #E5E7EB;
}

QWidget#sidePanel {
    background: #FFFFFF;
}

QWidget#panelHeader {
    background: #FFFFFF;
    border-bottom: 1px solid #E5E7EB;
    min-height: 42px;
}

QLabel#panelTitle {
    font-size: 13px;
    font-weight: 600;
    color: #111827;
}

QLabel#panelSubtle {
    color: #6B7280;
    font-size: 12px;
}

QWidget#textToolBody {
    background: #FFFFFF;
}

QLabel#panelSectionLabel {
    color: #6B7280;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.6px;
    padding-top: 2px;
}

QLabel#panelInlineHint {
    color: #6B7280;
    font-size: 11px;
    padding-right: 2px;
}

QLineEdit#textPrimaryInput,
QLineEdit#fontFamilyInput,
QComboBox#fontStyleCombo,
QDoubleSpinBox#fontSizeSpin {
    background: #FFFFFF;
    border: 1px solid #D1D5DB;
    border-radius: 9px;
    padding: 6px 10px;
    min-height: 30px;
}

QLineEdit#textPrimaryInput {
    font-size: 14px;
}

QToolButton#fontPopupButton {
    min-width: 30px;
    max-width: 30px;
    min-height: 30px;
    max-height: 30px;
    padding: 0;
    border-radius: 8px;
    border: 1px solid #D1D5DB;
    background: #FFFFFF;
    color: #4B5563;
}

QToolButton#fontPopupButton:hover {
    background: #F3F6FB;
    border-color: #BFDBFE;
}

QToolButton#styleToggleButton {
    min-width: 36px;
    max-width: 36px;
    min-height: 32px;
    max-height: 32px;
    padding: 0;
    border-radius: 8px;
    border: 1px solid #D1D5DB;
    background: #FFFFFF;
}

QToolButton#styleToggleButton:checked {
    background: #EAF1FF;
    border: 1px solid #93C5FD;
    color: #1D4ED8;
}

QPushButton#colorSwatch {
    min-width: 24px;
    max-width: 24px;
    min-height: 24px;
    max-height: 24px;
    padding: 0;
    border-radius: 12px;
    border: 1px solid #D1D5DB;
}

QPushButton#colorSwatch:checked {
    border: 2px solid #2563EB;
}

QPushButton#colorCustomButton {
    min-width: 24px;
    max-width: 24px;
    min-height: 24px;
    max-height: 24px;
    padding: 0;
    border-radius: 12px;
}

QLabel#colorPreviewBar {
    border: 1px solid #E5E7EB;
    border-radius: 8px;
}

QWidget#previewCard, QLabel#previewCard, QFrame#previewCard {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 10px;
    padding: 8px;
}

/* Bottom bar */
QWidget#bottomToolbarShell, QStatusBar {
    background: #FFFFFF;
    border-top: 1px solid #E5E7EB;
    color: #6B7280;
}

QLabel#statusText, QLabel#pageLabel {
    color: #6B7280;
    font-size: 11px;
}

QLineEdit#zoomInput {
    font-size: 11px;
    border: 1px solid transparent;
    border-radius: 6px;
    background: transparent;
    color: #374151;
}

QLineEdit#zoomInput:focus {
    border: 1px solid #BFDBFE;
    background: #FFFFFF;
}

/* Splitter and divider */
QSplitter::handle {
    background: #E5E7EB;
    width: 1px;
    height: 1px;
}

QFrame#toolDivider {
    background: #E5E7EB;
    min-width: 1px;
    max-width: 1px;
    margin: 4px 6px;
}

/* Menus */
QMenu {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    padding: 6px;
}

QMenu::item {
    padding: 7px 12px;
    border-radius: 6px;
}

QMenu::item:selected {
    background: #EFF6FF;
}

/* Scrollbars */
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 4px 2px;
}

QScrollBar::handle:vertical {
    background: rgba(100, 116, 139, 0.38);
    border-radius: 5px;
    min-height: 32px;
}

QScrollBar::handle:vertical:hover {
    background: rgba(100, 116, 139, 0.55);
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
    height: 0;
}

QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px 4px;
}

QScrollBar::handle:horizontal {
    background: rgba(100, 116, 139, 0.38);
    border-radius: 5px;
    min-width: 32px;
}

QScrollBar::handle:horizontal:hover {
    background: rgba(100, 116, 139, 0.55);
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
    width: 0;
}
"""


def apply_app_theme(app: QApplication, is_dark: bool = False):
    # Keep dark-mode toggle behavior stable by falling back to light theme for now.
    _ = is_dark
    app.setStyleSheet(APP_LIGHT_QSS)
