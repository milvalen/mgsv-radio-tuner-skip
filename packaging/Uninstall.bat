@echo off
set "SELF=%~f0"
net session >nul 2>&1
if not errorlevel 1 goto :elevated
echo Administrator rights are needed to change the game files.
powershell -NoProfile -Command "Start-Process -FilePath $env:SELF -Verb RunAs"
if errorlevel 1 pause
exit /b
:elevated
setlocal
set PYTHONUTF8=1
set PYTHONDONTWRITEBYTECODE=1
cd /d "%~dp0"
echo === MGSV Radio Tuner and Mission Skip: restore the game ===
"runtime\python.exe" "app\radio_tuner.py" --restore --config "radio_tuner.json"
pause
