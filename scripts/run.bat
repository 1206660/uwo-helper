@echo off
setlocal

set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%"

set "PYTHONPATH=%PROJECT_ROOT%\src"
python -m uwo_helper

if errorlevel 1 (
  echo.
  echo UWO Helper exited with an error.
  pause
)
