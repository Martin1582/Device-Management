@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "PYTHON_EXE=..\.venv\Scripts\python.exe"
if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" --version >nul 2>nul
    if errorlevel 1 set "PYTHON_EXE="
)

if "%PYTHON_EXE%"=="" if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
)

if "%PYTHON_EXE%"=="" (
    echo Keine funktionierende Python-Umgebung gefunden.
    echo Erwartet wurde entweder ..\.venv\Scripts\python.exe oder %%LOCALAPPDATA%%\Programs\Python\Python313\python.exe
    pause
    exit /b 1
)

"%PYTHON_EXE%" main.py
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Die Anwendung wurde mit Fehlercode %EXIT_CODE% beendet.
    pause
)

exit /b %EXIT_CODE%
