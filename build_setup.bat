@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
call "%~dp0resolve_app_ver.bat" "%~2"
if errorlevel 1 goto :fail
if not defined PY (
    echo ERROR: a working Python interpreter is required to stamp Help/About
    goto :fail
)
if exist "%~dp0build_setup_body_a.bat" if exist "%~dp0build_setup_body_b.bat" (
    copy /b /y "%~dp0build_setup_body_a.bat"+"%~dp0build_setup_body_b.bat" "%~dp0build_setup_body.bat" >nul
)
if not exist "%~dp0build_setup_body.bat" (
    echo ERROR: build_setup_body.bat missing
    goto :fail
)
call "%~dp0build_setup_body.bat" "%~1"
exit /b %ERRORLEVEL%
:fail
echo.
echo Setup installer was not created.
pause
endlocal
exit /b 1
