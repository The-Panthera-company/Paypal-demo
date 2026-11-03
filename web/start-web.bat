@echo off
rem Double-click to start the web app, then open http://localhost:3000 (Ctrl+C in this window to stop).
rem npm install runs every time so packages added on another branch are always there (quick when nothing changed).
cd /d "%~dp0"
call npm install --no-audit --no-fund
call npx next dev -p 3000
pause
