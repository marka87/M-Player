@echo off
setlocal
cd /d "%~dp0"

if "%1"=="" (
    python scripts\bump_version.py
) else (
    python scripts\bump_version.py %1
)
