# ==============================================================================
# SYRAX - Windows Desktop Shortcut Creator
# Tagline: "Speak. Gesture. Control."
# ==============================================================================
# This script creates a high-visibility desktop shortcut ("SYRAX.lnk") pointing
# directly to 'launch_syrax.bat' with the correct working directory and icon.
# ==============================================================================

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

try {
    Write-Host "==============================================================" -ForegroundColor Cyan
    Write-Host "    ____  __  ______  ___   _  __" -ForegroundColor Cyan
    Write-Host "   / __ \/ / / / __ \/   | | |/ /   S Y R A X" -ForegroundColor Cyan
    Write-Host "  / /_/ / / / / /_/ / /| | |   /    'Speak. Gesture. Control.'" -ForegroundColor DarkCyan
    Write-Host " / ____/ /_/ / _, _/ ___ |/   |     Desktop Shortcut Installer" -ForegroundColor DarkCyan
    Write-Host "/_/    \____/_/ |_/_/  |_/_/|_|     Windows 10/11" -ForegroundColor Cyan
    Write-Host "==============================================================" -ForegroundColor Cyan
    Write-Host ""

    # 1. Determine Project Directory
    $projectRoot = $PSScriptRoot
    if (-not $projectRoot) {
        $projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    if (-not $projectRoot) {
        $projectRoot = (Get-Location).Path
    }
    $projectRoot = (Resolve-Path -Path $projectRoot).Path

    # 2. Verify Target Batch Launcher Exists
    $targetBat = Join-Path $projectRoot "launch_syrax.bat"
    if (-not (Test-Path $targetBat)) {
        Write-Error "Launcher script not found at expected location: $targetBat"
        exit 1
    }

    # 3. Resolve Desktop Folder (Handles standard and OneDrive-redirected Desktops)
    $desktopPath = [Environment]::GetFolderPath([Environment+SpecialFolder]::Desktop)
    if (-not (Test-Path $desktopPath)) {
        $desktopPath = Join-Path $env:USERPROFILE "Desktop"
    }
    if (-not (Test-Path $desktopPath)) {
        Write-Error "Could not resolve a valid Windows Desktop folder: $desktopPath"
        exit 1
    }

    $shortcutFile = Join-Path $desktopPath "SYRAX.lnk"

    # 4. Create Shortcut via Windows Script Host (WScript.Shell)
    $wscript = New-Object -ComObject WScript.Shell
    $shortcut = $wscript.CreateShortcut($shortcutFile)

    $shortcut.TargetPath = $targetBat
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.Description = "SYRAX - Voice & Gesture Intelligence System for Windows 10/11"

    # Configure Icon (SYRAX.ico if present, otherwise standard Windows system shell icon)
    $customIcon = Join-Path $projectRoot "SYRAX.ico"
    if (Test-Path $customIcon) {
        $shortcut.IconLocation = "$customIcon,0"
        $iconDisplay = "$customIcon (Custom SYRAX Cyberpunk Icon)"
    } else {
        $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,220"
        $iconDisplay = "$env:SystemRoot\System32\shell32.dll,220 (Standard Application Icon)"
    }

    # Save shortcut to disk
    $shortcut.Save()

    # 5. Verify shortcut creation and report details
    if (Test-Path $shortcutFile) {
        Write-Host "[+] Desktop shortcut successfully created!" -ForegroundColor Green
        Write-Host "    ----------------------------------------------------------" -ForegroundColor DarkGray
        Write-Host "    Shortcut Location:  $shortcutFile" -ForegroundColor White
        Write-Host "    Target Launcher:    $targetBat" -ForegroundColor White
        Write-Host "    Working Directory:  $projectRoot" -ForegroundColor White
        Write-Host "    Configured Icon:    $iconDisplay" -ForegroundColor White
        Write-Host "    ----------------------------------------------------------" -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "[+] You can now launch SYRAX directly from your Desktop" -ForegroundColor Green
        Write-Host "    by double-clicking the 'SYRAX' icon." -ForegroundColor Green
        Write-Host "==============================================================" -ForegroundColor Cyan
    } else {
        Write-Error "Failed to verify shortcut creation at: $shortcutFile"
        exit 1
    }
}
catch {
    Write-Host ""
    Write-Host "==============================================================" -ForegroundColor Red
    Write-Host "[ERROR] Failed to create desktop shortcut!" -ForegroundColor Red
    Write-Host "Details: $_" -ForegroundColor Yellow
    Write-Host "==============================================================" -ForegroundColor Red
    exit 1
}
