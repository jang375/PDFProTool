"""
ocr_manager.py — OCR using EasyOCR (replaces Apple Vision framework on macOS)
Supports Korean+English, English only, Japanese+English, Chinese+English.
Runs OCR in a background QThread to avoid blocking the UI.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Optional

import fitz  # PyMuPDF
from PyQt6.QtCore import QThread, pyqtSignal


# Store OCR models in user profile so first download is reused forever.
DEFAULT_OCR_MODEL_DIR = os.path.join(os.path.expanduser("~"), ".PDFProTool", "easyocr", "model")


# ─────────────────────────────────────────────
# Language Enum
# ─────────────────────────────────────────────

class OCRLanguage(Enum):
    KOREAN_ENGLISH = ("한국어+영어", ["ko", "en"])
    ENGLISH = ("영어", ["en"])
    JAPANESE_ENGLISH = ("일본어+영어", ["ja", "en"])
    CHINESE_ENGLISH = ("중국어+영어", ["ch_sim", "en"])

    def __init__(self, label: str, lang_codes: list[str]):
        self.label = label
        self.lang_codes = lang_codes

    def __str__(self):
        return self.label

    @classmethod
    def all_cases(cls) -> list["OCRLanguage"]:
        return list(cls)


# ─────────────────────────────────────────────
# OCR Worker Thread
# ─────────────────────────────────────────────

class OCRWorker(QThread):
    """Runs EasyOCR in a background thread."""

    # Emits (current_page, total_pages)
    progress = pyqtSignal(int, int)
    # Emits status text for UI
    status = pyqtSignal(str)
    # Emits (page_index, recognized_text)
    page_done = pyqtSignal(int, str)
    # Emits (total_char_count, doc_bytes) on completion
    finished_ocr = pyqtSignal(int, bytes)
    # Emits error message on failure
    error = pyqtSignal(str)

    def __init__(
        self,
        file_path: str,
        language: OCRLanguage,
        model_dir: str = DEFAULT_OCR_MODEL_DIR,
        parent=None,
    ):
        super().__init__(parent)
        self._file_path = file_path
        self.language = language
        self._model_dir = model_dir
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self._run_ocr()
        except Exception as e:
            self.error.emit(str(e))

    @staticmethod
    def _has_any_model_file(model_dir: str) -> bool:
        if not os.path.isdir(model_dir):
            return False
        for name in os.listdir(model_dir):
            p = os.path.join(model_dir, name)
            if os.path.isfile(p) and name.lower().endswith((".pth", ".onnx")):
                return True
        return False

    def _run_ocr(self):
        # Lazy-import easyocr (slow to import, so do it here in the thread)
        try:
            import easyocr
        except ImportError:
            self.error.emit(
                "easyocr가 설치되지 않았습니다.\n"
                "pip install easyocr --break-system-packages\n"
                "명령어로 설치해주세요."
            )
            return

        os.makedirs(self._model_dir, exist_ok=True)
        had_model_before = self._has_any_model_file(self._model_dir)

        # Reader() downloads missing models on first run.
        if not had_model_before:
            self.status.emit("OCR 모델 다운로드 중... (최초 1회)")
        else:
            self.status.emit("OCR 엔진 준비 중...")

        try:
            reader = easyocr.Reader(
                self.language.lang_codes,
                gpu=False,
                verbose=False,
                model_storage_directory=self._model_dir,
                download_enabled=True,
            )
        except Exception as e:
            if not had_model_before:
                self.error.emit(
                    "OCR 모델 다운로드/초기화에 실패했습니다.\n"
                    f"모델 경로: {self._model_dir}\n"
                    f"오류: {e}"
                )
            else:
                self.error.emit(f"OCR 초기화 실패: {e}")
            return

        if not had_model_before and self._has_any_model_file(self._model_dir):
            self.status.emit("OCR 모델 다운로드 완료")

        # Open a worker-private document instance to avoid threading conflicts
        doc = fitz.open(self._file_path)
        try:
            page_count = doc.page_count
            total_chars = 0

            for i in range(page_count):
                if self._cancelled:
                    break

                self.progress.emit(i + 1, page_count)
                page = doc[i]

                # Check if page already has extractable text
                existing_text = page.get_text("text").strip()
                if existing_text:
                    self.page_done.emit(i, existing_text)
                    total_chars += len(existing_text)
                    continue

                # Render page to image for OCR
                try:
                    text = self._ocr_page(reader, page)
                    self.page_done.emit(i, text)
                    total_chars += len(text)
                except Exception:
                    self.page_done.emit(i, "")

            # OCR 텍스트가 삽입된 doc을 bytes로 직렬화하여 메인 스레드에 전달
            doc_bytes = doc.tobytes()
            self.finished_ocr.emit(total_chars, doc_bytes)
        finally:
            doc.close()

    def _get_font(self) -> "fitz.Font":
        """Return a font that supports the OCR language glyphs."""
        if self.language == OCRLanguage.KOREAN_ENGLISH:
            return fitz.Font("korea")
        if self.language == OCRLanguage.JAPANESE_ENGLISH:
            return fitz.Font("japan")
        if self.language == OCRLanguage.CHINESE_ENGLISH:
            return fitz.Font("china-s")
        return fitz.Font("helv")

    def _ocr_page(self, reader, page: fitz.Page) -> str:
        """Render a page to image, run EasyOCR, and insert invisible text layer."""
        scale = 3.0
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_bytes = pix.tobytes("png")

        # detail=1 returns bounding boxes: [([[x1,y1],...,[x4,y4]], text, conf), ...]
        results = reader.readtext(img_bytes, detail=1, paragraph=False)

        texts = []
        tw = fitz.TextWriter(page.rect)
        font = self._get_font()

        for bbox, text, _conf in results:
            text = text.strip()
            if not text:
                continue
            texts.append(text)

            # Convert image coords (at 3x scale) → PDF page coords
            x0 = bbox[0][0] / scale
            y0 = bbox[0][1] / scale
            y1 = bbox[2][1] / scale
            fontsize = max((y1 - y0) * 0.8, 4)

            try:
                tw.append(fitz.Point(x0, y1), text, font=font, fontsize=fontsize)
            except Exception:
                pass

        # render_mode=3 → invisible text (searchable but not visible)
        try:
            tw.write_text(page, render_mode=3)
        except Exception:
            pass

        return "\n".join(texts)


# ─────────────────────────────────────────────
# OCR Manager (thin wrapper around OCRWorker)
# ─────────────────────────────────────────────

class OCRManager:
    """
    High-level OCR manager.
    Usage:
        mgr = OCRManager()
        worker = mgr.start(doc, language)
        worker.progress.connect(...)
        worker.finished_ocr.connect(...)
    """

    def __init__(self, model_dir: str = DEFAULT_OCR_MODEL_DIR):
        self._current_worker: Optional[OCRWorker] = None
        self._model_dir = model_dir

    def start(self, file_path: str, language: OCRLanguage) -> OCRWorker:
        """Cancel any running OCR and start a new one. Returns the worker."""
        if self._current_worker and self._current_worker.isRunning():
            self._current_worker.cancel()
            self._current_worker.wait(msecs=2000)

        worker = OCRWorker(file_path, language, model_dir=self._model_dir)
        self._current_worker = worker
        worker.start()
        return worker

    def cancel(self):
        if self._current_worker and self._current_worker.isRunning():
            self._current_worker.cancel()
            self._current_worker.wait(msecs=2000)
