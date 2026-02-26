"""
sidebar.py — Sidebar panel: Thumbnails, Bookmarks, Outline, Page Grid View
Windows version of PDFProTool (converted from SidebarView.swift)
"""

from __future__ import annotations

import os
import tempfile
from typing import Optional

import fitz  # PyMuPDF
from PyQt6.QtCore import Qt, QEvent, QItemSelectionModel, QMimeData, QPoint, QThread, QUrl, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QDrag, QIcon, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QFrame, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMenu, QPushButton, QSizePolicy,
    QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from models import BookmarkManager


# ─────────────────────────────────────────────
# Thumbnail rendering thread
# ─────────────────────────────────────────────

class ThumbnailWorker(QThread):
    """
    Single background thread that renders ALL page thumbnails sequentially.
    스레드 전용 fitz.Document 인스턴스를 사용하여 스레드 안전성 보장.
    """
    done = pyqtSignal(int, QImage)

    def __init__(self, file_path: str, page_indices: list, size: int = 120,
                 doc_bytes: Optional[bytes] = None):
        super().__init__()
        self._file_path = file_path
        self._doc_bytes = doc_bytes
        self.page_indices = list(page_indices)
        self.size = size
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        if not self._file_path and not self._doc_bytes:
            return
        doc = None
        try:
            if self._doc_bytes:
                doc = fitz.open(stream=self._doc_bytes, filetype="pdf")
            else:
                doc = fitz.open(self._file_path)
            for page_index in self.page_indices:
                if self._cancelled:
                    break
                try:
                    page = doc[page_index]
                    pr = page.rect
                    dpi_scale = self.size / max(pr.width, pr.height, 1)
                    mat = fitz.Matrix(dpi_scale, dpi_scale)
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
                    img = img.copy()  # Detach from fitz memory

                    img.setDevicePixelRatio(dpi_scale)
                    self.done.emit(page_index, img)
                    QThread.msleep(2)  # 2ms yield to prevent UI freeze
                except Exception:
                    self.done.emit(page_index, QImage())
        except Exception:
            pass
        finally:
            if doc:
                try:
                    doc.close()
                except Exception:
                    pass


# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

THUMB_W = 140
THUMB_H = 185

# Grid view (full-screen page overview)
GRID_VIEW_THUMB_W = 130
GRID_VIEW_THUMB_H = 170


# ─────────────────────────────────────────────
# Draggable Thumbnail List (supports drag-out & drop-in)
# ─────────────────────────────────────────────

