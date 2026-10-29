@echo off
REM Stops Voice Anywhere from starting with Windows (removes the Startup folder shortcut).
REM It does not delete anything else. Runs scripts\make_shortcut.ps1 -Remove.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\make_shortcut.ps1" -Remove
pause
