@echo off
title Download maniger - Update yt-dlp
cd /d "%~dp0"
"bin\yt-dlp.exe" -U
pause
