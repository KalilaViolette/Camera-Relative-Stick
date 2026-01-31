@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Calibrate - Camera Relative Stick (pygame)

set "SCRIPT=camera_relative_stick_pygame.py"
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
  echo ERROR: Python was not found.
  echo Run the setup bat first, then try again.
  pause
  exit /b 1
)

if not exist "%SCRIPT%" (
  echo ERROR: "%SCRIPT%" was not found in:
  echo %cd%
  pause
  exit /b 1
)

echo Running calibration for: %SCRIPT%
%PYEXE% "%SCRIPT%" --recalibrate
pause
