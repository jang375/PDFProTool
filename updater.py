"""
updater.py — GitHub Releases 기반 자동 업데이트
QThread로 백그라운드 다운로드, bat 스크립트로 exe 교체 후 재시작
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import subprocess
import tempfile
import zipfile
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from version import __version__

logger = logging.getLogger(__name__)

GITHUB_API_URL = "https://api.github.com/repos/jang375/PDFProTool/releases/latest"
SETTINGS_KEY_SKIPPED = "updater/skipped_version"


# ─────────────────────────────────────────────
# 버전 비교 유틸
# ─────────────────────────────────────────────

def _parse_version(v: str) -> tuple[int, ...]:
    """'v1.2.3' 또는 '1.2.3' → (1, 2, 3)"""
    return tuple(int(x) for x in v.lstrip("vV").split("."))


def is_newer(remote: str, local: str) -> bool:
    """remote 버전이 local보다 높으면 True"""
    try:
        return _parse_version(remote) > _parse_version(local)
    except (ValueError, TypeError):
        return False


# ─────────────────────────────────────────────
# 업데이트 확인 스레드
# ─────────────────────────────────────────────

class UpdateCheckWorker(QThread):
    """GitHub Releases API로 최신 버전 확인 (백그라운드)"""
    update_available = pyqtSignal(str, str, str)  # version, changelog, download_url
    no_update = pyqtSignal()
    error = pyqtSignal(str)

    def run(self):
        try:
            req = Request(GITHUB_API_URL, headers={"Accept": "application/vnd.github.v3+json"})
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            tag: str = data.get("tag_name", "")
            changelog: str = data.get("body", "") or "변경사항 없음"

            if not is_newer(tag, __version__):
                self.no_update.emit()
                return

            # 에셋 찾기 (.zip 우선, .exe 폴백)
            download_url = ""
            exe_url = ""
            for asset in data.get("assets", []):
                name: str = asset.get("name", "")
                url: str = asset.get("browser_download_url", "")
                if name.lower().endswith(".zip"):
                    download_url = url
                    break
                elif name.lower().endswith(".exe") and not exe_url:
                    exe_url = url
            if not download_url:
                download_url = exe_url

            if not download_url:
                self.error.emit("새 버전이 있지만 다운로드 가능한 파일을 찾을 수 없습니다.")
                return

            self.update_available.emit(tag, changelog, download_url)

        except URLError as e:
            self.error.emit(f"업데이트 서버 연결 실패: {e.reason}")
        except Exception as e:
            self.error.emit(f"업데이트 확인 오류: {e}")


# ─────────────────────────────────────────────
# 다운로드 스레드
# ─────────────────────────────────────────────

class DownloadWorker(QThread):
    """exe 파일을 백그라운드로 다운로드"""
    progress = pyqtSignal(int, int)  # downloaded_bytes, total_bytes
    finished = pyqtSignal(str)       # 저장된 파일 경로
    error = pyqtSignal(str)

    def __init__(self, url: str, dest_path: str):
        super().__init__()
        self._url = url
        self._dest_path = dest_path

    def run(self):
        try:
            req = Request(self._url)
            with urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 64 * 1024  # 64KB

                with open(self._dest_path, "wb") as f:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        self.progress.emit(downloaded, total)

            self.finished.emit(self._dest_path)
        except Exception as e:
            # 실패 시 불완전 파일 삭제
            try:
                if os.path.exists(self._dest_path):
                    os.remove(self._dest_path)
            except OSError:
                pass
            self.error.emit(f"다운로드 실패: {e}")


# ─────────────────────────────────────────────
# 업데이트 다이얼로그
# ─────────────────────────────────────────────

class UpdateDialog(QDialog):
    """새 버전 알림 + 다운로드 진행률 다이얼로그"""

    def __init__(
        self,
        version: str,
        changelog: str,
        download_url: str,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("업데이트 알림")
        self.setMinimumWidth(460)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._version = version
        self._download_url = download_url
        self._download_worker: Optional[DownloadWorker] = None
        self._downloaded_path: Optional[str] = None

        vl = QVBoxLayout(self)

        # 헤더
        header = QLabel(f"새 버전 {version} 이 출시되었습니다!")
        header.setStyleSheet("font-size: 14px; font-weight: bold;")
        vl.addWidget(header)

        current_lbl = QLabel(f"현재 버전: {__version__}")
        current_lbl.setStyleSheet("font-size: 12px; color: #666;")
        vl.addWidget(current_lbl)

        vl.addSpacing(8)

        # 변경사항
        changes_header = QLabel("변경사항:")
        changes_header.setStyleSheet("font-weight: bold;")
        vl.addWidget(changes_header)

        from PyQt6.QtWidgets import QTextEdit
        self._changelog_edit = QTextEdit()
        self._changelog_edit.setReadOnly(True)
        self._changelog_edit.setPlainText(changelog)
        self._changelog_edit.setMaximumHeight(200)
        vl.addWidget(self._changelog_edit)

        vl.addSpacing(8)

        # 진행률 바 (숨김 상태)
        self._progress_bar = QProgressBar()
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("%p% (%v / %m KB)")
        self._progress_bar.hide()
        vl.addWidget(self._progress_bar)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("font-size: 11px; color: #666;")
        self._status_label.hide()
        vl.addWidget(self._status_label)

        # 버튼
        btn_layout = QHBoxLayout()

        self._skip_btn = QPushButton("이 버전 건너뛰기")
        self._skip_btn.setStyleSheet("color: #888;")
        self._skip_btn.clicked.connect(self._on_skip)
        btn_layout.addWidget(self._skip_btn)

        btn_layout.addStretch()

        self._later_btn = QPushButton("나중에")
        self._later_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._later_btn)

        self._update_btn = QPushButton("업데이트")
        self._update_btn.setStyleSheet(
            "QPushButton { background: #2979FF; color: white; font-weight: bold; "
            "padding: 6px 20px; border-radius: 4px; border: none; }"
            "QPushButton:hover { background: #2262CC; }"
            "QPushButton:disabled { background: #ccc; color: #888; }"
        )
        self._update_btn.clicked.connect(self._on_update)
        btn_layout.addWidget(self._update_btn)

        vl.addLayout(btn_layout)

    def _on_skip(self):
        """이 버전을 건너뛰기 — QSettings에 기록"""
        settings = QSettings()
        settings.setValue(SETTINGS_KEY_SKIPPED, self._version)
        self.reject()

    def _on_update(self):
        """다운로드 시작"""
        self._update_btn.setEnabled(False)
        self._later_btn.setEnabled(False)
        self._skip_btn.setEnabled(False)
        self._progress_bar.show()
        self._status_label.show()
        self._status_label.setText("다운로드 중...")

        # 임시 경로에 다운로드 (URL 확장자에 맞춤)
        ext = ".zip" if self._download_url.lower().endswith(".zip") else ".exe"
        dest = os.path.join(tempfile.gettempdir(), f"PDFProTool_update_{self._version}{ext}")
        self._download_worker = DownloadWorker(self._download_url, dest)
        self._download_worker.progress.connect(self._on_progress)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.error.connect(self._on_download_error)
        self._download_worker.start()

    def _on_progress(self, downloaded: int, total: int):
        if total > 0:
            self._progress_bar.setMaximum(total // 1024)
            self._progress_bar.setValue(downloaded // 1024)
        else:
            # Content-Length 없는 경우 indeterminate
            self._progress_bar.setMaximum(0)

    def _on_download_finished(self, path: str):
        self._downloaded_path = path
        self._status_label.setText("다운로드 완료! 앱을 재시작합니다...")
        self._progress_bar.setValue(self._progress_bar.maximum())

        # bat 스크립트로 exe 교체 후 재시작
        _apply_update_and_restart(path)

    def _on_download_error(self, msg: str):
        self._status_label.setText(f"오류: {msg}")
        self._status_label.setStyleSheet("font-size: 11px; color: #FF3B30;")
        self._update_btn.setEnabled(True)
        self._later_btn.setEnabled(True)
        self._skip_btn.setEnabled(True)

    def closeEvent(self, event):
        # 다운로드 중 닫기 방지
        if self._download_worker and self._download_worker.isRunning():
            event.ignore()
            return
        super().closeEvent(event)


# ─────────────────────────────────────────────
# exe 교체 및 재시작 (bat 스크립트)
# ─────────────────────────────────────────────

def _apply_update_and_restart(downloaded_path: str):
    """
    실행 중인 exe는 자기 자신을 교체할 수 없으므로,
    bat 스크립트를 생성하여:
    1. 현재 프로세스 종료 대기
    2. 기존 앱 폴더(또는 exe)를 .old로 백업
    3. 새 파일을 원래 위치에 복사
    4. 앱 재시작
    5. bat 자기 삭제

    zip 파일인 경우 압축 해제 후 폴더 전체를 교체한다.
    """
    current_exe = sys.executable
    app_dir = os.path.dirname(current_exe)
    bat_path = os.path.join(tempfile.gettempdir(), "pdfprotool_update.bat")
    log_path = os.path.join(tempfile.gettempdir(), "pdfprotool_update.log")
    pid = os.getpid()

    if downloaded_path.lower().endswith(".zip"):
        # zip 압축 해제 → 임시 폴더
        extract_dir = os.path.join(tempfile.gettempdir(), "PDFProTool_update_extracted")
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir, ignore_errors=True)

        with zipfile.ZipFile(downloaded_path, "r") as zf:
            zf.extractall(extract_dir)

        # zip 내부에 단일 폴더(예: PDFProTool/)가 있으면 그 안의 내용을 사용
        entries = os.listdir(extract_dir)
        if len(entries) == 1 and os.path.isdir(os.path.join(extract_dir, entries[0])):
            source_dir = os.path.join(extract_dir, entries[0])
        else:
            source_dir = extract_dir

        old_dir = app_dir + ".old"

        bat_content = f"""@echo off
