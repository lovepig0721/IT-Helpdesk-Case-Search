@echo off
chcp 65001 >nul
cd /d "%~dp0"
python open_console.py
if errorlevel 1 (
  echo.
  echo Failed. If python is missing, install Python 3.11+ and retry.
  pause
)
