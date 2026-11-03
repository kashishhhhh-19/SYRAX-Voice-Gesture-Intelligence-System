@echo off
setlocal EnableDelayedExpansion

:: ==============================================================================
:: SYRAX - Voice & Gesture Intelligence System Launcher
:: Tagline: "Speak. Gesture. Control."
:: ==============================================================================

:: Ensure working directory is always the script's folder (handles spaces & shortcuts)
cd /d "%~dp0"

echo ==============================================================
echo    ____  __  ______  ___   _  __
echo   / __ \/ / / / __ \/   ^| ^| ^|/ /   S Y R A X
echo  / /_/ / / / / /_/ / /^| ^| ^|   /    "Speak. Gesture. Control."
echo / ____/ /_/ / _, _/ ___ ^|/   ^|     Voice ^& Gesture Intelligence
echo /_/    \____/_/ ^|_/_/  ^|_/_/^|_^|     System for Windows 10/11
echo ==============================================================
echo.

:: ------------------------------------------------------------------------------
:: 1. Check Python Installation
:: ------------------------------------------------------------------------------
set "PYTHON_CMD="
python --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON_CMD=python"
) else (
    py --version >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set "PYTHON_CMD=py"
    )
)

if "%PYTHON_CMD%"=="" (
    echo.
    echo ==============================================================
    echo [ERROR] Python is not installed or not in your system PATH!
    echo ==============================================================
    echo SYRAX requires Python 3.10 or higher.
    echo.
    echo How to install Python:
    echo   1. Download Python 3.10+ from: https://www.python.org/downloads/
    echo   2. Run the installer and CRITICALLY check the box:
    echo      [x] Add python.exe to PATH
    echo   3. Complete setup, restart your computer, and launch again.
    echo ==============================================================
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('%PYTHON_CMD% --version 2^>^&1') do set "DETECTED_PY_VER=%%v"
echo [+] Detected: %DETECTED_PY_VER% via %PYTHON_CMD%

:: ------------------------------------------------------------------------------
:: 2. Virtual Environment (.venv) Activation or Creation
:: ------------------------------------------------------------------------------
if exist ".venv\Scripts\activate.bat" goto activate_venv

echo [*] Virtual environment .venv not found. Creating .venv...
%PYTHON_CMD% -m venv --system-site-packages .venv >nul 2>&1
if %ERRORLEVEL% EQU 0 goto activate_venv

%PYTHON_CMD% -m venv .venv
if %ERRORLEVEL% EQU 0 goto activate_venv

echo.
echo ==============================================================
echo [ERROR] Failed to create virtual environment .venv!
echo ==============================================================
echo Please verify that your Python installation includes the venv module.
echo Try running manually: %PYTHON_CMD% -m venv .venv
echo ==============================================================
echo.
pause
exit /b 1

:activate_venv
call .venv\Scripts\activate.bat
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ==============================================================
    echo [ERROR] Failed to activate virtual environment at .venv\Scripts\activate.bat
    echo ==============================================================
    echo.
    pause
    exit /b 1
)
echo [+] Virtual environment active: .venv

:: ------------------------------------------------------------------------------
:: 3. Check PyAudio Availability Separately (Windows-Specific Hardware Capture)
:: ------------------------------------------------------------------------------
python -c "import pyaudio" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [+] Audio capture: PyAudio is installed and ready.
    goto check_dependencies
)

echo [*] Audio capture: PyAudio not detected. Checking if pre-compiled wheel can be installed...
python -m pip install pyaudio >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    python -m pip install pipwin >nul 2>&1
    pipwin install pyaudio >nul 2>&1
)

python -c "import pyaudio" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [+] Audio capture: PyAudio installed successfully!
    goto check_dependencies
)

echo.
echo --------------------------------------------------------------
echo [NOTICE] PyAudio is not available for this Python build.
echo [NOTICE] NO ACTION NEEDED: SYRAX automatically uses 'sounddevice'
echo          for microphone audio capture, so voice recognition
echo          will function completely!
echo.
echo [OPTIONAL] To install native PyAudio manually:
echo   1. Visit: https://github.com/intxcc/pyaudio_portaudio/releases
echo   2. Download the .whl matching your Python version - e.g. cp310/cp311/cp312/cp314, win_amd64
echo   3. Run: pip install ^<downloaded_file^>.whl
echo --------------------------------------------------------------
echo.

:check_dependencies
:: ------------------------------------------------------------------------------
:: 4. Check Core Dependencies (Fast & Offline-Ready)
:: ------------------------------------------------------------------------------
python -c "import speech_recognition, sounddevice, comtypes, pyttsx3, cv2, pyautogui, win32gui, pygetwindow, numpy, PIL" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [+] Dependencies: All required packages are installed.
    goto run_diagnostics
)

echo [*] Installing missing dependencies from requirements.txt...
python -m pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ==============================================================
    echo [ERROR] Failed to install dependencies from requirements.txt!
    echo ==============================================================
    echo An active internet connection is required during first-time setup.
    echo Please verify your internet connection and re-run.
    echo ==============================================================
    echo.
    pause
    exit /b 1
)

:: Re-verify essential packages
python -c "import speech_recognition, sounddevice, comtypes, pyttsx3, cv2, pyautogui, win32gui, pygetwindow, numpy, PIL" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ==============================================================
    echo [ERROR] Essential packages are still missing after pip install!
    echo ==============================================================
    echo Please check requirements.txt and pip installation logs.
    echo ==============================================================
    echo.
    pause
    exit /b 1
)
echo [+] Dependencies installed and verified successfully.

:run_diagnostics
:: ------------------------------------------------------------------------------
:: 5. Run Hardware & Subsystem Self-Test Diagnostics
:: ------------------------------------------------------------------------------
echo.
echo [*] Running SYRAX Subsystem Self-Test Diagnostics...
python main.py --diagnose
set "DIAG_EXIT=%ERRORLEVEL%"

if %DIAG_EXIT% EQU 0 goto launch_app

:: If diagnostics returned non-zero, check if critical core components are functional
python -c "import speech_recognition, sounddevice, comtypes, pyttsx3, pyautogui, win32gui" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo.
    echo [*] Notice: Non-critical hardware warning reported above - e.g. camera busy or offline STT.
    echo [*] Core intelligence engine is ready. Continuing to launch...
    echo.
    goto launch_app
)

echo.
echo ==============================================================
echo [ERROR] Critical core components failed diagnostics!
echo ==============================================================
echo One or more essential libraries failed self-test.
echo Review diagnostic messages above to fix the failure.
echo ==============================================================
echo.
pause
exit /b 1

:launch_app
:: ------------------------------------------------------------------------------
:: 6. Launch Application
:: ------------------------------------------------------------------------------
echo.
echo [*] Launching SYRAX Voice ^& Gesture Intelligence System...
python main.py
set "APP_EXIT=%ERRORLEVEL%"

if %APP_EXIT% NEQ 0 (
    echo.
    echo ==============================================================
    echo [ERROR] SYRAX closed unexpectedly with exit code: %APP_EXIT%
    echo ==============================================================
    echo Check logs at: logs\syrax.log
    echo Or run: python main.py --diagnose
    echo ==============================================================
    echo.
    pause
    exit /b %APP_EXIT%
)
