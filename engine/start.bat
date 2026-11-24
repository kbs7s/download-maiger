@echo off
title Download maniger (keep this window open)
cd /d "%~dp0"
if not exist "bin\python\python.exe" goto nosetup
if not exist "bin\aria2c.exe" goto nosetup
if not exist "aria2.conf" goto nosetup
"bin\python\python.exe" "%~dp0bridge.py"
echo.
echo Download maniger stopped.
pause
exit /b 0
:nosetup
echo Setup has not finished yet. Double-click setup.bat first.
pause
exit /b 1
