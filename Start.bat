@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%device_management_v2"

call Start_V2.bat
exit /b %ERRORLEVEL%
