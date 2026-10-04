@echo off
REM resolve_app_ver.bat — export PY, PY_ARGS, APP_VER to caller (no setlocal)
REM Usage from build_setup.bat: call "%~dp0resolve_app_ver.bat" "%~2"
REM Exit /b 1 if APP_VER empty.

set "APP_VER=%~1"
set "PY="
set "PY_ARGS="
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PY=%~dp0.venv\Scripts\python.exe"
)
if not defined PY (
    py -3 -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "PY=py"
        set "PY_ARGS=-3"
    )
)
if not defined PY (
    python -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if defined PY (
    echo        Python: %PY% %PY_ARGS%
) else (
    echo        WARNING: no working Python found yet (stamp/release still need one)
)

if not defined APP_VER if defined PY (
    for /f "usebackq delims=" %%A in (`"%PY%" %PY_ARGS% "%~dp0scripts\stamp_setup_version.py" auto`) do set "APP_VER=%%A"
)
if not defined APP_VER (
    for /f "delims=" %%A in ('powershell -NoProfile -Command "$d=Get-Date; '{0}.{1:D2}.{2:D2}.{3:D2}{4:D2}' -f $d.Year,$d.Month,$d.Day,$d.Hour,$d.Minute"') do set "APP_VER=%%A"
    if defined APP_VER echo        Auto version via PowerShell fallback
)
if not defined APP_VER (
    echo ERROR: empty app version after auto-generate
    echo        Tried Python stamp_setup_version.py auto, then PowerShell Get-Date.
    exit /b 1
)
set "APP_VER=%APP_VER:"=%"
for /f "tokens=* delims= " %%A in ("%APP_VER%") do set "APP_VER=%%A"
if "%APP_VER%"=="" (
    echo ERROR: empty app version after auto-generate
    exit /b 1
)
echo        Using version: %APP_VER%
exit /b 0
