@echo off
cd /d "%~dp0"
powershell -NoProfile -Command "$d=(Resolve-Path '.').Path; Get-Process python,aria2c -ErrorAction SilentlyContinue | Where-Object { $_.Path -like ($d + '*') } | Stop-Process -Force"
echo Download maniger stopped.
timeout /t 3 >nul
