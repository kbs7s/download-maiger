@echo off
taskkill /im aria2c.exe /f >nul 2>&1 && echo Engine stopped. || echo Engine was not running.
timeout /t 3 >nul
