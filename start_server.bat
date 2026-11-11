@echo off
rem Starts the MCA filler server on http://127.0.0.1:8742 and opens its dashboard.
cd /d "%~dp0"
python mca.py serve
pause
