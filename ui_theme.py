from PyQt6.QtWidgets import QApplication


APP_LIGHT_QSS = """
/* Base */
QMainWindow, QDialog, QWidget#mainWindowShell {
    background: #EEF2F6;
    color: #1E293B;
}

QWidget {
    color: #1E293B;
    selection-background-color: #D9EAFE;
    selection-color: #0F172A;
    font-family: "Segoe UI";
}

/* Top area */
QWidget#appHeaderShell {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #F8FBFE, stop:1 #F3F7FB);
    border-bottom: 1px solid #DCE4EE;
}

QLabel#headerBrandMark {
    background: #0F4C81;
    color: #FFFFFF;
    border-radius: 14px;
    font-size: 18px;
    font-weight: 700;
}

QLabel#headerBrandTitle {
    color: #0F172A;
    font-size: 18px;
    font-weight: 700;
}

QLabel#headerBrandSubtitle {
    color: #64748B;
    font-size: 11px;
}

QWidget#topTabShell,
QWidget#topToolbarShell {
    background: rgba(255, 255, 255, 0.92);
    border-bottom: 1px solid #E1E8F0;
}

QTabBar#topTabBar::tab {
    background: #F3F7FB;
    color: #64748B;
    padding: 8px 14px;
    margin: 2px 3px 0 0;
    border-radius: 12px 12px 0 0;
    border: 1px solid transparent;
}

QTabBar#topTabBar::tab:selected {
    background: #FFFFFF;
    color: #0F172A;
    border: 1px solid #D9E2EE;
    border-bottom: 1px solid #FFFFFF;
}

QTabBar#topTabBar::tab:hover:!selected {
    background: #E9F0F8;
}

QToolButton#addTabButton {
    min-height: 32px;
    padding: 0 12px;
    border-radius: 10px;
    border: 1px solid #D9E2EE;
    background: #FFFFFF;
    color: #334155;
}

QToolButton#addTabButton:hover {
    background: #F8FBFF;
    border-color: #C8D7E6;
}

QLabel#quickToolsBadge {
    padding: 6px 12px;
    border-radius: 11px;
    background: #F3F7FB;
    color: #475569;
    font-size: 11px;
    font-weight: 700;
    border: 1px solid #DCE4EE;
}

QWidget#searchBarShell {
    background: #F7FAFD;
    border-radius: 11px;
    border: 1px solid #D7E1EC;
}

QLineEdit#searchInput {
    border: none;
    background: transparent;
    font-size: 12px;
    color: #334155;
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
    border-radius: 10px;
    border: 1px solid #D9E2EE;
    background: #FFFFFF;
    color: #1E293B;
}

QPushButton:hover, QToolButton:hover {
    background: #F8FBFF;
    border-color: #C8D7E6;
}

QPushButton:pressed, QToolButton:pressed {
    background: #EEF5FD;
    border-color: #BDD1E6;
}

QToolButton#iconToolButton {
    min-width: 34px;
    max-width: 34px;
    min-height: 32px;
    max-height: 32px;
    padding: 0;
}

QPushButton#primaryButton, QToolButton#primaryButton {
    background: #0F4C81;
    color: #FFFFFF;
    border: 1px solid #0F4C81;
}

QPushButton#primaryButton:hover, QToolButton#primaryButton:hover {
    background: #0B3D69;
    border: 1px solid #0B3D69;
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
QWidget#workspaceShell {
    background: #EEF2F6;
}

QWidget#leftSidebarShell {
    background: transparent;
    border: none;
}

QWidget#sidebarContentShell {
    background: #FFFFFF;
    border: 1px solid #D7E1EC;
    border-radius: 22px;
}

QWidget#sidebarNavStrip {
    background: #F4F7FB;
    border: 1px solid #E2E8F0;
    border-radius: 18px;
}

QToolButton#sidebarNavButton {
    min-width: 44px;
    max-width: 44px;
    min-height: 36px;
    max-height: 36px;
    padding: 0;
    border: none;
    border-radius: 12px;
    background: transparent;
}

QToolButton#sidebarNavButton:hover {
    background: #E8F0F8;
}

QToolButton#sidebarNavButton:checked {
    background: #E6F0FA;
    border: 1px solid #BED3EA;
}

QWidget#thumbnailPanel,
QWidget#sidebarSectionPanel,
QStackedWidget#sidebarContentStack {
    background: transparent;
    border: none;
}

QWidget#sidebarSectionHeader {
    background: transparent;
    border-bottom: 1px solid #EDF2F7;
}

QLabel#sidebarSectionTitle {
    color: #0F172A;
    font-size: 13px;
    font-weight: 700;
}

QLabel#sidebarSectionMeta {
    color: #64748B;
    font-size: 11px;
    font-weight: 600;
}

QPushButton#sidebarMiniActionButton {
    padding: 0;
    border-radius: 8px;
    border: 1px solid #D6DFEA;
    background: #F8FAFC;
    color: #334155;
    font-size: 14px;
    font-weight: 700;
}

QPushButton#sidebarMiniActionButton:hover {
    background: #EDF4FB;
    border-color: #BCD2E6;
}

QLabel#sidebarEmptyState {
    color: #94A3B8;
    font-size: 12px;
    padding: 16px;
}

QListWidget#thumbnailList {
    background: transparent;
    border: none;
    padding: 12px 14px 14px 14px;
    outline: none;
}

QListWidget#thumbnailList::item {
    background: #F8FAFC;
    border: 1px solid transparent;
    border-radius: 14px;
    padding: 10px;
    margin: 6px 0;
}

QListWidget#thumbnailList::item:hover {
    background: #F1F6FC;
    border: 1px solid #CBDAEA;
}

QListWidget#thumbnailList::item:selected {
    background: #EAF3FD;
    border: 1px solid #8CB3D9;
    color: #0F172A;
}

QListWidget#sidebarList,
QTreeWidget#sidebarTree {
    background: transparent;
    border: none;
    outline: none;
    padding: 6px 10px 12px 10px;
}

QListWidget#sidebarList::item,
QTreeWidget#sidebarTree::item {
    padding: 8px 10px;
    border-radius: 10px;
}

QListWidget#sidebarList::item:selected,
QTreeWidget#sidebarTree::item:selected {
    background: #EFF5FB;
    color: #0F172A;
}

/* Lists and trees */
QListWidget, QTreeWidget {
    background: #FFFFFF;
    border: 1px solid #E3E8EF;
    border-radius: 12px;
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
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #F7FAFD, stop:1 #EEF3F8);
    border: 1px solid #D7E1EC;
    border-radius: 24px;
}

QScrollArea#pdfScrollArea {
    background: #E8EDF4;
    border: 1px solid #D4DDE8;
    border-radius: 20px;
}

QWidget#pdfCanvas {
    background: transparent;
}

/* Right panels */
QWidget#rightPanelHost {
    background: transparent;
    border: none;
}

QWidget#sidePanel {
    background: #FFFFFF;
    border: 1px solid #D7E1EC;
    border-radius: 20px;
}

QWidget#panelHeader {
    background: transparent;
    border-bottom: 1px solid #EDF2F7;
    min-height: 46px;
}

QLabel#panelTitle {
    font-size: 13px;
    font-weight: 700;
    color: #0F172A;
}

QLabel#panelSubtle {
    color: #6B7280;
    font-size: 12px;
}

QWidget#textToolBody {
    background: transparent;
}

QWidget#aiPanelBody {
    background: transparent;
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
    border: 1px solid #E2E8F0;
    border-radius: 14px;
    padding: 8px;
}

QPushButton#aiActionButton {
    min-height: 38px;
    padding: 8px 12px;
    font-size: 13px;
    font-weight: 700;
}

QGroupBox#aiChatCard {
    margin-top: 10px;
    padding-top: 10px;
    border: 1px solid #E3E8EF;
    border-radius: 14px;
    background: #FBFCFE;
    font-size: 13px;
    font-weight: 700;
    color: #0F172A;
}

QScrollArea#aiChatScroll {
    border: 1px solid #E3E8EF;
    border-radius: 12px;
    background: #F8FAFC;
}

QPlainTextEdit#aiChatInput {
    font-size: 12px;
    border: 1px solid #D5DEE8;
    background: #FFFFFF;
}

QPlainTextEdit#aiChatInput:focus {
    border: 1px solid #8CB3D9;
}

QPushButton#aiSendButton {
    padding: 0 14px;
    font-size: 12px;
    font-weight: 600;
    background: #EAF3FD;
    border: 1px solid #BED3EA;
    color: #0F4C81;
}

QPushButton#aiSendButton:hover {
    background: #DCECFB;
    border-color: #97B8DA;
}

QListWidget#searchResultsList {
    background: transparent;
    border: none;
    padding: 10px;
}

/* Bottom bar */
QWidget#bottomToolbarShell, QStatusBar {
    background: rgba(255, 255, 255, 0.96);
    border: 1px solid #D7E1EC;
    border-radius: 18px;
    color: #64748B;
}

QLabel#statusText, QLabel#pageLabel {
    color: #475569;
    font-size: 11px;
    font-weight: 600;
}

QLineEdit#zoomInput {
    font-size: 11px;
    border: 1px solid #D7E1EC;
    border-radius: 8px;
    background: #FFFFFF;
    color: #334155;
}

QLineEdit#zoomInput:focus {
    border: 1px solid #8CB3D9;
    background: #FFFFFF;
}

/* Splitter and divider */
QSplitter::handle {
    background: transparent;
    width: 8px;
    height: 8px;
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
