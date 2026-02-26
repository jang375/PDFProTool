"""
panels.py — Right panels: StampPanel, TextToolPanel, SearchResultsPanel
Windows version of PDFProTool (converted from PanelsView.swift)
"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog, QFrame,
    QGridLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QScrollArea,
    QSizePolicy, QSlider, QSplitter, QTextEdit, QToolButton, QVBoxLayout,
    QWidget,
)

from models import StampManager, StampEntry
from ai_manager import AIManager


# ─────────────────────────────────────────────
# Global Cache
# ─────────────────────────────────────────────
_FONT_FAMILIES = []


# ─────────────────────────────────────────────
# Background Font Loader (prevents UI freeze)
# ─────────────────────────────────────────────

class _ChatLineEdit(QPlainTextEdit):
    """QPlainTextEdit를 단일행 입력창으로 사용.
    QLineEdit는 Windows 한글 IME 환경에서 조합 중인 글자가 블록으로 표시되고
    오른쪽 끝에서 커서가 사라지는 버그가 있다.
    QPlainTextEdit(QAbstractScrollArea 기반)는 이 문제가 없다.
    border-radius는 IME preedit 클리핑 버그를 유발하므로 사용하지 않는다.
    """
    returnPressed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._centering = False

    def keyPressEvent(self, event):
        if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
            self.returnPressed.emit()
            return
        super().keyPressEvent(event)

    def inputMethodEvent(self, event):
        """IME 조합 이벤트 후 preedit 글자가 뷰포트 안에 완전히 보이도록 스크롤."""
        super().inputMethodEvent(event)
        preedit = event.preeditString()
        def _ensure():
            try:
                self.ensureCursorVisible()
                if preedit:
                    # 커서 위치 + preedit 글자 폭만큼 추가 여유를 확보
                    cr = self.cursorRect()
                    margin = 20  # preedit 글자 폭 + 여유 (px)
                    right_needed = cr.right() + margin
                    vp_width = self.viewport().width()
                    if right_needed > vp_width:
                        hsb = self.horizontalScrollBar()
                        hsb.setValue(hsb.value() + (right_needed - vp_width))
            except RuntimeError:
                pass
        QTimer.singleShot(0, _ensure)

    def showEvent(self, event):
        super().showEvent(event)
        self._center_vertically()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._center_vertically()

    def _center_vertically(self):
        """문서 rootFrame 여백으로 텍스트를 수직 중앙 정렬.
        setViewportMargins 대신 rootFrame margin을 쓰면
        뷰포트 크기 축소 없이 텍스트 위치만 제어할 수 있다.
        """
        if self._centering:
            return
        self._centering = True
        line_h = self.fontMetrics().height()
        content_h = self.height() - 2           # border 1px × 2
        margin_v = max(0, (content_h - line_h) // 2)
        fmt = self.document().rootFrame().frameFormat()
        fmt.setTopMargin(margin_v)
        fmt.setBottomMargin(margin_v)
        fmt.setLeftMargin(8)
        fmt.setRightMargin(8)
        self.document().rootFrame().setFrameFormat(fmt)
        self._centering = False


def preload_fonts():
    """Call once at app startup to warm up the font cache on the main thread.

    Delays 2 seconds so font enumeration doesn't overlap with initial UI
    interaction (QFontDatabase.families() can take hundreds of ms on Windows
    with many installed fonts).
    """
    global _FONT_FAMILIES
    if _FONT_FAMILIES:
        return

    def _load():
        global _FONT_FAMILIES
        _FONT_FAMILIES = list(QFontDatabase.families())

    # Delay 2s so first user interaction isn't blocked by font enumeration
    QTimer.singleShot(2000, _load)


# ─────────────────────────────────────────────
# Text Tool Config
# ─────────────────────────────────────────────

class TextToolConfig:
    def __init__(self):
        self.text: str = "텍스트"
        self.font_name: str = "Arial"
        self.font_size: float = 14.0
        self.bold: bool = False
        self.italic: bool = False
        self.color_hex: str = "#000000"

    @property
    def color_rgb(self) -> tuple[float, float, float]:
        """Returns RGB tuple 0.0–1.0 for PyMuPDF."""
        h = self.color_hex.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        try:
            r = int(h[0:2], 16) / 255.0
            g = int(h[2:4], 16) / 255.0
            b = int(h[4:6], 16) / 255.0
            return (r, g, b)
        except Exception:
            return (0.0, 0.0, 0.0)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "font_name": self.font_name,
            "font_size": self.font_size,
            "color": self.color_rgb,
        }


# ─────────────────────────────────────────────
# Stamp Panel
# ─────────────────────────────────────────────

class StampPanel(QWidget):
    """Panel to manage and select image stamps."""

    stamp_selected = pyqtSignal(str)   # image path
    closed = pyqtSignal()

    def __init__(self, stamp_mgr: StampManager, parent=None):
        super().__init__(parent)
        self._stamp_mgr = stamp_mgr
        self.setFixedWidth(260)
        self._build_ui()
        self._refresh()
        self._stamp_mgr.stamps_changed.connect(self._refresh)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setStyleSheet("background: #f5f5f5; border-bottom: 1px solid #e0e0e0;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 8, 8, 8)
        title = QLabel("직인 / Stamps")
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        hl.addWidget(title)
        hl.addStretch()
        close_btn = QPushButton("x")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(
            "QPushButton { padding: 0px; font-size: 13px; font-weight: bold;"
            " border: none; background: transparent; color: #666; }"
            "QPushButton:hover { color: #333; background: #e0e0e0; border-radius: 3px; }"
        )
        close_btn.clicked.connect(self.closed.emit)
        hl.addWidget(close_btn)
        layout.addWidget(header)

        # Add button
        add_btn = QPushButton("+ 직인 추가")
        add_btn.clicked.connect(self._add_stamp)
        add_btn.setStyleSheet("margin: 8px; padding: 6px;")
        layout.addWidget(add_btn)

        # Stamp grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #fafafa; }")
        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(8, 8, 8, 8)
        self._grid_layout.setSpacing(8)
        scroll.setWidget(self._grid_container)
        layout.addWidget(scroll)

    def _add_stamp(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "직인 이미지 선택", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.svg)"
        )
        if not path:
            return
        name, ok = QInputDialog.getText(self, "직인 이름", "이름을 입력하세요:")
        if ok and name.strip():
            self._stamp_mgr.add(path, name.strip())

    def _refresh(self):
        # Clear grid
        for i in reversed(range(self._grid_layout.count())):
            self._grid_layout.itemAt(i).widget().deleteLater()

        for idx, stamp in enumerate(self._stamp_mgr.stamps):
            cell = self._make_stamp_cell(stamp, idx)
            row = idx // 2
            col = idx % 2
            self._grid_layout.addWidget(cell, row, col)

    def _make_stamp_cell(self, stamp: StampEntry, idx: int) -> QWidget:
        w = QWidget()
        w.setStyleSheet(
            "border: 1px solid #ddd; border-radius: 6px; background: white;"
        )
        w.setFixedSize(108, 90)
        vl = QVBoxLayout(w)
        vl.setContentsMargins(4, 4, 4, 4)
        vl.setSpacing(2)

        img_label = QLabel()
        img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_label.setFixedHeight(58)
        px = QPixmap(stamp.path)
        if not px.isNull():
            img_label.setPixmap(
                px.scaled(90, 56, Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            )
        vl.addWidget(img_label)

        name_lbl = QLabel(stamp.name)
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setStyleSheet("font-size: 10px; border: none;")
        name_lbl.setWordWrap(False)
        vl.addWidget(name_lbl)

        # Left-click to select stamp
        def on_press(e, path=stamp.path):
            if e.button() == Qt.MouseButton.LeftButton:
                self._on_stamp_clicked(path)
        w.mousePressEvent = on_press

        # Right-click to delete
        def context_menu(e, i=idx):
            from PyQt6.QtWidgets import QMenu
            menu = QMenu(self)
            menu.addAction("삭제").triggered.connect(lambda: self._stamp_mgr.remove(i))
            menu.exec(e.globalPos())
        w.contextMenuEvent = context_menu

        return w

    def _on_stamp_clicked(self, path: str):
        # stamp_selected 핸들러가 _clear_right_panel()을 호출하여 패널을 삭제하므로
        # closed를 추가로 emit하면 이중 호출이 발생한다. stamp_selected만 emit한다.
        self.stamp_selected.emit(path)


# ─────────────────────────────────────────────
# Text Tool Panel
# ─────────────────────────────────────────────

PRESET_COLORS = ["#FF3B30", "#1d1d1f", "#007AFF", "#34C759", "#FF9500", "#AF52DE"]


class TextToolPanel(QWidget):
    """Panel to configure and apply text annotations."""

    apply_requested = pyqtSignal(object)  # TextToolConfig
    cancel_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(260)
        self._config = TextToolConfig()
        self._last_font_params = None
        # 미리보기 갱신 디바운스 타이머
        # 매 키입력마다 setStyleSheet 호출하면 한글 IME 조합 중 입력이 멈춤
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(120)  # 120ms 입력 없으면 미리보기 갱신
        self._preview_timer.timeout.connect(self._refresh_preview)
        self._build_ui()
        # Proxy focus to text edit so if panel gets focus, input gets it
        self.setFocusProxy(self._text_edit)

    def showEvent(self, event):
        super().showEvent(event)
        # 패널이 완전히 그려진 다음 이벤트 루프에서 포커스 설정
        # 100ms는 너무 길고, enter_text_placement_mode 호출이 포커스를 빼앗을 수 있음
        def _focus():
            try:
                self._text_edit.setFocus(Qt.FocusReason.OtherFocusReason)
                self._text_edit.selectAll()
            except RuntimeError:
                pass
        QTimer.singleShot(0, _focus)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setStyleSheet("background: #f5f5f5; border-bottom: 1px solid #e0e0e0;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 8, 8, 8)
        title = QLabel("텍스트 도구")
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        hl.addWidget(title)
        hl.addStretch()
        cancel_btn = QPushButton("x")
        cancel_btn.setFixedSize(24, 24)
        cancel_btn.setStyleSheet(
            "QPushButton { padding: 0px; font-size: 13px; font-weight: bold;"
            " border: none; background: transparent; color: #666; }"
            "QPushButton:hover { color: #333; background: #e0e0e0; border-radius: 3px; }"
        )
        cancel_btn.clicked.connect(self.cancel_requested.emit)
        hl.addWidget(cancel_btn)
        layout.addWidget(header)

        # scroll = QScrollArea()
        # scroll.setWidgetResizable(True)
        # scroll.setStyleSheet("QScrollArea { border: none; background: #fafafa; }")
        
        container = QWidget()
        vl = QVBoxLayout(container)
        vl.setContentsMargins(12, 12, 12, 12)
        vl.setSpacing(10)

        # Text input
        lbl1 = QLabel("텍스트")
        lbl1.setStyleSheet("font-size: 10px; color: #888; font-weight: bold;")
        vl.addWidget(lbl1)
        self._text_edit = QLineEdit()
        self._text_edit.setFixedHeight(40)
        self._text_edit.setText(self._config.text)
        self._text_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._text_edit.setStyleSheet(
            "QLineEdit { border: 1px solid #ccc; border-radius: 4px; padding: 4px; "
            "font-size: 13px; background: white; }"
            "QLineEdit:focus { border: 2px solid #2979FF; }"
        )
        self._text_edit.textChanged.connect(self._update_config)
        vl.addWidget(self._text_edit)

        # Preview
        self._preview_label = QLabel(self._config.text)
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setStyleSheet(
            "background: white; border: 1px solid #ddd; border-radius: 6px; "
            "padding: 8px; min-height: 40px;"
        )
        self._preview_label.setWordWrap(True)
        vl.addWidget(self._preview_label)

        # Font family — QLineEdit+QCompleter instead of QComboBox
        # QComboBox.addItems() with 500+ fonts freezes UI on Windows
        lbl2 = QLabel("FONT")
        lbl2.setStyleSheet("font-size: 10px; color: #888; font-weight: bold;")
        vl.addWidget(lbl2)
        self._font_combo = QLineEdit()
        self._font_combo.setText(self._config.font_name)
        self._font_combo.setPlaceholderText("폰트 이름 입력...")
        self._font_combo.setStyleSheet(
            "QLineEdit { border: 1px solid #ccc; border-radius: 4px; padding: 4px; font-size: 12px; }"
        )
        self._font_combo.textChanged.connect(self._on_font_changed)
        vl.addWidget(self._font_combo)
        # Attach completer after fonts are ready
        self._schedule_font_populate()

        # Style & size row
        style_row = QHBoxLayout()
        self._style_combo = QComboBox()
        self._style_combo.addItems(["Regular", "Bold", "Italic", "Bold Italic"])
        self._style_combo.currentTextChanged.connect(self._on_style_changed)
        style_row.addWidget(self._style_combo)
        style_row.addStretch()
        lbl_pt = QLabel("pt:")
        lbl_pt.setStyleSheet("font-size: 11px;")
        style_row.addWidget(lbl_pt)
        self._size_spin = QDoubleSpinBox()
        self._size_spin.setRange(6, 200)
        self._size_spin.setSingleStep(1)
        self._size_spin.setValue(self._config.font_size)
        self._size_spin.setFixedWidth(64)
        self._size_spin.valueChanged.connect(self._on_size_changed)
        style_row.addWidget(self._size_spin)
        vl.addLayout(style_row)

        # Colors
        lbl3 = QLabel("COLOR")
        lbl3.setStyleSheet("font-size: 10px; color: #888; font-weight: bold;")
        vl.addWidget(lbl3)
        color_row = QHBoxLayout()
        for hex_color in PRESET_COLORS:
            btn = QPushButton()
            btn.setFixedSize(24, 24)
            btn.setStyleSheet(
                f"background: {hex_color}; border-radius: 12px; border: 1px solid #ccc;"
            )
            btn.clicked.connect(lambda _, h=hex_color: self._set_color(h))
            color_row.addWidget(btn)
        color_row.addStretch()
        custom_color_btn = QPushButton("…")
        custom_color_btn.setFixedSize(24, 24)
        custom_color_btn.clicked.connect(self._pick_custom_color)
        color_row.addWidget(custom_color_btn)
        vl.addLayout(color_row)

        # Color preview
        self._color_preview = QLabel()
        self._color_preview.setFixedHeight(20)
        self._color_preview.setStyleSheet(
            f"background: {self._config.color_hex}; border-radius: 4px; border: 1px solid #ccc;"
        )
        vl.addWidget(self._color_preview)

        vl.addStretch()

        # Action buttons
        btn_row = QHBoxLayout()
        apply_btn = QPushButton("적용")
        apply_btn.setStyleSheet(
            "background: #2979FF; color: white; padding: 6px 16px; border-radius: 4px;"
        )
        apply_btn.clicked.connect(self._on_apply)
        cancel_btn2 = QPushButton("취소")
        cancel_btn2.setStyleSheet("padding: 6px 16px; border-radius: 4px;")
        cancel_btn2.clicked.connect(self.cancel_requested.emit)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(cancel_btn2)
        vl.addLayout(btn_row)

        # Add container to main layout AFTER populating it
        layout.addWidget(container)

    def _schedule_font_populate(self):
        """폰트가 준비되면 QCompleter를 붙인다 (메인 스레드, 논블로킹)."""
        global _FONT_FAMILIES
        if _FONT_FAMILIES:
            def _pop():
                try:
                    self._populate_font_combo()
                except RuntimeError:
                    pass
            QTimer.singleShot(0, _pop)
        else:
            # 아직 로딩 전 → 200ms 후 재시도
            def _retry():
                try:
                    self._schedule_font_populate()
                except RuntimeError:
                    pass
            QTimer.singleShot(200, _retry)

    def _populate_font_combo(self):
        """QLineEdit에 QCompleter를 설정한다. addItems 없이 빠르게 동작."""
        from PyQt6.QtWidgets import QCompleter
        from PyQt6.QtCore import QStringListModel
        global _FONT_FAMILIES
        if not _FONT_FAMILIES:
            _FONT_FAMILIES = list(QFontDatabase.families())

        model = QStringListModel(_FONT_FAMILIES)
        completer = QCompleter(model, self._font_combo)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._font_combo.setCompleter(completer)

    def _update_config(self, text=None):
        self._config.text = self._text_edit.text()
        # 즉시 호출 대신 디바운스 타이머로 미리보기 지연 갱신
        # 한글 IME 조합 중 textChanged가 연속 발생해도 120ms 이후 1회만 실행됨
        self._preview_timer.start()

    def _on_font_changed(self, name: str):
        self._config.font_name = name
        self._preview_timer.start()

    def _on_style_changed(self, style: str):
        self._config.bold = "Bold" in style
        self._config.italic = "Italic" in style
        self._refresh_preview()

    def _on_size_changed(self, val: float):
        self._config.font_size = val
        self._refresh_preview()

    def _set_color(self, hex_color: str):
        self._config.color_hex = hex_color
        self._color_preview.setStyleSheet(
            f"background: {hex_color}; border-radius: 4px; border: 1px solid #ccc;"
        )
        self._refresh_preview()

    def _pick_custom_color(self):
        color = QColorDialog.getColor(
            QColor(self._config.color_hex), self, "색상 선택"
        )
        if color.isValid():
            self._set_color(color.name())

    def _refresh_preview(self):
        self._preview_label.setText(self._config.text or "미리보기")
        
        current_font_params = (self._config.font_name, self._config.font_size, self._config.bold, self._config.italic)
        if self._last_font_params != current_font_params:
            font = QFont(self._config.font_name, int(min(self._config.font_size, 18)))
            font.setBold(self._config.bold)
            font.setItalic(self._config.italic)
            self._preview_label.setFont(font)
            self._last_font_params = current_font_params

        # 같은 스타일이면 setStyleSheet 생략 (Qt6 스타일 재계산 비용 절약)
        new_style = (
            f"background: white; border: 1px solid #ddd; border-radius: 6px; "
            f"padding: 8px; min-height: 40px; color: {self._config.color_hex};"
        )
        if self._preview_label.styleSheet() != new_style:
            self._preview_label.setStyleSheet(new_style)

    def _on_apply(self):
        self._config.text = self._text_edit.text()
        self.apply_requested.emit(self._config)

    def load_config(self, config: TextToolConfig):
        self._config = config
        self._text_edit.setText(config.text)
        # _font_combo is now QLineEdit
        self._font_combo.setText(config.font_name)
        self._size_spin.setValue(config.font_size)
        self._set_color(config.color_hex)
        self._refresh_preview()

    @property
    def config(self) -> TextToolConfig:
        self._config.text = self._text_edit.text()
        return self._config


# ─────────────────────────────────────────────
# Search Results Panel
# ─────────────────────────────────────────────

class SearchResultsPanel(QWidget):
    """Panel showing search results grouped by page."""

    result_selected = pyqtSignal(int, object)  # page_index, fitz.Rect
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(280)
        self._results: list[tuple[int, object, str]] = []  # (page, rect, snippet)
        self._current_idx: int = -1
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setStyleSheet("background: #f5f5f5; border-bottom: 1px solid #e0e0e0;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(8, 6, 8, 6)

        _nav_style = (
            "QPushButton { padding: 0px 4px; font-size: 12px; font-weight: bold;"
            " border: 1px solid #bbb; border-radius: 3px; background: #f0f0f0; }"
            "QPushButton:hover { background: #e0e0e0; }"
        )
        self._prev_btn = QPushButton("<")
        self._prev_btn.setFixedSize(28, 24)
        self._prev_btn.setStyleSheet(_nav_style)
        self._prev_btn.clicked.connect(lambda: self._navigate(-1))
        hl.addWidget(self._prev_btn)

        self._next_btn = QPushButton(">")
        self._next_btn.setFixedSize(28, 24)
        self._next_btn.setStyleSheet(_nav_style)
        self._next_btn.clicked.connect(lambda: self._navigate(1))
        hl.addWidget(self._next_btn)

        hl.addStretch()

        self._count_label = QLabel("0건")
        self._count_label.setStyleSheet("font-size: 12px; color: #666;")
        hl.addWidget(self._count_label)

        close_btn = QPushButton("x")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(
            "QPushButton { padding: 0px; font-size: 13px; font-weight: bold;"
            " border: none; background: transparent; color: #666; }"
            "QPushButton:hover { color: #333; background: #e0e0e0; border-radius: 3px; }"
        )
        close_btn.clicked.connect(self.closed.emit)
        hl.addWidget(close_btn)
        layout.addWidget(header)

        # Results list
        self._list = QListWidget()
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list)

    def set_results(self, results: list[tuple[int, object, str]]):
        """results: list of (page_index, fitz.Rect, snippet_text)"""
        self._results = results
        self._current_idx = 0 if results else -1
        self._count_label.setText(f"{len(results)}건")
        self._list.clear()

        # Count results per page for header display
        page_counts: dict[int, int] = {}
        for page, _rect, _snippet in results:
            page_counts[page] = page_counts.get(page, 0) + 1

        current_page = -1
        for i, (page, rect, snippet) in enumerate(results):
            if page != current_page:
                count = page_counts[page]
                separator = QListWidgetItem(f"── {page + 1} 페이지 ({count}건) ──")
                separator.setFlags(Qt.ItemFlag.NoItemFlags)
                separator.setForeground(QColor("#999"))
                font = separator.font()
                font.setBold(True)
                separator.setFont(font)
                self._list.addItem(separator)
                current_page = page

            item = QListWidgetItem(f"  {snippet[:60]}")
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setToolTip(snippet)
            self._list.addItem(item)

        self._prev_btn.setEnabled(bool(results))
        self._next_btn.setEnabled(bool(results))

    def _on_item_clicked(self, item: QListWidgetItem):
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is not None:
            self._go_to(idx)

    def _navigate(self, delta: int):
        if not self._results:
            return
        self._current_idx = (self._current_idx + delta) % len(self._results)
        self._go_to(self._current_idx)

    def _go_to(self, idx: int):
        if 0 <= idx < len(self._results):
            self._current_idx = idx
            page, rect, _ = self._results[idx]
            self.result_selected.emit(page, rect)


class AIToolPanel(QWidget):
    """Panel offering AI assistant features (Summarize, Extract Table, OCR Correct)."""
    
    summarize_requested = pyqtSignal()
    table_extract_requested = pyqtSignal()
    ocr_correct_requested = pyqtSignal()
    chat_message_entered = pyqtSignal(str)
    closed = pyqtSignal()

    def __init__(self, ai_manager: AIManager, parent=None):
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.setMinimumWidth(300)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setStyleSheet("background: #f5f5f5; border-bottom: 1px solid #e0e0e0;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 8, 8, 8)
        title = QLabel("✨ AI 도구")
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        hl.addWidget(title)
        hl.addStretch()
        close_btn = QPushButton("x")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(
            "QPushButton { padding: 0px; font-size: 13px; font-weight: bold;"
            " border: none; background: transparent; color: #666; }"
            "QPushButton:hover { color: #333; background: #e0e0e0; border-radius: 3px; }"
        )
        close_btn.clicked.connect(self.closed.emit)
        hl.addWidget(close_btn)
        layout.addWidget(header)

        # Content
        content = QWidget()
        vl = QVBoxLayout(content)
        vl.setContentsMargins(12, 16, 12, 16)
        vl.setSpacing(16)

        # Status text
        self.status_lbl = QLabel(
            "AI 준비됨" if self.ai_manager.is_configured() 
            else "상단의 설정(⚙) 메뉴에서\nAPI Key를 입력해주세요."
        )
        self.status_lbl.setStyleSheet(
            "color: #2979FF; font-size: 11px; font-weight: bold;" if self.ai_manager.is_configured() 
            else "color: #FF3B30; font-size: 11px;"
        )
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(self.status_lbl)

        # Summarize Button
        sum_btn = QPushButton("📄 AI 요약")
        sum_btn.setToolTip("현재 화면에 표시된 페이지의 텍스트를 요약합니다. (미리 OCR이 되어 있어야 합니다)")
        sum_btn.setStyleSheet("padding: 10px; font-size: 13px; font-weight: bold;")
        sum_btn.clicked.connect(self.summarize_requested.emit)
        vl.addWidget(sum_btn)

        # Table Extract Button
        tbl_btn = QPushButton("📊 AI 표 추출 (영역 지정)")
        tbl_btn.setToolTip("마우스로 표 영역을 지정하면 AI가 분석하여 CSV로 변환해 줍니다.")
        tbl_btn.setStyleSheet("padding: 10px; font-size: 13px; font-weight: bold;")
        tbl_btn.clicked.connect(self.table_extract_requested.emit)
        vl.addWidget(tbl_btn)

        # OCR Correct Button
        ocr_btn = QPushButton("🔍 AI 오타 교정")
        ocr_btn.setToolTip("OCR 결과의 오타를 문맥에 맞게 교정합니다.")
        ocr_btn.setStyleSheet("padding: 10px; font-size: 13px; font-weight: bold;")
        ocr_btn.clicked.connect(self.ocr_correct_requested.emit)
        vl.addWidget(ocr_btn)

        # AI Chat Section
        chat_group = QGroupBox("💬 문서 채팅")
        chat_group.setStyleSheet("font-weight: bold; font-size: 13px; color: #333; margin-top: 10px;")
        chat_vl = QVBoxLayout(chat_group)
        chat_vl.setContentsMargins(8, 20, 8, 8)
        chat_vl.setSpacing(8)
        
        # Scroll area for chat bubbles
        self._chat_scroll = QScrollArea()
        self._chat_scroll.setWidgetResizable(True)
        self._chat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._chat_scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #ccc; border-radius: 4px; background: #f9f9f9; }"
        )

        self._chat_msg_container = QWidget()
        self._chat_msg_container.setStyleSheet("background: #f9f9f9;")
        self._chat_msg_layout = QVBoxLayout(self._chat_msg_container)
        self._chat_msg_layout.setContentsMargins(8, 8, 8, 8)
        self._chat_msg_layout.setSpacing(8)
        self._chat_msg_layout.addStretch()  # pushes messages upward initially

        self._chat_scroll.setWidget(self._chat_msg_container)
        chat_vl.addWidget(self._chat_scroll, 1)
        
        chat_hl = QHBoxLayout()
        chat_hl.setSpacing(6)

        # border-radius는 Qt 스타일시트에서 클리핑 영역을 만들어
        # 오른쪽 끝에서 IME preedit 글자가 잘리는 버그를 유발한다.
        # 사각 테두리를 사용하고, inputMethodEvent에서 ensureCursorVisible을
        # 호출하여 조합 중인 글자도 뷰포트 안에 유지한다.
        self.chat_input = _ChatLineEdit()
        self.chat_input.setFixedHeight(36)
        self.chat_input.setFrameShape(QFrame.Shape.NoFrame)
        self.chat_input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_input.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_input.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.chat_input.setPlaceholderText("질문을 입력하세요...")
        self.chat_input.document().setDocumentMargin(0)
        self.chat_input.setStyleSheet(
            "QPlainTextEdit { font-size: 12px; font-weight: normal;"
            " border: 1px solid #ccc; background: white; }"
            "QPlainTextEdit:focus { border: 1px solid #90CAF9; }"
        )
        self.chat_input.returnPressed.connect(self._on_send_chat)
        chat_hl.addWidget(self.chat_input, 1)

        send_btn = QPushButton("전송")
        send_btn.setFixedHeight(36)
        send_btn.setStyleSheet(
            "QPushButton { font-size: 12px; font-weight: normal; padding: 0 14px;"
            " background: #E3F2FD; border: 1px solid #BBDEFB; border-radius: 6px; color: #1565C0; }"
            "QPushButton:hover { background: #BBDEFB; }"
        )
        send_btn.clicked.connect(self._on_send_chat)
        chat_hl.addWidget(send_btn)
        
        chat_vl.addLayout(chat_hl)
        vl.addWidget(chat_group, 1)  # Stretch factor 1 so it expands vertically

        layout.addWidget(content)

        self.append_chat_message("🤖", "문서 내용을 바탕으로 유용한 정보를 물어보세요!")

    def set_input_enabled(self, enabled: bool):
        """Enable/disable chat input and send button during API calls."""
        self.chat_input.setEnabled(enabled)
        if enabled:
            self._remove_loading_indicator()
            self.chat_input.setFocus()
        else:
            self._show_loading_indicator()

    def _show_loading_indicator(self):
        """Show a 'thinking...' indicator in the chat."""
        self._loading_widget = QLabel("AI 응답 대기 중...")
        self._loading_widget.setStyleSheet(
            "background: #FFF3E0; border-radius: 12px; padding: 8px 12px;"
            " color: #e65100; font-size: 12px; font-style: italic; font-weight: normal;"
        )
        self._chat_msg_layout.insertWidget(self._chat_msg_layout.count() - 1, self._loading_widget)
        QTimer.singleShot(50, lambda: self._chat_scroll.verticalScrollBar().setValue(
            self._chat_scroll.verticalScrollBar().maximum()
        ))

    def _remove_loading_indicator(self):
        """Remove the loading indicator if present."""
        w = getattr(self, "_loading_widget", None)
        if w:
            w.hide()
            w.deleteLater()
            self._loading_widget = None

    def _on_send_chat(self):
        text = self.chat_input.toPlainText().strip()
        if not text:
            return
        self.chat_input.clear()
        self.chat_message_entered.emit(text)
        
    def append_chat_message(self, sender: str, msg: str):
        is_user = "👤" in sender
        is_error = "❌" in sender

        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)

        bubble = QLabel(msg)
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        if is_user:
            # 사용자 메시지: 오른쪽 정렬, 뷰포트 너비 기준 최대 80%
            bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
            vp_w = self._chat_scroll.viewport().width()
            if vp_w > 0:
                bubble.setMaximumWidth(int(vp_w * 0.80))
            bubble.setStyleSheet(
                "background: #DCF8C6; border-radius: 12px; padding: 8px 12px;"
                " color: #1b5e20; font-size: 12px; font-weight: normal;"
            )
            row_layout.addStretch()
            row_layout.addWidget(bubble)
        elif is_error:
            # 오류: 전체 너비 사용
            bubble.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            bubble.setText(f"{sender}: {msg}")
            bubble.setStyleSheet(
                "background: #FFEBEE; border-radius: 12px; padding: 8px 12px;"
                " color: #b71c1c; font-size: 12px; font-weight: normal;"
            )
            row_layout.addWidget(bubble)
        else:
            # AI 메시지: 전체 너비 사용 (잘림 없음)
            bubble.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            bubble.setStyleSheet(
                "background: #E3F2FD; border-radius: 12px; padding: 8px 12px;"
                " color: #1a237e; font-size: 12px; font-weight: normal;"
            )
            row_layout.addWidget(bubble)

        # Insert before the trailing stretch
        self._chat_msg_layout.insertWidget(self._chat_msg_layout.count() - 1, row)

        # Scroll to bottom after layout settles
        QTimer.singleShot(50, lambda: self._chat_scroll.verticalScrollBar().setValue(
            self._chat_scroll.verticalScrollBar().maximum()
        ))

