@echo off
setlocal
cd /d "%~dp0gui"

echo [*] Starting KokoroMemo dev (Tauri + Python backend)...
echo.

npm run tauri dev
