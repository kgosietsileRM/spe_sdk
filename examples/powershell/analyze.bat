@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Local virtual environment missing. Run run.ps1 or bootstrap.ps1 first.
    exit /b 1
)

".venv\Scripts\python.exe" batch_analyze.py %*
exit /b %errorlevel%
