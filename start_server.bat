@echo off
rem Starts Form Filler on http://127.0.0.1:8742 (this PC only) and opens it in the browser.
cd /d "%~dp0"
python mca.py serve
pause
