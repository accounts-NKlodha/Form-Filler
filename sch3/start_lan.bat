@echo off
REM Lets team members on the office network open the app at http://<this-PC-IP>:8765
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (echo Run setup.bat first. & pause & exit /b 1)
.venv\Scripts\python app.py --lan
pause
