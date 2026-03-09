"""
main_window.py — Main application window
Windows version of PDFProTool (converted from ContentView.swift + PDFProToolApp.swift)
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QSettings, QByteArray, QSize
from PyQt6.QtGui import (
    QAction, QColor, QFont, QIcon, QKeySequence, QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFileDialog,
    QFrame, QGridLayout, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox,
    QSplitter, QStackedWidget, QStatusBar, QTabBar, QTabWidget,
    QToolBar, QToolButton, QVBoxLayout, QWidget,
)

from models import (
    BookmarkManager, PDFTab, StampManager, AnnotationOverlayManager,
)
from ocr_manager import OCRLanguage, OCRManager
from panels import SearchResultsPanel, StampPanel, TextToolConfig, TextToolPanel, AIToolPanel
from pdf_viewer import PDFScrollView
from sidebar import SidebarWidget, PageGridView
from ai_manager import AIManager
from icons import icon as svg_icon
from version import __version__


# ─────────────────────────────────────────────
# Settings Dialog
# ─────────────────────────────────────────────

class SettingsDialog(QDialog):
    theme_changed = pyqtSignal(bool)  # is_dark

    def __init__(self, ai_manager: AIManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("환경설정")
        self.ai_manager = ai_manager
        self._settings = ai_manager.settings

        self.setMinimumWidth(400)
        vl = QVBoxLayout(self)

        # ── Theme section ──
        from PyQt6.QtWidgets import QCheckBox
        theme_frame = QFrame()
        theme_frame.setStyleSheet("background: white; border-radius: 5px; border: 1px solid #d0d0d0;")
        tf_layout = QVBoxLayout(theme_frame)

        theme_lbl = QLabel("테마:")
        theme_lbl.setStyleSheet("font-weight: bold; border: none;")
        tf_layout.addWidget(theme_lbl)

        self._dark_mode_cb = QCheckBox("다크 모드")
        self._dark_mode_cb.setStyleSheet("border: none;")
        self._dark_mode_cb.setChecked(self._settings.value("dark_mode", False, type=bool))
        tf_layout.addWidget(self._dark_mode_cb)
        vl.addWidget(theme_frame)

        vl.addSpacing(8)

        # ── Gemini API Key section ──
        gb = QFrame()
        gb.setStyleSheet("background: white; border-radius: 5px; border: 1px solid #d0d0d0;")
        gb_layout = QVBoxLayout(gb)

        lbl = QLabel("Gemini API Key:")
        lbl.setStyleSheet("font-weight: bold; border: none;")
        gb_layout.addWidget(lbl)

        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.api_key_input.setText(self.ai_manager.settings.value("gemini_api_key", "", type=str))
        self.api_key_input.setPlaceholderText("API 키를 입력하세요...")
        self.api_key_input.setStyleSheet("padding: 4px; border: 1px solid #ccc; border-radius: 3px;")
        gb_layout.addWidget(self.api_key_input)

        desc = QLabel("Gemini 2.5 Flash 모델을 사용하여 표 추출, 요약, 오타 교정 기능을 제공합니다. 무료 등급에서도 충분히 활용 가능합니다.")
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 11px; color: #666; border: none;")
        gb_layout.addWidget(desc)

        vl.addWidget(gb)
        vl.addStretch()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        vl.addWidget(btns)

    def accept(self):
        new_key = self.api_key_input.text().strip()
        self.ai_manager.update_api_key(new_key)

        is_dark = self._dark_mode_cb.isChecked()
        self._settings.setValue("dark_mode", is_dark)
        self.theme_changed.emit(is_dark)

        super().accept()



# ─────────────────────────────────────────────
# Tool button helper

# ─────────────────────────────────────────────

TOOL_BUTTON_STYLE = (
    "QToolButton { border: 1px solid transparent; border-radius: 7px; "
    "font-size: 16px; background: transparent; color: #2f3745; }"
    "QToolButton:hover { background: #edf2ff; border-color: #d6e2ff; color: #1f3a6d; }"
    "QToolButton:pressed { background: #dde7fb; border-color: #bfd3fa; }"
)

TOPBAR_BUTTON_STYLE = (
    "QPushButton { padding: 6px 11px; font-size: 12px; font-weight: 500; color: #2f3745; "
    "border: 1px solid transparent; background: transparent; border-radius: 7px; margin: 0px; }"
    "QPushButton:hover { background: #edf2ff; border: 1px solid #d6e2ff; color: #1f3a6d; }"
    "QPushButton:pressed { background: #dde7fb; border: 1px solid #bfd3fa; }"
)

TOPBAR_BUTTON_ACTIVE_STYLE = (
    "QPushButton { padding: 6px 11px; font-size: 12px; font-weight: 600; color: #0f4ac4; "
    "border: 1px solid #b6cdf8; background: #e6efff; border-radius: 7px; margin: 0px; }"
    "QPushButton:hover { background: #dce9ff; border: 1px solid #99baf5; }"
    "QPushButton:pressed { background: #cfe0ff; border: 1px solid #87abef; }"
)

DIVIDER_STYLE = "background: #d7dee8; min-width: 1px; max-width: 1px; margin: 4px 5px;"
TOP_TAB_ROW_STYLE = "background: #f7f9fc; border-bottom: 1px solid #e0e6ef;"
TOP_TOOLS_ROW_STYLE = "background: #fbfcfe; border-bottom: 1px solid #e0e6ef;"
BOTTOM_TOOLBAR_STYLE = "background: #f7f9fc; border-top: 1px solid #e0e6ef;"
SEARCH_CONTAINER_STYLE = "background: #f3f6fb; border-radius: 8px; border: 1px solid #dde5f0;"
SEARCH_INPUT_STYLE = "border: none; font-size: 12px; color: #2f3745; background: transparent;"
SEARCH_NAV_BUTTON_STYLE = (
    "QPushButton { padding: 0px 2px; font-size: 12px; font-weight: bold; border: none; "
    "background: transparent; color: #5f6d84; }"
    "QPushButton:hover { background: #e5edf9; border-radius: 4px; color: #31435e; }"
)

def make_tool_button(text: str, tooltip: str, icon_name: str = "") -> QToolButton:
    btn = QToolButton()
    if icon_name:
        btn.setIcon(svg_icon(icon_name, 18))
        btn.setIconSize(QSize(18, 18))
    else:
        btn.setText(text)
    btn.setToolTip(tooltip)
    btn.setFixedSize(36, 32)
    btn.setStyleSheet(TOOL_BUTTON_STYLE)
    return btn


def make_divider() -> QFrame:
    d = QFrame()
    d.setFrameShape(QFrame.Shape.VLine)
    d.setStyleSheet(DIVIDER_STYLE)
    return d


# ─────────────────────────────────────────────
# Main Window
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# Workers
# ─────────────────────────────────────────────

class SearchWorker(QThread):
    result_found = pyqtSignal(int, object, str)  # page_index, rect, snippet
    finished_search = pyqtSignal(int)            # total_count
    error = pyqtSignal(str)

    def __init__(self, file_path: str, query: str,
                 doc_bytes: Optional[bytes] = None):
        super().__init__()
        self._file_path = file_path
        self._doc_bytes = doc_bytes
        self.query = query
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        doc = None
        try:
            if self._doc_bytes:
                doc = fitz.open(stream=self._doc_bytes, filetype="pdf")
            else:
                doc = fitz.open(self._file_path)  # 스레드 전용 인스턴스
            total_count = 0
            for i in range(doc.page_count):
                if self._cancelled:
                    break
                page = doc[i]
                found = page.search_for(self.query)
                for rect in found:
                    if self._cancelled:
                        break
                    text = page.get_text("text", clip=rect).replace("\n", " ").strip()
                    if len(text) > 80:
                        text = text[:80] + "..."
                    self.result_found.emit(i, rect, text)
                    total_count += 1
            self.finished_search.emit(total_count)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            if doc:
                doc.close()


class FileSaveWorker(QThread):
    finished = pyqtSignal(bool, str) # success, message

    def __init__(self, doc_bytes: bytes, save_path: str, orig_path: str):
        super().__init__()
        self._doc_bytes = doc_bytes
        self._save_path = save_path
        self._orig_path = orig_path
        self.saved_bytes: Optional[bytes] = None

    def run(self):
        try:
            same_file = (
                self._orig_path
                and os.path.normpath(os.path.abspath(self._save_path))
                   == os.path.normpath(os.path.abspath(self._orig_path))
            )
            if same_file:
                # 동일 파일 저장: 바이트를 콜백에서 파일에 쓰고 reopen
                self.saved_bytes = self._doc_bytes
            else:
                with open(self._save_path, "wb") as f:
                    f.write(self._doc_bytes)
            self._doc_bytes = None  # 메모리 해제
            self.finished.emit(True, self._save_path)
        except Exception as e:
            self.finished.emit(False, str(e))


class ChatWorker(QThread):
    """Background thread for AI chat API calls to prevent UI freeze."""
    response_ready = pyqtSignal(str)      # AI response text
    error_occurred = pyqtSignal(str)       # Error message
    session_created = pyqtSignal(object)   # Chat session object

    def __init__(self, ai_mgr, text: str, session=None,
                 context_text: str = "", file_path: str = ""):
        super().__init__()
        self._ai_mgr = ai_mgr
        self._text = text
        self._session = session
        self._context_text = context_text
        self._file_path = file_path  # 세션 생성 시 스레드에서 텍스트 추출

    def run(self):
        try:
            if self._session is None:
                # 컨텍스트 텍스트를 스레드에서 추출 (메인 스레드 블로킹 방지)
                context = self._context_text
                if not context and self._file_path:
                    context = self._extract_context()
                self._session = self._ai_mgr.create_chat_session(context)
                self.session_created.emit(self._session)

            response = self._session.send_message(self._text)
            self.response_ready.emit(response.text)
        except Exception as e:
            self.error_occurred.emit(str(e))

    def _extract_context(self) -> str:
        """스레드 전용 doc으로 PDF 텍스트 추출."""
        doc = None
        try:
            doc = fitz.open(self._file_path)
            MAX_CHARS = 80000
            full_text = []
            total_chars = 0
            for idx in range(doc.page_count):
                if total_chars >= MAX_CHARS:
                    full_text.append(
                        f"\n(... 총 {doc.page_count}페이지 중 "
                        f"{idx}페이지까지만 포함됨)"
                    )
                    break
                p_text = doc[idx].get_text("text").strip()
                if p_text:
                    full_text.append(f"--- Page {idx + 1} ---\n{p_text}")
                    total_chars += len(p_text)
            context = "\n\n".join(full_text)
            return context if context.strip() else "이 문서에는 추출할 수 있는 텍스트가 없습니다."
        except Exception:
            return "문서 텍스트 추출 실패."
        finally:
            if doc:
                doc.close()


class AITaskWorker(QThread):
    """Background thread for one-shot AI API calls (summarize, table extract, OCR correct)."""
    result_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, func, *args):
        super().__init__()
        self._func = func
        self._args = args

    def run(self):
        try:
            result = self._func(*self._args)
            self.result_ready.emit(result)
        except Exception as e:
            self.error_occurred.emit(str(e))


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"PDF Pro Tool v{__version__}")
        self.setMinimumSize(1100, 750)
        self.resize(1280, 860)

        # Settings
        self._settings = QSettings("PDFProTool", "Settings")

        # Managers
        self._stamp_mgr = StampManager()
        self._bookmark_mgr = BookmarkManager()
        self._ocr_mgr = OCRManager()
        self._annot_overlay_mgr = AnnotationOverlayManager()
        self._ai_mgr = AIManager()

        # Tabs
        self._tabs: list[PDFTab] = [PDFTab()]
        self._active_tab_idx: int = 0

        # UI state
        self._sidebar_visible: bool = True
        self._text_config = TextToolConfig()
        self._search_query: str = ""
        self._split_start: int = 1
        self._split_end: int = 1

        self._build_ui()
        self._build_welcome_page()
        self._connect_signals()
        self._update_toolbar_state()
        self.setAcceptDrops(True)
        self._restore_window_state()
        # Delay welcome page update so layout is finalized
        QTimer.singleShot(0, self._update_welcome_page)

    # ── Worker lifecycle helper ───────────────
    @staticmethod
    def _stop_worker(worker: "QThread | None", timeout_ms: int = 2000):
        """기존 QThread 워커를 안전하게 정지 후 정리."""
        if worker is None:
            return
        if worker.isRunning():
            worker.quit()
            if not worker.wait(timeout_ms):
                worker.terminate()
                worker.wait(500)
        worker.deleteLater()

    # ── UI Build ──────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_hl = QHBoxLayout(central)
        root_hl.setContentsMargins(0, 0, 0, 0)
        root_hl.setSpacing(0)

        # ── Main Content Area (Right Side) ──
        right_container = QWidget()
        self._global_left_sidebar = None # No longer used
        root_hl.addWidget(right_container, 1)
        right_vl = QVBoxLayout(right_container)
        right_vl.setContentsMargins(0, 0, 0, 0)
        right_vl.setSpacing(0)
        
        # ── Top Bar Row 1: Tabs ──
        self._top_tab_widget = QWidget()
        self._top_tab_widget.setFixedHeight(35)
        self._top_tab_widget.setStyleSheet(TOP_TAB_ROW_STYLE)
        tab_layout = QHBoxLayout(self._top_tab_widget)
        tab_layout.setContentsMargins(10, 0, 10, 0)
        tab_layout.setSpacing(5)

        # Tabs
        self._tab_bar = QTabBar()
        self._tab_bar.setMovable(False)
        self._tab_bar.setTabsClosable(True)
        self._tab_bar.setDocumentMode(True)
        self._tab_bar.setStyleSheet("""
            QTabBar::tab {
                padding: 6px 15px;
                background: transparent;
                border: none;
                color: #556074;
                font-size: 13px;
                margin-top: 4px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                border-top: 2px solid #1f67e6;
                border-bottom: 2px solid #ffffff;
                color: #1f2d45;
                font-weight: 600;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
            QTabBar::tab:hover:!selected {
                background: #eef3fb;
                border-radius: 5px;
                color: #384a66;
            }
        """)
        self._tab_bar.tabCloseRequested.connect(self._close_tab)
        self._tab_bar.addTab("새 문서")
        tab_layout.addWidget(self._tab_bar)

        add_tab_btn = QToolButton()
        add_tab_btn.setText("+ 만들기")
        add_tab_btn.setToolTip("새 탭 추가")
        add_tab_btn.setStyleSheet(
            "QToolButton { border: 1px solid #d3dceb; border-radius: 6px; padding: 2px 9px; "
            "font-size: 11px; background: #fff; color: #2f3745; margin-left: 5px; margin-top: 5px; margin-bottom: 3px; }"
            "QToolButton:hover { background: #f2f6fd; border-color: #b8c8e6; }"
            "QToolButton:pressed { background: #e5edf9; }"
        )
        add_tab_btn.clicked.connect(self._add_new_tab)
        tab_layout.addWidget(add_tab_btn)
        tab_layout.addStretch()

        right_vl.addWidget(self._top_tab_widget)

        # ── Top Bar Row 2: Tools & Controls ──
        self._top_tools_widget = QWidget()
        self._top_tools_widget.setFixedHeight(45)
        self._top_tools_widget.setStyleSheet(TOP_TOOLS_ROW_STYLE)
        tb_layout = QHBoxLayout(self._top_tools_widget)
        tb_layout.setContentsMargins(10, 0, 10, 0)
        tb_layout.setSpacing(5)

        tb_layout.addStretch()
        
        # File ops
        open_btn = make_tool_button("📂", "열기 (Ctrl+O)", "folder-open")
        open_btn.clicked.connect(self._open_file)
        tb_layout.addWidget(open_btn)

        save_btn = make_tool_button("💾", "저장 (Ctrl+S)", "save")
        save_btn.clicked.connect(self._save_file)
        tb_layout.addWidget(save_btn)

        tb_layout.addWidget(make_divider())

        # ── Tools ──
        
        def make_topbar_btn(text, icon_name, callback=None):
            from PyQt6.QtGui import QCursor
            btn = QPushButton(f"  {text}")
            btn.setIcon(svg_icon(icon_name, 16))
            btn.setIconSize(QSize(16, 16))
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setStyleSheet(TOPBAR_BUTTON_STYLE)
            if callback:
                btn.clicked.connect(callback)
            return btn

        self._text_edit_btn = make_topbar_btn("텍스트 편집", "pencil", self._toggle_text_edit_mode)
        tb_layout.addWidget(self._text_edit_btn)
        tb_layout.addWidget(make_topbar_btn("텍스트 추가", "type", self._add_text))
        tb_layout.addWidget(make_topbar_btn("직인 추가", "stamp", self._show_stamp_panel))
        tb_layout.addWidget(make_topbar_btn("파일 결합", "merge", self._merge_pdfs))
        self._grid_view_btn = make_topbar_btn("페이지 구성", "layout", self._toggle_grid_view)
        tb_layout.addWidget(self._grid_view_btn)
        tb_layout.addWidget(make_topbar_btn("스캔/OCR", "scan", self._show_ocr_dialog))
        tb_layout.addWidget(make_topbar_btn("AI", "sparkles", self._show_ai_panel))

        tb_layout.addWidget(make_divider())
        tb_layout.addStretch()

        # Search bar (Moved to the right end)
        search_container = QWidget()
        search_container.setStyleSheet(SEARCH_CONTAINER_STYLE)
        search_container.setFixedHeight(30)
        search_container.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        sl = QHBoxLayout(search_container)
        sl.setContentsMargins(8, 0, 8, 0)
        sl.setSpacing(4)
        
        from PyQt6.QtWidgets import QLineEdit
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("텍스트 찾기")
        self._search_input.setFixedWidth(120)
        self._search_input.setStyleSheet(SEARCH_INPUT_STYLE)
        self._search_input.returnPressed.connect(self._perform_search)
        sl.addWidget(self._search_input)
        
        search_icon_btn = QToolButton()
        search_icon_btn.setIcon(svg_icon("search", 14, "#888"))
        search_icon_btn.setIconSize(QSize(14, 14))
        search_icon_btn.setFixedSize(20, 20)
        search_icon_btn.setStyleSheet("QToolButton { border: none; background: transparent; }")
        search_icon_btn.clicked.connect(self._perform_search)
        sl.addWidget(search_icon_btn)

        self._search_prev_btn = QPushButton("<")
        self._search_prev_btn.setFixedSize(22, 22)
        self._search_prev_btn.setStyleSheet(SEARCH_NAV_BUTTON_STYLE)
        self._search_prev_btn.clicked.connect(lambda: self._navigate_search(-1))
        self._search_prev_btn.hide()
        sl.addWidget(self._search_prev_btn)

        self._search_next_btn = QPushButton(">")
        self._search_next_btn.setFixedSize(22, 22)
        self._search_next_btn.setStyleSheet(SEARCH_NAV_BUTTON_STYLE)
        self._search_next_btn.clicked.connect(lambda: self._navigate_search(1))
        self._search_next_btn.hide()
        sl.addWidget(self._search_next_btn)

        tb_layout.addWidget(search_container)
        
        tb_layout.addSpacing(5)

        # Settings
        settings_btn = make_tool_button("⚙", "설정", "settings")
        settings_btn.clicked.connect(self._show_settings)
        tb_layout.addWidget(settings_btn)

        right_vl.addWidget(self._top_tools_widget)

        # ── Main Splitter (Left Sidebar / PDF / Right Panels) ──
        content_area = QWidget()
        content_hl = QHBoxLayout(content_area)
        content_hl.setContentsMargins(0, 0, 0, 0)
        content_hl.setSpacing(0)

        # Sub Sidebar (Thumbnails, Bookmarks, Outline)
        self._sidebar = SidebarWidget(self._bookmark_mgr)
        self._sidebar.page_selected.connect(self._go_to_page)
        self._sidebar.delete_pages.connect(self._delete_pages)
        self._sidebar.rotate_pages.connect(self._rotate_pages)
        self._sidebar.insert_pdf_at.connect(self._insert_pdf_at)
        self._sidebar.add_bookmark.connect(self._toggle_bookmark)
        self._sidebar.remove_bookmark.connect(self._remove_bookmark)
        self._sidebar.add_outline_entry.connect(self._add_outline_entry)
        self._sidebar.remove_outline_entry.connect(self._remove_outline_entry)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setStyleSheet("QSplitter::handle { background: #dfe6f0; width: 1px; }")
        self._splitter.addWidget(self._sidebar)

        # Center Area: PDF Viewer + Grid View Layout with Bottom Float Toolbar
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        self._pdf_scroll = PDFScrollView()
        self._pdf_scroll.page_changed.connect(self._on_pdf_page_changed)
        self._pdf_scroll.zoom_changed.connect(self._on_zoom_changed)
        self._pdf_scroll.doc_modified.connect(self._on_doc_modified)
        self._pdf_scroll.annot_edit_requested.connect(self._edit_annot_in_panel)
        self._pdf_scroll.pdf_widget.text_copied.connect(self._on_text_copied)

        self._grid_view = PageGridView()
        self._grid_view.page_selected.connect(self._on_grid_page_selected)

        self._content_stack = QStackedWidget()
        self._content_stack.addWidget(self._pdf_scroll)   # index 0
        self._content_stack.addWidget(self._grid_view)     # index 1
        center_layout.addWidget(self._content_stack, 1)

        # Bottom Float Toolbar (Status + Zoom + Paging)
        bottom_toolbar = QWidget()
        bottom_toolbar.setFixedHeight(36)
        bottom_toolbar.setStyleSheet(BOTTOM_TOOLBAR_STYLE)
        bt_hl = QHBoxLayout(bottom_toolbar)
        bt_hl.setContentsMargins(10, 0, 10, 0)
        bt_hl.setSpacing(10)

        self._status_label = QLabel("PDF Pro Tool — Windows Edition")
        self._status_label.setStyleSheet("font-size: 11px; color: #6b7588; padding: 2px;")
        bt_hl.addWidget(self._status_label)
        bt_hl.addStretch()

        delete_btn = make_tool_button("🗑", "현재 페이지 삭제 (Del)", "trash")
        delete_btn.clicked.connect(self._delete_current_page)
        bt_hl.addWidget(delete_btn)

        rotate_btn = make_tool_button("↻", "현재 페이지 회전 (Ctrl+R)", "rotate-cw")
        rotate_btn.clicked.connect(self._rotate_current_page)
        bt_hl.addWidget(rotate_btn)

        bt_hl.addWidget(make_divider())

        # Page navigation
        prev_pg_btn = make_tool_button("<", "이전 페이지", "chevron-left")
        prev_pg_btn.clicked.connect(self._prev_page)
        bt_hl.addWidget(prev_pg_btn)
        self._page_label = QLabel("—")
        self._page_label.setFixedWidth(60)
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_label.setStyleSheet("font-size: 11px; color: #3f4c63;")
        bt_hl.addWidget(self._page_label)
        next_pg_btn = make_tool_button(">", "다음 페이지", "chevron-right")
        next_pg_btn.clicked.connect(self._next_page)
        bt_hl.addWidget(next_pg_btn)

        bt_hl.addWidget(make_divider())

        # Zoom
        zoom_out_btn = make_tool_button("−", "축소", "minus")
        zoom_out_btn.clicked.connect(self._zoom_out)
        bt_hl.addWidget(zoom_out_btn)
        
        self._zoom_input = QLineEdit("100%")
        self._zoom_input.setFixedWidth(52)
        self._zoom_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_input.setStyleSheet(
            "QLineEdit { font-size: 11px; font-weight: 500; border: 1px solid transparent; "
            "border-radius: 4px; background: transparent; color: #2f3745; }"
            "QLineEdit:focus { border: 1px solid #b7c5da; background: #ffffff; }"
        )
        self._zoom_input.editingFinished.connect(self._apply_zoom_input)
        _orig_focus = self._zoom_input.focusInEvent
        def _zoom_focus_in(event, _orig=_orig_focus):
            _orig(event)
            QTimer.singleShot(0, self._zoom_input.selectAll)
        self._zoom_input.focusInEvent = _zoom_focus_in
        bt_hl.addWidget(self._zoom_input)
        
        zoom_in_btn = make_tool_button("+", "확대", "plus")
        zoom_in_btn.clicked.connect(self._zoom_in)
        bt_hl.addWidget(zoom_in_btn)

        center_layout.addWidget(bottom_toolbar)
        self._splitter.addWidget(center_widget)

        # Right panel container
        self._right_panel_container = QWidget()
        self._right_panel_container.hide()
        self._right_panel_hl = QHBoxLayout(self._right_panel_container)
        self._right_panel_hl.setContentsMargins(0, 0, 0, 0)
        self._right_panel_hl.setSpacing(0)

        self._splitter.addWidget(self._right_panel_container)
        self._splitter.setSizes([200, 800, 0])
        content_hl.addWidget(self._splitter)

        right_vl.addWidget(content_area, 1)

        # OCR progress bar
        self._ocr_progress_bar = QProgressBar()
        self._ocr_progress_bar.setFixedHeight(4)
        self._ocr_progress_bar.setTextVisible(False)
        self._ocr_progress_bar.hide()
        right_vl.addWidget(self._ocr_progress_bar)

        root_hl.addWidget(right_container, 1)

        # Initialize state properties usually set at the end of build UI
        self._sidebar_visible = True
        self._stamp_panel = None
        self._text_panel = None
        self._search_panel = None
        self._editing_annot = None
        self._editing_annot_page = -1

    def _connect_signals(self):
        self._tab_bar.currentChanged.connect(self._on_tab_changed)

        # Keyboard shortcuts
        QShortcut(QKeySequence("Ctrl+O"), self).activated.connect(self._open_file)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self._save_file)
        QShortcut(QKeySequence("Ctrl+Shift+S"), self).activated.connect(self._save_as)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(
            lambda: self._search_input.setFocus()
        )


    # ── Tab Management ────────────────────────

    def _active_tab(self) -> Optional[PDFTab]:
        if 0 <= self._active_tab_idx < len(self._tabs):
            return self._tabs[self._active_tab_idx]
        return None

    def _active_doc(self) -> Optional[fitz.Document]:
        t = self._active_tab()
        return t.document if t else None

    def _add_new_tab(self):
        tab = PDFTab()
        self._tabs.append(tab)
        self._tab_bar.addTab(tab.display_name)
        self._tab_bar.setCurrentIndex(len(self._tabs) - 1)

    def _close_tab(self, index: int):
        if len(self._tabs) <= 1:
            # Reset rather than close last tab
            tab = self._tabs[0]
            tab.close()
            tab.file_path = ""
            self._pdf_scroll.set_document(None)
            self._sidebar.load_document(None)
            self._tab_bar.setTabText(0, "새 탭")
            self._update_welcome_page()
            return

        self._tabs[index].close()
        self._tabs.pop(index)
        self._tab_bar.removeTab(index)
        # Switch to adjacent tab
        new_idx = min(index, len(self._tabs) - 1)
        self._active_tab_idx = new_idx
        self._tab_bar.setCurrentIndex(new_idx)
        self._load_active_tab()

    def _on_tab_changed(self, index: int):
        self._active_tab_idx = index
        self._load_active_tab()

    def _load_active_tab(self):
        tab = self._active_tab()
        if not tab:
            return
        # Switch back to PDF view when changing tabs
        if self._content_stack.currentWidget() == self._grid_view:
            self._content_stack.setCurrentWidget(self._pdf_scroll)
            self._grid_view_btn.setStyleSheet(TOPBAR_BUTTON_STYLE)
        self._pdf_scroll.set_document(tab.document, tab.file_path)
        self._sidebar.load_document(tab.document, tab.file_path)
        self._sidebar.set_current_page(tab.current_page)
        self._pdf_scroll.scroll_to_page(tab.current_page)
        self._update_toolbar_state()

    def _update_tab_title(self, tab: PDFTab):
        idx = self._tabs.index(tab)
        title = tab.display_name
        if tab.is_modified:
            title = "● " + title
        self._tab_bar.setTabText(idx, title)

    # ── File Operations ───────────────────────

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "파일 열기", "",
            "지원 파일 (*.pdf *.png *.jpg *.jpeg *.bmp *.gif *.tiff *.tif *.webp);;"
            "PDF Files (*.pdf);;"
            "이미지 (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.tif *.webp)"
        )
        if not path:
            return
        if path.lower().endswith(self._IMAGE_EXTS):
            self._import_images_as_pdf([path])
        else:
            self.load_file(path)

    def load_file(self, path: str):
        # Check if already open
        for i, tab in enumerate(self._tabs):
            if tab.file_path == path:
                self._tab_bar.setCurrentIndex(i)
                return

        # Use current empty tab or create new one
        tab = self._active_tab()
        if not tab or (tab.document is not None or tab.file_path):
            tab = PDFTab()
            self._tabs.append(tab)
            self._tab_bar.addTab("...")
            self._tab_bar.setCurrentIndex(len(self._tabs) - 1)
            self._active_tab_idx = len(self._tabs) - 1

        try:
            doc = fitz.open(path)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일을 열 수 없습니다:\n{e}")
            return

        tab.document = doc
        tab.file_path = path
        tab.current_page = 0
        tab.is_modified = False

        self._pdf_scroll.set_document(doc, path)
        self._pdf_scroll.set_zoom(1.0)
        self._sidebar.load_document(doc, path)
        self._update_tab_title(tab)
        self._update_toolbar_state()
        self._set_status(f"{Path(path).name} — {doc.page_count}p")
        self._add_recent_file(path)
        self._update_welcome_page()

    def _save_file(self):
        tab = self._active_tab()
        doc = self._active_doc()
        if not doc or not tab:
            return

        path = tab.file_path
        if not path:
            self._save_as()
            return

        # Burn overlay stamps first (on main thread as it modifies widgets/pixmaps)
        self._pdf_scroll.pdf_widget.burn_overlay_stamps()

        # Start async save
        self._start_save_worker(doc, path)

    def _start_save_worker(self, doc: fitz.Document, path: str):
        self._set_status("저장 중...")
        # Disable UI to prevent modification during save
        self.setEnabled(False)

        # 메인 스레드에서 바이트로 직렬화 후 워커에 전달 (스레드 안전)
        doc_bytes = doc.tobytes(garbage=3, deflate=True)
        orig_path = doc.name or ""
        self._save_worker = FileSaveWorker(doc_bytes, path, orig_path)
        self._save_worker.finished.connect(self._on_save_finished)
        self._save_worker.start()

    def _on_save_finished(self, success: bool, msg: str):
        self.setEnabled(True)
        tab = self._active_tab()
        if success:
            worker = self._save_worker
            if worker and worker.saved_bytes:
                # Same-file save: write bytes to file, reopen doc
                try:
                    data = worker.saved_bytes
                    worker.saved_bytes = None  # free memory

                    current_page = tab.current_page if tab else 0
                    current_zoom = self._pdf_scroll.pdf_widget._zoom

                    tab.document.close()

                    with open(msg, "wb") as f:
                        f.write(data)

                    new_doc = fitz.open(msg)
                    tab.document = new_doc
                    self._pdf_scroll.set_document(new_doc, msg)
                    self._pdf_scroll.set_zoom(current_zoom)
                    self._sidebar.load_document(new_doc, msg)
                    self._go_to_page(current_page)
                except Exception as e:
                    QMessageBox.critical(self, "저장 오류", f"파일 교체 중 오류:\n{e}")
                    self._set_status("저장 실패")
                    return

            # Handle save-as path update
            pending = getattr(self, "_pending_save_as_path", None)
            if pending and tab:
                tab.file_path = pending
                self._pending_save_as_path = None

            if tab:
                tab.is_modified = False
                self._update_tab_title(tab)
            self._set_status("저장 완료")
        else:
            self._pending_save_as_path = None
            QMessageBox.critical(self, "저장 오류", msg)
            self._set_status("저장 실패")

    def _save_as(self):
        tab = self._active_tab()
        doc = self._active_doc()
        if not doc or not tab:
            return

        default_name = Path(tab.file_path).name if tab.file_path else "document.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "다른 이름으로 저장", default_name, "PDF Files (*.pdf)"
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
            
        # Burn overlay stamps first
        self._pdf_scroll.pdf_widget.burn_overlay_stamps()
        
        # Update tab path immediately or wait? better wait for success
        # But we need to update tab.file_path for future saves.
        # We'll do it in _on_save_finished if passing context, 
        # or just assume active tab is same (modal block ensures this).
        
        self._pending_save_as_path = path # Store to update tab later
        self._start_save_worker(doc, path)

    # ── Navigation ────────────────────────────

    def _go_to_page(self, page: int):
        tab = self._active_tab()
        if not tab or not tab.document:
            return
        page = max(0, min(page, tab.document.page_count - 1))
        tab.current_page = page
        self._pdf_scroll.scroll_to_page(page)
        self._sidebar.set_current_page(page)
        self._update_page_label()

    def _prev_page(self):
        tab = self._active_tab()
        if tab:
            self._go_to_page(tab.current_page - 1)

    def _next_page(self):
        tab = self._active_tab()
        if tab:
            self._go_to_page(tab.current_page + 1)

    def _on_pdf_page_changed(self, page: int):
        tab = self._active_tab()
        if tab:
            tab.current_page = page
            self._sidebar.set_current_page(page)
            self._update_page_label()

    # ── Zoom ──────────────────────────────────

    def _zoom_in(self):
        z = self._pdf_scroll.pdf_widget.zoom
        self._pdf_scroll.zoom_to(z * 1.25)

    def _zoom_out(self):
        z = self._pdf_scroll.pdf_widget.zoom
        self._pdf_scroll.zoom_to(z / 1.25)

    def _on_zoom_changed(self, z: float):
        # Only update text when the input is not focused (don't override user typing)
        if not self._zoom_input.hasFocus():
            self._zoom_input.setText(f"{int(z * 100)}%")

    def _apply_zoom_input(self):
        """Parse the zoom percentage the user typed and apply it."""
        # Guard against re-entrant calls (clearFocus can re-trigger editingFinished)
        if getattr(self, "_zoom_input_busy", False):
            return
        self._zoom_input_busy = True
        try:
            text = self._zoom_input.text().strip().rstrip("%").strip()
            try:
                percent = float(text)
                percent = max(10.0, min(percent, 800.0))
                self._pdf_scroll.zoom_to(percent / 100.0)
                self._zoom_input.setText(f"{int(percent)}%")
            except ValueError:
                # Invalid input — restore the current zoom value
                z = self._pdf_scroll.pdf_widget.zoom
                self._zoom_input.setText(f"{int(z * 100)}%")
            self._zoom_input.clearFocus()
        finally:
            self._zoom_input_busy = False

    # ── Page Operations ───────────────────────

    def _delete_current_page(self):
        tab = self._active_tab()
        if tab:
            self._delete_pages([tab.current_page])

    def _delete_pages(self, pages: list[int]):
        doc = self._active_doc()
        tab = self._active_tab()
        if not doc or not tab:
            return
        if len(pages) >= doc.page_count:
            QMessageBox.warning(self, "알림", "마지막 페이지는 삭제할 수 없습니다.")
            return
        for p in sorted(pages, reverse=True):
            doc.delete_page(p)
        tab.current_page = min(tab.current_page, doc.page_count - 1)
        tab.is_modified = True
        self._on_doc_changed()
        self._set_status(f"{len(pages)}페이지 삭제됨")

    def _rotate_current_page(self):
        self._rotate_pages([self._active_tab().current_page if self._active_tab() else 0])

    def _rotate_pages(self, pages: list[int]):
        doc = self._active_doc()
        tab = self._active_tab()
        if not doc or not tab:
            return
        for p in pages:
            if 0 <= p < doc.page_count:
                page = doc[p]
                page.set_rotation((page.rotation + 90) % 360)
        tab.is_modified = True
        self._on_doc_changed()

    def _insert_pdf(self):
        doc = self._active_doc()
        tab = self._active_tab()
        if not doc or not tab:
            return
        path, _ = QFileDialog.getOpenFileName(self, "삽입할 PDF 선택", "", "PDF (*.pdf)")
        if not path:
            return
        try:
            extra = fitz.open(path)
            insert_at = tab.current_page + 1
            doc.insert_pdf(extra, start_at=insert_at)
            extra.close()
            tab.is_modified = True
            self._on_doc_changed()
            self._set_status(f"페이지 삽입 완료")
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))

    def _insert_pdf_at(self, file_path: str, insert_before: int):
        """Insert an external PDF at a specific page position (from sidebar drop)."""
        doc = self._active_doc()
        tab = self._active_tab()
        if not doc or not tab:
            return
        try:
            extra = fitz.open(file_path)
            added = extra.page_count
            doc.insert_pdf(extra, start_at=insert_before)
            extra.close()
            tab.is_modified = True
            self._on_doc_changed()
            self._set_status(f"{added}페이지 삽입 완료 (위치: {insert_before + 1})")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"PDF 삽입 실패:\n{e}")

    def _merge_pdfs(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "합칠 PDF 선택 (2개 이상)", "", "PDF (*.pdf)")
        if len(paths) < 2:
            QMessageBox.information(self, "알림", "2개 이상의 PDF를 선택하세요.")
            return
        dest, _ = QFileDialog.getSaveFileName(self, "저장 위치", "merged.pdf", "PDF (*.pdf)")
        if not dest:
            return
        try:
            merged = fitz.open()
            for p in paths:
                src = fitz.open(p)
                merged.insert_pdf(src)
                src.close()
            merged.save(dest, garbage=3, deflate=True)
            merged.close()
            self._set_status(f"합치기 완료: {Path(dest).name}")
            self.load_file(dest)
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))

    def _show_split_dialog(self):
        doc = self._active_doc()
        if not doc:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("PDF 분할")
        vl = QVBoxLayout(dlg)
        vl.addWidget(QLabel(f"총 {doc.page_count}페이지"))

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("시작:"))
        start_spin = QSpinBox()
        start_spin.setRange(1, doc.page_count)
        start_spin.setValue(1)
        row1.addWidget(start_spin)
        vl.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("끝:"))
        end_spin = QSpinBox()
        end_spin.setRange(1, doc.page_count)
        end_spin.setValue(doc.page_count)
        row2.addWidget(end_spin)
        vl.addLayout(row2)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        vl.addWidget(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        start = start_spin.value() - 1
        end = end_spin.value() - 1

        dest, _ = QFileDialog.getSaveFileName(self, "저장 위치", "split.pdf", "PDF (*.pdf)")
        if not dest:
            return
        try:
            new_doc = fitz.open()
            new_doc.insert_pdf(doc, from_page=start, to_page=end)
            new_doc.save(dest, garbage=3, deflate=True)
            new_doc.close()
            self._set_status(f"분할 완료 ({start+1}~{end+1}p)")
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))

    # ── AI Features ───────────────────────────

    def _show_ai_panel(self):
        doc = self._active_doc()
        if not doc:
            return
        self._clear_right_panel()
        self._active_chat_session = None  # Reset chat session
        
        from panels import AIToolPanel
        panel = AIToolPanel(self._ai_mgr)
        panel.summarize_requested.connect(self._on_ai_summarize)
        panel.table_extract_requested.connect(self._on_ai_table_extract)
        panel.ocr_correct_requested.connect(self._on_ai_ocr_correct)
        panel.chat_message_entered.connect(self._on_chat_message_entered)
        panel.closed.connect(self._clear_right_panel)
        self._set_right_panel(panel)
        
    def _show_settings(self):
        dlg = SettingsDialog(self._ai_mgr, self)
        dlg.theme_changed.connect(self._apply_theme)
        if dlg.exec():
            # Refresh AI panel status if it's open
            panel = self._find_ai_panel()
            if panel:
                if self._ai_mgr.is_configured():
                    panel.status_lbl.setText("AI 준비됨")
                    panel.status_lbl.setStyleSheet("color: #2979FF; font-size: 11px; font-weight: bold;")
                else:
                    panel.status_lbl.setText("상단의 설정(⚙) 메뉴에서\nAPI Key를 입력해주세요.")
                    panel.status_lbl.setStyleSheet("color: #FF3B30; font-size: 11px;")

    def _apply_theme(self, is_dark: bool):
        """Apply light or dark theme without restarting."""
        from main import apply_theme
        apply_theme(QApplication.instance(), is_dark)

    def _find_ai_panel(self):
        """Find the active AIToolPanel in the right panel."""
        for i in range(self._right_panel_hl.count()):
            w = self._right_panel_hl.itemAt(i).widget()
            if hasattr(w, "append_chat_message"):
                return w
        return None

    def _on_chat_message_entered(self, text: str):
        if not self._ai_mgr.is_configured():
            QMessageBox.warning(self, "설정 불완전", "Gemini API Key가 설정되지 않았습니다. 상단 톱니바퀴 [⚙] 버튼을 눌러 API 키를 입력해주세요.")
            return

        ai_panel = self._find_ai_panel()
        if not ai_panel:
            return

        ai_panel.append_chat_message("👤", text)
        ai_panel.set_input_enabled(False)

        # file_path를 전달하면 ChatWorker가 스레드에서 텍스트를 추출
        file_path = ""
        if not getattr(self, "_active_chat_session", None):
            tab = self._active_tab()
            if tab and tab.file_path:
                file_path = tab.file_path

        self._stop_worker(getattr(self, "_chat_worker", None))
        self._chat_worker = ChatWorker(
            self._ai_mgr, text,
            session=getattr(self, "_active_chat_session", None),
            file_path=file_path,
        )
        self._chat_worker.session_created.connect(self._on_chat_session_created)
        self._chat_worker.response_ready.connect(self._on_chat_response)
        self._chat_worker.error_occurred.connect(self._on_chat_error)
        self._chat_worker.start()

    def _on_chat_session_created(self, session):
        self._active_chat_session = session

    def _on_chat_response(self, response_text: str):
        ai_panel = self._find_ai_panel()
        if ai_panel:
            ai_panel.append_chat_message("🤖", response_text)
            ai_panel.set_input_enabled(True)

    def _on_chat_error(self, error_msg: str):
        ai_panel = self._find_ai_panel()
        if ai_panel:
            ai_panel.append_chat_message("❌ 오류", error_msg)
            ai_panel.set_input_enabled(True)

    def _is_ai_task_running(self) -> bool:
        return getattr(self, '_ai_task_worker', None) is not None and self._ai_task_worker.isRunning()

    def _on_ai_summarize(self):
        if self._is_ai_task_running():
            self._set_status("AI 작업이 진행 중입니다. 완료 후 다시 시도하세요.")
            return
        tab = self._active_tab()
        if not tab:
            return

        page = tab.document[tab.current_page]
        text = page.get_text("text").strip()

        if not text:
            QMessageBox.information(self, "AI 요약", "현재 페이지에 추출할 수 있는 텍스트가 없습니다. 먼저 빈 페이지인지 확인해주세요.")
            return

        self._set_status("AI 요약 중...")
        self._stop_worker(getattr(self, "_ai_task_worker", None))
        worker = AITaskWorker(self._ai_mgr.summarize_text, text)
        worker.result_ready.connect(self._on_summarize_done)
        worker.error_occurred.connect(lambda e: (
            QMessageBox.critical(self, "AI 요약 오류", e),
            self._set_status("AI 요약 실패")
        ))
        self._ai_task_worker = worker
        worker.start()

    def _on_summarize_done(self, summary: str):
        dlg = QDialog(self)
        dlg.setWindowTitle("AI 페이지 요약")
        dlg.resize(500, 400)
        vl = QVBoxLayout(dlg)

        from PyQt6.QtWidgets import QTextEdit
        te = QTextEdit()
        te.setReadOnly(True)
        te.setPlainText(summary)
        vl.addWidget(te)

        btn = QPushButton("닫기")
        btn.clicked.connect(dlg.accept)
        vl.addWidget(btn)

        dlg.exec()
        self._set_status("AI 요약 완료")
            
    def _on_ai_table_extract(self):
        if self._is_ai_task_running():
            self._set_status("AI 작업이 진행 중입니다. 완료 후 다시 시도하세요.")
            return
        if not self._ai_mgr.is_configured():
            QMessageBox.warning(self, "설정 불완전", "Gemini API Key가 설정되지 않았습니다. 상단 톱니바퀴 [⚙] 버튼을 눌러 API 키를 입력해주세요.")
            return

        tab = self._active_tab()
        if not tab:
            return
            
        self._set_status("표를 추출할 영역을 드래그하세요.")
        self._pdf_scroll.pdf_widget.enter_crop_mode(self._do_table_extract)
        
    def _do_table_extract(self, page_index: int, rect: fitz.Rect):
        self._set_status("AI 표 추출 중...")
        mat = fitz.Matrix(2.0, 2.0)
        try:
            pix = self._active_doc()[page_index].get_pixmap(matrix=mat, clip=rect)
            img_bytes = pix.tobytes("png")
        except Exception as e:
            QMessageBox.critical(self, "이미지 추출 오류", str(e))
            return

        self._table_extract_page_index = page_index
        self._stop_worker(getattr(self, "_ai_task_worker", None))
        worker = AITaskWorker(self._ai_mgr.extract_table, img_bytes)
        worker.result_ready.connect(self._on_table_extract_done)
        worker.error_occurred.connect(lambda e: (
            QMessageBox.critical(self, "AI 표 추출 오류", e),
            self._set_status("AI 표 추출 실패")
        ))
        self._ai_task_worker = worker
        worker.start()

    def _on_table_extract_done(self, csv_data: str):
        page_index = self._table_extract_page_index
        dlg = QDialog(self)
        dlg.setWindowTitle("AI 표 추출 결과 (CSV)")
        dlg.resize(600, 500)
        vl = QVBoxLayout(dlg)

        from PyQt6.QtWidgets import QTextEdit
        te = QTextEdit()
        te.setPlainText(csv_data)
        vl.addWidget(te)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Close)

        def save_csv():
            path, _ = QFileDialog.getSaveFileName(self, "CSV 저장", f"extracted_table_page_{page_index+1}.csv", "CSV Files (*.csv)")
            if path:
                with open(path, "w", encoding="utf-8-sig") as f:
                    f.write(te.toPlainText())
                dlg.accept()

        btns.button(QDialogButtonBox.StandardButton.Save).clicked.connect(save_csv)
        btns.button(QDialogButtonBox.StandardButton.Close).clicked.connect(dlg.reject)
        vl.addWidget(btns)

        dlg.exec()
        self._set_status("AI 표 추출 완료")
            
    def _on_ai_ocr_correct(self):
        if self._is_ai_task_running():
            self._set_status("AI 작업이 진행 중입니다. 완료 후 다시 시도하세요.")
            return
        if not self._ai_mgr.is_configured():
            QMessageBox.warning(self, "설정 불완전", "Gemini API Key가 설정되지 않았습니다. 상단 톱니바퀴 [⚙] 버튼을 눌러 API 키를 입력해주세요.")
            return

        tab = self._active_tab()
        if not tab:
            return

        page = tab.document[tab.current_page]
        text = page.get_text("text").strip()

        if not text:
            QMessageBox.information(self, "AI 오타 교정", "현재 페이지에 교정할 텍스트가 없습니다. 먼저 OCR을 실행하거나 텍스트가 있는 페이지를 선택하세요.")
            return

        self._set_status("AI 오타 교정 중...")
        self._ocr_correct_page_num = tab.current_page
        self._stop_worker(getattr(self, "_ai_task_worker", None))
        worker = AITaskWorker(self._ai_mgr.correct_ocr, text)
        worker.result_ready.connect(self._on_ocr_correct_done)
        worker.error_occurred.connect(lambda e: (
            QMessageBox.critical(self, "AI 오타 교정 오류", e),
            self._set_status("AI 오타 교정 실패")
        ))
        self._ai_task_worker = worker
        worker.start()

    def _on_ocr_correct_done(self, corrected_text: str):
        page_num = self._ocr_correct_page_num
        dlg = QDialog(self)
        dlg.setWindowTitle("AI 오타 교정 결과")
        dlg.resize(600, 500)
        vl = QVBoxLayout(dlg)

        from PyQt6.QtWidgets import QTextEdit
        te = QTextEdit()
        te.setPlainText(corrected_text)
        vl.addWidget(te)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Close)

        def save_txt():
            path, _ = QFileDialog.getSaveFileName(self, "텍스트 저장", f"corrected_page_{page_num+1}.txt", "Text Files (*.txt)")
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(te.toPlainText())
                dlg.accept()

        btns.button(QDialogButtonBox.StandardButton.Save).clicked.connect(save_txt)
        btns.button(QDialogButtonBox.StandardButton.Close).clicked.connect(dlg.reject)
        vl.addWidget(btns)

        dlg.exec()
        self._set_status("AI 오타 교정 완료")

    # ── Annotations ───────────────────────────

    def _show_stamp_panel(self):
        doc = self._active_doc()
        if not doc:
            return
        self._clear_right_panel()
        panel = StampPanel(self._stamp_mgr)
        panel.stamp_selected.connect(self._on_stamp_selected)
        panel.closed.connect(self._clear_right_panel)
        self._set_right_panel(panel)

    def _on_stamp_selected(self, path: str):
        tab = self._active_tab()
        if not tab:
            return
        self._pdf_scroll.pdf_widget.place_stamp_on_page(tab.current_page, path)
        self._set_status(f"직인이 {tab.current_page + 1}페이지에 추가됨")
        self._clear_right_panel()

    def _add_text(self):
        doc = self._active_doc()
        if not doc:
            return
        self._clear_right_panel()

        panel = TextToolPanel()
        panel.load_config(self._text_config)
        panel.apply_requested.connect(self._on_text_apply)
        panel.cancel_requested.connect(self._clear_right_panel)
        self._set_right_panel(panel)
        self._text_panel = panel

        # 타이머를 인스턴스 변수로 저장하여 _clear_right_panel에서 중지 가능
        self._text_enter_timer = QTimer(self)
        self._text_enter_timer.setSingleShot(True)
        self._text_enter_timer.timeout.connect(self._deferred_enter_text_mode)
        self._text_enter_timer.start(50)
        self._set_status("텍스트 위치를 클릭하거나 적용을 눌러 중앙에 추가")

    def _deferred_enter_text_mode(self):
        """타이머 콜백: 패널이 아직 살아있을 때만 텍스트 배치 모드 진입."""
        if self._text_panel:
            try:
                self._pdf_scroll.pdf_widget.enter_text_placement_mode(
                    self._text_config.to_dict()
                )
            except RuntimeError:
                pass

    def _on_text_apply(self, config: TextToolConfig):
        self._text_config = config
        tab = self._active_tab()
        if not tab:
            return
        pw = self._pdf_scroll.pdf_widget
        if pw.mode == pw.MODE_TEXT_PLACEMENT:
            # Place at center
            pw.add_text_at_page_center(tab.current_page, config.to_dict())
        pw.exit_text_placement_mode()
        self._clear_right_panel()
        self._set_status("텍스트 추가됨")

    # ── Annotation Edit via Panel ──────────────

    def _edit_annot_in_panel(self, annot, page_index: int):
        """Open TextToolPanel pre-filled with the annotation's current properties."""
        self._clear_right_panel()

        # Extract current text and color from the annotation
        try:
            text = annot.info.get("content", "")
            stroke = annot.colors.get("stroke", None)
        except Exception:
            text = ""
            stroke = None

        config = TextToolConfig()
        config.text = text
        config.font_name = self._text_config.font_name
        config.font_size = self._text_config.font_size
        config.bold = self._text_config.bold
        config.italic = self._text_config.italic
        if stroke:
            r, g, b = stroke
            config.color_hex = "#{:02x}{:02x}{:02x}".format(
                int(r * 255), int(g * 255), int(b * 255)
            )
        else:
            config.color_hex = self._text_config.color_hex

        self._editing_annot = annot
        self._editing_annot_page = page_index

        panel = TextToolPanel()
        panel.load_config(config)
        panel.apply_requested.connect(self._on_annot_edit_apply)
        panel.cancel_requested.connect(self._on_annot_edit_cancel)
        self._set_right_panel(panel)
        self._text_panel = panel

    def _on_annot_edit_apply(self, config: TextToolConfig):
        annot = self._editing_annot
        page_index = self._editing_annot_page
        self._editing_annot = None
        self._editing_annot_page = -1
        if annot is None:
            self._clear_right_panel()
            return
        self._text_config = config
        self._pdf_scroll.pdf_widget.update_freetext_annot(annot, page_index, config.to_dict())
        self._clear_right_panel()
        self._set_status("텍스트 수정됨")

    def _on_annot_edit_cancel(self):
        self._editing_annot = None
        self._editing_annot_page = -1
        self._clear_right_panel()

    # ── PDF Text Edit ────────────────────────

    def _toggle_text_edit_mode(self):
        """Toggle inline text edit mode for electronically created PDFs."""
        doc = self._active_doc()
        if not doc:
            return
        pw = self._pdf_scroll.pdf_widget
        if pw.mode == pw.MODE_TEXT_EDIT:
            pw._exit_current_mode()
            self._reset_text_edit_btn_style()
            self._set_status("텍스트 편집 모드 종료")
        else:
            # 다른 모드가 활성화되어 있으면 정리 (_clear_right_panel이 모드도 종료)
            self._clear_right_panel()
            pw.enter_text_edit_mode()
            self._text_edit_btn.setStyleSheet(TOPBAR_BUTTON_ACTIVE_STYLE)
            self._set_status("텍스트 편집 모드 — 텍스트를 클릭하여 수정 (Esc: 취소, Enter: 적용)")

    def _reset_text_edit_btn_style(self):
        """Reset text edit button to default style."""
        if hasattr(self, '_text_edit_btn'):
            self._text_edit_btn.setStyleSheet(TOPBAR_BUTTON_STYLE)

    # ── Grid View ─────────────────────────────

    def _toggle_grid_view(self):
        """Toggle between PDF view and full-page grid view."""
        if self._content_stack.currentWidget() == self._grid_view:
            # Switch back to PDF view
            self._content_stack.setCurrentWidget(self._pdf_scroll)
            if hasattr(self, '_grid_view_btn'):
                self._grid_view_btn.setStyleSheet(TOPBAR_BUTTON_STYLE)
            self._set_status("PDF 보기")
        else:
            doc = self._active_doc()
            tab = self._active_tab()
            if not doc or not tab:
                return
            # Save current page in tab so we can restore or focus
            self._clear_right_panel()
            
            # Switch to grid view before loading to fix QListWidget icon mode layout width
            self._content_stack.setCurrentWidget(self._grid_view)
            
            # Pass document to grid view
            pw = self._pdf_scroll.pdf_widget
            doc_bytes = pw._doc_bytes_snapshot
            self._grid_view.load_document(tab.document, tab.current_page, file_path=tab.file_path, doc_bytes=doc_bytes)
            if hasattr(self, '_grid_view_btn'):
                self._grid_view_btn.setStyleSheet(TOPBAR_BUTTON_ACTIVE_STYLE)
            self._set_status("그리드 보기 — 더블클릭으로 페이지 이동")

    def _on_grid_page_selected(self, page: int):
        """Handle double-click in grid view: navigate and switch back to PDF."""
        self._go_to_page(page)
        self._content_stack.setCurrentWidget(self._pdf_scroll)
        if hasattr(self, '_grid_view_btn'):
            self._grid_view_btn.setStyleSheet(TOPBAR_BUTTON_STYLE)
        self._set_status(f"Page {page + 1}")

    # ── Bookmarks ─────────────────────────────

    def _toggle_bookmark(self):
        tab = self._active_tab()
        if not tab or not tab.document:
            return
        added = self._bookmark_mgr.toggle(tab.file_path, tab.current_page)
        self._set_status(
            f"Page {tab.current_page + 1} {'★ 북마크' if added else '북마크 해제'}"
        )

    def _remove_bookmark(self, page: int):
        tab = self._active_tab()
        if not tab:
            return
        if self._bookmark_mgr.has(tab.file_path, page):
            self._bookmark_mgr.toggle(tab.file_path, page)
            self._set_status(f"Page {page + 1} 북마크 해제")

    # ── Outline (TOC) ────────────────────────

    def _add_outline_entry(self):
        """Add current page to the PDF's table of contents."""
        tab = self._active_tab()
        doc = self._active_doc()
        if not tab or not doc:
            return
        page_num = tab.current_page + 1  # 1-based for TOC

        title, ok = QInputDialog.getText(
            self, "목차 추가", f"Page {page_num} 목차 제목:",
        )
        if not ok or not title.strip():
            return

        toc = doc.get_toc()
        toc.append([1, title.strip(), page_num])
        toc.sort(key=lambda e: e[2])
        doc.set_toc(toc)

        tab.is_modified = True
        self._update_tab_title(tab)
        self._sidebar.load_document(doc, tab.file_path)
        self._set_status(f"목차 추가: \"{title.strip()}\" → Page {page_num}")

    def _remove_outline_entry(self, page: int, title: str):
        doc = self._active_doc()
        tab = self._active_tab()
        if not doc or not tab:
            return
        toc = doc.get_toc()
        page_num = page + 1  # TOC uses 1-based
        new_toc = [e for e in toc if not (e[1] == title and e[2] == page_num)]
        if len(new_toc) == len(toc):
            return  # nothing removed
        doc.set_toc(new_toc)
        tab.is_modified = True
        self._update_tab_title(tab)
        self._sidebar.load_document(doc, tab.file_path)
        self._pdf_scroll.pdf_widget._snapshot_doc_bytes()
        self._set_status(f"목차 제거: \"{title}\"")

    # ── OCR ───────────────────────────────────

    def _show_ocr_dialog(self):
        tab = self._active_tab()
        if not tab or not tab.document:
            return

        langs = OCRLanguage.all_cases()
        lang_names = [str(l) for l in langs]
        choice, ok = QInputDialog.getItem(
            self, "OCR 언어 선택", "언어:", lang_names, 0, False
        )
        if not ok:
            return
        lang = langs[lang_names.index(choice)]
        self._run_ocr(tab.file_path, tab.document, lang)

    def _run_ocr(self, file_path: str, doc: fitz.Document, language: OCRLanguage):
        self._ocr_progress_bar.setMaximum(doc.page_count)
        self._ocr_progress_bar.setValue(0)
        self._ocr_progress_bar.show()
        self._set_status("OCR 실행 중...")

        worker = self._ocr_mgr.start(file_path, language)
        worker.progress.connect(self._on_ocr_progress)
        worker.page_done.connect(self._on_ocr_page_done)
        worker.finished_ocr.connect(self._on_ocr_finished)
        worker.error.connect(self._on_ocr_error)

    def _on_ocr_progress(self, current: int, total: int):
        self._ocr_progress_bar.setMaximum(total)
        self._ocr_progress_bar.setValue(current)
        self._set_status(f"OCR {current}/{total}...")

    def _on_ocr_page_done(self, page_index: int, text: str):
        """OCR 텍스트가 PDF 페이지에 투명 텍스트로 삽입됨 — 뷰어 갱신."""
        pass  # 텍스트는 이미 ocr_manager에서 PDF에 삽입됨

    def _on_ocr_finished(self, total_chars: int, doc_bytes: bytes):
        self._ocr_progress_bar.hide()
        self._set_status(f"OCR 완료 — {total_chars}자 인식")
        tab = self._active_tab()
        if not tab:
            return

        # OCR 워커가 자체 doc에 텍스트를 삽입하고 bytes로 직렬화했으므로,
        # 메인 스레드의 doc을 이 bytes로부터 다시 열어야 OCR 결과가 반영된다.
        try:
            current_page = tab.current_page
            if tab.document:
                tab.document.close()
            new_doc = fitz.open(stream=doc_bytes, filetype="pdf")
            tab.document = new_doc
            tab.is_modified = True
            self._pdf_scroll.pdf_widget.set_document(new_doc, tab.file_path)
            self._pdf_scroll.pdf_widget._doc_bytes_snapshot = doc_bytes
            self._sidebar.load_document(new_doc, tab.file_path, doc_bytes=doc_bytes)
            self._update_tab_title(tab)
            self._go_to_page(current_page)
        except Exception as e:
            self._set_status(f"OCR 결과 적용 오류: {e}")

    def _on_ocr_error(self, msg: str):
        self._ocr_progress_bar.hide()
        QMessageBox.critical(self, "OCR 오류", msg)

    # ── Search ────────────────────────────────

    # ── Search ────────────────────────────────

    def _perform_search(self):
        query = self._search_input.text().strip()
        tab = self._active_tab()
        doc = self._active_doc()
        if not doc or not tab or not tab.file_path or not query:
            return

        # Prepare UI for search results
        self._clear_right_panel()
        self._search_panel = SearchResultsPanel()
        self._search_panel.result_selected.connect(self._on_search_result_selected)
        self._search_panel.closed.connect(self._on_search_closed)
        self._set_right_panel(self._search_panel)

        self._set_status(f"'{query}' 검색 중...")
        self._search_input.setEnabled(False)

        # Start async search — 수정된 doc이 있으면 bytes 스냅샷 사용
        self._stop_worker(getattr(self, "_search_worker", None))
        doc_bytes = self._pdf_scroll.pdf_widget._doc_bytes_snapshot
        self._search_worker = SearchWorker(tab.file_path, query, doc_bytes=doc_bytes)
        self._search_results_buf = []
        self._search_worker.result_found.connect(self._on_search_result_found)
        self._search_worker.finished_search.connect(self._on_search_finished)
        self._search_worker.error.connect(lambda e: self._set_status(f"검색 오류: {e}"))
        self._search_worker.start()

    def _on_search_result_found(self, page_idx: int, rect: object, snippet: str):
        self._search_results_buf.append((page_idx, rect, snippet))
        # Update panel periodically or immediately? 
        # For responsiveness, batch updates might be better, but let's try direct first.
        # Actually, let's just update the list model.
        # But SearchResultsPanel.set_results replaces the whole list.
        # We need an append method or set the whole list again.
        if self._search_panel:
            self._search_panel.set_results(self._search_results_buf)

    def _on_search_finished(self, total: int):
        self._search_input.setEnabled(True)
        self._set_status(f"검색 완료: {total}건 발견")
        
        if self._search_results_buf:
            # Highlight first result
            first = self._search_results_buf[0]
            self._go_to_page(first[0])
            
            # Update viewer highlights
            self._pdf_scroll.pdf_widget.set_search_highlights(
                [(r[0], r[1]) for r in self._search_results_buf], 0
            )
            
            self._search_prev_btn.show()
            self._search_next_btn.show()
        else:
            self._search_prev_btn.hide()
            self._search_next_btn.hide()

    def _navigate_search(self, delta: int):
        if self._search_panel:
            self._search_panel._navigate(delta)

    def _on_search_result_selected(self, page_index: int, rect):
        self._go_to_page(page_index)
        # Update the viewer highlight to reflect the currently selected result
        if self._search_panel and self._search_results_buf:
            current_idx = self._search_panel._current_idx
            self._pdf_scroll.pdf_widget.set_search_highlights(
                [(r[0], r[1]) for r in self._search_results_buf], current_idx
            )

    def _on_search_closed(self):
        self._pdf_scroll.pdf_widget.clear_search()
        self._search_input.clear()
        self._search_prev_btn.hide()
        self._search_next_btn.hide()
        self._clear_right_panel()

    # ── Right Panel ───────────────────────────

    def _set_right_panel(self, widget: QWidget):
        # Remove existing
        while self._right_panel_hl.count():
            item = self._right_panel_hl.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add divider line
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setStyleSheet("color: #d0d0d0;")
        self._right_panel_hl.addWidget(divider)
        self._right_panel_hl.addWidget(widget)

        # Set container width to accommodate the panel
        panel_w = widget.minimumWidth() or widget.sizeHint().width()
        target_width = max(panel_w, 260) + 4  # +4 for divider + margins
        
        self._right_panel_container.setMinimumWidth(target_width)
        
        sizes = self._splitter.sizes()
        total_w = sum(sizes)
        if self._right_panel_container.isHidden():
            sizes[0] = sizes[0] if sizes[0] > 0 else 220
            new_center_w = max(100, total_w - sizes[0] - target_width)
            self._splitter.setSizes([sizes[0], new_center_w, target_width])
            
        self._right_panel_container.show()
        # Allow the panel to resize up to a reasonable maximum
        self._right_panel_container.setMaximumWidth(800)
        
        # 레이아웃이 안정화된 다음 이벤트 루프에서 포커스 설정
        # 즉시 setFocus하면 enter_text_placement_mode가 뒤이어 호출되며 포커스를 빼앗음
        def _focus_widget():
            try:
                widget.setFocus(Qt.FocusReason.OtherFocusReason)
            except RuntimeError:
                pass
        QTimer.singleShot(0, _focus_widget)

    def _clear_right_panel(self):
        # 재진입 방지: 시그널 연쇄로 인한 이중 호출을 차단
        if getattr(self, "_clearing_right_panel", False):
            return
        self._clearing_right_panel = True
        try:
            while self._right_panel_hl.count():
                item = self._right_panel_hl.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            self._right_panel_container.setMinimumWidth(0)
            self._right_panel_container.setMaximumWidth(16777215) # QWIDGETSIZE_MAX
            self._right_panel_container.hide()

            # Give space back to center
            sizes = self._splitter.sizes()
            total = sum(sizes)
            self._splitter.setSizes([sizes[0], total - sizes[0], 0])

            # 텍스트 배치 모드 진입 타이머가 아직 활성이면 중지
            if getattr(self, '_text_enter_timer', None) and self._text_enter_timer.isActive():
                self._text_enter_timer.stop()

            self._text_panel = None
            self._stamp_panel = None
            self._search_panel = None
            self._editing_annot = None
            self._editing_annot_page = -1
            # 현재 활성 모드를 안전하게 종료 (TEXT_EDIT, TEXT_PLACEMENT, CROP 모두 처리)
            pw = self._pdf_scroll.pdf_widget
            if pw.mode != pw.MODE_NORMAL:
                was_text_edit = pw.mode == pw.MODE_TEXT_EDIT
                pw._exit_current_mode()
                if was_text_edit:
                    self._reset_text_edit_btn_style()
        finally:
            self._clearing_right_panel = False

    # ── Sidebar ───────────────────────────────

    def _toggle_sidebar(self):
        self._sidebar_visible = not self._sidebar_visible
        self._sidebar.setVisible(self._sidebar_visible)
        sizes = self._splitter.sizes()
        total = sum(sizes)
        if self._sidebar_visible:
            self._splitter.setSizes([220, total - 220])
        else:
            self._splitter.setSizes([0, total])

    # ── Helpers ───────────────────────────────

    def _on_doc_modified(self):
        tab = self._active_tab()
        if tab:
            tab.is_modified = True
            self._update_tab_title(tab)

    def _on_text_copied(self, char_count: int):
        self._set_status(f"{char_count}자 클립보드에 복사됨")

    def _on_doc_changed(self):
        """Called after structural page changes (delete, rotate, etc.)."""
        doc = self._active_doc()
        tab = self._active_tab()
        if not doc or not tab:
            return
        # 스냅샷을 set_document 전에 만들어야 update() 시 최신 doc_bytes로 렌더링
        self._pdf_scroll.pdf_widget._doc = doc
        self._pdf_scroll.pdf_widget._snapshot_doc_bytes()
        doc_bytes = self._pdf_scroll.pdf_widget._doc_bytes_snapshot
        self._pdf_scroll.pdf_widget.set_document(doc, tab.file_path,
                                                  keep_snapshot=True)
        self._pdf_scroll.pdf_widget.invalidate_all_pages()
        self._sidebar.reload_thumbnails(doc_bytes=doc_bytes)
        # Refresh grid view if it's currently visible
        if self._content_stack.currentWidget() == self._grid_view:
            self._grid_view.load_document(doc, tab.current_page,
                                          file_path=tab.file_path, doc_bytes=doc_bytes)
        self._update_tab_title(tab)
        self._update_toolbar_state()

    def _update_toolbar_state(self):
        doc = self._active_doc()
        tab = self._active_tab()
        has_doc = doc is not None
        self._update_page_label()

    def _update_page_label(self):
        tab = self._active_tab()
        doc = self._active_doc()
        if doc and tab:
            self._page_label.setText(f"{tab.current_page + 1}/{doc.page_count}")
        else:
            self._page_label.setText("—")

    def _set_status(self, msg: str):
        self._status_label.setText(msg)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_welcome_page') and self._welcome_page.isVisible():
            self._welcome_page.setGeometry(self._pdf_scroll.viewport().rect())

    # ── Drag & Drop (PDF / Image) ──────────────

    _IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.tif', '.webp')

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile().lower()
                if path.endswith('.pdf') or path.endswith(self._IMAGE_EXTS):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        image_paths = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            lower = path.lower()
            if lower.endswith('.pdf'):
                self.load_file(path)
                return
            if lower.endswith(self._IMAGE_EXTS):
                image_paths.append(path)

        if image_paths:
            self._import_images_as_pdf(image_paths)

    def _import_images_as_pdf(self, image_paths: list[str]):
        """이미지 파일(들)을 PDF로 변환하여 새 탭에 열기."""
        try:
            doc = fitz.open()
            for img_path in image_paths:
                pix = fitz.Pixmap(img_path)
                w, h = pix.width, pix.height
                pix = None  # free memory
                page = doc.new_page(width=w, height=h)
                page.insert_image(page.rect, filename=img_path)

            # 임시 파일로 저장 후 열기
            base = os.path.splitext(os.path.basename(image_paths[0]))[0]
            if len(image_paths) > 1:
                base += f"_외_{len(image_paths)-1}건"
            tmp_path = os.path.join(tempfile.gettempdir(), f"{base}.pdf")
            doc.save(tmp_path, garbage=3, deflate=True)
            doc.close()

            self.load_file(tmp_path)
            self._set_status(
                f"이미지 → PDF 변환 완료 ({len(image_paths)}장)"
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"이미지 변환 실패:\n{e}")

    # ── Window State Persistence ────────────────

    def _restore_window_state(self):
        """Restore window geometry and splitter sizes from QSettings."""
        geo = self._settings.value("window_geometry")
        if geo and isinstance(geo, QByteArray):
            self.restoreGeometry(geo)
        state = self._settings.value("window_state")
        if state and isinstance(state, QByteArray):
            self.restoreState(state)
        splitter_sizes = self._settings.value("splitter_sizes")
        if splitter_sizes:
            try:
                self._splitter.setSizes([int(s) for s in splitter_sizes])
            except (TypeError, ValueError):
                pass

    def _save_window_state(self):
        """Save window geometry and splitter sizes to QSettings."""
        self._settings.setValue("window_geometry", self.saveGeometry())
        self._settings.setValue("window_state", self.saveState())
        self._settings.setValue("splitter_sizes", self._splitter.sizes())

    # ── Recent Files ─────────────────────────

    def _get_recent_files(self) -> list[str]:
        """Get recent files list from QSettings."""
        files = self._settings.value("recent_files", [])
        if not files:
            return []
        # Filter out files that no longer exist
        return [f for f in files if os.path.exists(f)][:10]

    def _add_recent_file(self, path: str):
        """Add a file path to recent files list."""
        recent = self._get_recent_files()
        # Remove if already in list, then prepend
        abs_path = os.path.normpath(os.path.abspath(path))
        recent = [f for f in recent if os.path.normpath(os.path.abspath(f)) != abs_path]
        recent.insert(0, path)
        self._settings.setValue("recent_files", recent[:10])
        # Update welcome page if visible
        self._update_welcome_page()

    # ── Welcome Page (Start Page) ────────────

    def _build_welcome_page(self):
        """Build the welcome page overlay shown when no document is open."""
        self._welcome_page = QWidget(self._pdf_scroll)
        self._welcome_page.setStyleSheet("background: transparent;")
        vl = QVBoxLayout(self._welcome_page)
        vl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.setSpacing(16)

        # Icon
        icon_lbl = QLabel("📄")
        icon_lbl.setStyleSheet("font-size: 48px; background: transparent;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(icon_lbl)

        # Title
        title = QLabel("PDF Pro Tool")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #555; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(title)

        # Subtitle
        sub = QLabel("PDF 파일을 드래그하거나 열기 버튼(Ctrl+O)을 누르세요")
        sub.setStyleSheet("font-size: 12px; color: #888; background: transparent;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(sub)

        vl.addSpacing(12)

        # Recent files section
        self._recent_files_container = QWidget()
        self._recent_files_container.setStyleSheet("background: transparent;")
        self._recent_files_layout = QVBoxLayout(self._recent_files_container)
        self._recent_files_layout.setContentsMargins(0, 0, 0, 0)
        self._recent_files_layout.setSpacing(4)
        vl.addWidget(self._recent_files_container)

        self._update_welcome_recent_list()
        self._welcome_page.hide()

    def _update_welcome_recent_list(self):
        """Populate the recent files list on the welcome page."""
        layout = self._recent_files_layout
        # Clear existing
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        recent = self._get_recent_files()
        if not recent:
            return

        header = QLabel("최근 파일")
        header.setStyleSheet("font-size: 11px; font-weight: bold; color: #666; background: transparent;")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        for path in recent[:7]:
            name = os.path.basename(path)
            btn = QPushButton(f"  📄 {name}")
            btn.setToolTip(path)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { text-align: left; padding: 6px 16px; font-size: 12px;"
                " border: none; background: transparent; color: #2979FF; }"
                "QPushButton:hover { background: rgba(41,121,255,0.1); border-radius: 4px; }"
            )
            btn.clicked.connect(lambda _, p=path: self.load_file(p))
            layout.addWidget(btn)

    def _update_welcome_page(self):
        """Show or hide welcome page based on current document state."""
        if not hasattr(self, '_welcome_page'):
            return
        doc = self._active_doc()
        if doc is None:
            self._update_welcome_recent_list()
            self._welcome_page.setGeometry(self._pdf_scroll.viewport().rect())
            self._welcome_page.show()
            self._welcome_page.raise_()
        else:
            self._welcome_page.hide()

    # ── Close ─────────────────────────────────

    def closeEvent(self, event):
        modified = [t for t in self._tabs if t.is_modified]
        if modified:
            reply = QMessageBox.question(
                self, "저장하지 않은 변경사항",
                f"{len(modified)}개 탭의 변경사항이 저장되지 않았습니다. 종료하시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
        self._save_window_state()
        for tab in self._tabs:
            tab.close()
        event.accept()
