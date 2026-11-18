@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在从上游同步 ROM 目录...
python catalog.py sync
echo.
pause
