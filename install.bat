@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Controller Cam Helper - Setup

echo ===============================================
echo Controller Cam Helper - One-Click Setup
echo ===============================================
echo This will:
echo 1^) Check for Python
echo 2^) Install Python if missing (via winget if available)
echo 3^) Install required Python packages
echo 4^) Verify everything works
echo.

:: -----------------------------
:: Step 1: Find Python
:: -----------------------------
set "PYEXE="

where py >nul 2>&1
if "%errorlevel%"=="0" (
  set "PYEXE=py -3"
) else (
  where python >nul 2>&1
  if "%errorlevel%"=="0" (
    set "PYEXE=python"
  )
)

if not defined PYEXE (
  echo Python not found.
  echo.

  :: -----------------------------
  :: Step 2: Try to install Python
  :: -----------------------------
  where winget >nul 2>&1
  if "%errorlevel%"=="0" (
    echo Installing Python using winget...
    echo This may take a moment.
    echo.

    :: This installs the latest Python 3 from winget
    winget install -e --id Python.Python.3 --accept-package-agreements --accept-source-agreements

    if not "%errorlevel%"=="0" (
      echo.
      echo ERROR: winget failed to install Python.
      echo Opening Python download page...
      start "" "https://www.python.org/downloads/windows/"
      echo After installing Python, re-run this setup script.
      pause
      exit /b 1
    )
  ) else (
    echo winget is not available on this system.
    echo Opening Python download page...
    start "" "https://www.python.org/downloads/windows/"
    echo After installing Python, re-run this setup script.
    pause
    exit /b 1
  )

  echo.
  echo Re-checking for Python...
  set "PYEXE="

  where py >nul 2>&1
  if "%errorlevel%"=="0" (
    set "PYEXE=py -3"
  ) else (
    where python >nul 2>&1
    if "%errorlevel%"=="0" (
      set "PYEXE=python"
    )
  )
)

if not defined PYEXE (
  echo.
  echo ERROR: Python still not detected after install attempt.
  echo If you just installed Python, make sure "Add Python to PATH" was enabled,
  echo or close and reopen Command Prompt, then run this script again.
  pause
  exit /b 1
)

echo Found Python command: %PYEXE%
echo.

:: Print version
%PYEXE% --version
if not "%errorlevel%"=="0" (
  echo ERROR: Python command failed to run.
  pause
  exit /b 1
)

:: -----------------------------
:: Step 3: Install dependencies
:: -----------------------------
echo.
echo Upgrading pip...
%PYEXE% -m pip install --upgrade pip
if not "%errorlevel%"=="0" (
  echo ERROR: pip upgrade failed.
  pause
  exit /b 1
)

echo.
echo Installing required packages: pygame, vgamepad
%PYEXE% -m pip install --upgrade pygame vgamepad
if not "%errorlevel%"=="0" (
  echo ERROR: package install failed.
  pause
  exit /b 1
)

:: -----------------------------
:: Step 4: Verify imports
:: -----------------------------
echo.
echo Verifying packages...
%PYEXE% -c "import pygame; import vgamepad; print('OK: pygame and vgamepad imported successfully.')"
if not "%errorlevel%"=="0" (
  echo.
  echo ERROR: Import test failed.
  echo If vgamepad fails, you may need the ViGEmBus driver installed.
  echo https://github.com/ViGEm/ViGEmBus/releases
  pause
  exit /b 1
)

echo.
echo ===============================================
echo Setup complete!
echo ===============================================
echo Next step:
echo Run your script, for example:
echo   %PYEXE% controller_cam_helper.py
echo.
pause
exit /b 0