class _DraggableThumbList(QListWidget):
    """QListWidget with drag-out (export selected pages as PDF)
    and drop-in (import external PDF at drop position)."""

    insert_pdf_at = pyqtSignal(str, int)  # (file_path, insert_before_index)
    delete_selected = pyqtSignal(list)     # selected page indices

    def __init__(self, parent=None):
        super().__init__(parent)
        # Disable ALL drag-drop on QListWidget — drag-out is manual
        # (mousePressEvent/mouseMoveEvent/startDrag), and drop-in is
        # handled by the parent ThumbnailPanel (plain QWidget) to avoid
        # QAbstractItemView's internal drag-drop rejection.
        self.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.setDragEnabled(False)
        self.setAcceptDrops(False)
        self.viewport().setAcceptDrops(False)
        self._drop_indicator_index: int = -1
        self._doc: Optional[fitz.Document] = None
        self._drag_start_pos: Optional[QPoint] = None

    def set_doc(self, doc: Optional[fitz.Document]):
        self._doc = doc

    # ── Mouse overrides: prevent rubber-band from stealing drag ──

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            item = self.itemAt(pos)
            has_modifier = event.modifiers() & (
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
            )
            if item and item.isSelected() and not has_modifier:
                # Pressing on an already-selected item without modifiers:
                # prepare for drag — do NOT call super (which starts rubber-band)
                self._drag_start_pos = pos
                return
        self._drag_start_pos = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._drag_start_pos is not None
                and event.buttons() & Qt.MouseButton.LeftButton):
            dist = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
            if dist >= QApplication.startDragDistance():
                self._drag_start_pos = None
                self.startDrag(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_start_pos is not None:
            # Click-and-release on a selected item without dragging:
            # treat as a normal click (select only this item)
            self._drag_start_pos = None
            pos = event.position().toPoint()
            item = self.itemAt(pos)
            if item:
                self.clearSelection()
                item.setSelected(True)
                self.setCurrentItem(item)
            return
        super().mouseReleaseEvent(event)

    # ── Keyboard: Delete key ──

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            selected_rows = sorted(set(idx.row() for idx in self.selectedIndexes()))
            if selected_rows:
                self.delete_selected.emit(selected_rows)
                return
        super().keyPressEvent(event)

    # ── Drag out: export selected pages as temporary PDF ──

    def startDrag(self, supportedActions):
        selected_rows = sorted(set(idx.row() for idx in self.selectedIndexes()))
        if not selected_rows or not self._doc:
            return

        try:
            new_doc = fitz.open()
            for row in selected_rows:
                if 0 <= row < self._doc.page_count:
                    new_doc.insert_pdf(self._doc, from_page=row, to_page=row)

            # Use original filename prefix if available, else default to "pdfpro_drag_"
            prefix = "pdfpro_drag_"
            if self._doc and self._doc.name:
                import os
                base_name = os.path.basename(self._doc.name)
                name_without_ext = os.path.splitext(base_name)[0]
                if name_without_ext:
                    safe_name = "".join(c for c in name_without_ext if c.isalnum() or c in (' ', '-', '_')).strip()
                    if safe_name:
                        prefix = safe_name + "_"

            tmp_dir = tempfile.mkdtemp(prefix="pdfpro_")
            tmp_path = os.path.join(tmp_dir, f"{prefix}pages_{len(selected_rows)}.pdf")
            new_doc.save(tmp_path, garbage=3, deflate=True)
            new_doc.close()
        except Exception as e:
            print(f"Drag export error: {e}")
            return

        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(tmp_path)])

        drag = QDrag(self)
        drag.setMimeData(mime)

        # Create drag preview pixmap
        first_item = self.item(selected_rows[0])
        if first_item:
            icon = first_item.icon()
            pm = icon.pixmap(64, 64)
            if not pm.isNull():
                if len(selected_rows) > 1:
                    # Draw count badge
                    badge_pm = QPixmap(pm.size())
                    badge_pm.fill(Qt.GlobalColor.transparent)
                    p = QPainter(badge_pm)
                    p.drawPixmap(0, 0, pm)
                    p.setBrush(QColor(41, 121, 255))
                    p.setPen(Qt.PenStyle.NoPen)
                    badge_size = 20
                    p.drawEllipse(pm.width() - badge_size - 2, 2, badge_size, badge_size)
                    p.setPen(QColor("white"))
                    p.drawText(pm.width() - badge_size - 2, 2, badge_size, badge_size,
                               Qt.AlignmentFlag.AlignCenter, str(len(selected_rows)))
                    p.end()
                    drag.setPixmap(badge_pm)
                else:
                    drag.setPixmap(pm)

        # Support Copy + Move for maximum compatibility with Explorer
        drag.exec(
            Qt.DropAction.CopyAction | Qt.DropAction.MoveAction,
            Qt.DropAction.CopyAction,
        )

    def paintEvent(self, event):
        super().paintEvent(event)

        if self._drop_indicator_index >= 0:
            p = QPainter(self.viewport())
            p.setPen(QPen(QColor(41, 121, 255), 3))

            if self._drop_indicator_index < self.count():
                item = self.item(self._drop_indicator_index)
                rect = self.visualItemRect(item)
                y = rect.top()
            else:
                if self.count() > 0:
                    last_item = self.item(self.count() - 1)
                    rect = self.visualItemRect(last_item)
                    y = rect.bottom() + 1
                else:
                    y = 5

            p.drawLine(5, y, self.viewport().width() - 5, y)

            # Draw small triangles at the ends
            p.setBrush(QColor(41, 121, 255))
            p.setPen(Qt.PenStyle.NoPen)
            from PyQt6.QtGui import QPolygon
            left_tri = QPolygon([
                QPoint(2, y - 5), QPoint(2, y + 5), QPoint(8, y)
            ])
            p.drawPolygon(left_tri)
            rw = self.viewport().width()
            right_tri = QPolygon([
                QPoint(rw - 2, y - 5), QPoint(rw - 2, y + 5), QPoint(rw - 8, y)
            ])
            p.drawPolygon(right_tri)
            p.end()


