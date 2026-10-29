@echo off
REM Build AppLauncher-Setup.exe. Needs: pip install pyinstaller + Inno Setup (iscc on PATH).
cd /d "%~dp0\.."

pyinstaller --noconfirm --onefile --windowed --name AppLauncher --icon assets\app-launcher-icon.ico --add-data "assets\app-launcher-icon.ico;assets" --collect-all customtkinter main.py
if errorlevel 1 exit /b 1

REM iscc = Inno Setup compiler. Grab it from https://jrsoftware.org/isdl.php if missing.
set VER=
for /f "delims=" %%v in ('py -c "import version; print(version.VERSION)"') do set VER=%%v
if "%VER%"=="" (
    echo Could not read VERSION from version.py
    exit /b 1
)
iscc /DAppVersion=%VER% installer\app-launcher.iss
if errorlevel 1 exit /b 1

echo.
echo Done. Installer at: installer\Output\AppLauncher-Setup.exe
