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
    QMainWindow { background: #f0f0f0; }
    QScrollArea#pdfScrollArea { border: none; background: #444; }
    QSplitter::handle { background: #d0d0d0; }
    QTabBar::tab {
        padding: 4px 12px; background: #e0e0e0; border: none;
        border-radius: 4px 4px 0 0; font-size: 11px;
    }
    QTabBar::tab:selected { background: white; font-weight: bold; }
    QTabBar::tab:hover { background: #ebebeb; }
    QListWidget { border: none; }
    QTreeWidget { border: none; }
    QPushButton {
        padding: 4px 12px; border-radius: 4px;
        border: 1px solid #ccc; background: white;
    }
    QPushButton:hover { background: #f0f0f0; }
    QPushButton:pressed { background: #e0e0e0; }
    QStatusBar { background: #fafafa; border-top: 1px solid #e0e0e0; }
    QProgressBar { border: none; background: #e0e0e0; }
    QProgressBar::chunk { background: #2979FF; }
""" + _SCROLLBAR_STYLE

DARK_STYLE = """
    QMainWindow { background: #1e1e1e; }
    QScrollArea#pdfScrollArea { border: none; background: #2d2d2d; }
    QSplitter::handle { background: #3a3a3a; }
    QTabBar::tab {
        padding: 4px 12px; background: #2d2d2d; border: none;
        border-radius: 4px 4px 0 0; font-size: 11px; color: #ccc;
    }
    QTabBar::tab:selected { background: #3a3a3a; font-weight: bold; color: #fff; }
    QTabBar::tab:hover { background: #333; }
    QWidget { background: #1e1e1e; color: #ddd; }
    QListWidget { border: none; background: #252525; color: #ddd; }
    QTreeWidget { border: none; background: #252525; color: #ddd; }
    QListWidget::item:selected { background: #37474F; }
    QTreeWidget::item:selected { background: #37474F; }
    QPushButton {
        padding: 4px 12px; border-radius: 4px;
        border: 1px solid #555; background: #333; color: #ddd;
    }
    QPushButton:hover { background: #3a3a3a; }
    QPushButton:pressed { background: #444; }
    QLineEdit {
        background: #2d2d2d; color: #ddd; border: 1px solid #555; border-radius: 4px;
    }
    QLineEdit:focus { border: 1px solid #5c9ce6; }
    QTextEdit, QPlainTextEdit {
        background: #2d2d2d; color: #ddd; border: 1px solid #555;
    }
    QComboBox {
        background: #2d2d2d; color: #ddd; border: 1px solid #555; border-radius: 4px;
    }
    QComboBox QAbstractItemView { background: #333; color: #ddd; }
    QSpinBox, QDoubleSpinBox {
        background: #2d2d2d; color: #ddd; border: 1px solid #555;
    }
    QStatusBar { background: #252525; border-top: 1px solid #3a3a3a; color: #aaa; }
    QProgressBar { border: none; background: #333; }
    QProgressBar::chunk { background: #5c9ce6; }
    QLabel { color: #ddd; }
    QGroupBox { color: #ddd; border: 1px solid #444; }
    QGroupBox::title { color: #ddd; }
    QFrame { border-color: #444; }
    QToolTip { background: #333; color: #ddd; border: 1px solid #555; }
    QDialog { background: #1e1e1e; color: #ddd; }
    QMenu { background: #2d2d2d; color: #ddd; border: 1px solid #444; }
    QMenu::item:selected { background: #37474F; }
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
    app.setStyleSheet(DARK_STYLE if is_dark else LIGHT_STYLE)


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