chcp 65001 >nul
set "LOG={log_path}"
echo [%date% %time%] 업데이트 시작 (zip 모드) >> "%LOG%"
echo [%date% %time%] PID={pid} exe="{current_exe}" >> "%LOG%"
echo [%date% %time%] source="{source_dir}" >> "%LOG%"

:: 프로세스 강제 종료 후 대기
taskkill /PID {pid} /F >nul 2>&1
timeout /t 3 /nobreak >nul

:: 프로세스 완전 종료 대기 (최대 15초)
set RETRY=0
:wait_loop
tasklist /FI "PID eq {pid}" 2>nul | find /I "{pid}" >nul
if not errorlevel 1 (
    set /a RETRY+=1
    if %RETRY% GEQ 15 (
        echo [%date% %time%] ERROR: 프로세스 종료 대기 타임아웃 >> "%LOG%"
        goto :cleanup_exit
    )
    timeout /t 1 /nobreak >nul
    goto wait_loop
)
echo [%date% %time%] 프로세스 종료 확인 >> "%LOG%"

:: 이전 .old 폴더가 남아있으면 삭제
if exist "{old_dir}" (
    rmdir /S /Q "{old_dir}" >nul 2>&1
    echo [%date% %time%] 이전 .old 폴더 삭제 >> "%LOG%"
)

