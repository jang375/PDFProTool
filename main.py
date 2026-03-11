"""
main.py — Entry point for PDF Pro Tool (Windows)
Converted from Swift/macOS to Python/PyQt6/PyMuPDF
"""

import sys
import os
import ctypes
import logging

logger = logging.getLogger(__name__)

# High-DPI support
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

# Windows: raise timer resolution from ~15ms to 1ms so QTimer(16ms) fires
# accurately at ~60fps instead of stuttering at ~30fps (2 × 15.6ms ticks).
_winmm = None
try:
    _winmm = ctypes.WinDLL("winmm")
    _winmm.timeBeginPeriod(1)
except OSError:
    _winmm = None

from PyQt6.QtCore import Qt, QTimer, QSettings
from PyQt6.QtGui import QFont, QIcon, QPixmap, QColor
from PyQt6.QtWidgets import QApplication, QSplashScreen

from main_window import MainWindow
from panels import preload_fonts
from updater import UpdateManager, cleanup_old_files, is_update_in_progress
from ui_theme import apply_app_theme
from version import __version__


# ─────────────────────────────────────────────
# Theme stylesheets
# ─────────────────────────────────────────────

_SCROLLBAR_STYLE = """
    QScrollBar:vertical {
        background: transparent; width: 8px; margin: 0;
    }
    QScrollBar:vertical:hover { width: 10px; }
    QScrollBar::handle:vertical {
        background: rgba(0,0,0,0.25); border-radius: 4px; min-height: 30px;
    }
    QScrollBar::handle:vertical:hover { background: rgba(0,0,0,0.40); }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
    QScrollBar:horizontal {
        background: transparent; height: 8px; margin: 0;
    }
    QScrollBar:horizontal:hover { height: 10px; }
    QScrollBar::handle:horizontal {
        background: rgba(0,0,0,0.25); border-radius: 4px; min-width: 30px;
    }
    QScrollBar::handle:horizontal:hover { background: rgba(0,0,0,0.40); }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
"""

LIGHT_STYLE = """
    QMainWindow, QDialog {
        background: #eef2f7;
    }
    QWidget {
        color: #243043;
        selection-background-color: #d7e6ff;
        selection-color: #13243d;
    }
    QScrollArea#pdfScrollArea { border: none; background: #3b4048; }
    QSplitter::handle { background: #d9e1eb; }
    QTabBar::tab {
        padding: 5px 12px;
        background: #e9eef5;
        border: 1px solid #d6deea;
        border-bottom: none;
        border-radius: 6px 6px 0 0;
        font-size: 11px;
        color: #4b5870;
    }
    QTabBar::tab:selected {
        background: #ffffff;
        color: #1f2d45;
        font-weight: 600;
    }
    QTabBar::tab:hover:!selected { background: #f1f5fb; }
    QListWidget, QTreeWidget {
        border: 1px solid #d7deea;
        border-radius: 8px;
        background: #ffffff;
    }
    QListWidget::item:selected, QTreeWidget::item:selected {
        background: #e7f0ff;
        color: #13243d;
    }
    QPushButton, QToolButton {
        padding: 5px 12px;
        border-radius: 7px;
        border: 1px solid #ccd6e5;
        background: #ffffff;
        color: #2f3745;
    }
    QPushButton:hover, QToolButton:hover {
        background: #f3f7ff;
        border-color: #b8c9e5;
    }
    QPushButton:pressed, QToolButton:pressed {
        background: #e6eefb;
    }
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
        background: #ffffff;
        color: #283447;
        border: 1px solid #ccd6e5;
        border-radius: 6px;
    }
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {
        border: 1px solid #8eb1eb;
    }
    QMenu {
        background: #ffffff;
        border: 1px solid #d3dce9;
    }
    QMenu::item:selected { background: #edf3ff; }
    QStatusBar {
        background: #f6f8fb;
        border-top: 1px solid #dfe5ee;
        color: #5f6d84;
    }
    QProgressBar {
        border: 1px solid #d5ddeb;
        border-radius: 6px;
        background: #e8edf5;
        text-align: center;
    }
    QProgressBar::chunk {
        background: #3f7de8;
        border-radius: 5px;
    }
""" + _SCROLLBAR_STYLE

