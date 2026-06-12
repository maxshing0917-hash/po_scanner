@echo off
echo ============================================
echo   PO Scanner - Build OCR Runtime (slow)
echo ============================================
echo.

call venv\Scripts\activate.bat
pip install pyinstaller -q

echo Cleaning old build...
if exist dist\ocr_runtime rmdir /s /q dist\ocr_runtime
if exist build\ocr_core rmdir /s /q build\ocr_core

echo Building ocr_core.exe...
pyinstaller ocr_core.spec --clean

echo.
if exist dist\ocr_runtime\ocr_core.exe (
    echo ============================================
    echo   Build SUCCESS!
    echo   dist\ocr_runtime\ocr_core.exe
    echo ============================================
) else (
    echo ============================================
    echo   Build FAILED - check errors above
    echo ============================================
)

pause
