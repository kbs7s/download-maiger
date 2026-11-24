@echo off
title Download maniger - Video
cd /d "%~dp0"
set "OUT=%USERPROFILE%\Downloads\DownloadManiger"
set "URL=%~1"
if "%URL%"=="" set /p "URL=Paste a video link (YouTube, Instagram, TikTok, Facebook...): "
if "%URL%"=="" exit /b 0
"bin\yt-dlp.exe" --ffmpeg-location "bin" -P "%OUT%" -o "%%(title).150B [%%(id)s].%%(ext)s" ^
  -f "bv*[height<=1080]+ba/b" --merge-output-format mp4 --no-playlist "%URL%"
echo.
echo Saved to %OUT%
pause