# ─────────────────────────────────────────────
# Thumbnail Panel (sidebar)
# ─────────────────────────────────────────────

class ThumbnailPanel(QWidget):
    """Shows page thumbnails using QListWidget for virtual scrolling.
    Supports multi-select, drag-out/drop-in, centered layout.
    """

    page_selected = pyqtSignal(int)
    delete_pages = pyqtSignal(list)
    rotate_pages = pyqtSignal(list)
    insert_pdf_at = pyqtSignal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Accept drops on this plain QWidget — bypasses QAbstractItemView
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._list = _DraggableThumbList()
        self._list.setViewMode(QListWidget.ViewMode.IconMode)
        self._list.setIconSize(QSize(THUMB_W, THUMB_H))
        self._list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._list.setMovement(QListWidget.Movement.Static)
        self._list.setSpacing(10)
        self._list.setUniformItemSizes(True)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setMinimumWidth(160)
        self._list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Multi-select with Ctrl+Click
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.currentRowChanged.connect(self._on_current_row_changed)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)
        self._list.insert_pdf_at.connect(self.insert_pdf_at)
        self._list.delete_selected.connect(self.delete_pages)
        self._list.setStyleSheet(
            "QListWidget { background: #fafafa; border: none; padding: 5px; }"
            "QListWidget::item { border-radius: 6px; }"
            "QListWidget::item:selected { background: rgba(41, 121, 255, 0.12); }"
        )
        layout.addWidget(self._list)

        self._doc: Optional[fitz.Document] = None
        self._file_path: str = ""
        self._current_page: int = 0
        self._bookmark_pages: set[int] = set()
        self._workers: list[ThumbnailWorker] = []

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_layout()

    def _update_layout(self):
        """Set grid size to center thumbnails within available width."""
        viewport_w = self._list.viewport().width()
        if viewport_w <= 0:
            viewport_w = self._list.width() - 2
        if viewport_w <= 0:
            return
        spacing = self._list.spacing()
        item_h = THUMB_H + 20 + spacing
        # Force single column, centered within viewport
        self._list.setGridSize(QSize(viewport_w, item_h))

    def load_document(self, doc: Optional[fitz.Document], bookmarks: set[int] = set(),
                      file_path: str = "", doc_bytes: Optional[bytes] = None):
        self._list.clear()
        self._list.set_doc(doc)

        for w in self._workers:
            w.cancel()
            w.quit()
            w.wait(1000)
        self._workers.clear()

        self._doc = doc
        self._file_path = file_path
        self._doc_bytes = doc_bytes
        self._bookmark_pages = bookmarks

        if not doc:
            return

        placeholder = QPixmap(THUMB_W, THUMB_H)
        placeholder.fill(QColor("white"))
        placeholder_icon = QIcon(placeholder)

        for i in range(doc.page_count):
            bm = "★ " if i in bookmarks else ""
            item = QListWidgetItem(placeholder_icon, f"{bm}{i + 1}")
            item.setSizeHint(QSize(THUMB_W, THUMB_H + 20))
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            self._list.addItem(item)

        if 0 <= self._current_page < self._list.count():
            self._list.setCurrentRow(self._current_page)

        self._update_layout()

        # Render from current page outward so visible thumbnails appear first
        center = max(0, min(self._current_page, doc.page_count - 1))
        indices = []
        for d in range(doc.page_count):
            for idx in (center + d, center - d):
                if 0 <= idx < doc.page_count and idx not in indices:
                    indices.append(idx)
            if len(indices) >= doc.page_count:
                break

        worker = ThumbnailWorker(self._file_path, indices, size=THUMB_W * 6,
                                 doc_bytes=self._doc_bytes)
        worker.done.connect(self._on_thumbnail_done)
        self._workers.append(worker)
        worker.start()

    def _on_thumbnail_done(self, page_index: int, image: QImage):
        if image.isNull() or page_index >= self._list.count():
            return
        pixmap = QPixmap.fromImage(image)
        screen = self.screen()
        dpr = screen.devicePixelRatio() if screen else 1.0
        target_w = int((THUMB_W - 4) * dpr)
        target_h = int((THUMB_H - 4) * dpr)
        scaled = pixmap.scaled(
            target_w, target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(dpr)
        self._list.item(page_index).setIcon(QIcon(scaled))

    def set_current_page(self, page: int):
        if self._current_page == page:
            return
        self._current_page = page
        if 0 <= page < self._list.count():
            self._list.blockSignals(True)
            # setCurrentRow는 기존 다중 선택을 해제하므로,
            # setCurrentItem + 선택 보존으로 대체
            item = self._list.item(page)
            if item:
                self._list.setCurrentItem(
                    item, QItemSelectionModel.SelectionFlag.Current
                )
                self._list.scrollToItem(item)
            self._list.blockSignals(False)

    # ── External PDF drop handling ──
    # Handled here (plain QWidget) instead of _DraggableThumbList
    # because QAbstractItemView's internal state machine rejects
    # external file drops in its viewport.

    def _has_pdf_urls(self, mime_data) -> bool:
        if not mime_data or not mime_data.hasUrls():
            return False
        return any(
            url.toLocalFile().lower().endswith(".pdf")
            for url in mime_data.urls()
        )

    def _list_pos_from_event(self, event):
        """Map event position from ThumbnailPanel coords to list viewport coords."""
        panel_pos = event.position().toPoint()
        return self._list.viewport().mapFrom(self, panel_pos)

    def dragEnterEvent(self, event):
        if self._has_pdf_urls(event.mimeData()):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if not self._has_pdf_urls(event.mimeData()):
            event.ignore()
            return

        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

        # Map position to list widget coordinates and update indicator
        list_pos = self._list_pos_from_event(event)
        item = self._list.itemAt(list_pos)
        if item:
            self._list._drop_indicator_index = self._list.row(item)
            item_rect = self._list.visualItemRect(item)
            if list_pos.y() > item_rect.center().y():
                self._list._drop_indicator_index += 1
        else:
            self._list._drop_indicator_index = self._list.count()
        self._list.viewport().update()

    def dragLeaveEvent(self, event):
        self._list._drop_indicator_index = -1
        self._list.viewport().update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._list._drop_indicator_index = -1
        self._list.viewport().update()

        if not self._has_pdf_urls(event.mimeData()):
            event.ignore()
            return

        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                list_pos = self._list_pos_from_event(event)
                item = self._list.itemAt(list_pos)
                if item:
                    insert_idx = self._list.row(item)
                    item_rect = self._list.visualItemRect(item)
                    if list_pos.y() > item_rect.center().y():
                        insert_idx += 1
                else:
                    insert_idx = self._list.count()
                self.insert_pdf_at.emit(path, insert_idx)
                event.accept()
                return

        event.ignore()

    def _on_item_clicked(self, item: QListWidgetItem):
        # Ctrl/Shift 클릭 시에는 페이지 이동하지 않음 (다중 선택 유지)
        modifiers = QApplication.keyboardModifiers()
        if modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            return
        row = self._list.row(item)
        self.page_selected.emit(row)

    def _on_current_row_changed(self, row: int):
        if row >= 0 and row != self._current_page:
            # 다중 선택 중이면 페이지 이동하지 않음
            if len(self._list.selectedIndexes()) > 1:
                return
            self.page_selected.emit(row)

    def _show_context_menu(self, pos):
        item = self._list.itemAt(pos)
        if not item:
            return

        selected_rows = sorted(set(idx.row() for idx in self._list.selectedIndexes()))
        if not selected_rows:
            selected_rows = [self._list.row(item)]

        menu = QMenu(self._list)
        if len(selected_rows) == 1:
            page = selected_rows[0]
            menu.addAction("삭제").triggered.connect(lambda: self.delete_pages.emit([page]))
            menu.addAction("회전").triggered.connect(lambda: self.rotate_pages.emit([page]))
        else:
            menu.addAction(f"{len(selected_rows)}페이지 삭제").triggered.connect(
                lambda: self.delete_pages.emit(selected_rows)
            )
            menu.addAction(f"{len(selected_rows)}페이지 회전").triggered.connect(
                lambda: self.rotate_pages.emit(selected_rows)
            )
        menu.exec(self._list.mapToGlobal(pos))

    def refresh_bookmarks(self, bookmarks: set[int]):
        self._bookmark_pages = bookmarks
        for i in range(self._list.count()):
            bm = "★ " if i in bookmarks else ""
            self._list.item(i).setText(f"{bm}{i + 1}")


# ─────────────────────────────────────────────
# Bookmarks Panel
# ─────────────────────────────────────────────

class BookmarksPanel(QWidget):
    page_selected = pyqtSignal(int)
    add_bookmark = pyqtSignal()  # request to bookmark current page
    remove_bookmark = pyqtSignal(int)  # request to remove bookmark for page

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header with "+" button
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        lbl = QLabel("북마크")
        lbl.setStyleSheet("font-size: 11px; color: #666;")
        header_layout.addWidget(lbl)
        header_layout.addStretch()
        add_btn = QPushButton("+")
        add_btn.setFixedSize(22, 22)
        add_btn.setToolTip("현재 페이지 북마크 추가/제거")
        add_btn.setStyleSheet(
            "QPushButton { padding: 0px; border: 1px solid #ccc; border-radius: 4px; "
            "font-size: 15px; font-weight: bold; color: #444; background: #f0f0f0; }"
            "QPushButton:hover { background: #e0e0e0; }"
        )
        add_btn.clicked.connect(self.add_bookmark.emit)
        header_layout.addWidget(add_btn)
        layout.addWidget(header)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #ddd;")
        layout.addWidget(line)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self._list, 1)  # stretch=1 → 남은 공간 전부 사용

        self._empty_label = QLabel("북마크 없음")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #999; font-size: 12px;")
        layout.addWidget(self._empty_label, 1)

        # 초기 상태: 리스트 숨기고 빈 라벨 표시
        self._list.hide()
        self._empty_label.show()

    def refresh(self, pages: list[int]):
        self._list.clear()
        if not pages:
            self._list.hide()
            self._empty_label.show()
            return
        self._empty_label.hide()
        self._list.show()
        for pg in pages:
            item = QListWidgetItem(f"★  Page {pg + 1}")
            item.setData(Qt.ItemDataRole.UserRole, pg)
            self._list.addItem(item)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        pg = item.data(Qt.ItemDataRole.UserRole)
        if pg is not None:
            self.page_selected.emit(pg)

    def _show_context_menu(self, pos):
        item = self._list.itemAt(pos)
        if not item:
            return
        pg = item.data(Qt.ItemDataRole.UserRole)
        if pg is None:
            return
        menu = QMenu(self._list)
        action = menu.addAction(f"Page {pg + 1} 북마크 제거")
        action.triggered.connect(lambda: self.remove_bookmark.emit(pg))
        menu.exec(self._list.mapToGlobal(pos))