:: 기존 앱 폴더를 .old로 이름 변경 (재시도 포함)
set RETRY=0
:move_old_loop
move /Y "{app_dir}" "{old_dir}" >nul 2>&1
if errorlevel 1 (
    set /a RETRY+=1
    if %RETRY% GEQ 5 (
        echo [%date% %time%] ERROR: 앱 폴더 이름 변경 실패 >> "%LOG%"
        goto :cleanup_exit
    )
    echo [%date% %time%] 앱 폴더 이름 변경 재시도 %RETRY% >> "%LOG%"
    timeout /t 2 /nobreak >nul
    goto move_old_loop
)
echo [%date% %time%] 앱 폴더 → .old 이동 완료 >> "%LOG%"

:: 새 폴더를 앱 위치로 이동
move /Y "{source_dir}" "{app_dir}" >nul 2>&1
if errorlevel 1 (
    echo [%date% %time%] ERROR: 새 폴더 이동 실패, 롤백 시도 >> "%LOG%"
    move /Y "{old_dir}" "{app_dir}" >nul 2>&1
    goto :cleanup_exit
)
echo [%date% %time%] 새 폴더 이동 완료 >> "%LOG%"

:: 재시작
echo [%date% %time%] 앱 재시작 >> "%LOG%"
start "" "{current_exe}"

:: 임시 파일 정리
if exist "{downloaded_path}" del /Q "{downloaded_path}" >nul 2>&1
if exist "{extract_dir}" rmdir /S /Q "{extract_dir}" >nul 2>&1
echo [%date% %time%] 업데이트 완료! >> "%LOG%"
goto :eof

:cleanup_exit
echo [%date% %time%] 업데이트 실패 — 앱을 수동으로 재시작하세요. >> "%LOG%"
:: 원본이 남아있으면 재시작 시도
if exist "{current_exe}" start "" "{current_exe}"

:eof
del "%~f0" >nul 2>&1
"""
    else:
        # 단일 exe 업데이트 (하위 호환)
        bat_content = f"""@echo off
chcp 65001 >nul
set "LOG={log_path}"
echo [%date% %time%] 업데이트 시작 (exe 모드) >> "%LOG%"
echo [%date% %time%] PID={pid} exe="{current_exe}" >> "%LOG%"
echo [%date% %time%] source="{downloaded_path}" >> "%LOG%"

:: 프로세스 강제 종료 후 대기
taskkill /PID {pid} /F >nul 2>&1
timeout /t 3 /nobreak >nul

:: 프로세스 완전 종료 대기 (최대 15초)
set RETRY=0
:wait_loop
tasklist /FI "PID eq {pid}" 2>nul | find /I "{pid}" >nul
if not errorlevel 1 (
    set /a RETRY+=1
    if %RETRY% GEQ 15 (
        echo [%date% %time%] ERROR: 프로세스 종료 대기 타임아웃 >> "%LOG%"
        goto :cleanup_exit
    )
    timeout /t 1 /nobreak >nul
    goto wait_loop
)
echo [%date% %time%] 프로세스 종료 확인 >> "%LOG%"

