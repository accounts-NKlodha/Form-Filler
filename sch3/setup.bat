@echo off
REM One-time setup: installs the Python packages into a private folder (.venv) next to this file.
cd /d "%~dp0"
set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY (where python >nul 2>nul && set PY=python)
if defined PY goto havepy
echo Python is not installed. Trying to install Python 3.12 with winget...
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto nopy
echo Python installed. Close this window and run setup.bat again.
pause
exit /b 0
:nopy
echo.
echo Could not install automatically. Install Python 3.11 or later from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH" on the first screen. Then run setup.bat again.
pause
exit /b 1
:havepy
%PY% -m venv .venv
if errorlevel 1 (echo Could not create .venv & pause & exit /b 1)
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
if errorlevel 1 (echo Package install failed - check internet or proxy & pause & exit /b 1)
echo.
echo Setup complete. Double-click start.bat to open the app.
pause
