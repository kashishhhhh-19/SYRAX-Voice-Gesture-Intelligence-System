@echo off
setlocal EnableDelayedExpansion

echo ==============================================================
echo    ____  __  ______  ___   _  __
echo   / __ \/ / / / __ \/   ^| ^| ^|/ /   S Y R A X
echo  / /_/ / / / / /_/ / /^| ^| ^|   /    "Speak. Gesture. Control."
echo / ____/ /_/ / _, _/ ___ ^|/   ^|     Voice ^& Gesture Intelligence
echo /_/    \____/_/ ^|_/_/  ^|_/_/^|_^|     System for Windows 10/11
echo ==============================================================
echo.

:: 1. Check Python Installation
echo [*] Checking Python installation...
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in your PATH.
    echo Please install Python 3.10+ from https://www.python.org/
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do set PYTHON_VER=%%i
echo [+] Found %PYTHON_VER%

:: 2. Create and Activate Virtual Environment (.venv)
if not exist ".venv" (
    echo [*] Creating virtual environment (.venv)...
    python -m venv .venv
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [+] Virtual environment created.
) else (
    echo [+] Existing virtual environment (.venv) detected.
)

echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

:: 3. Upgrade pip
echo [*] Upgrading pip...
python -m pip install --upgrade pip >nul 2>&1

:: 4. PyAudio-First Installation (CRITICAL STEP FOR WINDOWS)
echo.
echo ==============================================================
echo [STEP 1/3] Installing PyAudio (Primary Audio Capture Engine)...
echo ==============================================================
python -m pip install pyaudio
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Direct 'pip install pyaudio' failed (common on Windows without C++ compiler).
    echo [*] Attempting fallback via pipwin...
    python -m pip install pipwin
    pipwin install pyaudio
    if !ERRORLEVEL! NEQ 0 (
        echo.
        echo [NOTICE] PyAudio binary could not be built automatically.
        echo [NOTICE] NO WORRIES: SYRAX includes an automatic built-in fallback
        echo          to sounddevice, which will capture microphone audio cleanly!
        echo.
        echo [OPTIONAL MANUAL FIX] If you want native PyAudio:
        echo   1. Visit: https://github.com/intxcc/pyaudio_portaudio/releases
        echo   2. Download .whl matching your Python version (e.g. cp310/cp311/cp312, win_amd64)
        echo   3. Run: pip install ^<downloaded_file^>.whl
    ) else (
        echo [+] PyAudio installed successfully via pipwin!
    )
) else (
    echo [+] PyAudio installed successfully!
)

:: 5. Install Remaining Requirements
echo.
echo ==============================================================
echo [STEP 2/3] Installing Remaining Dependencies from requirements.txt...
echo ==============================================================
python -m pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install one or more dependencies from requirements.txt.
    pause
    exit /b 1
)
echo [+] All dependencies installed successfully!

:: 6. Run System Diagnostics Mode
echo.
echo ==============================================================
echo [STEP 3/3] Running Hardware ^& Subsystem Self-Test Diagnostics...
echo ==============================================================
python main.py --diagnose
set DIAG_STATUS=%ERRORLEVEL%

echo.
echo ==============================================================
if %DIAG_STATUS% EQU 0 (
    echo [+] INSTALLATION ^& DIAGNOSTICS COMPLETE!
    echo [+] To start SYRAX at any time, run:
    echo.
    echo       .venv\Scripts\activate
    echo       python main.py
    echo.
) else (
    echo [!] Setup finished with warnings. Review diagnostic report above.
    echo [!] If the microphone failed, verify Windows microphone privacy settings
    echo     and re-run: python main.py --diagnose
)
echo ==============================================================
echo.
pause
