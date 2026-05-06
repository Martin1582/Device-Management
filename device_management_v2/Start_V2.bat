@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "VENV_DIR=%SCRIPT_DIR%.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE="
) else (
    "%PYTHON_EXE%" --version >nul 2>nul
    if errorlevel 1 set "PYTHON_EXE="
)

if "%PYTHON_EXE%"=="" (
    call :find_base_python
    if "!BASE_PYTHON!"=="" (
        echo Keine funktionierende Python-Installation gefunden.
        echo Bitte Python 3.13 oder neuer installieren und danach erneut Start.bat ausfuehren.
        pause
        exit /b 1
    )

    echo Erstelle lokale Python-Umgebung fuer Device Management v2...
    "!BASE_PYTHON!" -m venv --clear "%VENV_DIR%"
    if errorlevel 1 (
        echo Die lokale Python-Umgebung konnte nicht erstellt werden.
        pause
        exit /b 1
    )
    set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
)

if not exist "%PYTHON_EXE%" (
    echo Die lokale Python-Umgebung ist unvollstaendig.
    pause
    exit /b 1
)

"%PYTHON_EXE%" -c "import PySide6, openpyxl, PIL, zxingcpp" >nul 2>nul
if errorlevel 1 (
    echo Installiere benoetigte Python-Pakete...
    "%PYTHON_EXE%" -m pip install --upgrade pip
    if errorlevel 1 (
        echo pip konnte nicht aktualisiert werden.
        pause
        exit /b 1
    )
    "%PYTHON_EXE%" -m pip install -r requirements-runtime.txt
    if errorlevel 1 (
        echo Die benoetigten Python-Pakete konnten nicht installiert werden.
        echo Bitte Internetverbindung pruefen und Start.bat erneut ausfuehren.
        pause
        exit /b 1
    )
)

"%PYTHON_EXE%" main.py
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Die Anwendung wurde mit Fehlercode %EXIT_CODE% beendet.
    pause
)

exit /b %EXIT_CODE%

:find_base_python
set "BASE_PYTHON="
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
    set "BASE_PYTHON=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    exit /b 0
)
for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do (
    set "BASE_PYTHON=%%P"
    exit /b 0
)
for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)" 2^>nul') do (
    set "BASE_PYTHON=%%P"
    exit /b 0
)
exit /b 0
