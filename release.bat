@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo   PDF Pro Tool - 릴리즈 자동화 스크립트
echo ============================================
echo.

:: ── 1. version.py에서 버전 읽기 ──
for /f "tokens=2 delims='" %%a in ('findstr "__version__" version.py') do set VERSION=%%a
if "%VERSION%"=="" (
    echo [오류] version.py에서 버전을 읽을 수 없습니다.
    pause
    exit /b 1
)
echo [1/5] 현재 버전: v%VERSION%
echo.

:: 태그 중복 확인
git tag -l "v%VERSION%" | findstr "v%VERSION%" >nul 2>&1
if not errorlevel 1 (
    echo [오류] 태그 v%VERSION%이 이미 존재합니다.
    echo       version.py의 버전을 올려주세요.
    pause
    exit /b 1
)

:: ── 2. Git commit + push ──
echo [2/5] Git 커밋 및 푸시...
git add .
git commit -m "release: v%VERSION%"
if errorlevel 1 (
    echo [경고] 커밋할 변경사항이 없거나 커밋 실패. 계속 진행합니다.
)
git push origin main
if errorlevel 1 (
    echo [오류] git push 실패.
    pause
    exit /b 1
)
echo       완료.
echo.

:: ── 3. PyInstaller 빌드 ──
echo [3/5] PyInstaller 빌드 중... (수 분 소요)
pyinstaller PDFProTool.spec --noconfirm >nul 2>&1
if errorlevel 1 (
    echo [오류] PyInstaller 빌드 실패.
    pause
    exit /b 1
)
if not exist "dist\PDFProTool\PDFProTool.exe" (
    echo [오류] 빌드 결과물을 찾을 수 없습니다.
    pause
    exit /b 1
)
for %%F in (dist\PDFProTool\PDFProTool.exe) do set EXE_SIZE=%%~zF
set /a EXE_MB=!EXE_SIZE! / 1048576
echo       빌드 완료 (PDFProTool.exe: !EXE_MB!MB)
echo.

:: ── 4. dist 폴더를 zip으로 압축 ──
echo [4/5] dist\PDFProTool 폴더를 zip으로 압축 중...
set "ZIP_FILE=dist\PDFProTool-v%VERSION%.zip"
if exist "%ZIP_FILE%" del /Q "%ZIP_FILE%"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\PDFProTool' -DestinationPath '%ZIP_FILE%' -Force"
if errorlevel 1 (
    echo [오류] zip 압축 실패.
    pause
    exit /b 1
)
for %%F in ("%ZIP_FILE%") do set ZIP_SIZE=%%~zF
set /a ZIP_MB=!ZIP_SIZE! / 1048576
echo       압축 완료 (%ZIP_FILE%: !ZIP_MB!MB)
echo.

:: ── 5. GitHub Release 생성 + zip 업로드 ──
echo [5/5] GitHub Release v%VERSION% 생성 중...
gh release create "v%VERSION%" ^
    --title "v%VERSION%" ^
    --notes "PDF Pro Tool v%VERSION% 릴리즈" ^
    "%ZIP_FILE%"
if errorlevel 1 (
    echo [오류] Release 생성 실패. gh auth 상태를 확인하세요.
    pause
    exit /b 1
)
echo.
echo ============================================
echo   릴리즈 완료: v%VERSION%
echo   https://github.com/jang375/PDFProTool/releases/tag/v%VERSION%
echo ============================================
pause
