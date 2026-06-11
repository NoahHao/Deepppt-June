@echo off
REM LLM_Search 快速运行脚本
REM ========================
REM 使用 Python 3.10 运行（sentence-transformers 兼容性最佳）
REM
REM 用法: run.bat build
REM       run.bat search "查询文本"
REM       run.bat stats
REM       run.bat info

set PYTHON_EXE=C:\Python310\python.exe

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python 3.10 not found at %PYTHON_EXE%
    echo Please install Python 3.10 or set PYTHON_EXE to your Python path.
    exit /b 1
)

cd /d "%~dp0"
"%PYTHON_EXE%" cli.py %*