:: 기존 exe 백업 (재시도 포함)
set RETRY=0
:move_exe_loop
if exist "{current_exe}" (
    move /Y "{current_exe}" "{current_exe}.old" >nul 2>&1
    if errorlevel 1 (
        set /a RETRY+=1
        if %RETRY% GEQ 5 (
            echo [%date% %time%] ERROR: exe 백업 실패 >> "%LOG%"
            goto :cleanup_exit
        )
        echo [%date% %time%] exe 백업 재시도 %RETRY% >> "%LOG%"
        timeout /t 2 /nobreak >nul
        goto move_exe_loop
    )
)
echo [%date% %time%] exe 백업 완료 >> "%LOG%"

:: 새 exe 복사
copy /Y "{downloaded_path}" "{current_exe}" >nul 2>&1
if errorlevel 1 (
    echo [%date% %time%] ERROR: exe 복사 실패, 롤백 시도 >> "%LOG%"
    move /Y "{current_exe}.old" "{current_exe}" >nul 2>&1
    goto :cleanup_exit
)
echo [%date% %time%] exe 복사 완료 >> "%LOG%"

:: 재시작
echo [%date% %time%] 앱 재시작 >> "%LOG%"
start "" "{current_exe}"
echo [%date% %time%] 업데이트 완료! >> "%LOG%"
goto :eof

:cleanup_exit
echo [%date% %time%] 업데이트 실패 — 앱을 수동으로 재시작하세요. >> "%LOG%"
if exist "{current_exe}" start "" "{current_exe}"

:eof
del "%~f0" >nul 2>&1
"""

    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)

    logger.info(f"업데이트 bat 생성: {bat_path}")
    logger.info(f"업데이트 로그: {log_path}")

    # bat 실행 (현재 프로세스와 독립적으로)
    subprocess.Popen(
        ["cmd", "/c", bat_path],
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
        close_fds=True,
    )

    # 현재 앱 종료 — os._exit로 확실하게 프로세스 종료
    # app.quit()만 쓰면 Qt 이벤트 루프가 지연되어 exe 파일 잠금이 풀리지 않을 수 있음
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app:
        app.quit()
    # Qt가 즉시 종료하지 않을 수 있으므로 강제 종료
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(1000, lambda: os._exit(0))


# ─────────────────────────────────────────────
# .old 백업 파일 정리
# ─────────────────────────────────────────────

def cleanup_old_files():
    """이전 업데이트에서 남은 .old 백업 파일/폴더 삭제"""
    try:
        exe_path = sys.executable
        app_dir = os.path.dirname(exe_path)

        # 단일 exe .old 파일 정리
        old_exe = exe_path + ".old"
        if os.path.exists(old_exe):
            os.remove(old_exe)
            logger.info(f"이전 백업 파일 삭제: {old_exe}")

        # 폴더 .old 정리 (zip 업데이트 후 남은 이전 폴더)
        old_dir = app_dir + ".old"
        if os.path.isdir(old_dir):
            shutil.rmtree(old_dir, ignore_errors=True)
            logger.info(f"이전 백업 폴더 삭제: {old_dir}")
    except OSError as e:
        logger.warning(f".old 정리 실패: {e}")


# ─────────────────────────────────────────────
# 업데이트 체크 매니저
# ─────────────────────────────────────────────

class UpdateManager:
    """앱 시작 시 업데이트 확인을 관리하는 클래스"""

    def __init__(self, parent: Optional[QWidget] = None):
        self._parent = parent
        self._worker: Optional[UpdateCheckWorker] = None

    def check_for_updates(self):
        """백그라운드에서 업데이트 확인 시작"""
        self._worker = UpdateCheckWorker()
        self._worker.update_available.connect(self._on_update_available)
        self._worker.no_update.connect(self._on_no_update)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_update_available(self, version: str, changelog: str, download_url: str):
        """새 버전 발견 — 건너뛴 버전인지 확인 후 다이얼로그 표시"""
        settings = QSettings()
        skipped = settings.value(SETTINGS_KEY_SKIPPED, "", type=str)
        if skipped == version:
            logger.info(f"건너뛴 버전: {version}")
            return

        dlg = UpdateDialog(version, changelog, download_url, parent=self._parent)
        dlg.exec()

    def _on_no_update(self):
        logger.info("최신 버전입니다.")

    def _on_error(self, msg: str):
        logger.warning(f"업데이트 확인 실패: {msg}")