# ─────────────────────────────────────────────
# Outline Panel
# ─────────────────────────────────────────────

class OutlinePanel(QWidget):
    page_selected = pyqtSignal(int)
    add_outline_entry = pyqtSignal()  # request to add current page to TOC
    remove_outline_entry = pyqtSignal(int, str)  # (page_0based, title)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        lbl = QLabel("목차")
        lbl.setStyleSheet("font-size: 11px; color: #666;")
        header_layout.addWidget(lbl)
        header_layout.addStretch()
        add_btn = QPushButton("+")
        add_btn.setFixedSize(22, 22)
        add_btn.setToolTip("현재 페이지를 목차에 추가")
        add_btn.setStyleSheet(
            "QPushButton { padding: 0px; border: 1px solid #ccc; border-radius: 4px; "
            "font-size: 15px; font-weight: bold; color: #444; background: #f0f0f0; }"
            "QPushButton:hover { background: #e0e0e0; }"
        )
        add_btn.clicked.connect(self.add_outline_entry.emit)
        header_layout.addWidget(add_btn)
        layout.addWidget(header)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #ddd;")
        layout.addWidget(line)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(16)
        self._tree.itemDoubleClicked.connect(self._on_item_activated)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self._tree, 1)

        self._empty_label = QLabel("목차 없음")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #999; font-size: 12px;")
        layout.addWidget(self._empty_label, 1)

        # 초기 상태: 트리 숨기고 빈 라벨 표시
        self._tree.hide()
        self._empty_label.show()

    def load_toc(self, doc: Optional[fitz.Document]):
        self._tree.clear()
        if not doc:
            self._tree.hide()
            self._empty_label.show()
            return

        toc = doc.get_toc()  # [[level, title, page_num], ...]
        if not toc:
            self._tree.hide()
            self._empty_label.show()
            return

        self._empty_label.hide()
        self._tree.show()

        stack: list[tuple[int, QTreeWidgetItem]] = []
        for level, title, page in toc:
            item = QTreeWidgetItem([title])
            item.setData(0, Qt.ItemDataRole.UserRole, page - 1)  # 0-based
            item.setToolTip(0, f"Page {page}")

            while stack and stack[-1][0] >= level:
                stack.pop()

            if stack:
                stack[-1][1].addChild(item)
            else:
                self._tree.addTopLevelItem(item)

            stack.append((level, item))

        self._tree.expandAll()

    def _on_item_activated(self, item: QTreeWidgetItem, _column: int):
        page = item.data(0, Qt.ItemDataRole.UserRole)
        if page is not None:
            self.page_selected.emit(page)

    def _show_context_menu(self, pos):
        item = self._tree.itemAt(pos)
        if not item:
            return
        page = item.data(0, Qt.ItemDataRole.UserRole)
        title = item.text(0)
        if page is None:
            return
        menu = QMenu(self._tree)
        action = menu.addAction(f"'{title}' 목차 제거")
        action.triggered.connect(lambda: self.remove_outline_entry.emit(page, title))
        menu.exec(self._tree.mapToGlobal(pos))


