@echo off
REM Makes Voice Anywhere start with Windows (a shortcut in your Startup folder) and starts it now.
REM Double-click once. No administrator rights needed. Safe to run again (it overwrites).
REM It just runs scripts\make_shortcut.ps1; -ExecutionPolicy Bypass applies to this one run only.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\make_shortcut.ps1"
pause
