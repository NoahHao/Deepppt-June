@echo off
chcp 65001 >nul
REM ============================================
REM knowledge_base 文件监控器 — 启动脚本
REM ============================================
REM 用途: 持续监控 knowledge_base 目录，检测新文件并自动触发全量流水线
REM
REM 启动方式:
REM   start_watcher.bat             启动守护进程（默认每小时扫描）
REM   start_watcher.bat --once      单次扫描（立即执行一次后退出）
REM   start_watcher.bat --status    查看当前状态
REM   start_watcher.bat --reset     重置扫描状态
REM   start_watcher.bat --interval 600   每10分钟扫描一次
REM ============================================

cd /d "%~dp0"

set PYTHON=python

REM 检查 Python 是否可用
%PYTHON% --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [错误] 找不到 Python，请确认已安装并添加到 PATH
    pause
    exit /b 1
)

REM 解析参数 — 默认使用守护进程模式
if "%~1"=="" (
    echo 启动守护进程模式 (每小时扫描)...
    echo 按 Ctrl+C 停止
    echo.
    %PYTHON% file_watcher.py --daemon
) else (
    %PYTHON% file_watcher.py %*
)

pause