DARK_STYLE = """
    QMainWindow, QDialog { background: #141821; }
    QWidget {
        background: #141821;
        color: #dce5f3;
        selection-background-color: #304a78;
        selection-color: #f2f6ff;
    }
    QScrollArea#pdfScrollArea { border: none; background: #1f2430; }
    QSplitter::handle { background: #2a3140; }
    QTabBar::tab {
        padding: 5px 12px;
        background: #202634;
        border: 1px solid #2f384a;
        border-bottom: none;
        border-radius: 6px 6px 0 0;
        font-size: 11px;
        color: #b6c4db;
    }
    QTabBar::tab:selected {
        background: #2a3140;
        color: #f1f5ff;
        font-weight: 600;
    }
    QTabBar::tab:hover:!selected { background: #252d3c; }
    QListWidget, QTreeWidget {
        border: 1px solid #2e384a;
        border-radius: 8px;
        background: #1a202d;
        color: #dce5f3;
    }
    QListWidget::item:selected, QTreeWidget::item:selected {
        background: #304a78;
        color: #f1f5ff;
    }
    QPushButton, QToolButton {
        padding: 5px 12px;
        border-radius: 7px;
        border: 1px solid #3a465d;
        background: #232b3a;
        color: #dce5f3;
    }
    QPushButton:hover, QToolButton:hover {
        background: #2b3547;
        border-color: #4b5f80;
    }
    QPushButton:pressed, QToolButton:pressed {
        background: #344055;
    }
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
        background: #1c2331;
        color: #dce5f3;
        border: 1px solid #3a465d;
        border-radius: 6px;
    }
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {
        border: 1px solid #6d93d6;
    }
    QComboBox QAbstractItemView {
        background: #202838;
        color: #dce5f3;
        border: 1px solid #3a465d;
    }
    QStatusBar {
        background: #181e2a;
        border-top: 1px solid #2d3748;
        color: #9aaacd;
    }
    QGroupBox { color: #dce5f3; border: 1px solid #313c4d; }
    QGroupBox::title { color: #dce5f3; }
    QFrame { border-color: #313c4d; }
    QToolTip { background: #232b3a; color: #e6eeff; border: 1px solid #45556f; }
    QMenu { background: #202838; color: #dce5f3; border: 1px solid #3a465d; }
    QMenu::item:selected { background: #304a78; }
    QProgressBar {
        border: 1px solid #3a465d;
        border-radius: 6px;
        background: #212a3a;
        text-align: center;
    }
    QProgressBar::chunk {
        background: #5f8ddd;
        border-radius: 5px;
    }
    QScrollBar:vertical {
        background: transparent; width: 8px; margin: 0;
    }
    QScrollBar:vertical:hover { width: 10px; }
    QScrollBar::handle:vertical {
        background: rgba(255,255,255,0.25); border-radius: 4px; min-height: 30px;
    }
    QScrollBar::handle:vertical:hover { background: rgba(255,255,255,0.40); }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
    QScrollBar:horizontal {
        background: transparent; height: 8px; margin: 0;
    }
    QScrollBar:horizontal:hover { height: 10px; }
    QScrollBar::handle:horizontal {
        background: rgba(255,255,255,0.25); border-radius: 4px; min-width: 30px;
    }
    QScrollBar::handle:horizontal:hover { background: rgba(255,255,255,0.40); }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
"""


def apply_theme(app: QApplication, is_dark: bool):
    """Apply light or dark theme stylesheet to the application."""
    if is_dark:
        app.setStyleSheet(DARK_STYLE)
    else:
        apply_app_theme(app, is_dark=False)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PDF Pro Tool")
    app.setOrganizationName("PDFProTool")
    app.setStyle("Fusion")

    # 업데이트 진행 중이면 안내 메시지 표시 후 종료
    if is_update_in_progress():
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(
            None, "업데이트 진행 중",
            "PDF Pro Tool 업데이트가 진행 중입니다.\n"
            "업데이트가 완료되면 프로그램이 자동으로 시작됩니다.\n\n"
            "잠시만 기다려 주세요."
        )
        sys.exit(0)

    # Kick off font loading in background immediately (before any UI opens)
    preload_fonts()

    # App icon
    icon_path = os.path.join(os.path.dirname(__file__), "pdf_icon_512.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Splash screen
    splash = None
    if os.path.exists(icon_path):
        splash_pix = QPixmap(icon_path).scaled(
            280, 280, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        splash = QSplashScreen(splash_pix)
        splash.show()
        app.processEvents()

    # Default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Apply saved theme
    settings = QSettings("PDFProTool", "Settings")
    is_dark = settings.value("dark_mode", False, type=bool)
    apply_theme(app, is_dark)

    # 이전 업데이트에서 남은 .old 백업 파일 정리
    cleanup_old_files()

    window = MainWindow()

    # Open files passed as command-line arguments
    for arg in sys.argv[1:]:
        if arg.lower().endswith(".pdf") and os.path.exists(arg):
            window.load_file(arg)

    window.show()
    if splash:
        splash.finish(window)

    # MainWindow 표시 직후 비동기로 업데이트 확인
    updater = UpdateManager(parent=window)
    QTimer.singleShot(1500, updater.check_for_updates)

    exit_code = app.exec()

    # Restore Windows timer resolution on exit
    if _winmm is not None:
        try:
            _winmm.timeEndPeriod(1)
        except Exception:
            pass

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
