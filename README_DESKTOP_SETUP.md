# SYRAX: Desktop Setup & One-Click Launch Guide

> **"Speak. Gesture. Control."**
> AI-Powered Voice & Gesture Intelligence System for Windows 10/11

This guide explains how to launch SYRAX directly from your Windows Desktop with a single double-click—without needing to open VS Code, Antigravity, or a command terminal.

---

## 1. Quick Setup: Create Desktop Shortcut

You only need to run the shortcut installer **once**:

### Option A: Direct Right-Click (Fastest)
1. In File Explorer, navigate to your SYRAX folder:
   ```
   C:\Users\<YourUser>\OneDrive\Desktop\SYRAX
   ```
2. Right-click **`create_desktop_shortcut.ps1`**.
3. Select **"Run with PowerShell"**.
4. A terminal will flash briefly and create a **SYRAX** shortcut with the custom cyberpunk icon directly on your Windows Desktop.

### Option B: PowerShell Command Line (If script execution is restricted)
If Windows displays an execution policy warning, open PowerShell and run:
```powershell
powershell -ExecutionPolicy Bypass -File create_desktop_shortcut.ps1
```

Once complete, you will see `SYRAX.lnk` directly on your Desktop!

---

## 2. Launching SYRAX

To start the assistant:
1. Double-click the **SYRAX** icon on your Desktop.
2. `launch_syrax.bat` will automatically:
   - Detect the SYRAX project directory from any path (including paths with spaces and across drives).
   - Activate the `.venv` virtual environment (or create it automatically if missing).
   - Check PyAudio availability and fallback gracefully to `sounddevice` if needed.
   - Verify core dependencies without slow re-installations (fully works offline once installed).
   - Run a subsystem self-test (`python main.py --diagnose`).
   - Launch the futuristic dark/neon SYRAX Dashboard.
3. SYRAX will greet you by voice:
   > *"Hello! I'm SYRAX. What would you like me to do?"*

---

## 3. How to Move or Rename the Project Folder

If you move the `SYRAX` directory to another location (e.g. from `OneDrive\Desktop\SYRAX` to `D:\SYRAX` or `C:\Projects\SYRAX`), your existing desktop shortcut will still point to the old directory.

**To update the shortcut in 5 seconds:**
1. Open the new SYRAX folder in File Explorer.
2. Run `create_desktop_shortcut.ps1` (or run `powershell -ExecutionPolicy Bypass -File create_desktop_shortcut.ps1`).
3. The script will automatically detect the new project folder, update the working directory, re-attach the icon, and overwrite the Desktop shortcut with the updated path.

---

## 4. Troubleshooting Guide

### Issue 1: "Python is not installed or not in your system PATH"
- **Cause**: Python is missing or the Python binary was not added to your Windows environment variables during setup.
- **Solution**:
  1. Download Python 3.10+ from [python.org](https://www.python.org/downloads/).
  2. Launch the installer and **critically ensure** the bottom checkbox is checked:
     `[x] Add python.exe to PATH`
  3. Complete setup, restart your computer, and double-click the SYRAX shortcut again.

---

### Issue 2: "PyAudio is not available for this Python build"
- **Cause**: PyAudio on Windows requires pre-compiled PortAudio C binaries. On newer Python versions (such as Python 3.12+), building PyAudio from source fails without Visual Studio C++ compilers.
- **Is this fatal?**: **NO.** SYRAX is engineered with an automatic fallback to `sounddevice` for microphone capture. Voice recognition, noise calibration, and speech synthesis will work completely without PyAudio.
- **Optional Native Fix**:
  If you specifically want native PyAudio:
  1. Visit: [https://github.com/intxcc/pyaudio_portaudio/releases](https://github.com/intxcc/pyaudio_portaudio/releases)
  2. Download the `.whl` wheel file matching your Python version (e.g., `pyaudio-...-cp314-win_amd64.whl`).
  3. In a terminal within `.venv`, run:
     ```cmd
     pip install <path_to_downloaded_wheel>.whl
     ```

---

### Issue 3: PowerShell Script Execution Policy Blocking (`PSSecurityException`)
- **Cause**: Windows PowerShell security policy blocks un-signed scripts by default.
- **Solution**:
  Run the script using the `-ExecutionPolicy Bypass` parameter:
  ```powershell
  powershell -ExecutionPolicy Bypass -File create_desktop_shortcut.ps1
  ```
  Or launch PowerShell as Administrator and run:
  ```powershell
  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
  ```

---

### Issue 4: Launcher Window Opens and Closes Instantly
- **Cause**: A critical system or environment error crashed before the batch file paused.
- **Solution**:
  1. Open a Command Prompt window (`cmd.exe`).
  2. Navigate to your project folder:
     ```cmd
     cd /d "%USERPROFILE%\Desktop\SYRAX"
     ```
  3. Run the launcher directly to see the exact error output:
     ```cmd
     launch_syrax.bat
     ```
  4. Review the error message. If a core package is missing, run:
     ```cmd
     python -m pip install -r requirements.txt
     ```

---

### Issue 5: Microphone or Webcam Not Detected in Diagnostics
- **Microphone**:
  1. Open Windows **Settings -> System -> Sound -> Input**.
  2. Verify that your microphone (e.g. Realtek Audio) is enabled and set as the default device.
  3. Open **Settings -> Privacy & Security -> Microphone**. Ensure **"Let desktop apps access your microphone"** is turned **ON**.
- **Webcam**:
  1. Check if Zoom, Microsoft Teams, Discord, or a browser tab is currently using your webcam. Close competing apps.
  2. Open **Settings -> Privacy & Security -> Camera**. Ensure **"Let desktop apps access your camera"** is turned **ON**.
  3. If your laptop has multiple cameras (or an external USB webcam), you can adjust `CAMERA_INDEX` in `config.py` (e.g. `CAMERA_INDEX = 1`).

---

### Issue 6: Shortcut Pointing to an Old or Missing Folder
- **Cause**: You moved or renamed the SYRAX folder after creating the desktop shortcut.
- **Solution**:
  Simply re-run `create_desktop_shortcut.ps1` from inside the new folder location. The script will automatically update the shortcut on your Desktop to point to the correct folder.

---

## 5. Summary of Files

| File | Purpose |
| :--- | :--- |
| **`launch_syrax.bat`** | Self-contained Windows batch launcher. Activates `.venv`, checks dependencies, verifies hardware diagnostics, and launches SYRAX. |
| **`create_desktop_shortcut.ps1`** | Automated PowerShell script to generate `SYRAX.lnk` on your Desktop with the project icon and directory preset. |
| **`SYRAX.ico`** | Cyberpunk neon cyan/blue custom Windows application icon. |
| **`README_DESKTOP_SETUP.md`** | Complete setup, moving, and troubleshooting documentation. |
| **`main.py`** | Application entry point (`--diagnose` self-test & GUI mainloop). |
