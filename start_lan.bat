@echo off
rem Starts Form Filler for the whole office: other PCs open http://<this PC's IP>:8742
rem The Chrome extension still talks to this PC, so MCA filing runs on this PC.
cd /d "%~dp0"
python mca.py serve --lan
pause
