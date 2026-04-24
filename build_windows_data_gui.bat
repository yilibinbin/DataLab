@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%build_windows_data_gui.ps1"

if not exist "%PS_SCRIPT%" (
    echo [ERROR] Cannot find build_windows_data_gui.ps1 next to this batch file.
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" %*

endlocal
