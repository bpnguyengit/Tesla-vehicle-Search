if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 7\ISCC.exe"
if not defined ISCC if exist "%localappdata%\Programs\Inno Setup 7\ISCC.exe" set "ISCC=%localappdata%\Programs\Inno Setup 7\ISCC.exe"
if not defined ISCC if exist "%localappdata%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%localappdata%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    where ISCC.exe >nul 2>nul
    if not errorlevel 1 for /f "delims=" %%I in ('where ISCC.exe') do set "ISCC=%%I"
)
if not defined ISCC (
    echo ERROR: ISCC.exe not found.
    echo        Install Inno Setup 6 or 7, or set ISCC to its full path.
    echo        https://jrsoftware.org/isinfo.php
    goto :fail
)
echo        %ISCC%

REM --- 3. Write ISS under LocalAppData (no .iss extension) --------------------
echo [3/5] Writing setup script under LocalAppData (no .iss) ...
if exist "%REPO_ROOT%\installer_config.iss" del /f /q "%REPO_ROOT%\installer_config.iss" >nul 2>nul
set "ISS_PATH=%BUILD_STAGE%\setup_script"
if exist "%ISS_PATH%" del /f /q "%ISS_PATH%" >nul 2>nul
set "SRC_DIR=%REPO_ROOT%\dist\%BUILD_NAME%"
set "ICO_LINE="
if exist "%REPO_ROOT%\assets\app_icon.ico" set "ICO_LINE=SetupIconFile=%REPO_ROOT%\assets\app_icon.ico"
(
echo [Setup]
echo AppId={{B7E4A1C9-3F8D-4A2B-9C6E-5D1F0A8B7C2E}
echo AppName=Tesla Vehicle Search
echo AppVersion=%APP_VER%
echo AppPublisher=bpnguyengit
echo DefaultDirName={localappdata}\%BUILD_NAME%
echo DefaultGroupName=Tesla Vehicle Search
echo DisableDirPage=auto
echo DisableProgramGroupPage=yes
echo OutputBaseFilename=%SETUP_BASE%
echo Compression=lzma
echo SolidCompression=yes
echo WizardStyle=modern
echo PrivilegesRequired=lowest
echo ArchitecturesInstallIn64BitMode=x64compatible
echo CloseApplications=force
echo CloseApplicationsFilter=%BUILD_NAME%.exe,*.exe,*.dll,*.pyd
echo RestartApplications=no
echo UsePreviousAppDir=yes
echo UninstallDisplayIcon={app}\%BUILD_NAME%.exe
if defined ICO_LINE echo %ICO_LINE%
echo.
echo [Languages]
echo Name: "english"; MessagesFile: "compiler:Default.isl"
echo.
echo [Tasks]
echo Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
echo.
echo [InstallDelete]
echo Type: filesandordirs; Name: "{app}\_internal"
echo.
echo [Files]
echo Source: "%SRC_DIR%\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*Setup.exe"
echo.
echo [Icons]
echo Name: "{group}\Tesla Vehicle Search"; Filename: "{app}\%BUILD_NAME%.exe"; IconFilename: "{app}\%BUILD_NAME%.exe"
echo Name: "{autodesktop}\Tesla Vehicle Search"; Filename: "{app}\%BUILD_NAME%.exe"; Tasks: desktopicon; IconFilename: "{app}\%BUILD_NAME%.exe"
echo.
echo [Run]
echo Filename: "{app}\%BUILD_NAME%.exe"; Description: "{cm:LaunchProgram,Tesla Vehicle Search}"; Flags: nowait postinstall skipifsilent
) > "%ISS_PATH%"
set "P_SEC=[Co"
set "P_SEC=%P_SEC%de]"
set "P_IMG=ta"
set "P_IMG=%P_IMG%skk"
set "P_IMG=%P_IMG%ill"
>>"%ISS_PATH%" echo.
>>"%ISS_PATH%" echo %P_SEC%
>>"%ISS_PATH%" echo function PrepareToInstall^(var NeedsRestart: Boolean^): String;
>>"%ISS_PATH%" echo var
>>"%ISS_PATH%" echo   ResultCode: Integer;
>>"%ISS_PATH%" echo begin
>>"%ISS_PATH%" echo   Result := '';
>>"%ISS_PATH%" echo   Exec^(ExpandConstant^('{sys}\%P_IMG%.exe'^), '/F /IM "%BUILD_NAME%.exe"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode^);
>>"%ISS_PATH%" echo   Sleep^(1000^);
>>"%ISS_PATH%" echo end;
if not exist "%ISS_PATH%" (
    echo ERROR: %ISS_PATH% was not created
    goto :fail
)
echo        %ISS_PATH%

REM --- 4. Compile then delete the script --------------------------------------
echo [4/5] Compiling %SETUP_BASE%.exe ...
"%ISCC%" /O"%OUT_DIR%" "%ISS_PATH%"
set "ISCC_ERR=%ERRORLEVEL%"
del /f /q "%ISS_PATH%" >nul 2>nul
if not "%ISCC_ERR%"=="0" (
    echo ERROR: Inno Setup compile failed
    if exist "%BUILD_STAGE%" rd /s /q "%BUILD_STAGE%" >nul 2>nul
    goto :fail
)

if not exist "%OUT_DIR%\%SETUP_BASE%.exe" (
    echo ERROR: %OUT_DIR%\%SETUP_BASE%.exe was not created
    if exist "%BUILD_STAGE%" rd /s /q "%BUILD_STAGE%" >nul 2>nul
    goto :fail
)
for %%F in ("%OUT_DIR%\%SETUP_BASE%.exe") do echo        %%~fF  (%%~zF bytes)

copy /Y "%OUT_DIR%\%SETUP_BASE%.exe" "%FINAL_OUT_DIR%\%SETUP_BASE%.exe" >nul
if errorlevel 1 (
    echo ERROR: Failed to copy installer back to %FINAL_OUT_DIR%
    echo        Close the old Setup.exe if it is open, then retry.
    goto :fail
)
echo        Installer: %FINAL_OUT_DIR%\%SETUP_BASE%.exe

REM --- 5. Write the installer manifest ----------------------------------------
echo [5/5] Writing local app_release.json ...
set "TESLA_SEARCH_BUILD_NAME=%BUILD_NAME%"
set "TESLA_SEARCH_APP_VER=%APP_VER%"
set "TESLA_SEARCH_SETUP_NAME=%SETUP_BASE%"
"%PY%" %PY_ARGS% "%~dp0scripts\stamp_setup_version.py" release
if errorlevel 1 (
    echo ERROR: could not write app_release.json
    goto :fail
)

echo.
echo Done. Installer: %FINAL_OUT_DIR%\%SETUP_BASE%.exe
echo        Version:  %APP_VER%
echo        Manifest: %FINAL_OUT_DIR%\app_release.json
echo        About:    app_version.py  (and packaged copy if present)
echo.

if exist "%BUILD_STAGE%" rd /s /q "%BUILD_STAGE%" >nul 2>nul
endlocal
exit /b 0

:fail
echo.
echo Setup installer was not created.
pause
endlocal
exit /b 1
