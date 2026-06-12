@echo off
echo ============================================
echo   PO Scanner - Build App (fast)
echo ============================================
echo.

call venv\Scripts\activate.bat
pip install pyinstaller -q

echo Cleaning old build...
if exist dist\po_scanner rmdir /s /q dist\po_scanner
if exist build\po_scanner rmdir /s /q build\po_scanner
if exist build\settings   rmdir /s /q build\settings

echo Building po_scanner.exe + settings.exe...
pyinstaller po_scanner.spec --clean

echo.
if exist dist\po_scanner\po_scanner.exe (
    if exist dist\po_scanner\settings.exe (
        echo ============================================
        echo   Build SUCCESS!
        echo   dist\po_scanner\po_scanner.exe
        echo   dist\po_scanner\settings.exe
        echo ============================================
    ) else (
        echo [WARN] po_scanner.exe OK but settings.exe missing
    )
) else (
    echo ============================================
    echo   Build FAILED - check errors above
    echo ============================================
)

pause
