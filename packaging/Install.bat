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
echo === MGSV Radio Tuner and Mission Skip: install ===
echo Close the game before continuing. Do not use this mod online.
echo.
"runtime\python.exe" "app\radio_tuner.py" --apply --config "radio_tuner.json"
if errorlevel 1 goto :failed
echo.
echo Done. In a story mission or a loaded side op, hold V + R + E for 3 seconds to skip it.
pause
exit /b 0
:failed
echo.
echo Installation failed, see the message above.
pause
exit /b 1
