"""
models.py — Data models: PDFTab, StampManager, BookmarkManager
Windows version of PDFProTool (converted from Swift/macOS)
"""

import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from uuid import uuid4

import fitz  # PyMuPDF
from PyQt6.QtCore import QObject, pyqtSignal


# ─────────────────────────────────────────────
# PDF Tab Model
# ─────────────────────────────────────────────

class PDFTab:
    """Represents one open PDF tab (multi-tab support)."""

    def __init__(self):
        self.id: str = str(uuid4())
        self.document: Optional[fitz.Document] = None
        self.file_path: str = ""
        self.current_page: int = 0
        self.is_modified: bool = False

    @property
    def display_name(self) -> str:
        if not self.file_path:
            return "새 탭"
        return Path(self.file_path).stem

    def close(self):
        if self.document:
            self.document.close()
            self.document = None


# ─────────────────────────────────────────────
# Stamp Entry & Manager
# ─────────────────────────────────────────────

@dataclass
class StampEntry:
    id: str
    name: str
    path: str

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "path": self.path}

    @classmethod
    def from_dict(cls, d: dict) -> "StampEntry":
        return cls(id=d["id"], name=d["name"], path=d["path"])


class StampManager(QObject):
    stamps_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stamps: list[StampEntry] = []
        self._dir: Path = Path()
        self._meta_path: Path = Path()
        self._configure_paths()
        self._load()

    @staticmethod
    def config_dir() -> Path:
        """Returns the app config directory (Windows: %APPDATA%/PDFProTool)."""
        if os.name == "nt":
            base = Path(os.environ.get("APPDATA", Path.home())) / "PDFProTool"
        else:
            base = Path.home() / ".config" / "PDFProTool"
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _configure_paths(self):
        base = self.config_dir()
        self._dir = base / "stamps"
        self._meta_path = base / "stamps.json"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _load(self):
        if not self._meta_path.exists():
            self.stamps = []
            return
        try:
            data = json.loads(self._meta_path.read_text(encoding="utf-8"))
            self.stamps = [
                StampEntry.from_dict(d)
                for d in data
                if Path(d["path"]).exists()
            ]
        except Exception:
            self.stamps = []

    def _save(self):
        try:
            self._meta_path.write_text(
                json.dumps([s.to_dict() for s in self.stamps], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def add(self, src: str, name: str):
        src_path = Path(src)
        suffix = src_path.suffix if src_path.suffix else ""
        dest = self._dir / f"stamp_{int(time.time())}_{len(self.stamps)}{suffix}"
        shutil.copy2(src, dest)
        entry = StampEntry(id=str(uuid4()), name=name, path=str(dest))
        self.stamps.append(entry)
        self._save()
        self.stamps_changed.emit()

    def remove(self, index: int):
        if 0 <= index < len(self.stamps):
            try:
                Path(self.stamps[index].path).unlink()
            except Exception:
                pass
            self.stamps.pop(index)
            self._save()
            self.stamps_changed.emit()


# ─────────────────────────────────────────────
# Bookmark Manager
# ─────────────────────────────────────────────

class BookmarkManager(QObject):
    bookmarks_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: dict[str, list[int]] = {}
        self._path = StampManager.config_dir() / "bookmarks.json"
        self._load()

    def _load(self):
        if not self._path.exists():
            return
        try:
            self._data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            self._data = {}

    def _save(self):
        try:
            self._path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def toggle(self, file_path: str, page: int) -> bool:
        """Toggle bookmark. Returns True if added, False if removed."""
        if file_path not in self._data:
            self._data[file_path] = []
        pages = self._data[file_path]
        if page in pages:
            pages.remove(page)
            self._save()
            self.bookmarks_changed.emit()
            return False
        pages.append(page)
        pages.sort()
        self._save()
        self.bookmarks_changed.emit()
        return True

    def has(self, file_path: str, page: int) -> bool:
        return page in self._data.get(file_path, [])

    def pages(self, file_path: str) -> list[int]:
        return list(self._data.get(file_path, []))


# ─────────────────────────────────────────────
# In-memory Stamp Annotation (overlay, not PDF-native)
# ─────────────────────────────────────────────

@dataclass
class OverlayStamp:
    """An image stamp overlaid on a page (burned on save)."""
    id: str
    page_index: int
    rect: fitz.Rect   # in PDF page coordinates (top-left origin, Y down)
    image_path: str


class AnnotationOverlayManager:
    """Manages in-memory stamp overlays (burned into PDF on save)."""

    def __init__(self):
        self.stamps: list[OverlayStamp] = []

    def add_stamp(self, page_index: int, rect: fitz.Rect, image_path: str) -> OverlayStamp:
        stamp = OverlayStamp(
            id=str(uuid4()),
            page_index=page_index,
            rect=rect,
            image_path=image_path,
        )
        self.stamps.append(stamp)
        return stamp

    def remove_stamp(self, stamp_id: str):
        self.stamps = [s for s in self.stamps if s.id != stamp_id]

    def stamps_for_page(self, page_index: int) -> list[OverlayStamp]:
        return [s for s in self.stamps if s.page_index == page_index]

    def burn_into(self, doc: fitz.Document) -> fitz.Document:
        """Burn all overlay stamps into document pages and clear."""
        for stamp in self.stamps:
            if stamp.page_index < doc.page_count:
                page = doc[stamp.page_index]
                try:
                    page.insert_image(stamp.rect, filename=stamp.image_path)
                except Exception:
                    pass
        self.stamps.clear()
        return doc

    def clear(self):
        self.stamps.clear()
