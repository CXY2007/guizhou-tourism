@echo off
title 贵州文旅 · 可交付版（SQLite 演示库）
cd /d "%~dp0"
echo ============================================
echo   贵州文旅 · 可交付版
echo   地址：http://127.0.0.1:8900
echo ============================================
echo.
where python >NUL 2>NUL
if errorlevel 1 (
  echo [错误] 未找到 python，请安装 Python 3.11+ 并加入 PATH。
  pause
  exit /b 1
)
if not exist "instance\guizhou.db" (
  echo [提示] 未找到 instance\guizhou.db，请确认文件完整。
  pause
  exit /b 1
)
start "" "http://127.0.0.1:8900/"
python run.py
echo.
echo 服务已停止。关闭本窗口即可。
pause