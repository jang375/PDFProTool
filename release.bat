@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo   PDF Pro Tool - 릴리즈 자동화 스크립트
echo ============================================
echo.

:: ── 1. version.py에서 버전 읽기 (python import) ──
for /f %%a in ('python -c "import version; print(version.__version__)"') do set VERSION=%%a
if "%VERSION%"=="" (
    echo [오류] version.py에서 버전을 읽을 수 없습니다.
    pause
    exit /b 1
)
echo [1/6] 현재 버전: v%VERSION%
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
echo [2/6] Git 커밋 및 푸시...
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
echo [3/6] PyInstaller 빌드 중... (수 분 소요)
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
echo [4/6] dist\PDFProTool 폴더를 zip으로 압축 중...
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

:: ── 5. 업데이트 아티팩트(Manifest/Delta) 생성 ──
echo [5/6] 업데이트 아티팩트 생성 중...
set "MANIFEST_FILE=dist\app-update-manifest-v%VERSION%.json"
set "DELTA_FILE="
set "BASE_TAG="
set "BASE_VERSION="
set "BASE_ZIP="

for /f "tokens=1" %%a in ('gh release list --limit 1 2^>nul') do (
    if not defined BASE_TAG set BASE_TAG=%%a
)

if defined BASE_TAG (
    if /I not "!BASE_TAG!"=="v%VERSION%" (
        set "BASE_VERSION=!BASE_TAG:v=!"
        set "BASE_ZIP=dist\PDFProTool-v!BASE_VERSION!.zip"
        if exist "!BASE_ZIP!" del /Q "!BASE_ZIP!"
        echo       이전 릴리즈 감지: !BASE_TAG!
        gh release download "!BASE_TAG!" -p "PDFProTool-v!BASE_VERSION!.zip" -D dist >nul 2>&1
        if exist "!BASE_ZIP!" (
            python build_update_artifacts.py --current-dir "dist\PDFProTool" --target-version "%VERSION%" --output-dir "dist" --base-zip "!BASE_ZIP!" --base-version "!BASE_VERSION!"
            if errorlevel 1 (
                echo [오류] 업데이트 아티팩트 생성 실패.
                pause
                exit /b 1
            )
            if exist "dist\PDFProTool-delta-from-v!BASE_VERSION!-to-v%VERSION%.zip" (
                set "DELTA_FILE=dist\PDFProTool-delta-from-v!BASE_VERSION!-to-v%VERSION%.zip"
            )
        ) else (
            echo [경고] 이전 릴리즈 zip을 받지 못해 delta 생성을 건너뜁니다.
            python build_update_artifacts.py --current-dir "dist\PDFProTool" --target-version "%VERSION%" --output-dir "dist"
            if errorlevel 1 (
                echo [오류] Manifest 생성 실패.
                pause
                exit /b 1
            )
        )
    ) else (
        python build_update_artifacts.py --current-dir "dist\PDFProTool" --target-version "%VERSION%" --output-dir "dist"
        if errorlevel 1 (
            echo [오류] Manifest 생성 실패.
            pause
            exit /b 1
        )
    )
) else (
    echo [경고] 기존 릴리즈를 찾지 못해 delta 생성을 건너뜁니다.
    python build_update_artifacts.py --current-dir "dist\PDFProTool" --target-version "%VERSION%" --output-dir "dist"
    if errorlevel 1 (
        echo [오류] Manifest 생성 실패.
        pause
        exit /b 1
    )
)

if not exist "%MANIFEST_FILE%" (
    echo [오류] Manifest 파일을 찾을 수 없습니다: %MANIFEST_FILE%
    pause
    exit /b 1
)

echo       Manifest: %MANIFEST_FILE%
if defined DELTA_FILE (
    echo       Delta: !DELTA_FILE!
) else (
    echo       Delta: (없음)
)
echo.

:: ── 6. GitHub Release 생성 + 자산 업로드 ──
echo [6/6] GitHub Release v%VERSION% 생성 중...
if defined DELTA_FILE (
    gh release create "v%VERSION%" ^
        --title "v%VERSION%" ^
        --notes "PDF Pro Tool v%VERSION% 릴리즈" ^
        --latest ^
        "%ZIP_FILE%" ^
        "%MANIFEST_FILE%" ^
        "!DELTA_FILE!"
) else (
    gh release create "v%VERSION%" ^
        --title "v%VERSION%" ^
        --notes "PDF Pro Tool v%VERSION% 릴리즈" ^
        --latest ^
        "%ZIP_FILE%" ^
        "%MANIFEST_FILE%"
)

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
