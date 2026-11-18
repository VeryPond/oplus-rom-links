@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "ROMSITE_PORT=8000"
echo ============================================
echo   ROM 库 - 官方 ROM 直链站
echo   浏览器打开: http://127.0.0.1:%ROMSITE_PORT%
echo   关闭本窗口即停止服务
echo ============================================
echo.
python app.py
pause
