@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0import-models.ps1"
if errorlevel 1 (
  echo [Agent] Model import failed. See the error above.
  pause
  exit /b 1
)
endlocal
