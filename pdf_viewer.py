"""
pdf_viewer.py — PDF rendering widget with annotation interaction
Replaces PDFViewerWrapper.swift / EnhancedPDFView on Windows.

Uses PyMuPDF (fitz) for rendering pages → QPixmap.
Supports continuous scroll, zoom, annotation drag/resize/edit.
"""

from __future__ import annotations

import bisect
import math
from typing import Optional, Callable

import fitz  # PyMuPDF
from PyQt6.QtCore import (
    QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, pyqtSignal
)
from PyQt6.QtGui import (
    QColor, QCursor, QFont, QFontMetricsF, QImage, QKeyEvent, QMouseEvent,
    QPainter, QPen, QPixmap, QWheelEvent,
)
from PyQt6.QtWidgets import (
    QApplication, QInputDialog, QMenu, QScrollArea, QSizePolicy,
    QWidget,
)
from PyQt6.QtCore import QThreadPool, QRunnable, QObject

from collections import OrderedDict



def _resolve_freetext_font(text: str, font_name: str) -> dict:
    """Return kwargs (fontname) for add_freetext_annot with CJK support.

    Uses PyMuPDF built-in CJK font ("korea") instead of loading system font
    files (malgun.ttf ~15-20MB) which blocks the main thread for 300-2000ms.
    """
    has_cjk = any(ord(c) > 0x2E7F for c in text)
    if not has_cjk:
        name = font_name if font_name else "helv"
        if name.lower() in ("helvetica", "arial"):
            name = "helv"
        return {"fontname": name}
    # CJK text — use PyMuPDF built-in CJK font (no file I/O, instant)
    return {"fontname": "korea"}


# ─────────────────────────────────────────────
# Async Rendering Worker
# ─────────────────────────────────────────────

class WorkerSignals(QObject):
    finished = pyqtSignal(QImage, bool)  # True if high-res, False if low-res

class RenderWorker(QRunnable):
    """Background worker to render a PDF page (스레드 전용 doc 인스턴스 사용).

    doc_bytes가 제공되면 메모리에서 열고 (수정된 doc),
    없으면 file_path에서 열어 (원본 파일) 렌더링한다.
    """

    def __init__(self, file_path: str, page_index: int, zoom: float,
                 is_valid_cb: Optional[callable] = None,
                 doc_bytes: Optional[bytes] = None):
        super().__init__()
        self._file_path = file_path
        self._doc_bytes = doc_bytes
        self.page_index = page_index
        self.zoom = zoom
        self.is_valid_cb = is_valid_cb
        self.signals = WorkerSignals()

    def run(self):
        if self.is_valid_cb and not self.is_valid_cb():
            return

        doc = None
        try:
            if self._doc_bytes:
                doc = fitz.open(stream=self._doc_bytes, filetype="pdf")
            else:
                doc = fitz.open(self._file_path)
            dpr = 2.0

            # FAST PASS (Low Res Preview)
            try:
                page = doc[self.page_index]
                low_mat = fitz.Matrix(self.zoom * dpr * 0.2, self.zoom * dpr * 0.2)
                pix_low = page.get_pixmap(matrix=low_mat, alpha=False)
                fmt = QImage.Format.Format_RGB888 if pix_low.n == 3 else QImage.Format.Format_RGBA8888
                img_low = QImage(pix_low.samples, pix_low.width, pix_low.height, pix_low.stride, fmt)
                img_low = img_low.copy()
                img_low.setDevicePixelRatio(dpr * 0.2)
                self.signals.finished.emit(img_low, False)
            except Exception:
                pass

            if self.is_valid_cb and not self.is_valid_cb():
                return

            # HIGH RES PASS
            try:
                page = doc[self.page_index]
                mat = fitz.Matrix(self.zoom * dpr, self.zoom * dpr)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                fmt = QImage.Format.Format_RGB888 if pix.n == 3 else QImage.Format.Format_RGBA8888
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
                img = img.copy()  # Detach from fitz memory

                img.setDevicePixelRatio(dpr)
                self.signals.finished.emit(img, True)
            except Exception:
                pass
        except Exception:
            pass  # Fail silently
        finally:
            if doc:
                doc.close()


PAGE_GAP = 16  # pixels between pages


# ─────────────────────────────────────────────
# Helper: character-level text wrapping
# ─────────────────────────────────────────────

def _char_wrap_text(text: str, max_width: float, fontsize: float, fontname: str = "helv") -> str:
    """Wrap text at character boundaries (not word boundaries).

    Uses QFontMetricsF to precisely measure characters matching the display font
    so that words don't jump around erratically when resizing the annotation box.
    """
    if not text or max_width <= 0 or fontsize <= 0:
        return text

    from PyQt6.QtGui import QFont, QFontMetricsF
    
    # Map common PDF font names to Qt font families
    family = "Helvetica"
    if fontname.lower() in ("cour", "courier"):
        family = "Courier"
    elif fontname.lower() in ("tiro", "times"):
        family = "Times"
        
    font = QFont(family)
    font.setPixelSize(max(int(fontsize), 1))
    fm = QFontMetricsF(font)

    result_lines: list[str] = []
    for line in text.split("\n"):
        if not line:
            result_lines.append("")
            continue
        cur = ""
        cur_w = 0.0
        for ch in line:
            ch_w = fm.horizontalAdvance(ch)
            # Small buffer to prevent floating point edge case wraps
            if cur_w + ch_w > max_width + 0.1 and cur:
                result_lines.append(cur)
                cur = ch
                cur_w = ch_w
            else:
                cur += ch
                cur_w += ch_w
        if cur:
            result_lines.append(cur)
    return "\n".join(result_lines)


def _fitz_char_wrap_text(text: str, max_width: float, fontsize: float, fontname: str = "helv") -> str:
    """Wrap text using fitz font metrics so that the result matches fitz rendering.

    Unlike _char_wrap_text which uses Qt's QFontMetricsF, this function uses
    fitz.get_text_length for measurement, ensuring the wrapped text fits
    exactly within a FreeText annotation rendered by PyMuPDF.

    For characters not supported by the PDF font (e.g. Korean/CJK in Helvetica),
    fitz.get_text_length returns 0 — we fall back to Qt font metrics.
    """
    if not text or max_width <= 0 or fontsize <= 0:
        return text

    # FreeText annotations have internal padding (~2pt each side)
    effective_width = max_width - 4.0
    if effective_width <= 0:
        effective_width = max_width

    # Lazy-init Qt fallback metrics only if needed (CJK / unsupported chars)
    _qt_fm = None

    def _char_width(ch: str) -> float:
        nonlocal _qt_fm
        w = fitz.get_text_length(ch, fontname=fontname, fontsize=fontsize)
        if w > 0:
            return w
        # Font doesn't support this character — fall back to Qt metrics
        if _qt_fm is None:
            font = QFont()
            font.setPointSizeF(fontsize)
            _qt_fm = QFontMetricsF(font)
        return _qt_fm.horizontalAdvance(ch)

    result_lines: list[str] = []
    for line in text.split("\n"):
        if not line:
            result_lines.append("")
            continue
        cur = ""
        cur_w = 0.0
        for ch in line:
            ch_w = _char_width(ch)
            if cur_w + ch_w > effective_width and cur:
                result_lines.append(cur)
                cur = ch
                cur_w = ch_w
            else:
                cur += ch
                cur_w += ch_w
        if cur:
            result_lines.append(cur)
    return "\n".join(result_lines)


# ─────────────────────────────────────────────
# Helpers: coordinate conversion
# ─────────────────────────────────────────────

def fitz_rect_to_qrectf(r: fitz.Rect, offset_x: float, offset_y: float, zoom: float) -> QRectF:
    """Convert a fitz.Rect (page coords) to QRectF (screen coords)."""
    return QRectF(
        r.x0 * zoom + offset_x,
        r.y0 * zoom + offset_y,
        r.width * zoom,
        r.height * zoom,
    )


def qpointf_to_fitz_point(p: QPointF, offset_x: float, offset_y: float, zoom: float) -> fitz.Point:
    return fitz.Point((p.x() - offset_x) / zoom, (p.y() - offset_y) / zoom)


def qrectf_to_fitz_rect(r: QRectF, offset_x: float, offset_y: float, zoom: float) -> fitz.Rect:
    return fitz.Rect(
        (r.x() - offset_x) / zoom,
        (r.y() - offset_y) / zoom,
        (r.x() + r.width() - offset_x) / zoom,
        (r.y() + r.height() - offset_y) / zoom,
    )


def fitz_pixmap_to_qimage(pix: fitz.Pixmap) -> QImage:
    """Convert fitz.Pixmap to QImage."""
    fmt = QImage.Format.Format_RGB888 if pix.n == 3 else QImage.Format.Format_RGBA8888
    img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
    return img.copy()  # copy to detach from fitz memory


# ─────────────────────────────────────────────
# Selected annotation info
# ─────────────────────────────────────────────

class AnnotHit:
    BODY = -1

    def __init__(self, annot: fitz.Annot | dict, page_index: int, corner: int = -1, match_type: str = "annot", page_obj: Optional[fitz.Page] = None):
        self.annot = annot
        self.page_index = page_index
        self.corner = corner  # -1=body, 0=TL, 1=TR, 2=BR, 3=BL
        self.match_type = match_type  # "annot" or "stamp"
        self.page_obj = page_obj # MUST store page reference to prevent C-level use-after-free segfaults


# ─────────────────────────────────────────────
# Core PDF Widget
# ─────────────────────────────────────────────

