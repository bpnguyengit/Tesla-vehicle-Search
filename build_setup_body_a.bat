@echo off
setlocal EnableExtensions DisableDelayedExpansion
REM =============================================================================
REM  build_setup body — Inno Setup builder (ONEDIR) for Tesla Vehicle Search
REM
REM  Optional:  build_setup.bat "Tesla Search"
REM             build_setup.bat "Tesla Search" 2026.10.03.2130
REM
REM  Default version is auto-generated as yyyy.mm.dd.hhmm.
REM  Version is written to:
REM    - app_version.py                         (Help → About)
REM    - dist\NAME\_internal\app_version.py     (packaged About)
REM    - app_release.json                       (Check for updates)
REM    - Inno AppVersion
REM
REM  Setup output basename: TeslaSearch_Setup.exe (spaces stripped from name)
REM =============================================================================

cd /d "%~dp0"
set "REPO_ROOT=%CD%"
set "FINAL_OUT_DIR=%CD%"
set "BUILD_STAGE=%LOCALAPPDATA%\TeslaVehicleSearch\iscc_work\%RANDOM%_%TIME:~6,2%"
md "%BUILD_STAGE%" 2>nul
set "OUT_DIR=%BUILD_STAGE%"
set "ISS_PATH=%BUILD_STAGE%\inno_script.txt"

if not exist "packaging" mkdir "packaging"

echo.
echo ============================================================
echo  Tesla Vehicle Search  -  building Setup installer
echo ============================================================
echo.

REM --- 0. Pick the output app name --------------------------------------------
set "BUILD_NAME=%~1"
if not defined BUILD_NAME if exist "packaging\last_build_name.txt" (
    for /f "usebackq delims=" %%A in ("packaging\last_build_name.txt") do set "BUILD_NAME=%%A"
)
if not defined BUILD_NAME (
    set /p BUILD_NAME=Program file name without .exe [Tesla Search]: 
)
if not defined BUILD_NAME set "BUILD_NAME=Tesla Search"
set "BUILD_NAME=%BUILD_NAME:"=%"
if /I "%BUILD_NAME:~-4%"==".exe" set "BUILD_NAME=%BUILD_NAME:~0,-4%"
for /f "tokens=* delims= " %%A in ("%BUILD_NAME%") do set "BUILD_NAME=%%A"
if "%BUILD_NAME%"=="" set "BUILD_NAME=Tesla Search"
echo        Using name: %BUILD_NAME%

REM Compact setup filename (no spaces): TeslaSearch_Setup
set "SETUP_BASE="
for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "$n='%BUILD_NAME%'; -replace '[^A-Za-z0-9_-]','' ; if (-not $n) { $n='TeslaSearch' }; if ($n -notmatch '_Setup$') { $n = $n + '_Setup' }; Write-Output $n"`) do set "SETUP_BASE=%%A"
if not defined SETUP_BASE set "SETUP_BASE=TeslaSearch_Setup"
echo        Setup base: %SETUP_BASE%

REM --- 0b. Stamp version ------------------------------------------------------
set "TESLA_SEARCH_APP_VER=%APP_VER%"
set "TESLA_SEARCH_BUILD_NAME=%BUILD_NAME%"
set "TESLA_SEARCH_SETUP_NAME=%SETUP_BASE%"
"%PY%" %PY_ARGS% "%~dp0scripts\stamp_setup_version.py" stamp
if errorlevel 1 (
    echo ERROR: could not write version into Help/About
    echo        app_version.py
    goto :fail
)
echo        Version stamp OK

REM --- 1. Check required ONEDIR build output ----------------------------------
echo [1/5] Checking program ONEDIR ...
if not exist "dist\%BUILD_NAME%\" (
    echo ERROR: dist\%BUILD_NAME%\ not found.
    echo        Run build_exe.bat first.
    goto :fail
)
if not exist "dist\%BUILD_NAME%\%BUILD_NAME%.exe" (
    echo ERROR: dist\%BUILD_NAME%\%BUILD_NAME%.exe not found.
    echo        Run build_exe.bat first and enter the same name.
    goto :fail
)
echo        dist\%BUILD_NAME%\%BUILD_NAME%.exe OK
if not exist "dist\%BUILD_NAME%\_internal\" (
    echo ERROR: dist\%BUILD_NAME%\_internal\ missing — refusing onefile-style layout.
    echo        build_exe.bat must produce PyInstaller ONEDIR.
    goto :fail
)
echo        dist\%BUILD_NAME%\_internal\ OK

REM --- 2. Locate ISCC.exe -----------------------------------------------------
echo [2/5] Locating Inno Setup compiler (ISCC.exe) ...
if defined ISCC if not exist "%ISCC%" (
    echo ERROR: ISCC points to a missing file:
    echo        %ISCC%
    goto :fail
)
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
