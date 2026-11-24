@echo off
title Download maniger - Engine (keep this window open)
cd /d "%~dp0"
if not exist "bin\aria2c.exe" (
  echo Setup has not been run yet. Double-click setup.bat first.
  pause
  exit /b 1
)
if not exist "aria2.conf" (
  echo aria2.conf is missing. Double-click setup.bat first.
  pause
  exit /b 1
)
tasklist /fi "imagename eq aria2c.exe" | find /i "aria2c.exe" >nul
if not errorlevel 1 (
  echo The engine is already running.
  timeout /t 5 >nul
  exit /b 0
)
echo Download engine is running on http://localhost:6800/jsonrpc
echo Close this window to stop it.
echo.
"bin\aria2c.exe" --conf-path="%~dp0aria2.conf"
