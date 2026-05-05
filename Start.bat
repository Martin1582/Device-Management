@echo off
setlocal

set "SCRIPT_DIR=%~dp0"

if exist "%SCRIPT_DIR%DeviceManagementV2.exe" (
    "%SCRIPT_DIR%DeviceManagementV2.exe"
    exit /b %ERRORLEVEL%
)

cd /d "%SCRIPT_DIR%device_management_v2"
call Start_V2.bat
exit /b %ERRORLEVEL%
