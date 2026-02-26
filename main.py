"""
main.py — Entry point for PDF Pro Tool (Windows)
Converted from Swift/macOS to Python/PyQt6/PyMuPDF
"""

import sys
import os
import ctypes

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

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from main_window import MainWindow
from panels import preload_fonts


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PDF Pro Tool")
    app.setOrganizationName("PDFProTool")
    app.setStyle("Fusion")

    # Kick off font loading in background immediately (before any UI opens)
    preload_fonts()

    # Default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Light style sheet (mimics macOS look)
    app.setStyleSheet("""
        QMainWindow { background: #f0f0f0; }
        QScrollArea#pdfScrollArea { border: none; background: #444; }
        QSplitter::handle { background: #d0d0d0; }
        QTabBar::tab {
            padding: 4px 12px;
            background: #e0e0e0;
            border: none;
            border-radius: 4px 4px 0 0;
            font-size: 11px;
        }
        QTabBar::tab:selected {
            background: white;
            font-weight: bold;
        }
        QTabBar::tab:hover {
            background: #ebebeb;
        }
        QListWidget { border: none; }
        QTreeWidget { border: none; }
        QPushButton {
            padding: 4px 12px;
            border-radius: 4px;
            border: 1px solid #ccc;
            background: white;
        }
        QPushButton:hover { background: #f0f0f0; }
        QPushButton:pressed { background: #e0e0e0; }
        QStatusBar { background: #fafafa; border-top: 1px solid #e0e0e0; }
        QProgressBar { border: none; background: #e0e0e0; }
        QProgressBar::chunk { background: #2979FF; }
    """)

    window = MainWindow()

    # Open files passed as command-line arguments
    for arg in sys.argv[1:]:
        if arg.lower().endswith(".pdf") and os.path.exists(arg):
            window.load_file(arg)

    window.show()
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