class PDFViewWidget(QWidget):
    """
    Renders a PDF document using PyMuPDF, continuous scroll, with full
    annotation interaction (drag, resize, add text, add stamp, inline edit).
    """

    # Signals
    page_changed = pyqtSignal(int)
    zoom_changed = pyqtSignal(float)   # (중복 선언 제거됨)
    doc_modified = pyqtSignal()
    text_placed = pyqtSignal()
    annot_edit_requested = pyqtSignal(object, int)  # (annot, page_index)

    # Interaction modes
    MODE_NORMAL = "normal"
    MODE_TEXT_PLACEMENT = "text_placement"
    MODE_CROP = "crop"
    MODE_TEXT_EDIT = "text_edit"

    HANDLE_SIZE = 8.0   # corner handle size in screen pixels
    HIT_THRESHOLD = 10.0  # hit-test threshold in screen pixels

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        # PDF 뷰어는 키보드 포커스가 필요 없다.
        # StrongFocus는 텍스트 입력 위젯에서 포커스를 빼앗아 먹통을 유발한다.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # Windows IME(한글 입력 등)가 이 위젯으로 라우팅되지 않게 명시적으로 비활성화
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._doc: Optional[fitz.Document] = None
        self._file_path: str = ""
        self._doc_bytes_snapshot: Optional[bytes] = None  # 수정 후 렌더링용 스냅샷
        self._zoom: float = 1.0
        self._page_offsets: list[int] = []   # y-pixel offset of each page top
        self._page_heights: list[int] = []   # rendered height of each page
        self._page_rects: list[fitz.Rect] = [] # cache of original page rects for fast zoom logic

        # Async rendering state
        self._render_cache: OrderedDict[tuple[int, float], QPixmap] = OrderedDict()
        self._low_res_cache: OrderedDict[tuple[int, float], QPixmap] = OrderedDict()
        self._pending_renders: set[tuple[int, float]] = set()
        self._thread_pool = QThreadPool.globalInstance()
        # Optimize thread pool
        self._thread_pool.setMaxThreadCount(8)  # Increase count for background queueing

        self.mode: str = self.MODE_NORMAL

        # Annotation interaction
        self._selected_annot: Optional[fitz.Annot] = None
        self._selected_page: int = -1
        self._selected_page_obj: Optional[fitz.Page] = None # Keep page alive to prevent segfaults
        self._drag_annot: Optional[fitz.Annot] = None
        self._drag_page: int = -1
        self._drag_start: QPointF = QPointF()
        self._orig_rect: Optional[fitz.Rect] = None
        self._drag_annot_pixmap: Optional[QPixmap] = None  # snapshot for drag preview
        self._drag_raw_text: Optional[str] = None   # unwrapped text for char-wrap resize
        self._drag_da: dict = {}                     # parsed DA info for resize preview
        self._annot_raw_text: dict[int, str] = {}   # xref -> original unwrapped text
        self._is_resizing: bool = False
        self._resize_corner: int = -1
        self._resize_anchor: QPointF = QPointF()  # opposite corner in page coords

        # Text placement config (passed in from main window)
        self.pending_text_config: dict = {}

        # Pending stamp path for placement
        self._pending_stamp_path: Optional[str] = None

        # Overlay stamps (in-memory, burned on save)
        self._overlay_stamps: list[dict] = []  # {page, rect, path, id}

        # Inline text editing
        self._inline_edit_widget: Optional[QWidget] = None

        # Search highlights
        self._search_rects: list[tuple[int, fitz.Rect]] = []  # (page, rect)
        self._current_search_idx: int = -1

        # Text edit mode (for editing native PDF text)
        self._text_edit_lines_cache: dict = {}  # page_index -> list of line info
        self._text_edit_hover_line: Optional[dict] = None
        self._text_edit_hover_page: int = -1
        self._text_edit_widget: Optional[QWidget] = None
        self._text_edit_line_info: Optional[dict] = None
        self._text_edit_page: int = -1

        # Scroll offset managed by parent QScrollArea
        self._viewport_offset_y: int = 0

        # Refresh timer (debounce)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self.update)

        # Fast zoom timer
        self._is_zooming = False
        self._zoom_timer = QTimer(self)
        self._zoom_timer.setSingleShot(True)
        self._zoom_timer.timeout.connect(self._on_zoom_finished)

        # Settle timer: keeps _is_zooming=True for a bit after commit so
        # background renders finish before we stop showing the scaled fallback
        self._zoom_settle_timer = QTimer(self)
        self._zoom_settle_timer.setSingleShot(True)
        self._zoom_settle_timer.timeout.connect(self._on_zoom_settled)

        # Smooth zoom: _zoom_target is where we want to end up,
        # _visual_zoom lerps toward it at 60fps for a fluid feel.
        self._visual_zoom = 1.0
        self._zoom_target = 1.0
        self._lerp_timer = QTimer(self)
        self._lerp_timer.setInterval(16)   # ~60 fps
        self._lerp_timer.timeout.connect(self._lerp_zoom)
        
        # Crop Mode
        self._crop_start_pos: Optional[QPointF] = None
        self._crop_current_pos: Optional[QPointF] = None
        self._crop_callback: Optional[Callable[[int, fitz.Rect], None]] = None

    # ── Document ──────────────────────────────

    @property
    def document(self) -> Optional[fitz.Document]:
        return self._doc

    def set_document(self, doc: Optional[fitz.Document], file_path: str = "",
                     keep_snapshot: bool = False):
        self._doc = doc
        self._file_path = file_path
        if not keep_snapshot:
            self._doc_bytes_snapshot = None  # 새 문서 로드 시 스냅샷 초기화
        self._render_cache.clear()
        self._low_res_cache.clear()
        self._selected_annot = None
        self._selected_page = -1
        self._overlay_stamps.clear()
        self._search_rects.clear()
        self._page_rects.clear()
        
        if self._doc:
            for i in range(self._doc.page_count):
                self._page_rects.append(self._doc[i].rect)

        self._recalculate_layout()
        self.update()

    def _recalculate_layout(self):
        """Recalculate page positions based on zoom."""
        self._page_offsets.clear()
        self._page_heights.clear()
        if not self._doc:
            self.setMinimumSize(0, 0)
            return
        y = PAGE_GAP
        max_w = 0
        if not self._page_rects:
            return

        page_count = len(self._page_rects)
        for i in range(page_count):
            rect = self._page_rects[i]
            w = int(rect.width * self._zoom)
            h = int(rect.height * self._zoom)
            self._page_offsets.append(y)
            self._page_heights.append(h)
            y += h + PAGE_GAP
            max_w = max(max_w, w)

        total_h = y
        # Center pages horizontally
        widget_w = max(max_w + 80, self.parent().width() if self.parent() else 800)
        self.setMinimumSize(widget_w, total_h)

    @property
    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, z: float):
        z = max(0.1, min(z, 8.0))
        if abs(z - self._zoom) < 0.001:
            return
        self._zoom = z
        self._visual_zoom = z  # Keep visual zoom in sync to prevent scale distortion
        self._zoom_target = z  # Keep lerp target in sync
        self._is_zooming = True
        self._recalculate_layout()
        self.update()
        self.zoom_changed.emit(z)

        # Debounce the high-res rendering by 100ms
        self._zoom_timer.start(100)

    def _on_zoom_finished(self):
        """Called when user stops scrolling (150 ms debounce)."""
        if abs(self._zoom_target - self._zoom) > 0.001:
            self._lerp_timer.stop()

            # The lerp animation has been co-animating the scroll bar using the
            # gesture-origin formula.  Compute the exact final scroll with the
            # same formula so there is NO visible jump at commit time.
            vbar = getattr(self, "_zoom_gesture_vbar", None)
            zoom0 = getattr(self, "_zoom_gesture_zoom0", self._zoom)
            scroll0 = getattr(self, "_zoom_gesture_scroll0", 0)
            vh = getattr(self, "_zoom_gesture_vh", 600)
            anchor = getattr(self, "_zoom_gesture_cursor_vp_y", vh / 2.0)
            final_scroll = 0
            if vbar is not None and zoom0 > 0:
                ratio = self._zoom_target / zoom0
                final_scroll = max(0, int((scroll0 + anchor) * ratio - anchor))

            self._zoom = round(self._zoom_target, 3)
            self._visual_zoom = self._zoom
            self._recalculate_layout()
            self.zoom_changed.emit(self._zoom)

            # Apply final scroll immediately (lerp already brought us here) and
            # once more via singleShot(0) so QScrollArea's deferred layout event
            # cannot override us.
            if vbar is not None:
                vbar.setValue(final_scroll)
                _y = final_scroll
                QTimer.singleShot(0, lambda: vbar.setValue(_y))

            # 가로 스크롤: 페이지를 항상 중앙 정렬
            parent = self.parent()
            sa = parent.parent() if parent else None
            if sa and hasattr(sa, "horizontalScrollBar") and hasattr(sa, "viewport"):
                hbar = sa.horizontalScrollBar()
                vw = sa.viewport().width()
                widget_w = self.width()
                if widget_w > vw:
                    hval = max(0, (widget_w - vw) // 2)
                    hbar.setValue(hval)
                    QTimer.singleShot(0, lambda: hbar.setValue(hval))
                else:
                    hbar.setValue(0)

        self._pending_renders.clear()
        self.update()
        # Keep _is_zooming=True a bit longer so background renders complete
        # before we stop showing the scaled fallback — avoids the "Loading..." flash.
        self._zoom_settle_timer.start(250)

    def _lerp_zoom(self):
        """60fps: animate _visual_zoom toward _zoom_target.

        paintEvent가 view_cy(커서 앵커 또는 뷰포트 중앙)를 기준으로 페이지를 스케일하므로
        스크롤바를 여기서 건드리지 않아도 시각적으로 커서 앵커 줌이 작동함.
        커밋 시(_on_zoom_finished)에만 스크롤바를 정확히 보정함.
        """
        diff = self._zoom_target - self._visual_zoom
        if abs(diff) < 0.0005:
            self._visual_zoom = self._zoom_target
            self._lerp_timer.stop()
        else:
            self._visual_zoom += diff * 0.22   # 0.35→0.22: 더 부드러운 ease-out

        self.update()

    def _on_zoom_settled(self):
        """Called after renders have had time to complete post-zoom."""
        self._is_zooming = False
        self.update()

    # ── Rendering ─────────────────────────────

    def _get_page_pixmap(self, page_index: int, target_w: int, target_h: int) -> Optional[QPixmap]:
        """
        Returns cached pixmap if available. If zooming, returns the best available cached
        pixmap to be scaled by QPainter. If not zooming, triggers background render.
        """
        key = (page_index, round(self._zoom, 3))

        # Check exact cache (LRU access update)
        if key in self._render_cache:
            self._render_cache.move_to_end(key)
            return self._render_cache[key]

        # If we reach here, we don't have the exact resolution pixmap yet.
        # Start a background render if not already rendering.
        if key not in self._pending_renders:
            self._start_render_task(page_index, key)

        # Check for a low-res preview image for quick display
        if key in self._low_res_cache:
            return self._low_res_cache[key].scaled(target_w, target_h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)

        # Only show a blurry scaled fallback from another zoom level during active zoom transitions.
        if self._is_zooming:
            candidates = [(k, v) for k, v in self._render_cache.items() if k[0] == page_index]
            if candidates:
                _, best_pixmap = candidates[-1]
                return best_pixmap.scaled(target_w, target_h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)

        return None

    def _start_render_task(self, page_index: int, key: tuple[int, float]):
        if not self._doc or (not self._file_path and not self._doc_bytes_snapshot):
            return

        self._pending_renders.add(key)

        # Create worker — 수정된 doc이 있으면 bytes 스냅샷 사용, 없으면 원본 파일
        worker = RenderWorker(
            self._file_path, page_index, self._zoom,
            is_valid_cb=lambda z=self._zoom: self._is_render_valid(page_index, z),
            doc_bytes=self._doc_bytes_snapshot,
        )
        # Signal emits QImage, is_high_res
        worker.signals.finished.connect(lambda img, is_high_res, idx=page_index, k=key: self._on_render_finished(img, is_high_res, idx, k))
        self._thread_pool.start(worker)

    def _on_render_finished(self, image: QImage, is_high_res: bool, page_index: int, key: tuple[int, float]):
        """Callback from background thread (via signal)."""
        if is_high_res and key in self._pending_renders:
            self._pending_renders.remove(key)

        # Discard stale renders: zoom changed while this worker was rendering.
        current_key = (page_index, round(self._zoom, 3))
        if key != current_key:
            return

        if not image.isNull():
            # Convert QImage to QPixmap on the main thread
            pixmap = QPixmap.fromImage(image)
            pixmap.setDevicePixelRatio(image.devicePixelRatio())

            if is_high_res:
                self._render_cache[key] = pixmap
                self._render_cache.move_to_end(key)
                
                # We can remove the low-res version once high-res is ready
                if key in self._low_res_cache:
                    del self._low_res_cache[key]

                # Enforce cache size limit (30 pages ≈ 150–450MB at zoom 1.0 DPR 2.0)
                while len(self._render_cache) > 30:
                    self._render_cache.popitem(last=False)
            else:
                self._low_res_cache[key] = pixmap
                while len(self._low_res_cache) > 150:
                    self._low_res_cache.popitem(last=False)

            # Redraw
            self.update()

    def _is_render_valid(self, page_index: int, zoom: float) -> bool:
        """Checks if a background render is still valid for the current view state."""
        return abs(self._zoom - zoom) < 0.001

    def paintEvent(self, event):
        if not self._doc:
            self._draw_drop_zone()
            return

        try:
            _ = self._page_offsets
        except AttributeError:
            print("CRITICAL: _page_offsets missing!")
            print(f"Self: {self!r}")
            print(f"Dict: {self.__dict__}")
            print("INIT FAILED?")
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("#444444"))

        # Get page count — no lock needed (read-only on main thread)
        try:
            doc_page_count = self._doc.page_count if self._doc else 0
        except Exception:
            return

        # Compute the pure visual transform difference for fast optical zoom
        visual_scale = self._visual_zoom / self._zoom

        # To keep the zoom centered around the user's screen during the fast zoom,
        # we need to translate the layout coordinates relative to the scroll view viewport center
        scroll_area = self.parent().parent() if self.parent() and hasattr(self.parent(), "parent") and self.parent().parent() else None
        view_cx = 0
        view_cy = 0
        if scroll_area and hasattr(scroll_area, "horizontalScrollBar"):
            h_bar = scroll_area.horizontalScrollBar()
            v_bar = scroll_area.verticalScrollBar()
            view_cx = h_bar.value() + scroll_area.viewport().width() / 2.0
            view_cy = v_bar.value() + scroll_area.viewport().height() / 2.0

        # 줌 중에는 커서 위치를 앵커로 사용, 아닐 때는 뷰포트 중앙
        if self._is_zooming and hasattr(self, "_zoom_gesture_cursor_vp_y"):
            cursor_vp_y = self._zoom_gesture_cursor_vp_y
            if scroll_area and hasattr(scroll_area, "verticalScrollBar"):
                view_cy = scroll_area.verticalScrollBar().value() + cursor_vp_y

        vis_start, vis_end = self._visible_page_range()
        vis_end = min(vis_end, doc_page_count, len(self._page_offsets))

        for i in range(vis_start, vis_end):
            # Scale the layout offset towards the viewport center
            dy = self._page_offsets[i] - view_cy
            page_y = int(view_cy + (dy * visual_scale))
            
            page_h = int(self._page_heights[i] * visual_scale)
            pw = int((self._page_rects[i].width * self._zoom) * visual_scale)
            
            dx = self._page_x_offset(i) - view_cx
            page_x = int(view_cx + (dx * visual_scale))

            # Skip strictly offscreen pages
            if page_y + page_h < -100 or page_y > self.height() + 100:
                continue

            # Render page
            pixmap = self._get_page_pixmap(i, pw, page_h)

            if pixmap:
                if getattr(self, "_is_zooming", False) or pixmap.width() != pw or pixmap.height() != page_h:
                    # During zoom or when rendering an outdated/low-res fallback image, MUST stretch it
                    painter.drawPixmap(page_x, page_y, pw, page_h, pixmap)
                else:
                    painter.drawPixmap(page_x, page_y, pixmap)
            else:
                # Draw plain white placeholder to avoid flashing "Loading" text
                painter.fillRect(page_x, page_y, pw, page_h, QColor("white"))

            # Draw page border shadow
            painter.setPen(QPen(QColor(0, 0, 0, 60), 1))
            painter.drawRect(page_x - 1, page_y - 1, pw + 2, page_h + 2)

            # Draw overlay stamps for this page
            self._draw_overlay_stamps(painter, i, page_x, page_y)

            # Draw drag preview: cover old position, draw annotation at new position
            if (self._drag_annot and self._drag_page == i
                    and isinstance(self._drag_annot, fitz.Annot) and self._orig_rect):
                # Cover original annotation position with white
                orig_sr = fitz_rect_to_qrectf(self._orig_rect, page_x, page_y, self._zoom)
                painter.fillRect(orig_sr.adjusted(-2, -2, 2, 2), QColor("white"))
                # Draw annotation snapshot at current (new) position
                if self._drag_annot_pixmap:
                    try:
                        cur_rect = fitz.Rect(self._drag_annot.rect)
                        new_sr = fitz_rect_to_qrectf(cur_rect, page_x, page_y, self._zoom)
                        painter.drawPixmap(new_sr.toRect(), self._drag_annot_pixmap)
                    except Exception:
                        pass

            # Draw annotation handles for selected annotation
            if self._selected_page == i and self._selected_annot:
                try:
                    r = self._selected_annot.rect
                    sr = fitz_rect_to_qrectf(r, page_x, page_y, self._zoom)
                    self._draw_selection(painter, sr)
                except Exception:
                    pass

            # Draw search highlights
            for (pg, rect) in self._search_rects:
                if pg == i:
                    sr = fitz_rect_to_qrectf(rect, page_x, page_y, self._zoom)
                    painter.fillRect(sr, QColor(255, 165, 0, 80))
                    painter.setPen(QPen(QColor(255, 140, 0), 1))
                    painter.drawRect(sr)

            # Draw text edit hover highlight
            if self.mode == self.MODE_TEXT_EDIT:
                if self._text_edit_hover_page == i and self._text_edit_hover_line:
                    hr = self._text_edit_hover_line["bbox"]
                    hsr = fitz_rect_to_qrectf(hr, page_x, page_y, self._zoom)
                    painter.fillRect(hsr, QColor(41, 121, 255, 30))
                    painter.setPen(QPen(QColor(41, 121, 255, 120), 1))
                    painter.drawRect(hsr)

        # Draw crop rectangle
        if self.mode == self.MODE_CROP and self._crop_start_pos and self._crop_current_pos:
            r = QRectF(self._crop_start_pos, self._crop_current_pos).normalized()
            painter.setPen(QPen(QColor(0, 122, 255), 2, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(0, 122, 255, 40))
            painter.drawRect(r)

        painter.end()

    def _draw_drop_zone(self):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#f0f0f0"))
        painter.setPen(QPen(QColor("#999999"), 2, Qt.PenStyle.DashLine))
        painter.drawRect(self.rect().adjusted(40, 40, -40, -40))
        painter.setPen(QColor("#666666"))
        font = QFont()
        font.setPointSize(14)
        painter.setFont(font)
        painter.drawText(
            self.rect(), Qt.AlignmentFlag.AlignCenter,
            "PDF 파일을 드래그하거나\n열기 버튼을 누르세요"
        )
        painter.end()

    def _draw_overlay_stamps(self, painter: QPainter, page_index: int, px: int, py: int):
        for s in self._overlay_stamps:
            if s["page"] != page_index:
                continue
            r = s["rect"]
            sr = QRectF(
                r.x0 * self._zoom + px,
                r.y0 * self._zoom + py,
                r.width * self._zoom,
                r.height * self._zoom,
            )
            pixmap = s.get("_pixmap")
            if pixmap is None:
                pixmap = QPixmap(s["path"])
                s["_pixmap"] = pixmap
            if not pixmap.isNull():
                painter.drawPixmap(sr.toRect(), pixmap)

            # Selection handles for selected stamp
            if self._selected_annot is None and s.get("selected", False):
                self._draw_selection(painter, sr)

    def _draw_selection(self, painter: QPainter, sr: QRectF):
        # Dashed border
        pen = QPen(QColor("#2979FF"), 1.5, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(sr.adjusted(-2, -2, 2, 2))

        # Corner handles
        hs = self.HANDLE_SIZE
        corners = [
            QPointF(sr.left(), sr.top()),
            QPointF(sr.right(), sr.top()),
            QPointF(sr.right(), sr.bottom()),
            QPointF(sr.left(), sr.bottom()),
        ]
        painter.setPen(QPen(QColor("white"), 1.5))
        painter.setBrush(QColor("#2979FF"))
        for c in corners:
            painter.drawEllipse(c, hs / 2, hs / 2)

    # ── Layout ────────────────────────────────

    def _page_x_offset(self, page_index: int) -> int:
        """Returns the x offset to center a page horizontally."""
        if not self._page_rects or page_index >= len(self._page_rects):
            return 0
        pw = int(self._page_rects[page_index].width * self._zoom)
        widget_w = self.width()
        if pw >= widget_w - 20:
            return 10  # 페이지가 위젯보다 크면 최소 여백만
        return (widget_w - pw) // 2

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recalculate_layout()

    def page_at_y(self, y: int) -> int:
        """Returns the page index at the given y position (binary search, O(log n))."""
        if not self._page_offsets:
            return 0
        idx = bisect.bisect_right(self._page_offsets, y) - 1
        return max(0, min(idx, len(self._page_offsets) - 1))

    def _visible_page_range(self) -> tuple[int, int]:
        """Returns (start, end_exclusive) indices of pages visible in viewport + buffer.
        Uses binary search for O(log n) performance instead of iterating all pages.
        """
        n = len(self._page_offsets)
        if n == 0:
            return 0, 0
        scroll_area = None
        parent = self.parentWidget()
        if parent:
            scroll_area = parent.parentWidget()
        if not scroll_area or not hasattr(scroll_area, 'verticalScrollBar'):
            return 0, n
        vbar = scroll_area.verticalScrollBar()
        vh = scroll_area.viewport().height()
        top = vbar.value() - 500
        bottom = vbar.value() + vh + 500
        start = bisect.bisect_right(self._page_offsets, top) - 1
        start = max(0, start)
        end = bisect.bisect_right(self._page_offsets, bottom)
        end = min(n, end)
        return start, end

    def y_for_page(self, page_index: int) -> int:
        if 0 <= page_index < len(self._page_offsets):
            return self._page_offsets[page_index]
        return 0

    # ── Mouse Events ──────────────────────────

    def _hit_test_annot(self, pos: QPointF) -> Optional[AnnotHit]:
        """Find the annotation under pos. Returns AnnotHit or None.
        Only checks the page at the mouse position ±1 for O(1) performance.
        """
        if not self._doc or not self._page_offsets:
            return None

        center_page = self.page_at_y(int(pos.y()))
        page_count = len(self._page_offsets)
        check_start = max(0, center_page - 1)
        check_end = min(page_count, center_page + 2)

        for i in range(check_start, check_end):
            py = self._page_offsets[i]
            px = self._page_x_offset(i)
            try:
                page = self._doc[i]
                annots_list = list(page.annots()) if page.annots() else []
            except Exception:
                continue
            for annot in annots_list:
                try:
                    r = annot.rect
                    sr = fitz_rect_to_qrectf(r, px, py, self._zoom)

                    # Check corner handles first
                    corners = [
                        QPointF(sr.left(), sr.top()),      # 0 TL
                        QPointF(sr.right(), sr.top()),     # 1 TR
                        QPointF(sr.right(), sr.bottom()),  # 2 BR
                        QPointF(sr.left(), sr.bottom()),   # 3 BL
                    ]
                    for cidx, corner in enumerate(corners):
                        dist = math.hypot(pos.x() - corner.x(), pos.y() - corner.y())
                        if dist < self.HANDLE_SIZE:
                            return AnnotHit(annot, i, cidx, page_obj=page)

                    if sr.contains(pos):
                        return AnnotHit(annot, i, AnnotHit.BODY, page_obj=page)
                except Exception:
                    continue

        # Check overlay stamps (only on nearby pages)
        for s in reversed(self._overlay_stamps):
            i = s["page"]
            if i < check_start or i >= check_end:
                continue
            py = self._page_offsets[i]
            px = self._page_x_offset(i)
            r = s["rect"]
            sr = fitz_rect_to_qrectf(r, px, py, self._zoom)

            corners = [
                QPointF(sr.left(), sr.top()),
                QPointF(sr.right(), sr.top()),
                QPointF(sr.right(), sr.bottom()),
                QPointF(sr.left(), sr.bottom()),
            ]
            for cidx, corner in enumerate(corners):
                dist = math.hypot(pos.x() - corner.x(), pos.y() - corner.y())
                if dist < self.HANDLE_SIZE:
                    return AnnotHit(s, i, cidx, match_type="stamp")

            if sr.contains(pos):
                return AnnotHit(s, i, AnnotHit.BODY, match_type="stamp")

        return None

    def _screen_to_page_coords(self, screen_pos: QPointF, page_index: int) -> QPointF:
        px = self._page_x_offset(page_index)
        py = self._page_offsets[page_index]
        return QPointF(
            (screen_pos.x() - px) / self._zoom,
            (screen_pos.y() - py) / self._zoom,
        )

    def mousePressEvent(self, event: QMouseEvent):
        pos = QPointF(event.position())

        if self.mode == self.MODE_TEXT_PLACEMENT:
            self._place_text_at(pos)
            return
            
        if self.mode == self.MODE_CROP:
            self._crop_start_pos = pos
            self._crop_current_pos = pos
            return

        if self.mode == self.MODE_TEXT_EDIT:
            if event.button() == Qt.MouseButton.LeftButton:
                self._handle_text_edit_click(pos)
            return

        if event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(pos, event.globalPosition().toPoint())
            return

        hit = self._hit_test_annot(pos)
        if hit:
            if hit.match_type == "annot":
                self._selected_annot = hit.annot
            else:
                self._selected_annot = None
                for s in self._overlay_stamps:
                    s["selected"] = False
                hit.annot["selected"] = True

            self._selected_page = hit.page_index
            self._selected_page_obj = hit.page_obj # Store strong reference
            self._drag_annot = hit.annot
            self._drag_page = hit.page_index
            self._drag_start = self._screen_to_page_coords(pos, hit.page_index)

            if hit.match_type == "annot":
                self._orig_rect = fitz.Rect(hit.annot.rect)
            else:
                self._orig_rect = fitz.Rect(hit.annot["rect"])

            # Capture annotation appearance snapshot for smooth drag preview
            if hit.match_type == "annot":
                try:
                    mat = fitz.Matrix(self._zoom, self._zoom)
                    pix = hit.annot.get_pixmap(matrix=mat, alpha=True)
                    self._drag_annot_pixmap = QPixmap.fromImage(
                        fitz_pixmap_to_qimage(pix)
                    )
                except Exception:
                    self._drag_annot_pixmap = None
            else:
                self._drag_annot_pixmap = None

            # Prepare character-wrap info for FreeText resize
            self._drag_raw_text = None
            self._drag_da = {}
            if hit.match_type == "annot":
                try:
                    atype = hit.annot.type[1] if hit.annot.type else ""
                    if atype == "FreeText":
                        xref = hit.annot.xref
                        raw = self._annot_raw_text.get(xref)
                        if raw is None:
                            raw = hit.annot.info.get("content", "")
                        self._drag_raw_text = raw
                        self._drag_da = self._parse_annot_da(hit.annot)
                except Exception:
                    pass

            self._resize_corner = hit.corner

            if hit.corner >= 0:
                self._is_resizing = True
                r = self._orig_rect
                opp = [
                    QPointF(r.x1, r.y1),
                    QPointF(r.x0, r.y1),
                    QPointF(r.x0, r.y0),
                    QPointF(r.x1, r.y0),
                ][hit.corner]
                self._resize_anchor = opp
            else:
                self._is_resizing = False

            self.update()
        else:
            self._selected_annot = None
            self._selected_page = -1
            for s in self._overlay_stamps:
                s["selected"] = False
            self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Handle double-click for inline text editing."""
        pos = QPointF(event.position())
        hit = self._hit_test_annot(pos)
        if hit and hit.match_type == "annot" and hit.corner == AnnotHit.BODY:
            annot_type = hit.annot.type[1] if hit.annot.type else ""
            if annot_type == "FreeText":
                self._begin_inline_edit(hit.annot, hit.page_index)
                return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = QPointF(event.position())

        if self.mode == self.MODE_TEXT_PLACEMENT:
            self.setCursor(Qt.CursorShape.CrossCursor)
            return
            
        if self.mode == self.MODE_CROP:
            self.setCursor(Qt.CursorShape.CrossCursor)
            if self._crop_start_pos:
                self._crop_current_pos = pos
                self.update()
            return

        if self.mode == self.MODE_TEXT_EDIT:
            self._handle_text_edit_hover(pos)
            return

        if self._drag_annot:
            page_pos = self._screen_to_page_coords(pos, self._drag_page)
            if self._is_resizing and self._orig_rect:
                ax, ay = self._resize_anchor.x(), self._resize_anchor.y()
                px, py = page_pos.x(), page_pos.y()

                if not isinstance(self._drag_annot, fitz.Annot):
                    # Stamp: aspect-ratio-preserving resize
                    orig_w = self._orig_rect.width
                    orig_h = self._orig_rect.height
                    if orig_w > 0 and orig_h > 0:
                        aspect = orig_w / orig_h
                        dx = abs(px - ax)
                        dy = abs(py - ay)
                        if dx / aspect > dy:
                            new_w = max(dx, 20 / self._zoom)
                            new_h = new_w / aspect
                        else:
                            new_h = max(dy, 20 / self._zoom)
                            new_w = new_h * aspect
                        if px < ax:
                            nx0 = ax - new_w
                        else:
                            nx0 = ax
                        if py < ay:
                            ny0 = ay - new_h
                        else:
                            ny0 = ay
                        new_rect = fitz.Rect(nx0, ny0, nx0 + new_w, ny0 + new_h)
                        self._drag_annot["rect"] = new_rect
                else:
                    # Regular annotation: free resize
                    x0 = min(ax, px)
                    y0 = min(ay, py)
                    x1 = max(ax, px)
                    y1 = max(ay, py)
                    w = max(x1 - x0, 20 / self._zoom)
                    h = max(y1 - y0, 10 / self._zoom)
                    new_rect = fitz.Rect(x0, y0, x0 + w, y0 + h)
                    try:
                        self._drag_annot.set_rect(new_rect)
                        if self._drag_raw_text is not None:
                            # FreeText: QPainter preview with char-level wrap
                            fs = self._drag_da.get("fontsize", 14.0)
                            qc = self._drag_da.get("qcolor", QColor(0, 0, 0))
                            fn = self._drag_da.get("fontname", "helv")
                            wrapped = _fitz_char_wrap_text(
                                self._drag_raw_text, new_rect.width, fs, fn,
                            )
                            pw = max(int(new_rect.width * self._zoom), 1)
                            ph = max(int(new_rect.height * self._zoom), 1)
                            pm = QPixmap(pw, ph)
                            pm.fill(Qt.GlobalColor.transparent)
                            qp = QPainter(pm)
                            qp.setRenderHint(QPainter.RenderHint.Antialiasing)
                            font = QFont()
                            font.setPixelSize(max(int(fs * self._zoom), 1))
                            qp.setFont(font)
                            qp.setPen(qc)
                            fm = qp.fontMetrics()
                            line_h = fm.height()
                            ty = fm.ascent()
                            for ln in wrapped.split("\n"):
                                qp.drawText(2, int(ty), ln)
                                ty += line_h
                            qp.end()
                            self._drag_annot_pixmap = pm
                        else:
                            # Other annotations: fitz rendering
                            self._drag_annot.update()
                            mat = fitz.Matrix(self._zoom, self._zoom)
                            pix = self._drag_annot.get_pixmap(
                                matrix=mat, alpha=True
                            )
                            self._drag_annot_pixmap = QPixmap.fromImage(
                                fitz_pixmap_to_qimage(pix)
                            )
                    except Exception:
                        pass
            else:
                if self._orig_rect:
                    dx = page_pos.x() - self._drag_start.x()
                    dy = page_pos.y() - self._drag_start.y()
                    new_rect = fitz.Rect(
                        self._orig_rect.x0 + dx, self._orig_rect.y0 + dy,
                        self._orig_rect.x1 + dx, self._orig_rect.y1 + dy,
                    )
                    try:
                        if isinstance(self._drag_annot, fitz.Annot):
                            self._drag_annot.set_rect(new_rect)
                        else:  # Stamp dict
                            self._drag_annot["rect"] = new_rect
                    except Exception:
                        pass
            self.update()
            return

        # Cursor hover
        hit = self._hit_test_annot(pos)
        if hit:
            if hit.corner >= 0:
                cursors = [
                    Qt.CursorShape.SizeFDiagCursor,  # TL
                    Qt.CursorShape.SizeBDiagCursor,  # TR
                    Qt.CursorShape.SizeFDiagCursor,  # BR
                    Qt.CursorShape.SizeBDiagCursor,  # BL
                ]
                self.setCursor(cursors[hit.corner])
            else:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.mode == self.MODE_CROP and self._crop_start_pos:
            end_pos = QPointF(event.position())
            r = QRectF(self._crop_start_pos, end_pos).normalized()
            self._crop_start_pos = None
            self._crop_current_pos = None
            
            # Find page index
            page_index = self.page_at_y(int(r.center().y()))
            
            if r.width() > 10 and r.height() > 10:
                page_pos1 = self._screen_to_page_coords(r.topLeft(), page_index)
                page_pos2 = self._screen_to_page_coords(r.bottomRight(), page_index)
                fitz_r = fitz.Rect(page_pos1.x(), page_pos1.y(), page_pos2.x(), page_pos2.y())
                
                self.mode = self.MODE_NORMAL
                self.setCursor(Qt.CursorShape.ArrowCursor)
                self.update()
                
                if self._crop_callback:
                    self._crop_callback(page_index, fitz_r)
            else:
                self.mode = self.MODE_NORMAL
                self.setCursor(Qt.CursorShape.ArrowCursor)
                self.update()
            return
            
        if self._drag_annot:
            if isinstance(self._drag_annot, fitz.Annot):
                # FreeText resize → recreate with char-wrapped text
                if self._drag_raw_text is not None and self._is_resizing:
                    da = self._drag_da
                    fs = da.get("fontsize", 14.0)
                    clr = da.get("color", (0, 0, 0))
                    final_rect = fitz.Rect(self._drag_annot.rect)
                    page = self._doc[self._drag_page]
                    page.delete_annot(self._drag_annot)
                    font_kwargs = _resolve_freetext_font(
                        self._drag_raw_text, da.get("fontname", "helv"),
                    )
                    wrapped = _fitz_char_wrap_text(
                        self._drag_raw_text, final_rect.width, fs,
                        font_kwargs.get("fontname", "helv"),
                    )
                    new_annot = page.add_freetext_annot(
                        rect=final_rect,
                        text=wrapped,
                        fontsize=fs,
                        text_color=clr,
                        fill_color=None,
                        **font_kwargs,
                        border_color=None,
                    )
                    new_annot.update()
                    self._annot_raw_text[new_annot.xref] = self._drag_raw_text
                    self._selected_annot = new_annot
                else:
                    self._drag_annot.update()
            self._invalidate_page(self._drag_page)
            self._snapshot_doc_bytes()
            self.doc_modified.emit()
            self._drag_annot = None
            self._drag_annot_pixmap = None
            self._drag_raw_text = None
            self._drag_da = {}
            self._is_resizing = False
            self.update()

    def _parse_annot_da(self, annot: fitz.Annot) -> dict:
        """Parse DA string of a FreeText annotation → fontsize, fontname, color."""
        import re as _re
        info = {
            "fontsize": 14.0,
            "fontname": "helv",
            "color": (0, 0, 0),          # fitz 0-1 range
            "qcolor": QColor(0, 0, 0),   # Qt color
        }
        try:
            da_val = self._doc.xref_get_key(annot.xref, "DA")
            if da_val[0] == "string":
                da = da_val[1]
                m = _re.search(r"([\d.]+)\s+Tf", da)
                if m:
                    info["fontsize"] = float(m.group(1))
                m = _re.search(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+rg", da)
                if m:
                    r, g, b = float(m.group(1)), float(m.group(2)), float(m.group(3))
                    info["color"] = (r, g, b)
                    info["qcolor"] = QColor(int(r * 255), int(g * 255), int(b * 255))
        except Exception:
            pass
        return info

    def _snapshot_doc_bytes(self):
        """doc이 수정된 후 호출 — RenderWorker가 최신 내용을 렌더링하도록 bytes 스냅샷 갱신."""
        if self._doc:
            try:
                self._doc_bytes_snapshot = self._doc.tobytes()
            except Exception:
                pass

    def _invalidate_page(self, page_index: int):
        """Remove cached render for a page (to force re-render)."""
        keys_to_remove = [k for k in self._render_cache if k[0] == page_index]
        for k in keys_to_remove:
            del self._render_cache[k]
        keys_low = [k for k in self._low_res_cache if k[0] == page_index]
        for k in keys_low:
            del self._low_res_cache[k]

    def _prerender_near_pages(self, center_page: int, lookahead: int = 10, lookbehind: int = 4):
        """Pre-render pages near center_page so they're ready before scrolling to them."""
        if not self._doc:
            return
        page_count = len(self._page_offsets)
        for i in range(max(0, center_page - lookbehind), min(page_count, center_page + lookahead + 1)):
            key = (i, round(self._zoom, 3))
            if key not in self._render_cache and key not in self._pending_renders:
                self._start_render_task(i, key)

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Precision touchpad sends pixelDelta (small continuous values).
            # Standard mouse wheel sends angleDelta (multiples of ±120).
            pixel_y = event.pixelDelta().y()
            if pixel_y != 0:
                factor = 1.0 + pixel_y * 0.004   # ~0.4% per pixel
            else:
                angle_y = event.angleDelta().y()
                factor = 1.0 + (angle_y / 120.0) * 0.07   # 7% per tick

            # On the FIRST event of a new gesture, snapshot the scroll origin.
            # scroll0 / zoom0 define the invariant "center doc point" we keep
            # fixed throughout the animation (and reset on the next gesture).
            if not self._lerp_timer.isActive():
                parent = self.parent()
                if parent and parent.parent():
                    sa = parent.parent()
                    if hasattr(sa, "verticalScrollBar"):
                        vbar = sa.verticalScrollBar()
                        vh = sa.viewport().height() if hasattr(sa, "viewport") else 600
                        self._zoom_gesture_vbar = vbar
                        self._zoom_gesture_scroll0 = vbar.value()
                        self._zoom_gesture_zoom0 = self._zoom
                        self._zoom_gesture_vh = vh
                        # ── 커서 앵커: 뷰포트 기준 커서 Y 저장 ──
                        cursor_vp_y = event.position().y() - vbar.value()
                        self._zoom_gesture_cursor_vp_y = max(0.0, min(float(cursor_vp_y), float(vh)))

            self._zoom_target *= factor
            self._zoom_target = max(0.1, min(self._zoom_target, 8.0))
            self._is_zooming = True

            if not self._lerp_timer.isActive():
                self._lerp_timer.start()

            self._zoom_timer.start(150)
            event.accept()
        else:
            event.ignore()

    # ── Text Placement ────────────────────────

    def _exit_current_mode(self):
        """현재 활성 모드를 안전하게 종료하고 NORMAL 모드로 전환.
        새 모드 진입 전에 항상 호출하여 이전 모드 상태를 정리한다.
        """
        if self.mode == self.MODE_NORMAL:
            return

        if self.mode == self.MODE_TEXT_EDIT:
            if self._text_edit_widget:
                self._commit_text_edit()
            self._text_edit_lines_cache.clear()
            self._text_edit_hover_line = None
            self._text_edit_hover_page = -1

        elif self.mode == self.MODE_TEXT_PLACEMENT:
            self.pending_text_config = {}

        elif self.mode == self.MODE_CROP:
            self._crop_start_pos = None
            self._crop_current_pos = None
            self._crop_callback = None

        self.mode = self.MODE_NORMAL
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def enter_text_placement_mode(self, config: dict):
        self._exit_current_mode()
        self._selected_annot = None
        self._selected_page = -1
        self.pending_text_config = config
        self.mode = self.MODE_TEXT_PLACEMENT
        self.setCursor(Qt.CursorShape.CrossCursor)

    def exit_text_placement_mode(self):
        self.mode = self.MODE_NORMAL
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def _place_text_at(self, screen_pos: QPointF):
        """Add a text annotation at the clicked position."""
        if not self._doc or not self._page_offsets:
            return
        page_index = self.page_at_y(int(screen_pos.y()))
        if page_index < 0 or page_index >= len(self._page_offsets):
            return
        # Verify click is within the page bounds
        py = self._page_offsets[page_index]
        px = self._page_x_offset(page_index)
        pw = int(self._page_rects[page_index].width * self._zoom)
        ph = self._page_heights[page_index]
        rect = QRectF(px, py, pw, ph)
        if not rect.contains(screen_pos):
            return

        page_pos = self._screen_to_page_coords(screen_pos, page_index)
        config = self.pending_text_config
        text = config.get("text", "텍스트")
        font_size = config.get("font_size", 14.0)
        color = config.get("color", (0, 0, 0))  # RGB 0-1
        font_name = config.get("font_name", "helv")
        font_kwargs = _resolve_freetext_font(text, font_name)

        lines = text.split("\n")
        line_count = max(len(lines), 1)
        max_len = max(len(l) for l in lines) if lines else 1
        w = max(max_len * font_size * 0.6, 60)
        h = font_size * 1.6 * line_count + 10
        rect = fitz.Rect(
            page_pos.x() - w / 2, page_pos.y() - h / 2,
            page_pos.x() + w / 2, page_pos.y() + h / 2,
        )

        page = self._doc[page_index]
        annot = page.add_freetext_annot(
            rect=rect,
            text=text,
            fontsize=font_size,
            text_color=color,
            fill_color=None,
            border_color=None,
            **font_kwargs,
        )
        annot.update()

        self._annot_raw_text[annot.xref] = text
        self._invalidate_page(page_index)
        self._selected_annot = annot
        self._selected_page = page_index
        self.exit_text_placement_mode()
        self._snapshot_doc_bytes()
        self.doc_modified.emit()
        self.text_placed.emit()
        self.update()
        
    # ------------- Crop Mode -------------
    
    def enter_crop_mode(self, callback: Callable[[int, fitz.Rect], None]):
        self._exit_current_mode()
        self._selected_annot = None
        self._selected_page = -1
        self.mode = self.MODE_CROP
        self._crop_callback = callback
        self.setCursor(Qt.CursorShape.CrossCursor)

    def add_text_at_page_center(self, page_index: int, config: dict):
        """Add a text annotation at the center of a page."""
        if not self._doc or page_index >= self._doc.page_count:
            return
        page = self._doc[page_index]
        pr = page.rect
        center_x = pr.width / 2
        center_y = pr.height / 2
        text = config.get("text", "텍스트")
        font_size = config.get("font_size", 14.0)
        color = config.get("color", (0, 0, 0))
        font_name = config.get("font_name", "helv")
        font_kwargs = _resolve_freetext_font(text, font_name)

        lines = text.split("\n")
        w = max(max(len(l) for l in lines) * font_size * 0.6, 80) if lines else 80
        h = font_size * 1.6 * max(len(lines), 1) + 10

        rect = fitz.Rect(
            center_x - w / 2, center_y - h / 2,
            center_x + w / 2, center_y + h / 2,
        )
        annot = page.add_freetext_annot(
            rect=rect, text=text,
            fontsize=font_size, text_color=color, fill_color=None,
            **font_kwargs,
        )
        annot.update()
        self._annot_raw_text[annot.xref] = text
        self._invalidate_page(page_index)
        self._selected_annot = annot
        self._selected_page = page_index
        self._snapshot_doc_bytes()
        self.doc_modified.emit()
        self.update()

    # ── Inline Text Editing ───────────────────

    def _begin_inline_edit(self, annot: fitz.Annot, page_index: int):
        from PyQt6.QtWidgets import QTextEdit
        if self._inline_edit_widget:
            self._commit_inline_edit()

        r = annot.rect
        text_content = annot.info.get("content", "")
        py = self._page_offsets[page_index]
        px = self._page_x_offset(page_index)
        sr = fitz_rect_to_qrectf(r, px, py, self._zoom).toRect()
        sr = sr.adjusted(-4, -4, 4, 4)

        editor = QTextEdit(self)
        editor.setPlainText(text_content)
        editor.setGeometry(sr)
        editor.setStyleSheet(
            "background: white; border: 2px solid #2979FF; font-size: 12pt;"
        )
        editor.show()
        editor.setFocus()
        editor.selectAll()

        self._inline_edit_widget = editor
        self._inline_edit_annot = annot
        self._inline_edit_page = page_index

        _orig_focus_out = editor.focusOutEvent

        def _on_focus_out(event):
            _orig_focus_out(event)
            self._commit_inline_edit()

        editor.focusOutEvent = _on_focus_out

    def _commit_inline_edit(self):
        if not self._inline_edit_widget:
            return

        widget = self._inline_edit_widget
        annot = self._inline_edit_annot
        page_index = self._inline_edit_page

        self._inline_edit_widget = None
        self._inline_edit_annot = None
        self._inline_edit_page = -1

        from PyQt6.QtWidgets import QTextEdit
        if isinstance(widget, QTextEdit) and annot:
            new_text = widget.toPlainText()
            info = annot.info
            info["content"] = new_text
            annot.set_info(info)
            annot.update()
            self._annot_raw_text[annot.xref] = new_text
            self._invalidate_page(page_index)
            self._snapshot_doc_bytes()
            self.doc_modified.emit()

        widget.hide()
        widget.deleteLater()
        self.update()

    # ── PDF Text Edit Mode ─────────────────────

    def enter_text_edit_mode(self):
        """Enter mode for editing existing PDF text (electronically created PDFs)."""
        self._exit_current_mode()
        self._selected_annot = None
        self._selected_page = -1
        self.mode = self.MODE_TEXT_EDIT
        self._text_edit_lines_cache.clear()
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.update()

    def exit_text_edit_mode(self):
        """Exit text edit mode."""
        if self._text_edit_widget:
            self._commit_text_edit()
        self.mode = self.MODE_NORMAL
        self._text_edit_lines_cache.clear()
        self._text_edit_hover_line = None
        self._text_edit_hover_page = -1
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def _get_text_lines_for_page(self, page_index: int) -> list:
        """Extract text lines from a page for editing. Cached per page."""
        if page_index in self._text_edit_lines_cache:
            return self._text_edit_lines_cache[page_index]

        if not self._doc or page_index >= self._doc.page_count:
            return []

        page = self._doc[page_index]
        # rawdict gives per-character bounding boxes for precise space detection
        text_dict = page.get_text("rawdict")

        lines = []
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                bbox = fitz.Rect(line["bbox"])

                # Build text from individual character positions.
                # When the gap between consecutive chars exceeds a threshold,
                # insert a space. This is the most accurate method because
                # it reads the actual glyph positions from the PDF.
                text = self._extract_line_text_from_chars(spans)
                if not text:
                    continue

                first_span = spans[0]

                # 첫 번째 실제(공백 아닌) 글자의 시각적 x 위치를 저장.
                # span origin은 폰트 bearing을 포함하므로 폰트 교체 시
                # 시각적 시작 위치가 달라질 수 있다. bbox.x0은 폰트 무관.
                first_char_x = None
                for _sp in spans:
                    for _ch in _sp.get("chars", []):
                        _c = _ch.get("c", "")
                        _cb = _ch.get("bbox")
                        if _c and _c.strip() and _cb:
                            first_char_x = _cb[0]
                            break
                    if first_char_x is not None:
                        break

                lines.append({
                    "text": text,
                    "bbox": bbox,
                    "font": first_span.get("font", ""),
                    "size": first_span.get("size", 12),
                    "color": first_span.get("color", 0),
                    "origin": first_span.get("origin", (bbox.x0, bbox.y1)),
                    "first_char_x": first_char_x,
                    "spans": spans,
                })

        # ── 중복 텍스트 라인 제거 ──────────────────────────────
        # draw_rect + insert_text 방식은 원본 텍스트를 시각적으로만 덮고
        # 콘텐츠 스트림에는 남겨둔다. rawdict 추출 시 원본 + 새 텍스트가
        # 같은 위치에 겹쳐서 나오므로, 마지막(최신) 것만 유지한다.
        if lines:
            deduped: list = []
            for i, line_i in enumerate(lines):
                bi = line_i["bbox"]
                has_later_dup = False
                for j in range(i + 1, len(lines)):
                    bj = lines[j]["bbox"]
                    # 수직 위치가 거의 같고 수평 범위가 겹치면 중복
                    if (abs(bi.y0 - bj.y0) < 3 and abs(bi.y1 - bj.y1) < 3
                            and bi.x0 < bj.x1 and bj.x0 < bi.x1):
                        has_later_dup = True
                        break
                if not has_later_dup:
                    deduped.append(line_i)
            lines = deduped

        self._text_edit_lines_cache[page_index] = lines
        return lines

    @staticmethod
    def _extract_line_text_from_chars(spans: list) -> str:
        """Reconstruct line text from per-character bounding boxes.

        Analyses the horizontal gap between consecutive glyphs to decide
        where a space character should be inserted.  This is far more
        accurate than get_text("text") or get_text("words") because it
        works directly with the glyph positions stored in the PDF.

        Algorithm:
        1. Collect all chars across spans in reading order.
        2. Compute a per-span *space threshold* = average char width × 0.35.
           (A gap wider than this is treated as a word separator.)
        3. Walk through chars; when the gap between the end of one char
           and the start of the next exceeds the threshold, emit a space.
        """
        if not spans:
            return ""

        # Flatten all chars with their span-level font size
        all_chars = []  # list of (char_dict, font_size)
        for span in spans:
            fs = span.get("size", 12)
            for ch in span.get("chars", []):
                all_chars.append((ch, fs))

        if not all_chars:
            # Fallback: rawdict might lack "chars" for some spans (e.g. Type3).
            # Concatenate span texts directly.
            return "".join(s.get("text", "") for s in spans)

        # Compute a robust space-threshold from average character width
        # across the whole line.
        widths = []
        for ch, _ in all_chars:
            cb = ch.get("bbox")
            if cb:
                w = cb[2] - cb[0]
                if w > 0:
                    widths.append(w)
        avg_char_w = (sum(widths) / len(widths)) if widths else 5.0
        space_threshold = avg_char_w * 0.35

        parts = []
        prev_x1 = None
        for ch, _fs in all_chars:
            c = ch.get("c", "")
            cb = ch.get("bbox")
            if not cb or not c:
                continue
            x0 = cb[0]
            if prev_x1 is not None:
                gap = x0 - prev_x1
                if gap > space_threshold:
                    parts.append(" ")
            parts.append(c)
            prev_x1 = cb[2]

        return "".join(parts).strip()

    def _handle_text_edit_hover(self, pos: QPointF):
        """Update hover highlight for text edit mode."""
        if not self._doc or not self._page_offsets:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        page_index = self.page_at_y(int(pos.y()))
        if page_index < 0 or page_index >= len(self._page_offsets):
            self._text_edit_hover_line = None
            self._text_edit_hover_page = -1
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()
            return

        page_pos = self._screen_to_page_coords(pos, page_index)
        lines = self._get_text_lines_for_page(page_index)

        found = None
        for line_info in lines:
            if line_info["bbox"].contains(fitz.Point(page_pos.x(), page_pos.y())):
                found = line_info
                break

        if found is not self._text_edit_hover_line or page_index != self._text_edit_hover_page:
            self._text_edit_hover_line = found
            self._text_edit_hover_page = page_index
            self.setCursor(Qt.CursorShape.IBeamCursor if found else Qt.CursorShape.ArrowCursor)
            self.update()

    def _handle_text_edit_click(self, pos: QPointF):
        """Handle click in text edit mode — start editing the clicked text line."""
        # Commit any existing edit first
        if self._text_edit_widget:
            self._commit_text_edit()

        if not self._doc or not self._page_offsets:
            return

        page_index = self.page_at_y(int(pos.y()))
        if page_index < 0 or page_index >= len(self._page_offsets):
            return

        page_pos = self._screen_to_page_coords(pos, page_index)
        lines = self._get_text_lines_for_page(page_index)

        for line_info in lines:
            if line_info["bbox"].contains(fitz.Point(page_pos.x(), page_pos.y())):
                self._begin_text_edit(line_info, page_index)
                return

    def _begin_text_edit(self, line_info: dict, page_index: int):
        """Show inline editor for a text line."""
        from PyQt6.QtWidgets import QLineEdit as _QLE

        if self._text_edit_widget:
            self._commit_text_edit()

        bbox = line_info["bbox"]
        py = self._page_offsets[page_index]
        px = self._page_x_offset(page_index)
        sr = fitz_rect_to_qrectf(bbox, px, py, self._zoom).toRect()
        # Expand slightly for comfortable editing
        sr = sr.adjusted(-4, -2, 4, 2)
        if sr.height() < 26:
            sr.setHeight(26)

        editor = _QLE(self)
        editor.setText(line_info["text"])
        editor.setGeometry(sr)

        # Match font size (scaled to screen)
        font_size = max(int(line_info["size"] * self._zoom * 0.75), 8)
        # Convert color integer to RGB
        color_int = line_info["color"]
        cr = (color_int >> 16) & 0xFF
        cg = (color_int >> 8) & 0xFF
        cb = color_int & 0xFF

        editor.setStyleSheet(
            f"QLineEdit {{ background: rgba(255,255,255,245); border: 2px solid #2979FF; "
            f"font-size: {font_size}pt; color: rgb({cr},{cg},{cb}); padding: 1px 3px; }}"
        )
        editor.show()
        editor.setFocus()
        editor.selectAll()

        self._text_edit_widget = editor
        self._text_edit_line_info = line_info
        self._text_edit_page = page_index

        # Enter commits
        editor.returnPressed.connect(self._commit_text_edit)

        # Escape cancels
        original_key_press = editor.keyPressEvent
        def _on_key_press(event):
            if event.key() == Qt.Key.Key_Escape:
                self._cancel_text_edit()
                return
            original_key_press(event)
        editor.keyPressEvent = _on_key_press

        # Focus-out commits
        _orig_focus_out = editor.focusOutEvent
        def _on_focus_out(event):
            _orig_focus_out(event)
            QTimer.singleShot(0, self._commit_text_edit)
        editor.focusOutEvent = _on_focus_out

    def _cancel_text_edit(self):
        """Cancel text editing without saving."""
        if not self._text_edit_widget:
            return
        widget = self._text_edit_widget
        self._text_edit_widget = None
        self._text_edit_line_info = None
        self._text_edit_page = -1
        widget.hide()
        widget.deleteLater()
        self.update()

    def _commit_text_edit(self):
        """Save the edited text back into the PDF page."""
        if not self._text_edit_widget:
            return

        widget = self._text_edit_widget
        line_info = self._text_edit_line_info
        page_index = self._text_edit_page

        # Clear state to prevent re-entry
        self._text_edit_widget = None
        self._text_edit_line_info = None
        self._text_edit_page = -1

        from PyQt6.QtWidgets import QLineEdit as _QLE
        if not isinstance(widget, _QLE) or not line_info:
            widget.hide()
            widget.deleteLater()
            return

        new_text = widget.text()
        old_text = line_info["text"]

        widget.hide()
        widget.deleteLater()

        if new_text == old_text or not new_text.strip():
            self.update()
            return

        if not self._doc or page_index >= self._doc.page_count:
            return

        # Extract formatting from the original line
        color_int = line_info["color"]
        r = ((color_int >> 16) & 0xFF) / 255.0
        g = ((color_int >> 8) & 0xFF) / 255.0
        b = (color_int & 0xFF) / 255.0
        font_size = line_info["size"]
        origin = line_info["origin"]
        bbox = line_info["bbox"]

        try:
            page = self._doc[page_index]

            # ── 폰트 결정 ────────────────────────────────────────
            # 1순위: PDF 내장 폰트 추출 → 원본과 동일한 폰트 재사용
            # 2순위: 시스템 폰트 파일 매핑 (폰트 이름/굵기 기반)
            # 3순위: PyMuPDF 내장 폰트 (fallback)
            font_kwargs = self._extract_embedded_font(page, line_info["font"])
            if font_kwargs is None:
                font_kwargs = self._map_to_fitz_font(line_info["font"], new_text)

            # ── 배경색 감지 ──────────────────────────────────────
            # bbox 중심 픽셀의 배경색을 샘플링하여 커버 색상으로 사용한다.
            # apply_redactions() 대신 draw_rect()를 쓰는 이유:
            #   apply_redactions()는 PDF 콘텐츠 스트림 전체를 재작성하여
            #   페이지의 모든 텍스트 좌표가 오른쪽으로 밀리는 버그를 유발한다.
            #   draw_rect()는 콘텐츠 스트림을 건드리지 않고 덮어씌우기만 하므로
            #   다른 텍스트 위치에 영향을 주지 않는다.
            bg_color = self._sample_background_color(page, bbox)

            # 1) 기존 텍스트 영역을 배경색 사각형으로 덮는다
            #    overlay=True: 기존 콘텐츠 위에 그린다 (텍스트가 가려짐)
            cover_rect = fitz.Rect(
                bbox.x0 - 1, bbox.y0 - 1,
                bbox.x1 + 1, bbox.y1 + 1,
            )
            page.draw_rect(cover_rect, color=None, fill=bg_color, overlay=True)

            # 2) 원래 baseline 위치에 새 텍스트 삽입
            #    first_char_x: 첫 글자의 시각적 x 위치 (폰트 bearing 무관)
            #    origin[0]: span의 text origin (폰트 bearing 포함, 교체 시 어긋남)
            #    render_mode=0: fill only (스트로크 없음 → 볼드/음영 방지)
            first_char_x = line_info.get("first_char_x")
            insert_x = first_char_x if first_char_x is not None else origin[0]
            insert_point = fitz.Point(insert_x, origin[1])
            page.insert_text(
                insert_point,
                new_text,
                fontsize=font_size,
                color=(r, g, b),
                render_mode=0,
                **font_kwargs,
            )
        except Exception as e:
            print(f"Text edit error: {e}")

        # 수정된 doc 상태를 bytes로 스냅샷 → RenderWorker가 최신 내용 렌더링
        self._snapshot_doc_bytes()

        # Invalidate caches so the page re-renders
        if page_index in self._text_edit_lines_cache:
            del self._text_edit_lines_cache[page_index]
        self._invalidate_page(page_index)
        self.doc_modified.emit()
        self.update()

    @staticmethod
    def _sample_background_color(page: fitz.Page, bbox: fitz.Rect) -> tuple[float, float, float]:
        """bbox 중심 픽셀을 렌더링해서 배경색(RGB 0.0~1.0)을 감지한다.

        대부분의 PDF는 흰 배경이므로 기본값은 (1, 1, 1).
        컬러 배경 PDF에서도 올바른 배경색으로 덮어씌울 수 있다.
        """
        try:
            cx = (bbox.x0 + bbox.x1) / 2
            cy = (bbox.y0 + bbox.y1) / 2
            # 1px × 1px 픽셀 샘플링 (텍스트 bbox 중앙, 텍스트 자체보다 bbox 상단 근처)
            sample_rect = fitz.Rect(cx - 1, bbox.y0 - 2, cx + 1, bbox.y0 - 0.5)
            pix = page.get_pixmap(matrix=fitz.Matrix(1, 1), clip=sample_rect, alpha=False)
            if pix.width > 0 and pix.height > 0:
                sample = pix.samples
                pr = sample[0] / 255.0
                pg = sample[1] / 255.0
                pb = sample[2] / 255.0
                return (pr, pg, pb)
        except Exception:
            pass
        return (1.0, 1.0, 1.0)

    @staticmethod
    def _map_to_fitz_font(original_font: str, text: str) -> dict:
        """Map a PDF font name to PyMuPDF font parameters.

        Returns a dict with 'fontname' and optionally 'fontfile' keys,
        suitable for passing as **kwargs to page.insert_text().

        NOTE: This function uses system font files (fontfile) for CJK text
        to ensure accurate glyph positioning when editing existing PDF text.
        Unlike _resolve_freetext_font (which uses built-in fonts for speed),
        text editing requires precise metrics to match the original layout.
        """
        import os

        # Check for CJK characters
        has_korean = False
        has_cjk = False
        for c in text:
            cp = ord(c)
            if 0xAC00 <= cp <= 0xD7AF or 0x3131 <= cp <= 0x318E:
                has_korean = True
                has_cjk = True
                break
            if cp > 0x2E7F:
                has_cjk = True

        if has_cjk:
            windir = os.environ.get("WINDIR", "C:\\Windows")
            fonts_dir = os.path.join(windir, "Fonts")
            lower = original_font.lower().replace("-", "").replace(" ", "").replace("_", "")
            is_bold = "bold" in lower or "heavy" in lower or "black" in lower
            is_light = "light" in lower or "thin" in lower or "semilight" in lower

            # Map original font family to system font files
            font_map = [
                ("malgun",  "malgun.ttf",  "malgunbd.ttf", "malgunsl.ttf"),
                ("gothic",  "malgun.ttf",  "malgunbd.ttf", "malgunsl.ttf"),
                ("gulim",   "gulim.ttc",   "gulim.ttc",    "gulim.ttc"),
                ("dotum",   "gulim.ttc",   "gulim.ttc",    "gulim.ttc"),
                ("batang",  "batang.ttc",  "batang.ttc",   "batang.ttc"),
                ("gungsuh", "batang.ttc",  "batang.ttc",   "batang.ttc"),
                ("myeongjo","batang.ttc",  "batang.ttc",   "batang.ttc"),
                ("nanum",   "NanumGothic.ttf", "NanumGothicBold.ttf", "NanumGothicLight.ttf"),
            ]

            matched = None
            for keyword, reg, bold, light in font_map:
                if keyword in lower:
                    if is_bold:
                        matched = bold
                    elif is_light:
                        matched = light
                    else:
                        matched = reg
                    break

            if matched:
                path = os.path.join(fonts_dir, matched)
                if os.path.exists(path):
                    return {"fontname": matched.split(".")[0], "fontfile": path}

            # Default: Malgun Gothic with weight matching
            if is_bold:
                default_file = "malgunbd.ttf"
            elif is_light:
                default_file = "malgunsl.ttf"
            else:
                default_file = "malgun.ttf"
            path = os.path.join(fonts_dir, default_file)
            if os.path.exists(path):
                return {"fontname": default_file.split(".")[0], "fontfile": path}
            path = os.path.join(fonts_dir, "malgun.ttf")
            if os.path.exists(path):
                return {"fontname": "malgun", "fontfile": path}

            # Fallback to built-in CJK
            if has_korean:
                return {"fontname": "korea"}
            return {"fontname": "china-s"}

        # Latin font mapping — use system font files for accurate rendering
        import os as _os
        lower = original_font.lower().replace("-", "").replace(" ", "").replace("_", "")
        is_bold = "bold" in lower or "heavy" in lower or "black" in lower
        is_italic = "italic" in lower or "oblique" in lower

        windir = _os.environ.get("WINDIR", "C:\\Windows")
        fonts_dir = _os.path.join(windir, "Fonts")

        # (keyword, regular, bold, italic, bolditalic)
        latin_font_map = [
            ("arial",      "arial.ttf",    "arialbd.ttf",   "ariali.ttf",    "arialbi.ttf"),
            ("helvetica",  "arial.ttf",    "arialbd.ttf",   "ariali.ttf",    "arialbi.ttf"),
            ("calibri",    "calibri.ttf",  "calibrib.ttf",  "calibrii.ttf",  "calibriz.ttf"),
            ("cambria",    "cambria.ttc",  "cambriab.ttf",  "cambriai.ttf",  "cambriaz.ttf"),
            ("times",      "times.ttf",    "timesbd.ttf",   "timesi.ttf",    "timesbi.ttf"),
            ("georgia",    "georgia.ttf",  "georgiab.ttf",  "georgiai.ttf",  "georgiaz.ttf"),
            ("verdana",    "verdana.ttf",  "verdanab.ttf",  "verdanai.ttf",  "verdanaz.ttf"),
            ("tahoma",     "tahoma.ttf",   "tahomabd.ttf",  "tahoma.ttf",    "tahomabd.ttf"),
            ("trebuchet",  "trebuc.ttf",   "trebucbd.ttf",  "trebucit.ttf",  "trebucbi.ttf"),
            ("segoeui",    "segoeui.ttf",  "segoeuib.ttf",  "segoeuii.ttf",  "segoeuiz.ttf"),
            ("segoe",      "segoeui.ttf",  "segoeuib.ttf",  "segoeuii.ttf",  "segoeuiz.ttf"),
            ("consola",    "consola.ttf",  "consolab.ttf",  "consolai.ttf",  "consolaz.ttf"),
            ("courier",    "cour.ttf",     "courbd.ttf",    "couri.ttf",     "courbi.ttf"),
            ("mono",       "consola.ttf",  "consolab.ttf",  "consolai.ttf",  "consolaz.ttf"),
            ("garamond",   "GARA.TTF",     "GARABD.TTF",    "GARAIT.TTF",    "GARABD.TTF"),
            ("bookantiqua","BKANT.TTF",    "ANTQUAB.TTF",   "ANTQUAI.TTF",   "ANTQUABI.TTF"),
        ]

        for keyword, reg, bold, italic, bolditalic in latin_font_map:
            if keyword in lower:
                if is_bold and is_italic:
                    chosen = bolditalic
                elif is_bold:
                    chosen = bold
                elif is_italic:
                    chosen = italic
                else:
                    chosen = reg
                path = _os.path.join(fonts_dir, chosen)
                if _os.path.exists(path):
                    return {"fontname": chosen.split(".")[0], "fontfile": path}
                # Try regular as fallback
                path = _os.path.join(fonts_dir, reg)
                if _os.path.exists(path):
                    return {"fontname": reg.split(".")[0], "fontfile": path}
                break

        # Fallback: try Arial as default system font
        fallback = "arialbd.ttf" if is_bold else "arial.ttf"
        path = _os.path.join(fonts_dir, fallback)
        if _os.path.exists(path):
            return {"fontname": fallback.split(".")[0], "fontfile": path}

        # Last resort: PyMuPDF built-in fonts
        if "courier" in lower or "mono" in lower or "consol" in lower:
            return {"fontname": "cour"}
        if "times" in lower or ("serif" in lower and "sans" not in lower):
            return {"fontname": "tiro"}
        return {"fontname": "helv"}

    # ── Embedded Font Extraction ─────────────

    _embedded_font_cache: dict = {}  # xref -> temp file path

    def _extract_embedded_font(self, page: fitz.Page, font_name: str) -> Optional[dict]:
        """PDF에 내장된 폰트를 추출하여 재사용한다.

        Returns dict with fontname/fontfile keys, or None if extraction fails.
        서브셋 폰트(이름에 '+' 포함)는 모든 글리프를 갖고 있지 않을 수 있으므로 건너뛴다.
        """
        import os as _os

        if not self._doc:
            return None

        try:
            fonts = page.get_fonts(full=True)
        except Exception:
            return None

        for xref, _ext, _ftype, fname, sname, _encoding in fonts:
            # fname 또는 sname이 원본 폰트 이름과 일치하는지 확인
            if font_name not in (fname, sname):
                continue

            # 서브셋 폰트 건너뛰기 (예: "ABCDEF+ArialMT")
            if "+" in fname:
                continue

            # 캐시 확인
            if xref in self._embedded_font_cache:
                cached = self._embedded_font_cache[xref]
                if _os.path.exists(cached):
                    return {"fontname": fname, "fontfile": cached}

            try:
                basename, ext, subtype, content = self._doc.extract_font(xref)
                if not content or len(content) < 100:
                    continue

                # 임시 파일로 저장
                import tempfile
                suffix = f".{ext}" if ext else ".ttf"
                tmp = tempfile.NamedTemporaryFile(
                    delete=False, suffix=suffix, prefix="pdfpro_font_"
                )
                tmp.write(content)
                tmp.close()
                self._embedded_font_cache[xref] = tmp.name
                return {"fontname": fname, "fontfile": tmp.name}
            except Exception:
                continue

        return None

    # ── Stamp Placement ───────────────────────

    def place_stamp_on_page(self, page_index: int, image_path: str, screen_pos: Optional[QPointF] = None):
        """Place an image stamp on the specified page."""
        if not self._doc or page_index >= self._doc.page_count:
            return

        page = self._doc[page_index]
        pr = page.rect
        stamp_w = pr.width * 0.15

        if screen_pos:
            page_pos = self._screen_to_page_coords(screen_pos, page_index)
            cx, cy = page_pos.x(), page_pos.y()
        else:
            cx, cy = pr.width / 2, pr.height / 2

        try:
            pix_img = QPixmap(image_path)
            if not pix_img.isNull():
                aspect = pix_img.width() / max(pix_img.height(), 1)
            else:
                aspect = 1.0
        except Exception:
            aspect = 1.0

        stamp_h = stamp_w / aspect
        rect = fitz.Rect(
            cx - stamp_w / 2, cy - stamp_h / 2,
            cx + stamp_w / 2, cy + stamp_h / 2,
        )

        from uuid import uuid4 as _uuid4
        stamp_id = str(_uuid4())
        self._overlay_stamps.append({
            "id": stamp_id,
            "page": page_index,
            "rect": rect,
            "path": image_path,
        })

        self._snapshot_doc_bytes()
        self.doc_modified.emit()
        self.update()

    # ── Context Menu ──────────────────────────

    def _show_context_menu(self, pos: QPointF, global_pos: QPoint):
        hit = self._hit_test_annot(pos)
        if not hit:
            return

        self._selected_page = hit.page_index
        menu = QMenu(self)

        if hit.match_type == "stamp":
            self._selected_annot = None
            for s in self._overlay_stamps:
                s["selected"] = False
            hit.annot["selected"] = True
            self.update()

            delete_action = menu.addAction("삭제")
            stamp_ref = hit.annot
            delete_action.triggered.connect(lambda: self._delete_stamp(stamp_ref))
        else:
            self._selected_annot = hit.annot
            self.update()

            annot_type = hit.annot.type[1] if hit.annot.type else ""
            if annot_type == "FreeText":
                edit_action = menu.addAction("수정")
                edit_action.triggered.connect(
                    lambda: self.annot_edit_requested.emit(hit.annot, hit.page_index)
                )
                menu.addSeparator()

            delete_action = menu.addAction("삭제")
            delete_action.triggered.connect(lambda: self._delete_annot(hit.annot, hit.page_index))

        menu.exec(global_pos)

    def _delete_stamp(self, stamp: dict):
        """Remove an overlay stamp."""
        if stamp in self._overlay_stamps:
            self._overlay_stamps.remove(stamp)
        self._selected_annot = None
        self._selected_page = -1
        self._snapshot_doc_bytes()
        self.doc_modified.emit()
        self.update()

    def _delete_annot(self, annot: fitz.Annot, page_index: int):
        if not self._doc:
            return
        page = self._doc[page_index]
        page.delete_annot(annot)
        self._selected_annot = None
        self._selected_page = -1
        self._invalidate_page(page_index)
        self._snapshot_doc_bytes()
        self.doc_modified.emit()
        self.update()

    def update_freetext_annot(self, annot: fitz.Annot, page_index: int, config: dict):
        """Replace an existing FreeText annotation with updated text/style."""
        if not self._doc:
            return
        page = self._doc[page_index]
        text = config.get("text", "")
        font_name = config.get("font_name", "Arial")
        font_size = float(config.get("font_size", 14))
        color = config.get("color", (0, 0, 0))
        font_kwargs = _resolve_freetext_font(text, font_name)
        rect = fitz.Rect(annot.rect)
        page.delete_annot(annot)
        new_annot = page.add_freetext_annot(
            rect=rect,
            text=text,
            fontsize=font_size,
            text_color=color,
            fill_color=None,
            border_color=None,
            **font_kwargs,
        )
        new_annot.update()
        self._annot_raw_text[new_annot.xref] = text
        self._selected_annot = new_annot
        self._selected_page = page_index
        self._invalidate_page(page_index)
        self._snapshot_doc_bytes()
        self.doc_modified.emit()
        self.update()

    # ── Search ────────────────────────────────

    def set_search_highlights(self, rects: list[tuple[int, fitz.Rect]], current_idx: int):
        self._search_rects = rects
        self._current_search_idx = current_idx
        self.update()

    def clear_search(self):
        self._search_rects.clear()
        self.update()

    # ── Navigation ────────────────────────────

    def scroll_to_page(self, page_index: int):
        """Request parent scroll area to scroll to this page."""
        if 0 <= page_index < len(self._page_offsets):
            y = self._page_offsets[page_index]
            parent = self.parentWidget()
            if parent:
                scroll_area = parent.parentWidget()
                from PyQt6.QtWidgets import QScrollArea
                if isinstance(scroll_area, QScrollArea):
                    scroll_area.verticalScrollBar().setValue(y)

    def visible_page(self) -> int:
        """Returns the page index currently most visible."""
        parent = self.parentWidget()
        if not parent:
            return 0
        scroll_area = parent.parentWidget()
        from PyQt6.QtWidgets import QScrollArea
        if isinstance(scroll_area, QScrollArea):
            scroll_y = scroll_area.verticalScrollBar().value()
            viewport_center = scroll_y + scroll_area.viewport().height() // 2
            return self.page_at_y(viewport_center)
        return 0

    # ── Overlay Stamp burn-in ─────────────────

    def burn_overlay_stamps(self):
        """Burn in-memory stamps into the PDF document."""
        if not self._doc:
            return
        for s in self._overlay_stamps:
            if s["page"] < self._doc.page_count:
                page = self._doc[s["page"]]
                try:
                    page.insert_image(s["rect"], filename=s["path"])
                except Exception:
                    pass
        self._overlay_stamps.clear()
        self._render_cache.clear()
        self.update()

    def invalidate_all_pages(self):
        self._render_cache.clear()
        self.update()


# ─────────────────────────────────────────────
# Scrollable PDF Container
# ─────────────────────────────────────────────

class PDFScrollView(QScrollArea):
    """A QScrollArea wrapping PDFViewWidget with scroll-to-page support."""

    page_changed = pyqtSignal(int)
    zoom_changed = pyqtSignal(float)
    doc_modified = pyqtSignal()
    annot_edit_requested = pyqtSignal(object, int)  # (annot, page_index)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pdfScrollArea")
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._pdf_widget = PDFViewWidget()
        self.setWidget(self._pdf_widget)

        self._pdf_widget.page_changed.connect(self.page_changed)
        self._pdf_widget.zoom_changed.connect(self.zoom_changed)
        self._pdf_widget.doc_modified.connect(self.doc_modified)
        self._pdf_widget.annot_edit_requested.connect(self.annot_edit_requested)
        self._pdf_widget.text_placed.connect(lambda: self.parent().window()._clear_right_panel() if self.parent() and hasattr(self.parent().window(), '_clear_right_panel') else None)

        # Track scroll to update current page
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

        self.setAcceptDrops(True)

    @property
    def pdf_widget(self) -> PDFViewWidget:
        return self._pdf_widget

    def set_document(self, doc, file_path: str = ""):
        self._pdf_widget.set_document(doc, file_path)

    def set_zoom(self, z: float):
        old_zoom = self._pdf_widget.zoom
        vbar = self.verticalScrollBar()
        hbar = self.horizontalScrollBar()
        old_vscroll = vbar.value()
        old_hscroll = hbar.value()
        vh = self.viewport().height()
        vw = self.viewport().width()

        self._pdf_widget.set_zoom(z)

        # Keep viewport center fixed after zoom from buttons/input.
        # (wheelEvent has its own anchor logic; this covers the toolbar path.)
        new_zoom = self._pdf_widget.zoom
        if old_zoom > 0 and abs(new_zoom - old_zoom) > 0.001:
            ratio = new_zoom / old_zoom
            new_vscroll = int((old_vscroll + vh / 2) * ratio - vh / 2)
            vbar.setValue(max(0, new_vscroll))
            # 가로: 페이지가 뷰포트보다 넓으면 페이지 중앙에 맞춤
            widget_w = self._pdf_widget.width()
            if widget_w > vw:
                hbar.setValue(max(0, (widget_w - vw) // 2))
            else:
                hbar.setValue(0)

    def scroll_to_page(self, page_index: int):
        y = self._pdf_widget.y_for_page(page_index)
        self.verticalScrollBar().setValue(y)

    def _on_scroll(self, value: int):
        visible = self._pdf_widget.visible_page()
        self.page_changed.emit(visible)
        # Pre-render pages about to scroll into view so they're cached before they appear
        self._pdf_widget._prerender_near_pages(visible)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                self.parent().window().load_file(path)
                break
