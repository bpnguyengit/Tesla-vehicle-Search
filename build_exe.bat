@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM =============================================================================
REM  build_exe.bat — PyInstaller one-folder build for Tesla Vehicle Search
REM
REM  Optional:  build_exe.bat "Tesla Search"
REM  Default exe base name (no .exe): Tesla Search  →  Tesla Search.exe
REM
REM  Output:
REM    dist\<name>\<name>.exe   (plus _internal\ runtime folder)
REM =============================================================================

cd /d "%~dp0"
title Tesla Vehicle Search — build exe

echo.
echo ============================================================
echo  Tesla Vehicle Search  —  building program EXE
echo ============================================================
echo.

REM --- 0. Program file name ---------------------------------------------------
set "RAW_NAME=%~1"
if not defined RAW_NAME set "RAW_NAME=Tesla Search"
set "RAW_NAME=%RAW_NAME:"=%"
if /I "%RAW_NAME:~-4%"==".exe" set "RAW_NAME=%RAW_NAME:~0,-4%"
if "%RAW_NAME%"=="" set "RAW_NAME=Tesla Search"

REM --- 1. Virtual environment -------------------------------------------------
if exist ".venv\Scripts\python.exe" (
    echo [1/5] Using existing .venv
) else (
    call :create_venv
    if errorlevel 1 exit /b 1
)

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo ERROR: "%PY%" not found
    exit /b 1
)

REM Sanitize name: allow letters, digits, space, dash, underscore
set "RAW=%RAW_NAME%"
set "NAME_PY=%TEMP%\tesla_search_sanitize_name.py"
set "NAME_OUT=%TEMP%\tesla_search_build_name.txt"
> "%NAME_PY%" echo import os, re
>>"%NAME_PY%" echo s = os.environ.get("RAW", "Tesla Search")
>>"%NAME_PY%" echo s = re.sub(r"(?i)\.exe$", "", s.strip())
>>"%NAME_PY%" echo s = "".join(c for c in s if c.isalnum() or c in "-_ ") or "Tesla Search"
>>"%NAME_PY%" echo s = re.sub(r"\s+", " ", s).strip()
>>"%NAME_PY%" echo print(s)
"%PY%" "%NAME_PY%" > "%NAME_OUT%"
if errorlevel 1 (
    echo ERROR: .venv python failed while sanitizing the build name
    exit /b 1
)
set /p BUILD_NAME=<"%NAME_OUT%"
if not defined BUILD_NAME set "BUILD_NAME=Tesla Search"
echo        Build name: !BUILD_NAME!
if not exist "packaging" mkdir "packaging"
echo !BUILD_NAME!> "packaging\last_build_name.txt"

REM --- 2. Dependencies --------------------------------------------------------
echo [2/5] Installing requirements + PyInstaller ...
"%PY%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo        pip not in .venv — bootstrapping ...
    "%PY%" -m ensurepip --upgrade >nul 2>&1
)
"%PY%" -m pip --version >nul 2>&1
if errorlevel 1 (
    where uv >nul 2>&1
    if not errorlevel 1 (
        echo        Using uv pip ...
        uv pip install -q -r requirements.txt pyinstaller --python "%PY%"
        if errorlevel 1 (
            echo ERROR: uv pip install failed
            exit /b 1
        )
        goto :deps_ok
    )
    echo ERROR: pip is not available in .venv
    echo        Recreate it with:  py -3 -m venv .venv
    exit /b 1
)
"%PY%" -m pip install -q -r requirements.txt pyinstaller
if errorlevel 1 (
    echo ERROR: pip install failed
    exit /b 1
)
:deps_ok

REM --- 3. Assets check --------------------------------------------------------
echo [3/5] Checking sources ...
if not exist "tesla_search.py" (
    echo ERROR: tesla_search.py missing
    exit /b 1
)
if not exist "inventory.py" (
    echo ERROR: inventory.py missing
    exit /b 1
)
if not exist "app_version.py" (
    echo ERROR: app_version.py missing
    exit /b 1
)
if not exist "app_release.json" (
    echo WARNING: app_release.json missing — Check for updates will rely on GitHub when online
)
if not exist "packaging\tesla_search.spec" (
    echo ERROR: packaging\tesla_search.spec missing
    exit /b 1
)

REM --- 4. PyInstaller ---------------------------------------------------------
echo [4/5] Running PyInstaller (one-folder, windowed) ...
echo        spec: packaging\tesla_search.spec
echo        exe:  dist\!BUILD_NAME!\!BUILD_NAME!.exe
set "TESLA_SEARCH_BUILD_NAME=!BUILD_NAME!"
"%PY%" -m PyInstaller --noconfirm --clean packaging\tesla_search.spec
if errorlevel 1 (
    echo ERROR: PyInstaller failed
    exit /b 1
)

REM Ensure version + release manifest land under _internal
if not exist "dist\!BUILD_NAME!\_internal" mkdir "dist\!BUILD_NAME!\_internal"
copy /y "app_version.py" "dist\!BUILD_NAME!\_internal\app_version.py" >nul
if exist "app_release.json" copy /y "app_release.json" "dist\!BUILD_NAME!\_internal\app_release.json" >nul

REM --- 5. Verify --------------------------------------------------------------
echo [5/5] Verifying output ...
if not exist "dist\!BUILD_NAME!\!BUILD_NAME!.exe" (
    echo ERROR: dist\!BUILD_NAME!\!BUILD_NAME!.exe was not created
    exit /b 1
)
if exist "dist\!BUILD_NAME!\tests" rmdir /s /q "dist\!BUILD_NAME!\tests"
if exist "dist\!BUILD_NAME!\_internal\tests" rmdir /s /q "dist\!BUILD_NAME!\_internal\tests"

for %%F in ("dist\!BUILD_NAME!\!BUILD_NAME!.exe") do echo        %%~fF  (%%~zF bytes)

echo.
echo Done. Program: %~dp0dist\!BUILD_NAME!\!BUILD_NAME!.exe
echo Name saved in packaging\last_build_name.txt for build_setup.bat
echo Next: run build_setup.bat
echo.
endlocal
pause
exit /b 0

:create_venv
set "BOOT_PY="
if exist "C:\Python3.12\python.exe" set "BOOT_PY=C:\Python3.12\python.exe"
if not defined BOOT_PY if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "BOOT_PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined BOOT_PY if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "BOOT_PY=%LocalAppData%\Programs\Python\Python313\python.exe"
if not defined BOOT_PY (
    where uv >nul 2>&1
    if not errorlevel 1 (
        echo [1/5] Creating .venv with uv ...
        uv venv .venv
        if errorlevel 1 (
            echo ERROR: uv venv failed
            exit /b 1
        )
        exit /b 0
    )
)
if not defined BOOT_PY (
    where py >nul 2>&1
    if not errorlevel 1 (
        echo [1/5] Creating .venv with py -3 ...
        py -3 -m venv .venv
        if errorlevel 1 (
            echo ERROR: failed to create .venv with py -3
            exit /b 1
        )
        exit /b 0
    )
)
if not defined BOOT_PY set "BOOT_PY=python"
echo [1/5] Creating .venv with %BOOT_PY% ...
"%BOOT_PY%" -m venv .venv
if errorlevel 1 (
    echo ERROR: failed to create .venv — install Python 3.12+ or uv, then retry.
    exit /b 1
)
exit /b 0
