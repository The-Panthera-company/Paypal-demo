@echo off
rem Double-click to start the web app, then open http://localhost:3000 (Ctrl+C in this window to stop).
cd /d "%~dp0"
if not exist node_modules call npm install
call npx next dev -p 3000
pause
