@echo off
REM One-time setup on each PC: installs the Python packages Form Filler needs.
cd /d "%~dp0"
set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY (where python >nul 2>nul && set PY=python)
if not defined PY (echo Install Python 3.11 or later from python.org and tick "Add python.exe to PATH", then run this again. & pause & exit /b 1)
%PY% -m pip install -r requirements.txt
if errorlevel 1 (echo Package install failed - check the internet connection & pause & exit /b 1)
echo.
echo Setup complete. Double-click start_server.bat to open Form Filler.
pause