# ─────────────────────────────────────────────
# Main Sidebar Widget
# ─────────────────────────────────────────────

class SidebarWidget(QWidget):
    """Sidebar with tabs: Thumbnails | Bookmarks | Outline"""

    page_selected = pyqtSignal(int)
    delete_pages = pyqtSignal(list)
    rotate_pages = pyqtSignal(list)
    insert_pdf_at = pyqtSignal(str, int)
    add_bookmark = pyqtSignal()
    remove_bookmark = pyqtSignal(int)       # page (0-based)
    add_outline_entry = pyqtSignal()
    remove_outline_entry = pyqtSignal(int, str)  # (page_0based, title)

    def __init__(self, bookmark_mgr: BookmarkManager, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(160)
        self.setMaximumWidth(220)
        self._bookmark_mgr = bookmark_mgr
        self._file_path: str = ""
        self._doc: Optional[fitz.Document] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setTabPosition(QTabWidget.TabPosition.North)
        self._tabs.setDocumentMode(True)

        self._thumb_panel = ThumbnailPanel()
        self._thumb_panel.page_selected.connect(self.page_selected)
        self._thumb_panel.delete_pages.connect(self.delete_pages)
        self._thumb_panel.rotate_pages.connect(self.rotate_pages)
        self._thumb_panel.insert_pdf_at.connect(self.insert_pdf_at)

        self._bm_panel = BookmarksPanel()
        self._bm_panel.page_selected.connect(self.page_selected)
        self._bm_panel.add_bookmark.connect(self.add_bookmark)
        self._bm_panel.remove_bookmark.connect(self.remove_bookmark)

        self._outline_panel = OutlinePanel()
        self._outline_panel.page_selected.connect(self.page_selected)
        self._outline_panel.add_outline_entry.connect(self.add_outline_entry)
        self._outline_panel.remove_outline_entry.connect(self.remove_outline_entry)

        self._tabs.addTab(self._thumb_panel, "썸네일")
        self._tabs.addTab(self._bm_panel, "북마크")
        self._tabs.addTab(self._outline_panel, "목차")

        layout.addWidget(self._tabs)

        self._bookmark_mgr.bookmarks_changed.connect(self._refresh_bookmarks)

    def load_document(self, doc: Optional[fitz.Document], file_path: str = "",
                      doc_bytes: Optional[bytes] = None):
        self._doc = doc
        self._file_path = file_path
        self._doc_bytes = doc_bytes
        bookmarks_set = set(self._bookmark_mgr.pages(file_path))
        self._thumb_panel.load_document(doc, bookmarks_set, file_path=file_path,
                                        doc_bytes=doc_bytes)
        self._bm_panel.refresh(self._bookmark_mgr.pages(file_path))
        self._outline_panel.load_toc(doc)

    def set_current_page(self, page: int):
        self._thumb_panel.set_current_page(page)

    def _refresh_bookmarks(self):
        if self._file_path:
            pages = self._bookmark_mgr.pages(self._file_path)
            self._bm_panel.refresh(pages)
            self._thumb_panel.refresh_bookmarks(set(pages))

    def reload_thumbnails(self, doc_bytes: Optional[bytes] = None):
        """Reload thumbnails after page structure changes."""
        if self._doc:
            if doc_bytes is not None:
                self._doc_bytes = doc_bytes
            bookmarks_set = set(self._bookmark_mgr.pages(self._file_path))
            self._thumb_panel.load_document(self._doc, bookmarks_set,
                                            file_path=self._file_path,
                                            doc_bytes=self._doc_bytes)


# ─────────────────────────────────────────────
# Page Grid View (full-screen page overview)
# ─────────────────────────────────────────────

class PageGridView(QWidget):
    """Full-screen grid view showing all pages as thumbnails.
    Double-click a page to navigate there and close the grid view.
    """

    page_selected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._list = QListWidget()
        self._list.setViewMode(QListWidget.ViewMode.IconMode)
        self._list.setIconSize(QSize(GRID_VIEW_THUMB_W, GRID_VIEW_THUMB_H))
        self._list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._list.setMovement(QListWidget.Movement.Static)
        self._list.setSpacing(14)
        self._list.setUniformItemSizes(True)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.itemDoubleClicked.connect(self._on_double_clicked)
        self._list.setStyleSheet(
            "QListWidget { background: #f0f0f0; border: none; padding: 10px; }"
            "QListWidget::item { border-radius: 6px; }"
            "QListWidget::item:selected { background: rgba(41, 121, 255, 0.15); }"
        )
        layout.addWidget(self._list)

        self._doc: Optional[fitz.Document] = None
        self._file_path: str = ""
        self._workers: list[ThumbnailWorker] = []

    def load_document(self, doc: Optional[fitz.Document], current_page: int = 0,
                      file_path: str = "", doc_bytes: Optional[bytes] = None):
        self._list.clear()

        for w in self._workers:
            w.cancel()
            w.quit()
            w.wait(1000)
        self._workers.clear()

        self._doc = doc
        self._file_path = file_path
        self._doc_bytes = doc_bytes
        if not doc:
            return

        placeholder = QPixmap(GRID_VIEW_THUMB_W, GRID_VIEW_THUMB_H)
        placeholder.fill(QColor("white"))
        placeholder_icon = QIcon(placeholder)

        for i in range(doc.page_count):
            item = QListWidgetItem(placeholder_icon, str(i + 1))
            item.setSizeHint(QSize(GRID_VIEW_THUMB_W + 10, GRID_VIEW_THUMB_H + 24))
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            self._list.addItem(item)

        if 0 <= current_page < self._list.count():
            self._list.setCurrentRow(current_page)
            self._list.scrollToItem(self._list.item(current_page))

        worker = ThumbnailWorker(self._file_path, list(range(doc.page_count)),
                                 size=GRID_VIEW_THUMB_W * 2, doc_bytes=self._doc_bytes)
        worker.done.connect(self._on_thumbnail_done)
        self._workers.append(worker)
        worker.start()

    def _on_thumbnail_done(self, page_index: int, image: QImage):
        if image.isNull() or page_index >= self._list.count():
            return
        pixmap = QPixmap.fromImage(image)
        screen = self.screen()
        dpr = screen.devicePixelRatio() if screen else 1.0
        target_w = int(GRID_VIEW_THUMB_W * dpr)
        target_h = int(GRID_VIEW_THUMB_H * dpr)
        scaled = pixmap.scaled(
            target_w, target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(dpr)
        self._list.item(page_index).setIcon(QIcon(scaled))

    def _on_double_clicked(self, item: QListWidgetItem):
        row = self._list.row(item)
        self.page_selected.emit(row)

    def cleanup(self):
        for w in self._workers:
            w.cancel()
            w.quit()
            w.wait(1000)
        self._workers.clear()
