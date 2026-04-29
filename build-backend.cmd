@echo off
setlocal
cd /d "%~dp0"

echo [*] Building KokoroMemo backend with Nuitka ...
echo [*] This may take 3-5 minutes on first run.
echo.

python -m nuitka --standalone --onefile ^
    --assume-yes-for-downloads ^
    --include-package=app ^
    --include-package=uvicorn ^
    --include-package=fastapi ^
    --include-package=httpx ^
    --include-package=lancedb ^
    --include-package=pyarrow ^
    --include-package=aiosqlite ^
    --include-package=pydantic ^
    --include-package=yaml ^
    --include-package=websockets ^
    --include-package=dotenv ^
    --output-filename=kokoromemo-server.exe ^
    app\main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Build failed. Check the output above.
    pause
    exit /b 1
)

echo.
echo [+] Build succeeded: dist\kokoromemo-server.exe
echo [+] Test: dist\kokoromemo-server.exe --help
echo.
pause
