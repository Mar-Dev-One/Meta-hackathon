@echo off
rem Studio: starts the app with everything in view.
rem   - this window: the app's log (uvicorn and the agents), the Studio's log
rem   - the Studio's window: the renderer building and rendering each shot
rem     as the agents drive it (closing it stops the run in progress)
rem   - the browser: http://127.0.0.1:8000
rem Ctrl+C here stops it all.

setlocal
cd /d "%~dp0"
title Studio app

if not exist ".venv\Scripts\python.exe" (
    echo No Python environment at .venv: create it and install pipeline\requirements.txt ^(README.md^).
    pause
    exit /b 1
)
if not exist "build\Release\Studio.exe" (
    echo No build\Release\Studio.exe: build the Studio first ^(README.md^).
    pause
    exit /b 1
)
if not exist ".env" echo Warning: no .env, so the Meta model calls will fail without their keys.

set STUDIO_VISIBLE=1
set PYTHONUNBUFFERED=1
set PORT=8000

rem The browser opens once the app answers (up to 60 s), from a second window that closes itself then.
start "open browser" cmd /c "for /l %%i in (1,1,60) do (curl -s -o nul http://127.0.0.1:%PORT%/ && (start "" http://127.0.0.1:%PORT%/ & exit) || timeout /t 1 /nobreak >nul)"

echo Studio app on http://127.0.0.1:%PORT%/  (Ctrl+C to stop)
echo.
".venv\Scripts\python.exe" -m app --port %PORT%

echo.
echo The app has stopped.
pause
